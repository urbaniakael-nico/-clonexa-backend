// Equipo de la empresa (en Clonexa sale del módulo Personal) + uniformes por rol.
import { Store, uid, state } from './store.js';
import { defaultToon, defaultHuman } from './char.js';

// En Clonexa el equipo sale del módulo Personal REAL de la empresa (nombre corto con su privacidad, cargo/área y
// turno) y cada persona guarda su personaje {toon, human, uniform, custom} en el servidor (oficina_personajes).
// Los uniformes son por empresa (constructor_uniformes); la primera vez llegan los 4 del prototipo.
export const AREAS = state().areas && state().areas.length ? state().areas : ['Barra', 'Salón', 'Cocina', 'Caja', 'Bodega', 'Oficina'];
export function loadTeam() { return Store.get('team', []); }
export function saveTeam(t) { Store.set('team', t); }
export function loadUniforms() { return Store.get('uniforms', []); }
export function saveUniforms(u) { Store.set('uniforms', u); }
