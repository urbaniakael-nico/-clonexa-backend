from pathlib import Path
import re

js_path = Path("app/web/client_references_v1.js")
html_path = Path("app/web/client.html")

src = js_path.read_text(encoding="utf-8-sig")

src = re.sub(
    r'window\.CLONEXA_REFERENCES_V1_BUILD\s*=\s*"[^"]+";',
    'window.CLONEXA_REFERENCES_V1_BUILD = "REF_02C_CLIENT_ANTIBLOCK_2026_05_09";',
    src
)

def replace_function(src, name, replacement):
    pattern = rf"  function {name}\([^)]*\) \{{.*?\n  \}}\n"
    new_src, count = re.subn(pattern, replacement + "\n", src, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"No pude reemplazar function {name}")
    return new_src

src = replace_function(src, "isReferencesScreen", r'''  function isReferencesScreen() {
    // Anti-bloqueo: NO leer document.body.innerText.
    // Solo detectamos pantalla por H1/H2 exacto del placeholder.
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    return headers.some((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });
  }''')

src = replace_function(src, "findMountTarget", r'''  function findMountTarget() {
    const headers = Array.from(document.querySelectorAll("h1,h2"));
    const header = headers.find((node) => {
      const value = (node.textContent || "").trim().toLowerCase();
      return value === "references" || value === "referencias" || value === "références";
    });

    if (!header) return null;

    let node = header.parentElement;

    for (let i = 0; i < 10 && node && node !== document.body; i += 1) {
      const tag = (node.tagName || "").toLowerCase();
      const id = (node.id || "").toLowerCase();
      const klass = String(node.className || "").toLowerCase();
      const text = (node.textContent || "").toLowerCase();

      const forbidden =
        tag === "body" ||
        tag === "html" ||
        tag === "main" ||
        id === "app" ||
        klass.includes("client-shell") ||
        text.includes("tenant activo") ||
        text.includes("active tenant") ||
        text.includes("cerrar sesión") ||
        text.includes("log out") ||
        text.includes("ajustes") ||
        text.includes("settings");

      const hasReferenceTitle =
        text.includes("references") ||
        text.includes("referencias") ||
        text.includes("références");

      const hasPlaceholder =
        text.includes("módulo activo") ||
        text.includes("modulo activo") ||
        text.includes("module active") ||
        text.includes("este módulo está asignado") ||
        text.includes("este modulo esta asignado") ||
        text.includes("this module is assigned");

      const widthOk = (node.offsetWidth || 0) > 420;

      if (!forbidden && hasReferenceTitle && hasPlaceholder && widthOk) {
        return node;
      }

      node = node.parentElement;
    }

    // Seguridad: si no encontramos contenedor limpio, no montamos.
    return null;
  }''')

src = replace_function(src, "mount", r'''  function mount() {
    try {
      if (!isReferencesScreen()) return;

      const target = findMountTarget();

      if (!target) {
        console.warn("[CLONEXA References] Safe mount skipped: no clean module container found.");
        return;
      }

      if (target.getAttribute("data-clx-references-v1-mounted") === "1") return;

      injectStyles();

      state.companyId = getCompanyId();
      state.root = target;
      state.root.setAttribute("data-clx-references-v1-mounted", "1");

      bindEvents();
      render();
      loadData();
    } catch (error) {
      console.error("[CLONEXA References] mount failed safely:", error);
    }
  }''')

# Debounce observer. Reemplaza bloque del observer/start si existe.
src = re.sub(
    r'''  const observer = new MutationObserver\(\(\) => \{\s*if \(document\.body\) mount\(\);\s*\}\);\s*function start\(\) \{\s*mount\(\);\s*observer\.observe\(document\.body, \{ childList: true, subtree: true \}\);\s*\}''',
    r'''  const observer = new MutationObserver(() => {
    clearTimeout(window.__CLX_REF_MOUNT_TIMER__);
    window.__CLX_REF_MOUNT_TIMER__ = setTimeout(() => {
      if (document.body) mount();
    }, 120);
  });

  function start() {
    mount();
    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }''',
    src,
    flags=re.DOTALL
)

js_path.write_text(src, encoding="utf-8")

html = html_path.read_text(encoding="utf-8-sig")
html = re.sub(
    r'client_references_v1\.js\?v=[^"\']+',
    'client_references_v1.js?v=REF02C_20260509',
    html,
    flags=re.IGNORECASE
)
html_path.write_text(html, encoding="utf-8")

print("REF_02C_ANTIBLOCK_OK")
