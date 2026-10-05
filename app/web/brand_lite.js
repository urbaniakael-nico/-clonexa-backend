// Estudio de marca · modo liviano automatico (Fase 4). Solo se carga cuando la
// empresa tiene marca publicada. En equipos lentos o con ahorro de datos marca
// <html class="cx-lite">: el CSS de la marca usa la imagen liviana y apaga el
// desenfoque y los brillos. El panel nunca debe sentirse lento por la marca.
(() => {
  try {
    const c = navigator.connection || {};
    const mq = (q) => typeof window.matchMedia === "function" && window.matchMedia(q).matches;
    const slow = c.saveData === true || /(^|-)(2g|3g)$/.test(String(c.effectiveType || "")) ||
      (navigator.deviceMemory && navigator.deviceMemory <= 2) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2) ||
      mq("(prefers-reduced-data: reduce)") || mq("(prefers-reduced-motion: reduce)");
    if (slow) document.documentElement.classList.add("cx-lite");
  } catch (_) {}
})();
