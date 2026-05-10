from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "crm_core_v1_router" not in src:
    src += '''

# CLONEXA CRM Core V1 router
from app.api.v1.endpoints import crm_core_v1 as crm_core_v1_router
api_router.include_router(crm_core_v1_router.router, prefix="/crm-core-v1", tags=["crm_core_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("CRM_CORE_01_ROUTER_OK")
