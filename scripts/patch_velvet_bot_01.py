from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "velvet_bot_v1_router" not in src:
    src += '''

# CLONEXA Velvet Bot V1 router
from app.api.v1.endpoints import velvet_bot_v1 as velvet_bot_v1_router
api_router.include_router(velvet_bot_v1_router.router, prefix="/velvet-bot-v1", tags=["velvet_bot_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("VELVET_BOT_01_ROUTER_OK")
