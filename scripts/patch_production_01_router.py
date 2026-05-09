from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "production_v1_router" not in src:
    src += '''

# CLONEXA Production V1 router
from app.api.v1.endpoints import production_v1 as production_v1_router
api_router.include_router(production_v1_router.router, prefix="/production-v1", tags=["production_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("PRODUCTION_01_ROUTER_OK")
