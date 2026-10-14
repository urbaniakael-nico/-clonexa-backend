"""Rutas estaticas seguras (2026-10-14).

/client-static y /admin-static montaban la carpeta app/web completa: cualquiera
sin sesion podia bajar el codigo Python (.py), los respaldos y las cachés.
Aqui queda una sola regla para todas las rutas que sirven archivos:

- solo archivos con extension publica (css, js, png, jpg, svg, ico, webp, woff2)
  mas una lista explicita de nombres permitidos;
- nunca subcarpetas salvo las que se declaren (ej. brand/ en /assets);
- nunca puntos ("..", ".env", ".git"), __pycache__ ni extensiones de codigo
  o configuracion: todo eso responde 404, exista o no el archivo.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from urllib.parse import unquote

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

PUBLIC_EXTENSIONS = frozenset({".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".woff2"})

# Extensiones que nunca salen por una ruta estatica, aunque el archivo exista.
BLOCKED_EXTENSIONS = frozenset({
    ".py", ".pyc", ".pyo", ".env", ".json", ".md", ".txt", ".sql", ".ini", ".toml",
    ".yml", ".yaml", ".lock", ".cfg", ".conf", ".sh", ".ps1", ".bat", ".log", ".bak",
    ".db", ".sqlite", ".pem", ".key", ".crt", ".git",
})

# Prefijos de las rutas que sirven archivos; el bloqueo global los cubre a todos.
STATIC_PREFIXES = ("/client-static/", "/assets/", "/admin-v2-assets/", "/admin-static/")


def blocks_request(path: str) -> bool:
    """Bloqueo global: lo usa el middleware de app/main.py en toda ruta estatica."""
    if not any(path.startswith(prefix) for prefix in STATIC_PREFIXES):
        return False
    return is_blocked_path(path)


def is_blocked_path(raw_path: str) -> bool:
    """True si la ruta pide algo que ninguna ruta estatica debe servir."""
    path = unquote(unquote(raw_path or "")).replace("\\", "/")
    parts = [p for p in path.split("/") if p]
    for part in parts:
        if part == ".." or part.startswith(".") or part == "__pycache__":
            return True
        lower = part.lower()
        if any(lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
            return True
        if ".backup" in lower or lower.endswith("~"):
            return True
    return False


def is_allowed_file(rel_path: str, *, allowed_names: frozenset[str] = frozenset(),
                    allowed_dirs: frozenset[str] = frozenset()) -> bool:
    """La lista blanca: nombre explicito o extension publica, en la raiz o en
    una subcarpeta declarada."""
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or is_blocked_path(rel):
        return rel in allowed_names
    pure = PurePosixPath(rel)
    folder = str(pure.parent) if str(pure.parent) != "." else ""
    if folder and folder not in allowed_dirs:
        return False
    return rel in allowed_names or pure.suffix.lower() in PUBLIC_EXTENSIONS


class SafeStaticFiles(StaticFiles):
    """StaticFiles que solo sirve la lista blanca; lo demas es 404."""

    def __init__(self, *args, allowed_names: frozenset[str] = frozenset(),
                 allowed_dirs: frozenset[str] = frozenset(), **kwargs):
        super().__init__(*args, **kwargs)
        self.allowed_names = frozenset(allowed_names)
        self.allowed_dirs = frozenset(allowed_dirs)

    async def get_response(self, path: str, scope):  # type: ignore[override]
        if not is_allowed_file(path, allowed_names=self.allowed_names, allowed_dirs=self.allowed_dirs):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)
