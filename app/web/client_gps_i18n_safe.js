
(function clonexaSafeGpsI18n020GR1() {
  "use strict";

  if (window.__CLONEXA_020G_R1_GPS_I18N__) return;
  window.__CLONEXA_020G_R1_GPS_I18N__ = true;

  const LANG_KEY = "clonexa_client_language";

  const DICT = {
    es: {
      settings: "Ajustes",
      logout: "Cerrar sesión",

      moduleEyebrow: "Módulo GPS",
      moduleTitle: "GPS",
      moduleSubtitle: "Configura hasta 5 perímetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.",

      back: "Volver",
      refresh: "Actualizar",

      operationalValidation: "Validación operativa",
      gpsSummary: "Resumen GPS",
      sentLocations: "Ubicaciones enviadas",
      insidePerimeter: "Dentro de perímetro",
      outsidePerimeter: "Fuera de perímetro",

      allowedParameters: "Parámetros permitidos",
      perimeters: "Perímetros",
      perimeterHelp: "El bot solo envía ubicación. La validación dentro/fuera la hace CLONEXA con estos parámetros.",

      point: "Punto",
      latFrom: "Lat desde",
      latTo: "Lat hasta",
      lngFrom: "Lng desde",
      lngTo: "Lng hasta",
      active: "Activo",

      pointName: "Nombre punto",
      latitudeFrom: "Latitud desde",
      latitudeTo: "Latitud hasta",
      longitudeFrom: "Longitud desde (-74...)",
      longitudeTo: "Longitud hasta (-74...)",

      savePerimeters: "Guardar perímetros",
      savedPerimeters: "Perímetros GPS guardados.",
      loadError: "No se pudo cargar GPS.",

      insideLabel: "Dentro de perímetro",
      outsideLabel: "Fuera de perímetro",
      noValidation: "Sin validación",
      noLocation: "Sin ubicación"
    },

    en: {
      settings: "Settings",
      logout: "Log out",

      moduleEyebrow: "GPS module",
      moduleTitle: "GPS",
      moduleSubtitle: "Configure up to 5 allowed perimeters. CLONEXA validates the locations received from the bot.",

      back: "Back",
      refresh: "Refresh",

      operationalValidation: "Operational validation",
      gpsSummary: "GPS summary",
      sentLocations: "Locations sent",
      insidePerimeter: "Inside perimeter",
      outsidePerimeter: "Outside perimeter",

      allowedParameters: "Allowed parameters",
      perimeters: "Perimeters",
      perimeterHelp: "The bot only sends location. CLONEXA performs inside/outside validation using these parameters.",

      point: "Point",
      latFrom: "Lat from",
      latTo: "Lat to",
      lngFrom: "Lng from",
      lngTo: "Lng to",
      active: "Active",

      pointName: "Point name",
      latitudeFrom: "Latitude from",
      latitudeTo: "Latitude to",
      longitudeFrom: "Longitude from (-74...)",
      longitudeTo: "Longitude to (-74...)",

      savePerimeters: "Save perimeters",
      savedPerimeters: "GPS perimeters saved.",
      loadError: "Could not load GPS.",

      insideLabel: "Inside perimeter",
      outsideLabel: "Outside perimeter",
      noValidation: "No validation",
      noLocation: "No location"
    },

    fr: {
      settings: "Configuration",
      logout: "Quitter",

      moduleEyebrow: "Module GPS",
      moduleTitle: "GPS",
      moduleSubtitle: "Configurez jusqu’à 5 périmètres autorisés. CLONEXA valide les positions reçues par le bot.",

      back: "Retour",
      refresh: "Actualiser",

      operationalValidation: "Validation opérationnelle",
      gpsSummary: "Résumé GPS",
      sentLocations: "Positions envoyées",
      insidePerimeter: "Dans le périmètre",
      outsidePerimeter: "Hors périmètre",

      allowedParameters: "Paramètres autorisés",
      perimeters: "Périmètres",
      perimeterHelp: "Le bot envoie uniquement la position. CLONEXA valide dedans/dehors avec ces paramètres.",

      point: "Point",
      latFrom: "Lat de",
      latTo: "Lat à",
      lngFrom: "Lng de",
      lngTo: "Lng à",
      active: "Actif",

      pointName: "Nom du point",
      latitudeFrom: "Latitude de",
      latitudeTo: "Latitude à",
      longitudeFrom: "Longitude de (-74...)",
      longitudeTo: "Longitude à (-74...)",

      savePerimeters: "Enregistrer les périmètres",
      savedPerimeters: "Périmètres GPS enregistrés.",
      loadError: "Impossible de charger le GPS.",

      insideLabel: "Dans le périmètre",
      outsideLabel: "Hors périmètre",
      noValidation: "Sans validation",
      noLocation: "Sans position"
    }
  };

  const ALIASES = {};

  Object.keys(DICT).forEach((language) => {
    Object.keys(DICT[language]).forEach((key) => {
      ALIASES[norm(DICT[language][key])] = key;
    });
  });

  [
    ["Modulo GPS", "moduleEyebrow"],
    ["Módulo GPS", "moduleEyebrow"],
    ["GPS", "moduleTitle"],
    ["Configura hasta 5 perímetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.", "moduleSubtitle"],
    ["Configura hasta 5 perimetros permitidos. CLONEXA valida las ubicaciones recibidas por el bot.", "moduleSubtitle"],

    ["Volver", "back"],
    ["Actualizar", "refresh"],

    ["Validación operativa", "operationalValidation"],
    ["Validacion operativa", "operationalValidation"],
    ["Resumen GPS", "gpsSummary"],
    ["Ubicaciones enviadas", "sentLocations"],
    ["Dentro de perímetro", "insidePerimeter"],
    ["Dentro de perimetro", "insidePerimeter"],
    ["Fuera de perímetro", "outsidePerimeter"],
    ["Fuera de perimetro", "outsidePerimeter"],

    ["Parámetros permitidos", "allowedParameters"],
    ["Parametros permitidos", "allowedParameters"],
    ["Perímetros", "perimeters"],
    ["Perimetros", "perimeters"],
    ["El bot solo envía ubicación. La validación dentro/fuera la hace CLONEXA con estos parámetros.", "perimeterHelp"],
    ["El bot solo envia ubicacion. La validacion dentro/fuera la hace CLONEXA con estos parametros.", "perimeterHelp"],

    ["Punto", "point"],
    ["Lat desde", "latFrom"],
    ["Lat hasta", "latTo"],
    ["Lng desde", "lngFrom"],
    ["Lng hasta", "lngTo"],
    ["Activo", "active"],

    ["Nombre punto", "pointName"],
    ["Latitud desde", "latitudeFrom"],
    ["Latitud hasta", "latitudeTo"],
    ["Longitud desde (-74...)", "longitudeFrom"],
    ["Longitud hasta (-74...)", "longitudeTo"],

    ["Guardar perímetros", "savePerimeters"],
    ["Guardar perimetros", "savePerimeters"],
    ["Perímetros GPS guardados.", "savedPerimeters"],
    ["Perimetros GPS guardados.", "savedPerimeters"],
    ["No se pudo cargar GPS.", "loadError"],

    ["Sin validación", "noValidation"],
    ["Sin validacion", "noValidation"],
    ["Sin ubicacion", "noLocation"],
    ["Sin ubicación", "noLocation"],

    ["Ajustes", "settings"],
    ["Cerrar sesión", "logout"],
    ["Cerrar sesion", "logout"]
  ].forEach(([text, key]) => {
    ALIASES[norm(text)] = key;
  });

  function lang() {
    const value = String(localStorage.getItem(LANG_KEY) || "es").toLowerCase();
    return ["es", "en", "fr"].includes(value) ? value : "es";
  }

  function norm(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function t(key) {
    return (DICT[lang()] && DICT[lang()][key]) || DICT.es[key] || key;
  }

  function shouldSkipText(value) {
    const raw = String(value || "").trim();
    if (!raw) return true;
    if (/^[\d\s.,:$%#@/_-]+$/.test(raw)) return true;
    if (/^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$/.test(raw)) return true;
    if (raw.includes("@")) return true;
    if (/^[a-f0-9-]{20,}$/i.test(raw)) return true;
    return false;
  }

  function translateText(value) {
    const raw = String(value || "");
    const clean = raw.replace(/\s+/g, " ").trim();

    if (shouldSkipText(clean)) return raw;

    const key = ALIASES[norm(clean)];
    if (!key) return raw;

    return raw.replace(clean, t(key));
  }

  function isGpsVisible() {
    const app = document.getElementById("app");
    if (!app) return false;

    if (app.querySelector("[data-gps-perimeters-grid]")) return true;
    if (app.querySelector("[data-gps-field]")) return true;
    if (app.querySelector("[data-gps-save]")) return true;
    if (app.querySelector("[data-gps-refresh]")) return true;

    const text = app.textContent || "";
    return (
      text.includes("Modulo GPS") ||
      text.includes("Módulo GPS") ||
      text.includes("GPS module") ||
      text.includes("Module GPS") ||
      text.includes("Resumen GPS") ||
      text.includes("GPS summary") ||
      text.includes("Résumé GPS")
    );
  }

  function skipElement(el) {
    if (!el || !el.tagName) return true;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "code", "pre"].includes(tag)) return true;
    if (el.closest && el.closest("[data-clx-no-i18n]")) return true;
    return false;
  }

  function translateAttributes(base) {
    base.querySelectorAll("[placeholder], [title], [aria-label], input[type='button'], input[type='submit']").forEach((el) => {
      if (skipElement(el)) return;

      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!el.hasAttribute(attr)) return;
        const current = el.getAttribute(attr);
        const next = translateText(current);
        if (next !== current) el.setAttribute(attr, next);
      });

      if (el.matches("input[type='button'], input[type='submit']")) {
        const next = translateText(el.value);
        if (next !== el.value) el.value = next;
      }
    });
  }

  function translateGps() {
    try {
      if (!isGpsVisible()) return;

      const app = document.getElementById("app");
      if (!app) return;

      const walker = document.createTreeWalker(app, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipElement(parent)) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });

      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      nodes.forEach((node) => {
        const next = translateText(node.nodeValue);
        if (next !== node.nodeValue) node.nodeValue = next;
      });

      translateAttributes(app);

      const settings = document.getElementById("clxOpenCoreSettings");
      const logout = document.getElementById("clxCoreLogout");

      if (settings) settings.textContent = `⚙ ${t("settings")}`;
      if (logout) logout.textContent = `⏻ ${t("logout")}`;

      document.documentElement.lang = lang();
    } catch (error) {
      console.warn("CLONEXA GPS i18n skipped:", error);
    }
  }

  let timer = null;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(translateGps, 140);
  }

  function burst() {
    let count = 0;
    const id = setInterval(() => {
      count += 1;
      translateGps();
      if (count >= 8) clearInterval(id);
    }, 220);
  }

  document.addEventListener("click", () => {
    schedule();
    setTimeout(schedule, 450);
    setTimeout(schedule, 1000);
  }, true);

  document.addEventListener("input", schedule, true);
  document.addEventListener("change", schedule, true);

  const observer = new MutationObserver(schedule);

  function init() {
    try {
      if (document.body) {
        observer.observe(document.body, {
          childList: true,
          subtree: true
        });
      }
      schedule();
      burst();
    } catch (error) {
      console.warn("CLONEXA GPS i18n init skipped:", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
