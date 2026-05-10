from pathlib import Path
import re

path = Path("app/web/client.js")
src = path.read_text(encoding="utf-8-sig")

# 1) Cualquier ruta vieja de CRM debe caer al Core.
src = src.replace("await renderCrmLiveModule();", "await renderCrmCoreModule();")
src = src.replace("await renderCrmModule();", "await renderCrmCoreModule();")

# 2) El refresco viejo dentro del CRM no debe volver a pintar crm-live.
src = src.replace("[data-crm-live-refresh]", "[data-crm-core-refresh]")

# 3) KPIs del CRM Core: dinámicos. No mostrar Con referencia/Sesiones/Producción si la empresa no tiene production+references.
new_kpis = r'''  function crmCoreKpis(summary) {
    const cards = [
      ["Activos", summary?.active_now ?? 0],
      ["En pausa", summary?.on_break ?? 0],
      ["Fuera", summary?.out ?? 0],
    ];

    if (summary?.production_adapter) {
      cards.push(["Con referencia", summary?.with_reference ?? 0]);
      cards.push(["Producción", "ON"]);
    }

    if (summary?.gps_adapter) cards.push(["GPS", "ON"]);
    if (summary?.materials_adapter) cards.push(["Materiales", "ON"]);
    if (summary?.inventory_adapter) cards.push(["Inventario", "ON"]);

    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
        ${cards.map(([label, value]) => `
          <div style="padding:16px;border-radius:18px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)">
            <div style="font-size:12px;opacity:.75;text-transform:uppercase;letter-spacing:.08em">${h(label)}</div>
            <strong style="display:block;margin-top:8px;font-size:28px;line-height:1">${h(value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

'''

src = re.sub(
    r"  function crmCoreKpis\(summary\) \{.*?\n  function crmCoreTimeRows",
    new_kpis + "  function crmCoreTimeRows",
    src,
    flags=re.S,
)

path.write_text(src, encoding="utf-8")
print("CRM_CORE_FINAL_02_CLIENT_OK")
