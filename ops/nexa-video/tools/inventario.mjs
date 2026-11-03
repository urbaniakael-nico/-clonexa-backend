// Empresa DEMO de restaurante (Brasa & Maiz): Inventario con Carta (insumos que descuentan las recetas).
// Datos 100 % inventados.
export const CID = "0de30000-0000-4000-8000-0000000000b7";
export const COMPANY = "Brasa & Maíz (demo)";
export const SLUG = "brasa-y-maiz-demo";
export const MODULES = [["hospitality", "Hospitality"], ["carta", "Carta"], ["inventory", "Inventario"], ["reports", "Reportes"]];
const ago = (d) => new Date(Date.now() - d * 86400000).toISOString();
// [id, nombre, unidad base, unidad natural, factor, existencia base, saldo $, minimo natural, bajo, ultima compra [cant, unidad, total, dias]]
const I = [
  ["i1", "Lomo de res", "g", "kg", 1000, 8400, 302400, 5, false, [10, "kg", 360000, 2]],
  ["i2", "Pollo entero", "unidad", "unidad", 1, 6, 108000, 10, true, [12, "unidad", 216000, 3]],
  ["i3", "Papa criolla", "g", "kg", 1000, 12500, 43750, 6, false, [15, "kg", 52500, 1]],
  ["i4", "Pan de hamburguesa", "unidad", "unidad", 1, 34, 40800, 24, false, [48, "unidad", 57600, 2]],
  ["i5", "Queso cheddar", "g", "kg", 1000, 1800, 79200, 2, true, [3, "kg", 132000, 4]],
  ["i6", "Limón", "g", "kg", 1000, 4200, 21000, 3, false, [6, "kg", 30000, 1]],
];
const insumos = I.map(([id, name, base, unit, f, stock, value, min, , lp]) => ({
  id, name, consumption_unit: base, unit, unit_label: unit === "kg" ? "kg" : "unidad", natural_factor: f, stock, stock_natural: stock / f,
  stock_value: value, avg_cost: value / stock, cost_per_unit: (value / stock) * f, min_stock_natural: min, balance_suspect: false,
  last_purchase: { id: `p-${id}`, quantity: lp[0], unit: lp[1], unit_label: lp[1] === "kg" ? "kg" : "unidad", total_paid: lp[2], created_at: ago(lp[3]), has_invoice: false },
}));
const items = I.map(([id, name, base, , f, stock, , min, low]) => ({
  id, name_reference: name, current_stock: stock, min_stock: min * f, status: "active", alert_low: low, unit: base,
}));
export const init = () => { window.__cxInventoryMode = "modify"; };
export async function api(q) {
  if (q.startsWith("/inventory/companies/") && q.includes("/items")) return { summary: { active: 6, low_stock: 2, inactive: 0, total: 6, total_entry_value: 595150 }, items };
  if (q.startsWith("/inventory/companies/") && q.includes("/movements")) return { movements: [] };
  if (q === `/carta/companies/${CID}`) return { insumos, platos: [], categorias: [] };
  return undefined;
}
export const SHOTS = [
  { name: "tabla", module: "inventory", w: 1440, h: 1000, scale: 2, init, selector: ".cx-inv-table-wrap" },
];
