from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "adaptive_kpis_panel_v1_router" not in src:
    src += '''

# CLONEXA Adaptive KPI Panel V1 router
from app.api.v1.endpoints import adaptive_kpis_panel_v1 as adaptive_kpis_panel_v1_router
api_router.include_router(adaptive_kpis_panel_v1_router.router, prefix="/adaptive-kpis-panel-v1", tags=["adaptive_kpis_panel_v1"])
'''

if "adaptive_reports_detail_v1_router" not in src:
    src += '''

# CLONEXA Adaptive Reports Detail V1 router
from app.api.v1.endpoints import adaptive_reports_detail_v1 as adaptive_reports_detail_v1_router
api_router.include_router(adaptive_reports_detail_v1_router.router, prefix="/adaptive-reports-detail-v1", tags=["adaptive_reports_detail_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("DATA_BOARD_01_ROUTER_OK")
