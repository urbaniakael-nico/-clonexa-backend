from pathlib import Path
import re

html_path = Path("app/web/client.html")
html = html_path.read_text(encoding="utf-8-sig")

# Quitar traductores externos del cliente.
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_google_translate\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_i18n\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

html_path.write_text(html, encoding="utf-8")

print("OK: traductores externos removidos de client.html")
