from pathlib import Path
import re

router_path = Path("app/api/v1/router.py")
payroll_path = Path("app/api/v1/endpoints/payroll.py")
client_path = Path("app/web/client.js")

# =========================================================
# 1) NEW CENTRAL COMPANY SETTINGS ENDPOINT
# =========================================================

settings_endpoint = Path("app/api/v1/endpoints/company_settings_v1.py")
settings_endpoint.write_text(r'''from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

DEFAULT_SETTINGS = {
    "payroll": {
        "ordinary_hours_limit": None,
        "pause_policy": "exclude",
    },
    "payroll_cuts": {
        "allow_close": True,
        "allow_export": True,
        "allow_archive": True,
    },
}


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_hours(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit must be numeric")

    if number <= 0:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit must be greater than zero")

    if number > 744:
        raise HTTPException(status_code=400, detail="ordinary_hours_limit too high")

    return round(number, 2)


def merge_settings(current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = json.loads(json.dumps(DEFAULT_SETTINGS))

    if isinstance(current, dict):
        for key, value in current.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key].update(value)
            else:
                base[key] = value

    if isinstance(incoming, dict):
        payroll = incoming.get("payroll")
        if isinstance(payroll, dict):
            if "ordinary_hours_limit" in payroll:
                base["payroll"]["ordinary_hours_limit"] = normalize_hours(payroll.get("ordinary_hours_limit"))
            if "pause_policy" in payroll:
                base["payroll"]["pause_policy"] = "exclude"

        cuts = incoming.get("payroll_cuts")
        if isinstance(cuts, dict):
            for field in ["allow_close", "allow_export", "allow_archive"]:
                if field in cuts:
                    base["payroll_cuts"][field] = bool(cuts.get(field))

    base["payroll"]["pause_policy"] = "exclude"
    return base


async def ensure_company_settings_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_settings (
            company_id text PRIMARY KEY,
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))
    await db.commit()


async def read_settings_row(db: AsyncSession, company_id: str) -> dict[str, Any]:
    await ensure_company_settings_storage(db)

    result = await db.execute(
        text("""
            SELECT settings_json, updated_at
            FROM company_settings
            WHERE company_id = :company_id
            LIMIT 1
        """),
        {"company_id": company_id},
    )

    row = result.mappings().first()

    if not row:
        settings = merge_settings(None, None)

        await db.execute(
            text("""
                INSERT INTO company_settings (company_id, settings_json, created_at, updated_at)
                VALUES (:company_id, CAST(:settings AS jsonb), now(), now())
                ON CONFLICT (company_id) DO NOTHING
            """),
            {
                "company_id": company_id,
                "settings": json.dumps(settings),
            },
        )
        await db.commit()

        return {
            "company_id": company_id,
            "settings": settings,
            "updated_at": None,
        }

    raw = row.get("settings_json") or {}

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}

    return {
        "company_id": company_id,
        "settings": merge_settings(raw, None),
        "updated_at": row.get("updated_at").isoformat() if isinstance(row.get("updated_at"), datetime) else row.get("updated_at"),
    }


@router.get("/companies/{company_id}")
async def get_company_settings(
    company_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    data = await read_settings_row(db, company_id)
    return {
        "ok": True,
        **data,
    }


@router.put("/companies/{company_id}")
async def put_company_settings(
    company_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    current = await read_settings_row(db, company_id)
    settings = merge_settings(current.get("settings"), payload)

    await db.execute(
        text("""
            INSERT INTO company_settings (company_id, settings_json, created_at, updated_at)
            VALUES (:company_id, CAST(:settings AS jsonb), now(), now())
            ON CONFLICT (company_id)
            DO UPDATE SET settings_json = EXCLUDED.settings_json, updated_at = now()
        """),
        {
            "company_id": company_id,
            "settings": json.dumps(settings),
        },
    )
    await db.commit()

    fresh = await read_settings_row(db, company_id)

    return {
        "ok": True,
        **fresh,
    }
''', encoding="utf-8")

# =========================================================
# 2) ROUTER
# =========================================================

router = router_path.read_text(encoding="utf-8-sig")

if "company_settings_v1_router" not in router:
    router += '''

# CLONEXA Company Settings V1 router
from app.api.v1.endpoints import company_settings_v1 as company_settings_v1_router
api_router.include_router(company_settings_v1_router.router, prefix="/company-settings-v1", tags=["company_settings_v1"])
'''

router_path.write_text(router, encoding="utf-8")

# =========================================================
# 3) PAYROLL READS CENTRAL CONFIG
# =========================================================

payroll = payroll_path.read_text(encoding="utf-8-sig")

if "import json" not in payroll:
    payroll = payroll.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nimport json\n", 1)

helper = r'''

# CLONEXA CORE_PAYROLL_CONFIG_01
def _cx_payroll_number(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(str(value).replace(",", "."))
    except Exception:
        return float(default)


def _cx_payroll_money(value) -> float:
    return round(_cx_payroll_number(value, 0.0), 2)


async def _cx_ensure_company_settings_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_settings (
            company_id text PRIMARY KEY,
            settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))


async def _cx_company_payroll_rule(db: AsyncSession, company_id) -> dict:
    await _cx_ensure_company_settings_storage(db)

    result = await db.execute(
        text("""
            SELECT settings_json
            FROM company_settings
            WHERE company_id = :company_id
            LIMIT 1
        """),
        {"company_id": str(company_id)},
    )

    row = result.mappings().first()
    settings = {}

    if row:
        raw = row.get("settings_json") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        if isinstance(raw, dict):
            settings = raw

    payroll_settings = settings.get("payroll") if isinstance(settings.get("payroll"), dict) else {}
    hours_limit = payroll_settings.get("ordinary_hours_limit")

    if hours_limit is None or hours_limit == "":
        return {
            "enabled": False,
            "source": "legacy_payroll_calculation",
            "label": "Regla actual del sistema",
            "ordinary_hours_limit": None,
            "ordinary_minutes_limit": None,
            "pause_policy": "exclude",
        }

    hours = _cx_payroll_number(hours_limit, 0.0)

    if hours <= 0:
        return {
            "enabled": False,
            "source": "invalid_company_settings",
            "label": "Configuración inválida: total de horas ordinarias no válido",
            "ordinary_hours_limit": None,
            "ordinary_minutes_limit": None,
            "pause_policy": "exclude",
        }

    minutes = int(round(hours * 60))

    return {
        "enabled": True,
        "source": "company_settings",
        "label": f"Hasta {hours:g}h ordinarias; después extra. Pausas excluidas.",
        "ordinary_hours_limit": hours,
        "ordinary_minutes_limit": minutes,
        "pause_policy": "exclude",
    }


async def _cx_apply_payroll_config_rule(db: AsyncSession, company_id, snapshot: dict) -> dict:
    rule = await _cx_company_payroll_rule(db, company_id)

    snapshot["payroll_rule"] = rule

    if not rule.get("enabled"):
        totals = snapshot.get("totals") if isinstance(snapshot.get("totals"), dict) else {}
        totals["payroll_rule"] = rule
        snapshot["totals"] = totals
        return snapshot

    limit_minutes = int(rule.get("ordinary_minutes_limit") or 0)
    rows = snapshot.get("rows") if isinstance(snapshot.get("rows"), list) else []

    total_regular = 0
    total_extra = 0
    total_gross = 0.0
    total_discounts = 0.0
    total_net = 0.0

    for row in rows:
        current_regular = int(_cx_payroll_number(row.get("regular_minutes"), 0))
        current_extra = int(_cx_payroll_number(row.get("extra_minutes"), 0))
        effective_minutes = current_regular + current_extra

        regular_minutes = min(effective_minutes, limit_minutes)
        extra_minutes = max(effective_minutes - limit_minutes, 0)

        regular_rate = _cx_payroll_money(row.get("hourly_rate_regular"))
        extra_rate = _cx_payroll_money(row.get("hourly_rate_extra"))

        regular_amount = round((regular_minutes / 60.0) * regular_rate, 2)
        extra_amount = round((extra_minutes / 60.0) * extra_rate, 2)
        gross_amount = round(regular_amount + extra_amount, 2)

        discount_amount = _cx_payroll_money(
            row.get("discount_amount", row.get("deduction_amount", row.get("discounts", 0)))
        )
        net_amount = round(gross_amount - discount_amount, 2)

        row["regular_minutes"] = regular_minutes
        row["extra_minutes"] = extra_minutes
        row["regular_amount"] = regular_amount
        row["extra_amount"] = extra_amount
        row["gross_amount"] = gross_amount
        row["discount_amount"] = discount_amount
        row["net_amount"] = net_amount
        row["payroll_rule"] = rule

        total_regular += regular_minutes
        total_extra += extra_minutes
        total_gross += gross_amount
        total_discounts += discount_amount
        total_net += net_amount

    totals = snapshot.get("totals") if isinstance(snapshot.get("totals"), dict) else {}

    totals["regular_minutes"] = total_regular
    totals["extra_minutes"] = total_extra
    totals["gross_amount"] = round(total_gross, 2)
    totals["discount_amount"] = round(total_discounts, 2)
    totals["net_amount"] = round(total_net, 2)
    totals["payroll_rule"] = rule

    snapshot["rows"] = rows
    snapshot["totals"] = totals
    return snapshot

'''

if "CORE_PAYROLL_CONFIG_01" not in payroll:
    marker = "async def calculate_period_snapshot("
    if marker not in payroll:
        raise SystemExit("No encontré calculate_period_snapshot en payroll.py")
    payroll = payroll.replace(marker, helper + "\n" + marker, 1)

pattern = re.compile(
    r'''    return \{
        "period": \{
            "company_id": str\(company_id\),
            "period_start": period_start\.isoformat\(\),
            "period_end": period_end\.isoformat\(\),
            "status": "open",
        \},
        "rows": serializable_rows,
        "totals": serializable_totals,
    \}''',
    re.S,
)

replacement = '''    snapshot_payload = {
        "period": {
            "company_id": str(company_id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "status": "open",
        },
        "rows": serializable_rows,
        "totals": serializable_totals,
    }

    snapshot_payload = await _cx_apply_payroll_config_rule(db, company_id, snapshot_payload)
    return snapshot_payload'''

payroll2, count = pattern.subn(replacement, payroll, count=1)

if count != 1 and "_cx_apply_payroll_config_rule(db, company_id, snapshot_payload)" not in payroll:
    raise SystemExit("No pude reemplazar return de calculate_period_snapshot.")

payroll = payroll2

payroll_path.write_text(payroll, encoding="utf-8")

# =========================================================
# 4) CLIENT UI CONFIG + PAYROLL RULE DISPLAY
# =========================================================

client = client_path.read_text(encoding="utf-8-sig")

settings_block = r'''
  /* CX_CORE_PAYROLL_CONFIG_01_START */
  function corePayrollConfigNumber(value) {
    const n = Number(String(value ?? "").replace(",", "."));
    return Number.isFinite(n) ? n : null;
  }

  function corePayrollRuleLabel(rule = null) {
    if (!rule || !rule.enabled) return "Regla actual del sistema";
    return rule.label || `Hasta ${rule.ordinary_hours_limit}h ordinarias; después extra. Pausas excluidas.`;
  }

  async function loadCompanySettingsV1() {
    return await api(`/company-settings-v1/companies/${encodeURIComponent(state.companyId)}`);
  }

  async function saveCompanyPayrollSettingsV1() {
    const hoursInput = document.querySelector("[data-core-payroll-hours-limit]");
    const hours = corePayrollConfigNumber(hoursInput?.value || "");

    if (!hours || hours <= 0) {
      alert("Ingresa un total de horas ordinarias mayor a cero.");
      return;
    }

    await api(`/company-settings-v1/companies/${encodeURIComponent(state.companyId)}`, {
      method: "PUT",
      body: JSON.stringify({
        payroll: {
          ordinary_hours_limit: hours,
          pause_policy: "exclude",
        },
        payroll_cuts: {
          allow_close: true,
          allow_export: true,
          allow_archive: true,
        },
      }),
    });

    await renderCoreSettingsModule();
  }

  function renderPayrollRuleCard(rule = null) {
    return `
      <section class="client-panel" style="padding:16px">
        <div class="client-eyebrow">Regla aplicada</div>
        <h2>Nómina</h2>
        <p class="client-muted">${h(corePayrollRuleLabel(rule))}</p>
      </section>
    `;
  }

  async function renderCoreSettingsModule() {
    const company = state.company || {};
    let data = { settings: {} };
    let loadError = "";

    try {
      data = await loadCompanySettingsV1();
    } catch (error) {
      loadError = error.message || "No se pudo cargar configuración.";
    }

    const settings = data.settings || {};
    const payroll = settings.payroll || {};
    const cuts = settings.payroll_cuts || {};

    $("app").innerHTML = `
      <main class="client-shell">
        <div class="client-layout">
          <aside class="client-sidebar">
            <div class="client-logo">${logo(company, normalizeBranding(state.branding || {}))}</div>
            <h2 class="client-company-name">${h(company.name || "Empresa")}</h2>
            <div class="client-muted">${h(company.slug || "tenant")}</div>
            <nav class="client-nav">${renderClientNav("core_settings")}</nav>
            <div class="client-footer-id"><strong>Tenant activo</strong><br>${h(state.companyId || "")}</div>
          </aside>

          <section class="client-main">
            <header class="client-hero">
              <div class="client-eyebrow">Núcleo</div>
              <h1 class="client-title">Configuración</h1>
              <p class="client-muted">Reglas centrales por empresa. Los módulos leen esta configuración; no se parcha por cliente.</p>
              <div class="client-actions">
                <button class="client-btn" type="button" data-client-back-dashboard>Volver</button>
              </div>
              <div id="coreSettingsNotice">${loadError ? `<div class="personal-toast error">${h(loadError)}</div>` : ""}</div>
            </header>

            <section class="client-panel">
              <div class="client-eyebrow">Nómina</div>
              <h2>Total de horas ordinarias</h2>
              <p class="client-muted">Hasta este total se calcula como hora ordinaria. A partir de ese total se calcula como hora extra. Las pausas no cuentan.</p>

              <div style="display:grid;grid-template-columns:minmax(220px,320px) auto;gap:12px;align-items:end;margin-top:16px">
                <label>
                  <span class="client-muted">Total horas ordinarias hasta</span>
                  <input
                    data-core-payroll-hours-limit
                    type="number"
                    min="0.01"
                    step="0.25"
                    value="${h(payroll.ordinary_hours_limit ?? "")}"
                    placeholder="Ej: 48"
                    style="width:100%;margin-top:7px;border:1px solid rgba(255,255,255,.16);background:rgba(0,0,0,.22);color:inherit;border-radius:14px;padding:13px;font-weight:900"
                  >
                </label>

                <button class="client-btn client-btn-primary" type="button" data-core-payroll-save>Guardar regla</button>
              </div>
            </section>

            <section class="client-panel">
              <div class="client-eyebrow">Cortes</div>
              <h2>Acciones permitidas</h2>
              <p class="client-muted">Estas acciones quedan disponibles para el flujo de cortes de nómina: cerrar corte, exportar y archivar sin borrar histórico.</p>

              <div class="client-kpi-grid">
                <div class="client-kpi"><span>Cerrar corte</span><strong>${cuts.allow_close === false ? "OFF" : "ON"}</strong></div>
                <div class="client-kpi"><span>Exportar corte</span><strong>${cuts.allow_export === false ? "OFF" : "ON"}</strong></div>
                <div class="client-kpi"><span>Archivar corte</span><strong>${cuts.allow_archive === false ? "OFF" : "ON"}</strong></div>
              </div>
            </section>
          </section>
        </div>
      </main>
    `;
  }

  if (!window.__cxCorePayrollConfig01Bound) {
    window.__cxCorePayrollConfig01Bound = true;

    document.addEventListener("click", async (event) => {
      const settingsTrigger = event.target.closest('[data-client-module="core_settings"], [data-client-module="settings"]');
      if (settingsTrigger) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        await renderCoreSettingsModule();
        return;
      }

      const savePayroll = event.target.closest("[data-core-payroll-save]");
      if (savePayroll) {
        event.preventDefault();
        await saveCompanyPayrollSettingsV1();
      }
    }, true);
  }
  /* CX_CORE_PAYROLL_CONFIG_01_END */

'''

if "CX_CORE_PAYROLL_CONFIG_01_START" not in client:
    marker = "  function renderClientNav("
    if marker not in client:
        raise SystemExit("No encontré renderClientNav")
    client = client.replace(marker, settings_block + "\n" + marker, 1)

# Add Configuración button to nav without making it a normal operational module card.
client = client.replace(
'''    return buttons.join("");
  }''',
'''    const settingsActive = activeClientModules().some((module) => ["core_settings", "settings", "core"].includes(String(module.code || "")));
    if (settingsActive) {
      buttons.push(`
        <button class="${activeCode === "core_settings" || activeCode === "settings" ? "active" : ""}" type="button" data-client-module="core_settings">
          Configuración
        </button>
      `);
    }

    return buttons.join("");
  }''',
1
)

# Preserve payroll rule from API response.
client = client.replace(
'''      return {
        rows,
        totals: payrollNormalizeTotals(payload.totals || {}, rows),
        period: payload.period || period,
        warning: payload.warning || "",
      };''',
'''      return {
        rows,
        totals: payrollNormalizeTotals(payload.totals || {}, rows),
        period: payload.period || period,
        warning: payload.warning || "",
        rule: payload.payroll_rule || payload?.totals?.payroll_rule || null,
      };''',
1
)

client = client.replace(
'''    let mode = "Periodo abierto";''',
'''    let mode = "Periodo abierto";
    let payrollRule = null;''',
1
)

client = client.replace(
'''      loadWarning = calculated.warning || "";''',
'''      loadWarning = calculated.warning || "";
      payrollRule = calculated.rule || null;''',
1
)

# Insert rule card once after summary cards.
client = client.replace(
'''              ${payrollSummaryCards(totals)}''',
'''              ${payrollSummaryCards(totals)}
              ${renderPayrollRuleCard(payrollRule)}''',
1
)

client_path.write_text(client, encoding="utf-8")

print("CORE_PAYROLL_CONFIG_01_OK")
