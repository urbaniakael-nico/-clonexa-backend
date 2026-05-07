from pathlib import Path
import re

html_path = Path("app/web/client.html")
guard_path = Path("app/web/client_language_guard.js")

html = html_path.read_text(encoding="utf-8-sig")

js = r'''
(function clonexaClientLanguageGuard020ER2() {
  "use strict";

  if (window.__CLONEXA_020E_R2_LANGUAGE_GUARD__) return;
  window.__CLONEXA_020E_R2_LANGUAGE_GUARD__ = true;

  const LANG_KEY = "clonexa_client_language";
  const PIN_PREFIX = "clonexa_language_pin_";
  const VALID = new Set(["es", "en", "fr"]);

  function companyId() {
    const params = new URLSearchParams(window.location.search);
    return params.get("company_id") || params.get("companyId") || params.get("tenant") || "global";
  }

  function pinKey() {
    return `${PIN_PREFIX}${companyId()}`;
  }

  function normalize(value) {
    const lang = String(value || "").toLowerCase().trim();
    return VALID.has(lang) ? lang : "";
  }

  function currentPinned() {
    return normalize(localStorage.getItem(pinKey()));
  }

  function currentLocal() {
    return normalize(localStorage.getItem(LANG_KEY));
  }

  function selectedFromModal() {
    const select = document.getElementById("clxCoreLanguage");
    return normalize(select && select.value);
  }

  function preferredLanguage() {
    return selectedFromModal() || currentPinned() || currentLocal() || "es";
  }

  function emit(lang) {
    try {
      window.dispatchEvent(new CustomEvent("clonexa:language-guard-applied", {
        detail: { language: lang, company_id: companyId() }
      }));

      window.dispatchEvent(new CustomEvent("clonexa:core-settings-changed", {
        detail: {
          language: lang,
          company_id: companyId(),
          source: "language_guard"
        }
      }));
    } catch (_) {}
  }

  function applyLanguage(lang, options) {
    const next = normalize(lang) || preferredLanguage();

    localStorage.setItem(LANG_KEY, next);
    localStorage.setItem(pinKey(), next);
    document.documentElement.lang = next;

    if (window.CLX_CORE_SETTINGS && typeof window.CLX_CORE_SETTINGS === "object") {
      window.CLX_CORE_SETTINGS.language = next;
    }

    if (options && options.updateSelect !== false) {
      const select = document.getElementById("clxCoreLanguage");
      if (select && normalize(select.value) !== next) {
        select.value = next;
      }
    }

    emit(next);
    return next;
  }

  function protectLanguage() {
    const pin = currentPinned();
    const local = currentLocal();

    if (pin && local !== pin) {
      return applyLanguage(pin, { updateSelect: true });
    }

    if (!local && pin) {
      return applyLanguage(pin, { updateSelect: true });
    }

    if (!pin && local) {
      localStorage.setItem(pinKey(), local);
      document.documentElement.lang = local;
      emit(local);
      return local;
    }

    return applyLanguage(preferredLanguage(), { updateSelect: true });
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      protectLanguage();
      if (count >= 12) clearInterval(id);
    }, 250);
  }

  function bind() {
    document.addEventListener("change", (event) => {
      const el = event.target;
      if (el && el.id === "clxCoreLanguage") {
        applyLanguage(el.value, { updateSelect: false });
        burst();
      }
    }, true);

    document.addEventListener("click", (event) => {
      const el = event.target;

      if (el && el.id === "clxSaveCorePreferences") {
        const selected = selectedFromModal() || preferredLanguage();
        applyLanguage(selected, { updateSelect: false });

        setTimeout(() => applyLanguage(selected, { updateSelect: true }), 300);
        setTimeout(() => applyLanguage(selected, { updateSelect: true }), 900);
        setTimeout(burst, 1200);
      } else {
        setTimeout(protectLanguage, 80);
        setTimeout(protectLanguage, 450);
        setTimeout(protectLanguage, 1200);
      }
    }, true);

    window.addEventListener("storage", (event) => {
      if (event.key === LANG_KEY || event.key === pinKey()) {
        protectLanguage();
        burst();
      }
    });

    window.addEventListener("popstate", () => {
      protectLanguage();
      burst();
    });
  }

  function init() {
    bind();
    protectLanguage();
    burst();

    const observer = new MutationObserver(() => {
      protectLanguage();
    });

    if (document.body) {
      observer.observe(document.body, {
        childList: true,
        subtree: true
      });
    }
  }

  window.CLX_LANGUAGE_GUARD = {
    get: preferredLanguage,
    set: applyLanguage,
    protect: protectLanguage,
    pinKey
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
'''

guard_path.write_text(js, encoding="utf-8")

# Quitar versiones previas del guard
html = re.sub(
    r'\s*<script[^>]+src=["\'][^"\']*client_language_guard\.js[^"\']*["\'][^>]*>\s*</script>\s*',
    "\n",
    html,
    flags=re.IGNORECASE,
)

# Insertar guard después de client_core_settings.js y ANTES de dashboard/workforce i18n
core_matches = list(re.finditer(
    r'<script[^>]+src=["\']([^"\']*client_core_settings\.js[^"\']*)["\'][^>]*>\s*</script>',
    html,
    flags=re.IGNORECASE,
))

if core_matches:
    last = core_matches[-1]
    src = last.group(1)
    guard_src = re.sub(r'client_core_settings\.js(?:\?v=[^"\']*)?', 'client_language_guard.js?v=020ER2', src)
    html = html[:last.end()] + f'\n<script src="{guard_src}"></script>\n' + html[last.end():]
else:
    client_matches = list(re.finditer(
        r'<script[^>]+src=["\']([^"\']*client\.js[^"\']*)["\'][^>]*>\s*</script>',
        html,
        flags=re.IGNORECASE,
    ))
    if client_matches:
        last = client_matches[-1]
        src = last.group(1)
        guard_src = re.sub(r'client\.js(?:\?v=[^"\']*)?', 'client_language_guard.js?v=020ER2', src)
        html = html[:last.end()] + f'\n<script src="{guard_src}"></script>\n' + html[last.end():]
    else:
        html = html.replace("</body>", '<script src="/client-static/client_language_guard.js?v=020ER2"></script>\n</body>')

html_path.write_text(html, encoding="utf-8")

print("PATCH_OK: 020E-R2 language guard added")
