from pathlib import Path
import re

js_path = Path("app/web/client_references_v1.js")
html_path = Path("app/web/client.html")

src = js_path.read_text(encoding="utf-8-sig")

src = re.sub(
    r'window\.CLONEXA_REFERENCES_V1_BUILD\s*=\s*"[^"]+";',
    'window.CLONEXA_REFERENCES_V1_BUILD = "REF_02D_CLIENT_THEME_SYNC_2026_05_09";',
    src
)

# Insert theme helpers after t(key)
anchor = '''  function t(key) {
    const lang = getLanguage();
    return (I18N[lang] && I18N[lang][key]) || I18N.es[key] || key;
  }
'''

theme_helpers = '''  function t(key) {
    const lang = getLanguage();
    return (I18N[lang] && I18N[lang][key]) || I18N.es[key] || key;
  }

  function firstColor(values, fallback) {
    for (const value of values) {
      const raw = String(value || "").trim();
      if (!raw) continue;
      if (/^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(raw)) return raw;
      if (/^rgb\\(/i.test(raw) || /^rgba\\(/i.test(raw) || /^hsl\\(/i.test(raw)) return raw;
    }
    return fallback;
  }

  function readJsonStorage(keys) {
    for (const key of keys) {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) continue;
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") return parsed;
      } catch (_) {}
    }
    return {};
  }

  function deepFindColor(obj, names) {
    if (!obj || typeof obj !== "object") return "";
    const wanted = new Set(names.map((x) => String(x).toLowerCase()));

    for (const [key, value] of Object.entries(obj)) {
      const k = String(key).toLowerCase();

      if (wanted.has(k) && typeof value === "string") return value;

      if (value && typeof value === "object") {
        const found = deepFindColor(value, names);
        if (found) return found;
      }
    }

    return "";
  }

  function detectTheme() {
    const rootStyle = getComputedStyle(document.documentElement);
    const bodyStyle = getComputedStyle(document.body);

    const stored = readJsonStorage([
      "clonexa_company",
      "clonexa_current_company",
      "clonexa_company_settings",
      "clonexa_theme",
      "CLONEXA_COMPANY",
      "CLONEXA_THEME",
      "clonexa_core_settings",
      "CLX_CORE_SETTINGS"
    ]);

    const primary = firstColor([
      rootStyle.getPropertyValue("--clx-primary"),
      rootStyle.getPropertyValue("--clx-brand-primary"),
      rootStyle.getPropertyValue("--clx-company-primary"),
      rootStyle.getPropertyValue("--tenant-primary"),
      rootStyle.getPropertyValue("--brand-primary"),
      rootStyle.getPropertyValue("--primary-color"),
      rootStyle.getPropertyValue("--accent-color"),
      bodyStyle.getPropertyValue("--clx-primary"),
      bodyStyle.getPropertyValue("--clx-brand-primary"),
      bodyStyle.getPropertyValue("--tenant-primary"),
      deepFindColor(stored, [
        "primary",
        "primaryColor",
        "primary_color",
        "brandColor",
        "brand_color",
        "accent",
        "accentColor",
        "accent_color"
      ])
    ], "#ff12b8");

    const secondary = firstColor([
      rootStyle.getPropertyValue("--clx-secondary"),
      rootStyle.getPropertyValue("--clx-brand-secondary"),
      rootStyle.getPropertyValue("--clx-company-secondary"),
      rootStyle.getPropertyValue("--tenant-secondary"),
      rootStyle.getPropertyValue("--brand-secondary"),
      rootStyle.getPropertyValue("--secondary-color"),
      bodyStyle.getPropertyValue("--clx-secondary"),
      bodyStyle.getPropertyValue("--tenant-secondary"),
      deepFindColor(stored, [
        "secondary",
        "secondaryColor",
        "secondary_color",
        "brandSecondary",
        "brand_secondary"
      ])
    ], "#6e2d82");

    const surface = firstColor([
      rootStyle.getPropertyValue("--clx-surface"),
      rootStyle.getPropertyValue("--clx-card"),
      rootStyle.getPropertyValue("--surface-color"),
      rootStyle.getPropertyValue("--card-color"),
      bodyStyle.getPropertyValue("--clx-surface"),
      deepFindColor(stored, [
        "surface",
        "surfaceColor",
        "surface_color",
        "card",
        "cardColor",
        "card_color"
      ])
    ], "rgba(10,14,25,.94)");

    return { primary, secondary, surface };
  }

  function applyTheme() {
    if (!state.root) return;

    const theme = detectTheme();

    state.root.style.setProperty("--ref-primary", theme.primary);
    state.root.style.setProperty("--ref-secondary", theme.secondary);
    state.root.style.setProperty("--ref-surface", theme.surface);
    state.root.style.setProperty("--ref-primary-soft", `color-mix(in srgb, ${theme.primary} 38%, transparent)`);
    state.root.style.setProperty("--ref-secondary-soft", `color-mix(in srgb, ${theme.secondary} 42%, transparent)`);
    state.root.style.setProperty("--ref-primary-border", `color-mix(in srgb, ${theme.primary} 70%, white 10%)`);
  }
'''

if anchor not in src:
    raise SystemExit("No encontré función t(key) esperada.")
src = src.replace(anchor, theme_helpers)

# Replace hardcoded colors in CSS with variables.
replacements = {
    "#ff18c7": "var(--ref-primary)",
    "#ff12b8": "var(--ref-primary)",
    "#6e2d82": "var(--ref-secondary)",
    "rgba(255,0,170,.38)": "var(--ref-primary-soft)",
    "rgba(80,16,83,.55)": "var(--ref-secondary-soft)",
    "rgba(255,70,120,.17)": "color-mix(in srgb, var(--ref-primary) 20%, transparent)",
    "rgba(255,70,120,.45)": "color-mix(in srgb, var(--ref-primary) 55%, transparent)"
}

for old, new in replacements.items():
    src = src.replace(old, new)

# Replace card/hero gradients more safely.
src = src.replace(
    "background:linear-gradient(135deg,rgba(8,13,24,.96),var(--ref-primary-soft));",
    "background:linear-gradient(135deg,rgba(8,13,24,.96),var(--ref-primary-soft));"
)

src = src.replace(
    "background:linear-gradient(135deg,rgba(10,14,25,.94),var(--ref-secondary-soft));",
    "background:linear-gradient(135deg,var(--ref-surface),var(--ref-secondary-soft));"
)

# Ensure applyTheme runs before render.
src = src.replace(
    '''      bindEvents();
      render();
      loadData();''',
    '''      bindEvents();
      applyTheme();
      render();
      loadData();'''
)

# Also apply theme before each render if root exists.
src = src.replace(
    '''  function render() {
    if (!state.root) return;''',
    '''  function render() {
    if (!state.root) return;
    applyTheme();'''
)

js_path.write_text(src, encoding="utf-8")

html = html_path.read_text(encoding="utf-8-sig")
html = re.sub(
    r'client_references_v1\.js\?v=[^"\']+',
    'client_references_v1.js?v=REF02D_20260509',
    html,
    flags=re.IGNORECASE
)
html_path.write_text(html, encoding="utf-8")

print("REF_02D_THEME_SYNC_OK")
