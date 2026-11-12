// Oficina 3D · gestos de la cámara (sin three; se prueba en Chrome con emulación táctil: tests/oficina_gestos.test.cjs).
// Antes: girar con el dedo o con dos dedos en el touchpad hacía "atrás" en Chrome y sacaba de la oficina.
// Ahora la oficina maneja sus gestos y cancela los del navegador:
// - un dedo / ratón: girar (arrastrar) · clic derecho, Shift o dos dedos: mover
// - pellizco (dos dedos) o Ctrl + rueda (pellizco del touchpad): acercar / alejar
// - rueda vertical: acercar · rueda horizontal (dos dedos de lado en el touchpad): girar, nunca "atrás"
// - doble clic: volver a la vista inicial
// El CSS acompaña: overscroll-behavior: none en html/body y touch-action: none en el lienzo.
export const TAP_PX = 6;

export function attachGestures(el, h, {win = window} = {}) {
  const pts = new Map(); let drag = null, pinch = null;
  const two = () => { const [a, b] = [...pts.values()]; return {d: Math.hypot(a.x - b.x, a.y - b.y) || 1, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2}; };
  const onDown = e => {
    if (e.pointerType !== 'mouse') e.preventDefault();
    pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    try { el.setPointerCapture(e.pointerId); } catch (_) { /* sin captura: igual funciona con la ventana */ }
    if (pts.size === 2) { pinch = two(); drag = null; }
    else if (pts.size === 1) drag = {x: e.clientX, y: e.clientY, m: 0, pan: e.button === 2 || e.shiftKey, id: e.pointerId};
  };
  const onMove = e => {
    if (!pts.has(e.pointerId)) return;
    e.preventDefault();
    pts.set(e.pointerId, {x: e.clientX, y: e.clientY});
    if (pinch && pts.size >= 2) {
      const now = two();
      h.zoom && h.zoom(pinch.d / now.d);            // separar los dedos acerca
      h.pan && h.pan(now.x - pinch.x, now.y - pinch.y);
      pinch = now; return;
    }
    if (!drag || drag.id !== e.pointerId) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.m += Math.abs(dx) + Math.abs(dy); drag.x = e.clientX; drag.y = e.clientY;
    if (drag.pan) h.pan && h.pan(dx, dy); else h.rotate && h.rotate(dx, dy);
  };
  const onUp = e => {
    if (!pts.has(e.pointerId)) return;
    pts.delete(e.pointerId);
    if (drag && drag.id === e.pointerId && drag.m < TAP_PX && e.type === 'pointerup' && !pinch) h.tap && h.tap(e);
    if (pts.size < 2) pinch = null;
    if (pts.size === 1) { const [[id, p]] = [...pts.entries()]; drag = {x: p.x, y: p.y, m: TAP_PX, pan: false, id}; } else drag = null;
  };
  const onWheel = e => {
    e.preventDefault();                               // nunca scroll ni "atrás" del navegador
    if (e.ctrlKey) { h.zoom && h.zoom(Math.exp(e.deltaY * 0.01)); return; }   // pellizco del touchpad
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) { h.rotate && h.rotate(-e.deltaX * 0.5, 0); return; }
    h.zoom && h.zoom(1 + Math.sign(e.deltaY) * 0.08);
  };
  const stopTouch = e => { if (e.cancelable) e.preventDefault(); };   // Safari / WebView sin pointer events completos
  const onCtx = e => e.preventDefault();
  const onDbl = () => h.reset && h.reset();
  el.addEventListener('pointerdown', onDown, {passive: false});
  win.addEventListener('pointermove', onMove, {passive: false});
  win.addEventListener('pointerup', onUp); win.addEventListener('pointercancel', onUp);
  el.addEventListener('wheel', onWheel, {passive: false});
  el.addEventListener('touchstart', stopTouch, {passive: false}); el.addEventListener('touchmove', stopTouch, {passive: false});
  el.addEventListener('contextmenu', onCtx); el.addEventListener('dblclick', onDbl);
  return {
    get dragging() { return pts.size > 0; },
    detach() {
      el.removeEventListener('pointerdown', onDown); win.removeEventListener('pointermove', onMove);
      win.removeEventListener('pointerup', onUp); win.removeEventListener('pointercancel', onUp);
      el.removeEventListener('wheel', onWheel); el.removeEventListener('touchstart', stopTouch); el.removeEventListener('touchmove', stopTouch);
      el.removeEventListener('contextmenu', onCtx); el.removeEventListener('dblclick', onDbl);
    }};
}
