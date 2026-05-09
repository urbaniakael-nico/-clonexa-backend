from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "adaptive_kpis_v1_router" not in src:
    src += '''

# CLONEXA Adaptive KPIs V1 router
from app.api.v1.endpoints import adaptive_kpis_v1 as adaptive_kpis_v1_router
api_router.include_router(adaptive_kpis_v1_router.router, prefix="/adaptive-kpis-v1", tags=["adaptive_kpis_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("REPORTS_KPIS_HARD_01_ROUTER_OK")
