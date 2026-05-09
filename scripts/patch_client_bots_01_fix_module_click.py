from pathlib import Path

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

before = src

# En renderBotsModule la variable existente es "bot", no "config".
src = src.replace("clientBotFlowLabel(config?.flow_code)", "clientBotFlowLabel(bot?.flow_code)")
src = src.replace('config?.webhook_mode === "dedicated"', 'bot?.webhook_mode === "dedicated"')
src = src.replace("config?.webhook_mode", "bot?.webhook_mode")
src = src.replace("config?.flow_code", "bot?.flow_code")

if before == src:
    print("CLIENT_BOTS_01_NO_CHANGES_FOUND")
else:
    path.write_text(src, encoding="utf-8")
    print("CLIENT_BOTS_01_FIXED")
