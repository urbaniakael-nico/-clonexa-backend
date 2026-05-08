from pathlib import Path
import re

html_path = Path("app/web/client.html")
router_path = Path("app/api/v1/router.py")

# 1) Quitar scripts DAY del HTML
html = html_path.read_text(encoding="utf-8-sig")

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_day_closing[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE
)

html_path.write_text(html, encoding="utf-8")

# 2) Eliminar archivos frontend DAY
for name in [
    "app/web/client_day_closing.js",
    "app/web/client_day_closing_r7_clean.js",
]:
    path = Path(name)
    if path.exists():
        path.unlink()

# 3) Eliminar endpoints DAY anteriores
for name in [
    "app/api/v1/endpoints/day_closing.py",
    "app/api/v1/endpoints/day_closing_safe.py",
    "app/api/v1/endpoints/closure_store.py",
]:
    path = Path(name)
    if path.exists():
        path.unlink()

# 4) Limpiar router.py de includes DAY
router = router_path.read_text(encoding="utf-8-sig")

patterns = [
    r'\n# CLONEXA 022B day closing router\nfrom app\.api\.v1\.endpoints import day_closing as day_closing_router\napi_router\.include_router\(day_closing_router\.router, prefix="/day-closing", tags=\["day_closing"\]\)\n?',
    r'\n# CLONEXA 022B-R4 safe day closing save router\nfrom app\.api\.v1\.endpoints import day_closing_safe as day_closing_safe_router\napi_router\.include_router\(day_closing_safe_router\.router, prefix="/day-closing-safe", tags=\["day_closing_safe"\]\)\n?',
    r'\n# CLONEXA safe day closing save router\nfrom app\.api\.v1\.endpoints import day_closing_safe as day_closing_safe_router\napi_router\.include_router\(day_closing_safe_router\.router, prefix="/day-closing-safe", tags=\["day_closing_safe"\]\)\n?',
    r'\n# CLONEXA closure store router\nfrom app\.api\.v1\.endpoints import closure_store as closure_store_router\napi_router\.include_router\(closure_store_router\.router, prefix="/closure-store", tags=\["closure_store"\]\)\n?',
]

for pattern in patterns:
    router = re.sub(pattern, "\n", router, flags=re.IGNORECASE)

# limpieza defensiva por si quedaron líneas sueltas
router = re.sub(r'^from app\.api\.v1\.endpoints import day_closing.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^from app\.api\.v1\.endpoints import day_closing_safe.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^from app\.api\.v1\.endpoints import closure_store.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(day_closing.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(day_closing_safe.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(closure_store.*\n', '', router, flags=re.MULTILINE)

router_path.write_text(router, encoding="utf-8")

print("DAY_CLOSING_KILLED_OK")
