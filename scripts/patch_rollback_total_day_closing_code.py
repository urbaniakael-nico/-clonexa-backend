from pathlib import Path
import re

html_path = Path("app/web/client.html")
router_path = Path("app/api/v1/router.py")

# 1) Limpiar client.html de cualquier script day_closing.
if html_path.exists():
    html = html_path.read_text(encoding="utf-8-sig")

    html = re.sub(
        r'\s*<script[^>]+src=["\'][^"\']*client_day_closing[^"\']*["\'][^>]*>\s*</script>\s*',
        "\n",
        html,
        flags=re.IGNORECASE,
    )

    html_path.write_text(html, encoding="utf-8")

# 2) Eliminar frontend del módulo.
for file_name in [
    "app/web/client_day_closing.js",
    "app/web/client_day_closing_r7_clean.js",
]:
    path = Path(file_name)
    if path.exists():
        path.unlink()

# 3) Eliminar endpoints creados para este módulo.
for file_name in [
    "app/api/v1/endpoints/day_closing.py",
    "app/api/v1/endpoints/day_closing_safe.py",
    "app/api/v1/endpoints/closure_store.py",
    "app/api/v1/endpoints/day_closing_v1.py",
]:
    path = Path(file_name)
    if path.exists():
        path.unlink()

# 4) Limpiar router.py.
router = router_path.read_text(encoding="utf-8-sig")

blocks = [
    r'\n# CLONEXA 022B day closing router\nfrom app\.api\.v1\.endpoints import day_closing as day_closing_router\napi_router\.include_router\(day_closing_router\.router, prefix="/day-closing", tags=\["day_closing"\]\)\n?',
    r'\n# CLONEXA 022B-R4 safe day closing save router\nfrom app\.api\.v1\.endpoints import day_closing_safe as day_closing_safe_router\napi_router\.include_router\(day_closing_safe_router\.router, prefix="/day-closing-safe", tags=\["day_closing_safe"\]\)\n?',
    r'\n# CLONEXA safe day closing save router\nfrom app\.api\.v1\.endpoints import day_closing_safe as day_closing_safe_router\napi_router\.include_router\(day_closing_safe_router\.router, prefix="/day-closing-safe", tags=\["day_closing_safe"\]\)\n?',
    r'\n# CLONEXA closure store router\nfrom app\.api\.v1\.endpoints import closure_store as closure_store_router\napi_router\.include_router\(closure_store_router\.router, prefix="/closure-store", tags=\["closure_store"\]\)\n?',
    r'\n# CLONEXA Day Closing V1 clean backend router\nfrom app\.api\.v1\.endpoints import day_closing_v1 as day_closing_v1_router\napi_router\.include_router\(day_closing_v1_router\.router, prefix="/day-closing-v1", tags=\["day_closing_v1"\]\)\n?',
]

for block in blocks:
    router = re.sub(block, "\n", router, flags=re.IGNORECASE)

# Limpieza defensiva de líneas sueltas.
router = re.sub(r'^from app\.api\.v1\.endpoints import day_closing.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^from app\.api\.v1\.endpoints import day_closing_safe.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^from app\.api\.v1\.endpoints import closure_store.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^from app\.api\.v1\.endpoints import day_closing_v1.*\n', '', router, flags=re.MULTILINE)

router = re.sub(r'^api_router\.include_router\(day_closing.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(day_closing_safe.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(closure_store.*\n', '', router, flags=re.MULTILINE)
router = re.sub(r'^api_router\.include_router\(day_closing_v1.*\n', '', router, flags=re.MULTILINE)

router_path.write_text(router, encoding="utf-8")

print("CODE_ROLLBACK_DAY_CLOSING_OK")
