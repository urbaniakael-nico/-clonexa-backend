from pathlib import Path

router_path = Path("app/api/v1/router.py")
src = router_path.read_text(encoding="utf-8-sig")

if "bot_flow_v1_router" not in src:
    src += '''

# CLONEXA Bot Flow V1 router
from app.api.v1.endpoints import bot_flow_v1 as bot_flow_v1_router
api_router.include_router(bot_flow_v1_router.router, prefix="/bot-flow-v1", tags=["bot_flow_v1"])
'''

router_path.write_text(src, encoding="utf-8")
print("BOT_FLOW_02_ROUTER_OK")
