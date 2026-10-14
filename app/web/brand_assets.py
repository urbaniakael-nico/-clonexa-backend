"""Marca CLONEXA (logo nuevo, 2026-10): UNA sola fuente para pantallas y PDF.

Los archivos entregados por el dueño viven en app/web/assets/brand/ y se
sirven por el montaje /assets ya existente (sin rutas nuevas). Las URLs llevan
?v=VERSION: el navegador los guarda un año (immutable) y, cuando cambie el
logo, basta con subir VERSION.

Uso: fondo oscuro -> clonexa-logo-horizontal / clonexa-nombre; fondo claro ->
las versiones "-fondo-claro"; espacios cuadrados o pequenos -> el icono.
Esto es SOLO la marca Clonexa: el logo de una empresa cliente (panel_logo,
Estudio de marca, tickets, cartas) nunca sale de aqui.
"""
from __future__ import annotations

from pathlib import Path

from app.web.safe_static import SafeStaticFiles

VERSION = "cx26a"
DIR = Path(__file__).resolve().parent / "assets" / "brand"
URL_PREFIX = "/assets/brand/"
CACHE_LONG = "public, max-age=31536000, immutable"

FILES = (
    "clonexa-icono.svg", "clonexa-icono-16.png", "clonexa-icono-32.png", "clonexa-icono-180.png", "clonexa-icono-192.png",
    "clonexa-icono-512.png", "favicon.ico", "clonexa-logo-horizontal.svg", "clonexa-logo-horizontal.png",
    "clonexa-logo-horizontal-fondo-claro.svg", "clonexa-logo-horizontal-fondo-claro.png", "clonexa-logo-vertical.svg",
    "clonexa-logo-vertical.png", "clonexa-nombre.svg", "clonexa-nombre-fondo-claro.svg",
)


def url(name: str) -> str:
    if name not in FILES:
        raise KeyError(name)
    return f"{URL_PREFIX}{name}?v={VERSION}"


def path(name: str) -> Path:
    if name not in FILES:
        raise KeyError(name)
    return DIR / name


# Para los PDF (reportlab no dibuja SVG): PNG de la marca.
def pdf_logo_dark() -> Path:
    """Horizontal para banda oscura."""
    return path("clonexa-logo-horizontal.png")


def pdf_logo_light() -> Path:
    """Horizontal para fondo claro (comprobantes)."""
    return path("clonexa-logo-horizontal-fondo-claro.png")


def pdf_icon() -> Path:
    return path("clonexa-icono-192.png")


class CachedAssets(SafeStaticFiles):
    """El /assets de siempre; solo brand/ sale con cache larga (URL versionada).
    Solo imagenes de la raiz y de brand/ (lista blanca de safe_static)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allowed_dirs", frozenset({"brand"}))
        super().__init__(*args, **kwargs)

    async def get_response(self, path_: str, scope):  # type: ignore[override]
        response = await super().get_response(path_, scope)
        if path_.replace("\\", "/").startswith("brand/") and response.status_code == 200:
            response.headers["Cache-Control"] = CACHE_LONG
        return response
