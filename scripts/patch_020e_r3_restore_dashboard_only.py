from pathlib import Path
import re

html_path = Path("app/web/client.html")
html = html_path.read_text(encoding="utf-8-sig")

# Quitar guard de idioma que está interfiriendo con Ajustes y navegación.
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_language_guard\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Quitar Workforce i18n por ahora. Lo rehacemos más seguro.
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_workforce_i18n_safe\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Mantener SOLO:
# client.js
# client_core_settings.js
# client_dashboard_i18n_safe.js

html_path.write_text(html, encoding="utf-8")

print("OK: removidos client_language_guard.js y client_workforce_i18n_safe.js del client.html")
