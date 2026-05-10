from pathlib import Path
import re

backend = Path("app/api/v1/endpoints/crm_core_v1.py")
client = Path("app/web/client.js")

src = backend.read_text(encoding="utf-8-sig")

src = src.replace(
    "from fastapi import APIRouter, Depends",
    "from fastapi import APIRouter, Body, Depends",
)

if "import json" not in src:
    src = src.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nimport json\n", 1)

card_catalog = r'''
CARD_CATALOG = [
    {"code": "core_active", "label": "Activos", "module": "core"},
    {"code": "core_break", "label": "En pausa", "module": "core"},
    {"code": "core_out", "label": "Fuera", "module": "core"},
    {"code": "production_reference", "label": "Con referencia", "module": "production"},
    {"code": "production_on", "label": "Producción", "module": "production"},
    {"code": "gps_on", "label": "GPS", "module": "gps"},
    {"code": "materials_on", "label": "Materiales", "module": "materials"},
    {"code": "inventory_on", "label": "Inventario", "module": "inventory"},
]
'''

if "CARD_CATALOG" not in src:
    src = src.replace(
        'END_EVENTS = {"check_out", "salida", "end_shift", "shift_end", "fin_turno", "clock_out"}\n',
        'END_EVENTS = {"check_out", "salida", "end_shift", "shift_end", "fin_turno", "clock_out"}\n' + card_catalog,
        1,
    )

card_helpers = r'''

async def ensure_card_storage(db: AsyncSession) -> None:
    await db.execute(
        text("""
            CREATE TABLE IF NOT EXISTS crm_card_preferences (
                company_id text NOT NULL,
                scope text NOT NULL DEFAULT 'crm',
                cards jsonb NOT NULL DEFAULT '[]'::jsonb,
                updated_at timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (company_id, scope)
            )
        """)
    )
    await db.commit()


def default_card_codes(modules: set[str]) -> list[str]:
    cards = ["core_active", "core_break", "core_out"]

    if {"production", "references"}.issubset(modules):
        cards = ["core_active", "core_break", "production_reference", "production_on"]

    if "gps" in modules and "gps_on" not in cards:
        cards.append("gps_on")

    if "materials" in modules and "materials_on" not in cards:
        cards.append("materials_on")

    if "inventory" in modules and "inventory_on" not in cards:
        cards.append("inventory_on")

    return cards[:6]


def card_available(card: dict[str, Any], modules: set[str]) -> bool:
    module = clean(card.get("module")).lower()

    if module == "core":
        return True

    if module == "production":
        return {"production", "references"}.issubset(modules)

    return module in modules


async def selected_card_codes(db: AsyncSession, company_id: str, modules: set[str]) -> list[str]:
    await ensure_card_storage(db)

    rows = await safe_rows(
        db,
        """
        SELECT cards
        FROM crm_card_preferences
        WHERE company_id = :company_id
          AND scope = 'crm'
        LIMIT 1
        """,
        {"company_id": company_id},
    )

    if not rows:
        return default_card_codes(modules)

    raw = rows[0].get("cards")

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []

    allowed = {
        card["code"]
        for card in CARD_CATALOG
        if card_available(card, modules)
    }

    selected = []
    for item in raw or []:
        code = clean(item)
        if code in allowed and code not in selected:
            selected.append(code)

    return selected[:6] or default_card_codes(modules)


def build_cards(summary: dict[str, Any], modules: set[str], selected: list[str]) -> dict[str, Any]:
    values = {
        "core_active": summary.get("active_now", 0),
        "core_break": summary.get("on_break", 0),
        "core_out": summary.get("out", 0),
        "production_reference": summary.get("with_reference", 0),
        "production_on": "ON" if summary.get("production_adapter") else "OFF",
        "gps_on": "ON" if summary.get("gps_adapter") else "OFF",
        "materials_on": "ON" if summary.get("materials_adapter") else "OFF",
        "inventory_on": "ON" if summary.get("inventory_adapter") else "OFF",
    }

    catalog = [
        {
            **card,
            "available": card_available(card, modules),
            "selected": card["code"] in selected,
            "value": values.get(card["code"], 0),
        }
        for card in CARD_CATALOG
    ]

    visible = [
        {
            "code": item["code"],
            "label": item["label"],
            "value": item["value"],
            "module": item["module"],
        }
        for item in catalog
        if item["available"] and item["selected"]
    ]

    return {
        "catalog": catalog,
        "selected": selected,
        "visible": visible[:6],
    }
'''

if "ensure_card_storage" not in src:
    marker = "\n\nasync def employees_snapshot("
    if marker not in src:
        raise SystemExit("No encontré employees_snapshot")
    src = src.replace(marker, card_helpers + marker, 1)

ref_helpers = r'''

def normalize_reference_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []

    for row in rows:
        started_at = parse_dt(row.get("started_at"))
        ended_at = parse_dt(row.get("ended_at"))
        status = clean(row.get("status")).lower()
        is_active = status == "active" or ended_at is None

        output.append({
            "session_id": row.get("id") or row.get("session_id"),
            "employee_id": clean(row.get("employee_id")),
            "employee_name": clean(row.get("employee_name")),
            "telegram_user_id": clean(row.get("telegram_user_id")),
            "reference_id": clean(row.get("reference_id")),
            "reference_name": clean(row.get("reference_name")),
            "started_at": dt_text(started_at),
            "ended_at": dt_text(ended_at),
            "status": status,
            "is_active": is_active,
            "stored_seconds": intval(row.get("stored_seconds")),
        })

    return output


async def active_reference_sessions_company(db: AsyncSession, company_id: str) -> list[dict[str, Any]]:
    if not await table_exists(db, "reference_work_sessions"):
        return []

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            COALESCE(employee_id, '') AS employee_id,
            COALESCE(employee_name, '') AS employee_name,
            COALESCE(telegram_user_id, '') AS telegram_user_id,
            COALESCE(reference_id, '') AS reference_id,
            COALESCE(reference_name, '') AS reference_name,
            started_at::text AS started_at,
            ended_at::text AS ended_at,
            COALESCE(status, '') AS status,
            GREATEST(COALESCE(duration_minutes, 0) * 60, 0)::int AS stored_seconds
        FROM reference_work_sessions
        WHERE company_id::text = :company_id
          AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        ORDER BY started_at DESC
        LIMIT 100
        """,
        {"company_id": company_id},
    )

    return normalize_reference_rows(rows)


def session_matches_employee(session: dict[str, Any], employee_id: str, employee_name: str, telegram_user_id: str) -> bool:
    if clean(session.get("employee_id")) == employee_id:
        return True

    if telegram_user_id and clean(session.get("telegram_user_id")) == telegram_user_id:
        return True

    if employee_name and clean(session.get("employee_name")).lower() == employee_name.lower():
        return True

    return False
'''

if "active_reference_sessions_company" not in src:
    marker = "\n\ndef earliest_active_reference_start"
    if marker not in src:
        raise SystemExit("No encontré earliest_active_reference_start")
    src = src.replace(marker, ref_helpers + marker, 1)

cards_routes = r'''

@router.get("/companies/{company_id}/cards")
async def get_crm_cards(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    modules = await active_modules(db, company_id)
    selected = await selected_card_codes(db, company_id, modules)

    empty_summary = {
        "active_now": 0,
        "on_break": 0,
        "out": 0,
        "with_reference": 0,
        "production_adapter": {"production", "references"}.issubset(modules),
        "gps_adapter": "gps" in modules,
        "materials_adapter": "materials" in modules,
        "inventory_adapter": "inventory" in modules,
    }

    return {
        "ok": True,
        "company_id": company_id,
        "cards": build_cards(empty_summary, modules, selected),
    }


@router.put("/companies/{company_id}/cards")
async def put_crm_cards(
    company_id: str,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_card_storage(db)

    modules = await active_modules(db, company_id)

    allowed = {
        card["code"]
        for card in CARD_CATALOG
        if card_available(card, modules)
    }

    raw_cards = payload.get("cards", [])
    if not isinstance(raw_cards, list):
        raw_cards = []

    selected = []
    for item in raw_cards:
        code = clean(item)
        if code in allowed and code not in selected:
            selected.append(code)

    selected = selected[:6] or default_card_codes(modules)

    await db.execute(
        text("""
            INSERT INTO crm_card_preferences (company_id, scope, cards, updated_at)
            VALUES (:company_id, 'crm', CAST(:cards AS jsonb), now())
            ON CONFLICT (company_id, scope)
            DO UPDATE SET cards = EXCLUDED.cards, updated_at = now()
        """),
        {
            "company_id": company_id,
            "cards": json.dumps(selected),
        },
    )
    await db.commit()

    return {
        "ok": True,
        "company_id": company_id,
        "selected": selected,
    }
'''

if '@router.get("/companies/{company_id}/cards")' not in src:
    marker = '@router.get("/companies/{company_id}/snapshot")'
    if marker not in src:
        raise SystemExit("No encontré snapshot route")
    src = src.replace(marker, cards_routes + "\n" + marker, 1)

# Insert company active sessions + active people after employees load.
src = src.replace(
'''    modules = await active_modules(db, company_id)
    employees = await employees_snapshot(db, company_id)

    rows = []''',
'''    modules = await active_modules(db, company_id)
    employees = await employees_snapshot(db, company_id)
    company_active_sessions = await active_reference_sessions_company(db, company_id)

    active_people = [
        employee for employee in employees
        if normalize_status(employee.get("work_status")) in {"working", "on_break"}
    ]

    rows = []
    consumed_session_ids: set[str] = set()''',
1
)

# Add fallback after preliminary_sessions.
src = src.replace(
'''        preliminary_sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            None,
        )

        shift_start = latest_shift_start_from_events(events)''',
'''        preliminary_sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            None,
        )

        if not preliminary_sessions and employee_status in {"working", "on_break"}:
            preliminary_sessions = [
                session for session in company_active_sessions
                if session_matches_employee(session, employee_id, employee_name, telegram_user_id)
            ]

        if not preliminary_sessions and employee_status in {"working", "on_break"} and len(active_people) == 1:
            preliminary_sessions = [
                session for session in company_active_sessions
                if clean(session.get("session_id")) not in consumed_session_ids
            ]

        for session in preliminary_sessions:
            sid = clean(session.get("session_id"))
            if sid:
                consumed_session_ids.add(sid)

        shift_start = latest_shift_start_from_events(events)''',
1
)

# Add fallback after sessions query.
src = src.replace(
'''        sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            shift_start,
        )

        pause_intervals, current_pause_started = pause_intervals_from_events(''',
'''        sessions = await reference_sessions_for_employee(
            db,
            company_id,
            employee_id,
            employee_name,
            telegram_user_id,
            shift_start,
        )

        if not sessions and preliminary_sessions:
            sessions = preliminary_sessions

        pause_intervals, current_pause_started = pause_intervals_from_events(''',
1
)

# Replace summary tail to include cards.
tail_pattern = r'''    production_enabled = \{"production", "references"\}\.issubset\(modules\)

    return \{
        "ok": True,
        "company_id": company_id,
        "company": company,
        "language": "es",
        "module": "crm",
        "mode": "crm_core_with_adapters",
        "server_time": dt_text\(now_value\),
        "active_modules": sorted\(modules\),
        "summary": \{.*?
        "employees": rows,
    \}
'''

tail_replacement = r'''    production_enabled = {"production", "references"}.issubset(modules)

    summary = {
        "employees_total": len(rows),
        "active_now": sum(1 for row in rows if row["core"]["status"] == "working"),
        "on_break": sum(1 for row in rows if row["core"]["status"] == "on_break"),
        "out": sum(1 for row in rows if row["core"]["status"] not in {"working", "on_break"}),
        "production_adapter": production_enabled,
        "gps_adapter": "gps" in modules,
        "materials_adapter": "materials" in modules,
        "inventory_adapter": "inventory" in modules,
        "with_reference": sum(
            1
            for row in rows
            for adapter in row["adapters"]
            if adapter.get("code") == "production_references"
            for item in adapter.get("items", [])
            if item.get("is_active")
        ) if production_enabled else 0,
    }

    selected = await selected_card_codes(db, company_id, modules)
    cards = build_cards(summary, modules, selected)

    return {
        "ok": True,
        "company_id": company_id,
        "company": company,
        "language": "es",
        "module": "crm",
        "mode": "crm_core_with_adapters",
        "server_time": dt_text(now_value),
        "active_modules": sorted(modules),
        "summary": summary,
        "cards": cards,
        "employees": rows,
    }
'''

src2 = re.sub(tail_pattern, tail_replacement, src, flags=re.S)
if src2 == src and '"cards": cards' not in src:
    raise SystemExit("No pude reemplazar tail summary/snapshot")
src = src2

backend.write_text(src, encoding="utf-8")

# ---------------- CLIENT ----------------

js = client.read_text(encoding="utf-8-sig")

# Kpis now reads snapshot.cards.visible.
new_kpis = r'''  function crmCoreKpis(snapshot) {
    const cards = Array.isArray(snapshot?.cards?.visible) ? snapshot.cards.visible : [];

    if (!cards.length) return `<div class="client-muted">Sin tarjetas configuradas.</div>`;

    return `
      <div style="display:flex;flex-wrap:wrap;gap:10px">
        ${cards.map((card) => `
          <div style="min-width:130px;padding:10px 12px;border-radius:14px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.11)">
            <div style="font-size:11px;opacity:.72;text-transform:uppercase;letter-spacing:.08em">${h(card.label)}</div>
            <strong style="display:block;margin-top:5px;font-size:20px;line-height:1">${h(card.value)}</strong>
          </div>
        `).join("")}
      </div>
    `;
  }

  function crmCoreCardsConfig(snapshot) {
    const catalog = Array.isArray(snapshot?.cards?.catalog) ? snapshot.cards.catalog : [];
    const available = catalog.filter((card) => card.available);

    if (!available.length) return "";

    return `
      <section class="client-panel" data-crm-card-config-panel style="display:none">
        <div class="client-section-kicker">Configuración</div>
        <h2>Tarjetas visibles</h2>
        <p class="client-muted">Selecciona hasta 6 tarjetas para este CRM. Se guardan por empresa.</p>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:12px">
          ${available.map((card) => `
            <label style="display:flex;align-items:center;gap:10px;padding:12px;border-radius:14px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)">
              <input type="checkbox" data-crm-card-code="${h(card.code)}" ${card.selected ? "checked" : ""}>
              <span>${h(card.label)}</span>
            </label>
          `).join("")}
        </div>
        <div class="client-actions" style="margin-top:14px">
          <button class="client-btn client-btn-primary" type="button" data-crm-save-cards>Guardar tarjetas</button>
        </div>
      </section>
    `;
  }

'''

js2 = re.sub(
    r"  function crmCoreKpis\(summary\) \{.*?\n  function crmCoreTimeRows",
    new_kpis + "  function crmCoreTimeRows",
    js,
    flags=re.S,
)
if js2 == js and "crmCoreCardsConfig" not in js:
    raise SystemExit("No pude reemplazar crmCoreKpis")
js = js2

# save function before render.
save_fn = r'''
  async function saveCrmCoreCards() {
    const checked = Array.from(document.querySelectorAll("[data-crm-card-code]:checked"))
      .map((node) => node.dataset.crmCardCode)
      .filter(Boolean)
      .slice(0, 6);

    await api(`/crm-core-v1/companies/${state.companyId}/cards`, {
      method: "PUT",
      body: JSON.stringify({ cards: checked }),
    });

    await renderCrmCoreModule();
  }

'''

if "saveCrmCoreCards" not in js:
    js = js.replace("  async function renderCrmCoreModule() {", save_fn + "  async function renderCrmCoreModule() {", 1)

js = js.replace("${crmCoreKpis(snapshot?.summary || {})}", "${crmCoreKpis(snapshot || {})}")

js = js.replace(
'''                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn client-btn-primary" type="button" data-crm-core-refresh>Actualizar</button>''',
'''                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
                <button class="client-btn" type="button" data-crm-config-cards>Tarjetas</button>
                <button class="client-btn client-btn-primary" type="button" data-crm-core-refresh>Actualizar</button>''',
1
)

js = js.replace(
'''            <section class="client-panel">
              <div class="client-section-kicker">Colaboradores</div>''',
'''            ${crmCoreCardsConfig(snapshot || {})}

            <section class="client-panel">
              <div class="client-section-kicker">Colaboradores</div>''',
1
)

# Add event handlers.
js = js.replace(
'''      const refresh = event.target.closest("[data-crm-core-refresh]");
      if (refresh) {
        event.preventDefault();
        await renderCrmCoreModule();
      }
    }, true);''',
'''      const refresh = event.target.closest("[data-crm-core-refresh]");
      if (refresh) {
        event.preventDefault();
        await renderCrmCoreModule();
        return;
      }

      const config = event.target.closest("[data-crm-config-cards]");
      if (config) {
        event.preventDefault();
        const panel = document.querySelector("[data-crm-card-config-panel]");
        if (panel) panel.style.display = panel.style.display === "none" ? "block" : "none";
        return;
      }

      const save = event.target.closest("[data-crm-save-cards]");
      if (save) {
        event.preventDefault();
        await saveCrmCoreCards();
      }
    }, true);''',
1
)

js = js.replace("await renderCrmLiveModule();", "await renderCrmCoreModule();")
js = js.replace("await renderCrmModule();", "await renderCrmCoreModule();")

client.write_text(js, encoding="utf-8")

print("CRM_PROD_CARDS_01_COMPACT_OK")
