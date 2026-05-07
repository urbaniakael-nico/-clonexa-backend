from pathlib import Path
import re

html_path = Path("app/web/client.html")
html = html_path.read_text(encoding="utf-8-sig")

# Quitar traductores rotos si quedaron cargados
for name in [
    "client_i18n.js",
    "client_google_translate.js",
    "client_dashboard_i18n_safe.js",
]:
    html = re.sub(
        rf'\s*<script[^>]+src=["\'][^"\']*{re.escape(name)}[^"\']*["\'][^>]*>\s*</script>\s*',
        "\n",
        html,
        flags=re.IGNORECASE,
    )

# Dejar core settings estable
html = re.sub(
    r"client_core_settings\.js(?:\?v=[^\"']*)?",
    "client_core_settings.js?v=020B_STABLE_EMERGENCY",
    html,
    flags=re.IGNORECASE,
)

html_path.write_text(html, encoding="utf-8")
print("OK: client.html limpio")
