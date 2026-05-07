
(function clonexaGoogleStyleTranslatorBridge() {
  "use strict";

  if (window.__CLONEXA_GOOGLE_TRANSLATE_BRIDGE__) return;
  window.__CLONEXA_GOOGLE_TRANSLATE_BRIDGE__ = true;

  const LANG_KEY = "clonexa_client_language";
  const SOURCE_LANG = "es";
  const TARGETS = new Set(["es", "en", "fr"]);

  function getLang() {
    const raw = String(localStorage.getItem(LANG_KEY) || document.documentElement.lang || "es").toLowerCase();
    return TARGETS.has(raw) ? raw : "es";
  }

  function setGoogTransCookie(target) {
    const value = target === "es" ? "" : `/${SOURCE_LANG}/${target}`;
    const maxAge = target === "es" ? "0" : "31536000";

    const host = location.hostname;

    document.cookie = `googtrans=${value}; path=/; max-age=${maxAge}`;
    document.cookie = `googtrans=${value}; path=/; domain=${host}; max-age=${maxAge}`;

    if (host.split(".").length > 2) {
      const root = "." + host.split(".").slice(-2).join(".");
      document.cookie = `googtrans=${value}; path=/; domain=${root}; max-age=${maxAge}`;
    }
  }

  function installCss() {
    if (document.getElementById("clx-google-translate-bridge-css")) return;

    const style = document.createElement("style");
    style.id = "clx-google-translate-bridge-css";
    style.textContent = `
      .goog-te-banner-frame,
      .goog-te-balloon-frame,
      #goog-gt-tt,
      .goog-te-gadget,
      .goog-logo-link,
      iframe.skiptranslate {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        width: 0 !important;
        height: 0 !important;
      }

      body {
        top: 0 !important;
      }

      #clx_google_translate_mount {
        position: fixed;
        left: -9999px;
        bottom: -9999px;
        width: 1px;
        height: 1px;
        overflow: hidden;
        pointer-events: none;
      }
    `;
    document.head.appendChild(style);
  }

  function ensureMount() {
    let mount = document.getElementById("clx_google_translate_mount");
    if (!mount) {
      mount = document.createElement("div");
      mount.id = "clx_google_translate_mount";
      document.body.appendChild(mount);
    }
    return mount;
  }

  function loadGoogleScript() {
    if (window.google && window.google.translate) return;
    if (document.getElementById("clx-google-translate-script")) return;

    window.googleTranslateElementInit = function () {
      try {
        new window.google.translate.TranslateElement(
          {
            pageLanguage: SOURCE_LANG,
            includedLanguages: "es,en,fr",
            autoDisplay: false,
            layout: window.google.translate.TranslateElement.InlineLayout.SIMPLE
          },
          "clx_google_translate_mount"
        );
      } catch (error) {
        console.warn("CLONEXA Google Translate init failed:", error);
      }
    };

    const script = document.createElement("script");
    script.id = "clx-google-translate-script";
    script.src = "https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
    script.async = true;
    script.onerror = function () {
      console.warn("CLONEXA Google Translate script could not be loaded.");
    };
    document.head.appendChild(script);
  }

  function applyLanguage(target, shouldReload) {
    const lang = TARGETS.has(target) ? target : "es";

    localStorage.setItem(LANG_KEY, lang);
    document.documentElement.lang = lang;

    setGoogTransCookie(lang);

    if (lang !== "es") {
      installCss();
      ensureMount();
      loadGoogleScript();
    }

    if (shouldReload) {
      setTimeout(function () {
        window.location.reload();
      }, 250);
    }
  }

  function syncAccountButtons() {
    const lang = getLang();
    const settings = document.getElementById("clxAccountSettingsBtn");
    const logout = document.getElementById("clxAccountLogoutBtn");

    if (settings) {
      settings.textContent =
        lang === "fr" ? "⚙ Configuration" :
        lang === "en" ? "⚙ Settings" :
        "⚙ Configuración";
    }

    if (logout) {
      logout.textContent =
        lang === "fr" ? "⏻ Quitter" :
        lang === "en" ? "⏻ Log out" :
        "⏻ Salir";
    }
  }

  function bindLanguageSelect() {
    document.addEventListener("change", function (event) {
      const el = event.target;
      if (!el || el.id !== "clxAccountLanguage") return;

      const selected = String(el.value || "es").toLowerCase();
      applyLanguage(selected, true);
    }, true);
  }

  function observeButtons() {
    const observer = new MutationObserver(function () {
      syncAccountButtons();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true
    });

    syncAccountButtons();
  }

  function init() {
    installCss();
    ensureMount();
    bindLanguageSelect();
    observeButtons();

    const lang = getLang();
    applyLanguage(lang, false);

    if (lang !== "es") {
      loadGoogleScript();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
