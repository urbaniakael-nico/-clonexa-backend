// Plantillas de locales (planos de inicio). Todo se puede mover, pintar y cambiar después.
import { uid } from './core.js';
const O = (item, x, z, rot = 0, extra = {}) => ({ id: uid(), item, x, z, rot, ...extra });
const W = (mat, color) => ({ mat, color });

export const TEMPLATES = {
  bar: { name: 'Bar', icon: '🍸', desc: 'Barra, pista, DJ, mesas QR', make: () => {
    const objs = [O('contrabarra', -6.75, -2.6, 90), O('contrabarra', -6.75, -.2, 90), O('barra_recta', -5.1, -2.6, 90), O('barra_recta', -5.1, -.2, 90)];
    for (let i = 0; i < 7; i++) objs.push(O('taburete', -4.35, -3.6 + i * .72));
    objs.push(O('caja', -5.2, 2.2, 90, { conn: 'Caja principal' }), O('nevera_bebidas', -3.3, -4.55, 0, { products: 'Cervezas', conn: 'Bebidas frías' }), O('neon', -1.2, -4.88, 0, { text: 'Night Bar' }), O('tv_pared', 2.2, -4.88, 0, { screen: 'Partido / TV' }));
    objs.push(O('cabina_dj', 5, -4.2, 0, { conn: 'Canciones pedidas' }), O('parlante', 3.7, -4.3), O('parlante', 6.3, -4.3), O('pista_led', 5, -2.1));
    [[-1.6, -1.6], [.9, -1.6], [-1.6, 1.2], [.9, 1.2], [-.35, 3.6]].forEach(([x, z], i) => objs.push(O('mesa_redonda', x, z, 0, { conn: 'Mesa ' + (i + 1) })));
    objs.push(O('mesa_alta', 3.3, 1.4, 0, { conn: 'Mesa 6' }), O('mesa_alta', 4.6, 1.4, 0, { conn: 'Mesa 7' }), O('sofa', 5.3, 4.2, 180), O('mesa_centro', 5.3, 3.3));
    [[-1.6, -1.6], [.9, -1.6], [-1.6, 1.2], [.9, 1.2]].forEach(([x, z]) => objs.push(O('lampara', x, z)));
    objs.push(O('planta', 6.4, -.6), O('planta', -.4, -4.4), O('planta_alta', 6.5, 1.2), O('tapete', 5.3, 3.5));
    return { name: 'Bar', room: { w: 14, d: 10, h: 3.6 }, floor: { mat: 'madera_oscura', color: '#5b3a26' }, walls: { n: W('ladrillo', '#8a4130'), w: W('ladrillo', '#8a4130'), s: W('ladrillo', '#8a4130'), e: W('ladrillo', '#8a4130') }, openings: [{ id: uid(), wall: 's', pos: .78, type: 'puerta_vidrio' }], objects: objs };
  } },
  restaurante: { name: 'Restaurante', icon: '🍽️', desc: 'Cocina abierta, salón, domicilios', make: () => {
    const objs = [O('estufa', -5.2, -4.45), O('parrilla', -3.9, -4.4, 0, { conn: 'Parrilla' }), O('freidora', -2.85, -4.45), O('horno', -1.95, -4.42), O('campana', -4.55, -4.75), O('meson', -.3, -4.45), O('lavaplatos', 1.3, -4.45), O('nevera_industrial', 2.75, -4.42), O('pase', -2.2, -2.7), O('tv_pared', 4.8, -4.88, 0, { screen: 'Comandas en cocina' })];
    [[-4.6, .2], [-1.6, .2], [1.4, .2], [-4.6, 3.2], [-1.6, 3.2], [1.4, 3.2]].forEach(([x, z], i) => objs.push(O('mesa_cuadrada', x, z, 0, { conn: 'Mesa ' + (i + 1), color: '#c8a27a', color2: '#7f1d1d' })));
    objs.push(O('mesa_2', 4.2, .4, 0, { conn: 'Mesa 7' }), O('mesa_2', 4.2, 2.6, 0, { conn: 'Mesa 8' }), O('mostrador', 5.6, -2.3, -90), O('caja', 5.6, -1.0, -90, { conn: 'Caja principal' }), O('planta', 6.4, 4.3), O('planta', -6.3, 4.3), O('cuadro', -6.85, 1.5, 90), O('cuadro', -6.85, -1.0, 90, { color: '#f97316' }));
    return { name: 'Restaurante', room: { w: 14, d: 10, h: 3.4 }, floor: { mat: 'baldosa', color: '#e8e6e3' }, walls: { n: W('azulejo', '#e8f1f5'), w: W('madera', '#7c4a2d'), s: W('pintura', '#e7e2f0'), e: W('pintura', '#e7e2f0') }, openings: [{ id: uid(), wall: 's', pos: .55, type: 'puerta_doble' }, { id: uid(), wall: 'w', pos: .3, type: 'ventana' }], objects: objs };
  } },
  taller: { name: 'Taller', icon: '🧵', desc: 'Máquinas, corte, lotes', make: () => {
    const objs = []; let n = 1;
    [-1.8, 1.4].forEach(z => [-5, -3, -1, 1, 3].forEach(x => objs.push(O(n % 4 === 0 ? 'fileteadora' : 'maquina_plana', x, z, 0, { conn: 'Puesto ' + n++ }))));
    objs.push(O('mesa_corte', 5.6, -1.2, 90, { conn: 'Corte' }), O('rollos', 6.8, 2.6, 90), O('estante_lotes', -5.5, -4.6), O('estante_lotes', -3.4, -4.6), O('tablero', 1.5, -4.88, 0, { screen: 'Tablero de producción' }), O('perchero', 4.4, 4.2), O('perchero', 2.6, 4.2, 0, { color2: '#7c3aed' }), O('maniqui', 6.6, 4.3), O('planta', -7.3, 4.3));
    return { name: 'Taller', room: { w: 16, d: 10, h: 3.4 }, floor: { mat: 'epoxico', color: '#5c6670' }, walls: { n: W('pintura', '#f1eff4'), w: W('pintura', '#f1eff4'), s: W('pintura', '#f1eff4'), e: W('pintura', '#f1eff4') }, openings: [{ id: uid(), wall: 'n', pos: .82, type: 'ventanal' }, { id: uid(), wall: 's', pos: .2, type: 'puerta' }], objects: objs };
  } },
  callcenter: { name: 'Call center', icon: '🎧', desc: 'Escritorios, tablero, supervisión', make: () => {
    const objs = []; let n = 1;
    [-2.2, 1.0].forEach(z => [-4.2, -1.4, 1.4, 4.2].forEach(x => objs.push(O('escritorio', x, z, 0, { conn: 'Agente ' + n++ }))));
    objs.push(O('tablero', 0, -4.88, 0, { screen: 'Comandas en cocina' }), O('tv_pared', -6.85, -.5, 90, { screen: 'Domicilios' }), O('mesa_juntas', 3.6, 3.6), O('planta_alta', -6.3, -4.3), O('planta_alta', 6.3, -4.3), O('archivador', -6.4, 3.8), O('archivador', -5.8, 3.8), O('dispensador' in {} ? 'planta' : 'planta', -4.4, 4.2));
    return { name: 'Call center', room: { w: 14, d: 10, h: 3.4 }, floor: { mat: 'alfombra', color: '#3b2d4f' }, walls: { n: W('panel', '#121016'), w: W('pintura', '#2a2433'), s: W('pintura', '#2a2433'), e: W('pintura', '#2a2433') }, openings: [{ id: uid(), wall: 's', pos: .15, type: 'puerta_vidrio' }], objects: objs };
  } },
  bodega: { name: 'Bodega / campo', icon: '📦', desc: 'Racks, estibas, casilleros', make: () => {
    const objs = [];
    [-4.6, -1.6, 1.4].forEach(z => [-5, -2.6].forEach(x => objs.push(O('rack', x, z))));
    objs.push(O('estiba', 2.2, -2.5), O('estiba', 3.6, -2.5), O('estiba', 2.2, -.8), O('casilleros', 6.6, -3.5, -90), O('conos', 4.5, 3.2), O('conos', 5.6, 3.2), O('escritorio', 5.4, .8, -90, { conn: 'Almacén' }), O('tv_pared', 7.85, .8, -90, { screen: 'Tablero de producción' }));
    return { name: 'Bodega', room: { w: 16, d: 11, h: 4.2 }, floor: { mat: 'concreto', color: '#8d8d91' }, walls: { n: W('concreto', '#8f8f93'), w: W('concreto', '#8f8f93'), s: W('concreto', '#8f8f93'), e: W('concreto', '#8f8f93') }, openings: [{ id: uid(), wall: 'n', pos: .78, type: 'cortina' }], objects: objs };
  } },
  oficina: { name: 'Oficina', icon: '🏢', desc: 'Puestos, sala de juntas, lounge', make: () => {
    const objs = [O('escritorio', -4.6, -2.2), O('escritorio', -2.6, -2.2), O('escritorio', -4.6, .6), O('escritorio', -2.6, .6), O('division', -3.6, -.8), O('mesa_juntas', 3.2, -2.6), O('tv_pared', 3.2, -4.88, 0, { screen: 'Logo de la empresa' }), O('sofa', 3.4, 3.4, 180, { color: '#1e3a8a' }), O('mesa_centro', 3.4, 2.4), O('tapete', 3.4, 2.6, 0, { color: '#c8a27a' }), O('archivador', -6.4, 4.0), O('planta_alta', 6.3, 4.2), O('planta', -6.3, -4.3), O('cuadro', -6.85, 1.8, 90), O('reloj', 0, -4.88)];
    return { name: 'Oficina', room: { w: 14, d: 10, h: 3.2 }, floor: { mat: 'madera_clara', color: '#c8a27a' }, walls: { n: W('pintura', '#e7e2f0'), w: W('tapiz', '#6d28d9'), s: W('pintura', '#e7e2f0'), e: W('pintura', '#e7e2f0') }, openings: [{ id: uid(), wall: 'n', pos: .2, type: 'ventanal' }, { id: uid(), wall: 's', pos: .5, type: 'puerta' }], objects: objs };
  } },
};
export function blankPlan(w = 14, d = 10) { return { name: 'Mi local', room: { w, d, h: 3.4 }, floor: { mat: 'madera_clara', color: '#c8a27a' }, walls: { n: W('pintura', '#e7e2f0'), w: W('pintura', '#e7e2f0'), s: W('pintura', '#e7e2f0'), e: W('pintura', '#e7e2f0') }, openings: [{ id: uid(), wall: 's', pos: .5, type: 'puerta' }], objects: [] }; }
// entidades reales de la empresa: en Clonexa salen de la API (store.entities(): mesas QR, puestos/máquinas, agentes,
// cajas, pantallas, inventario y "Canciones pedidas"). Las conexiones de ejemplo de cada plantilla ("Mesa 1",
// "Caja principal"...) se cambian por las entidades reales de la empresa al crear el diseño (editor.realConns).
