from pathlib import Path

path = Path("app/main.py")
text = path.read_text(encoding="utf-8-sig")

if "_clonexa_legacy_admin_redirect" in text:
    print("OK: legacy /admin redirect ya existe.")
    path.write_text(text, encoding="utf-8")
    raise SystemExit(0)

if "RedirectResponse" not in text:
    if "from fastapi.responses import" in text:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("from fastapi.responses import"):
                if "RedirectResponse" not in line:
                    lines[i] = line.rstrip() + ", RedirectResponse"
                break
        text = "\n".join(lines) + "\n"
    elif "from fastapi import" in text:
        text = text.replace("from fastapi import", "from fastapi.responses import RedirectResponse\nfrom fastapi import", 1)
    else:
        text = "from fastapi.responses import RedirectResponse\n" + text

app_pos = text.find("app = FastAPI(")
if app_pos < 0:
    raise SystemExit("No encontré app = FastAPI( en app/main.py")

insert_pos = text.find("\n\n", app_pos)
if insert_pos < 0:
    raise SystemExit("No encontré punto seguro después de app = FastAPI(...)")

middleware = '''

@app.middleware("http")
async def _clonexa_legacy_admin_redirect(request, call_next):
    """
    CLONEXA 019D:
    /admin legacy queda depurado como redirect permanente a /admin-v2.
    No se elimina para no romper accesos guardados.
    """
    if request.url.path.rstrip("/") == "/admin":
        return RedirectResponse(url="/admin-v2", status_code=308)
    return await call_next(request)
'''

text = text[:insert_pos] + middleware + text[insert_pos:]
path.write_text(text, encoding="utf-8")

print("PATCH_OK: /admin redirige a /admin-v2")
