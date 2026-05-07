from pathlib import Path
import re

js_path = Path("app/web/client_core_settings.js")
html_path = Path("app/web/client.html")

js = js_path.read_text(encoding="utf-8-sig")
html = html_path.read_text(encoding="utf-8-sig")

# Quitar runtime global 020C si existe
js = re.sub(
    r"\n?/\* CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL \*/[\s\S]*?/\* END CLONEXA 020C CORE SETTINGS RUNTIME GLOBAL \*/\n?",
    "\n",
    js,
    flags=re.MULTILINE,
)

# Quitar runtime global 020C-R1 si existe
js = re.sub(
    r"\n?/\* CLONEXA 020C-R1 FORCE CORE GLOBALS \*/[\s\S]*?/\* END CLONEXA 020C-R1 FORCE CORE GLOBALS \*/\n?",
    "\n",
    js,
    flags=re.MULTILINE,
)

# Dejar versión estable 020B del script
html = re.sub(
    r"client_core_settings\.js(?:\?v=[^\"']*)?",
    "client_core_settings.js?v=020B_STABLE",
    html,
    flags=re.IGNORECASE,
)

# Asegurar que no queden traductores viejos
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_i18n\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_google_translate\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

js_path.write_text(js, encoding="utf-8")
html_path.write_text(html, encoding="utf-8")

print("OK: 020C/020C-R1 removidos. client_core_settings vuelve a modo 020B estable.")
