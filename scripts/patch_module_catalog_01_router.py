from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "module_catalog_v1_router" not in src:
    src += '''

# CLONEXA Module Catalog V1 router
from app.api.v1.endpoints import module_catalog_v1 as module_catalog_v1_router
api_router.include_router(module_catalog_v1_router.router, prefix="/module-catalog-v1", tags=["module_catalog_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("MODULE_CATALOG_01_ROUTER_OK")
