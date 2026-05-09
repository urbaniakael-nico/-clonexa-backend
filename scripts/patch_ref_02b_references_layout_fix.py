from pathlib import Path
import re

js_path = Path("app/web/client_references_v1.js")
html_path = Path("app/web/client.html")

src = js_path.read_text(encoding="utf-8-sig")

src = src.replace(
    'window.CLONEXA_REFERENCES_V1_BUILD = "REF_02_CLIENT_SCREEN_2026_05_09";',
    'window.CLONEXA_REFERENCES_V1_BUILD = "REF_02B_CLIENT_LAYOUT_FIX_2026_05_09";'
)

old = r'''  function findMountTarget() {
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    const header = headers.find((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });

    if (!header) return null;

    const main = header.closest("main");
    if (main) return main;

    let node = header.parentElement;
    for (let i = 0; i < 5 && node && node.parentElement; i += 1) {
      if ((node.offsetWidth || 0) > window.innerWidth * 0.45) return node;
      node = node.parentElement;
    }

    return header.parentElement || null;
  }'''

new = r'''  function findMountTarget() {
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    const header = headers.find((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });

    if (!header) return null;

    // Nunca montar sobre main/body porque elimina el sidebar del portal cliente.
    let node = header.parentElement;

    for (let i = 0; i < 8 && node && node !== document.body; i += 1) {
      const buttons = Array.from(node.querySelectorAll("button,a")).map((el) => {
        return (el.textContent || "").trim().toLowerCase();
      });

      const containsSidebar =
        buttons.includes("dashboard") ||
        buttons.includes("crm campo") ||
        buttons.includes("workforce") ||
        buttons.includes("ajustes") ||
        buttons.includes("cerrar sesión") ||
        buttons.includes("settings") ||
        buttons.includes("log out");

      const containsHeader = node.contains(header);
      const widthOk = (node.offsetWidth || 0) > 420;

      if (containsHeader && widthOk && !containsSidebar && node.tagName.toLowerCase() !== "main") {
        return node;
      }

      node = node.parentElement;
    }

    return header.parentElement || null;
  }'''

if old not in src:
    raise SystemExit("No encontré findMountTarget esperado.")

src = src.replace(old, new)

js_path.write_text(src, encoding="utf-8")

html = html_path.read_text(encoding="utf-8-sig")
html = re.sub(
    r'client_references_v1\.js\?v=[^"\']+',
    'client_references_v1.js?v=REF02B_20260509',
    html,
    flags=re.IGNORECASE
)
html_path.write_text(html, encoding="utf-8")

print("REF_02B_LAYOUT_FIX_OK")
