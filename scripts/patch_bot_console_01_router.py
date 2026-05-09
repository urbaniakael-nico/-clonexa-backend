from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "company_bots_v1_router" not in src:
    src += '''

# CLONEXA Company Bots V1 router
from app.api.v1.endpoints import company_bots_v1 as company_bots_v1_router
api_router.include_router(company_bots_v1_router.router, prefix="/company-bots-v1", tags=["company_bots_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("BOT_CONSOLE_01_ROUTER_OK")
