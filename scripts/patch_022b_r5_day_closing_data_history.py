from pathlib import Path
import re

client_path = Path("app/web/client_day_closing.js")
endpoint_path = Path("app/api/v1/endpoints/day_closing_safe.py")
router_path = Path("app/api/v1/router.py")

endpoint_path.write_text(r'''
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_load(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    try:
        return json.loads(str(value))
    except Exception:
        return {}


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS clonexa_day_closures_v2 (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            closure_date text NOT NULL,
            start_time text NOT NULL,
            end_time text NOT NULL,
            responsible text NULL,
            notes text NULL,
            status text NOT NULL DEFAULT 'generated',
            summary_json text NOT NULL DEFAULT '{}',
            source_modules text NOT NULL DEFAULT '[]',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_clonexa_day_closures_v2_company_date
        ON clonexa_day_closures_v2 (company_id, closure_date, created_at DESC)
    """))

    await db.commit()


@router.post("/companies/{company_id}/closures")
async def save_closure(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)

    closure_date = _clean(payload.get("date") or payload.get("closure_date"))
    start_time = _clean(payload.get("start_time") or "07:00")[:5]
    end_time = _clean(payload.get("end_time") or "18:00")[:5]

    if not closure_date:
        raise HTTPException(status_code=422, detail="Fecha inválida.")
    if ":" not in start_time:
        raise HTTPException(status_code=422, detail="Hora inicio inválida.")
    if ":" not in end_time:
        raise HTTPException(status_code=422, detail="Hora fin inválida.")

    closure_id = str(uuid4())

    summary = payload.get("summary") or {}
    source_modules = payload.get("source_modules") or []
    responsible = _clean(payload.get("responsible"))
    notes = _clean(payload.get("notes"))
    status = _clean(payload.get("status") or "generated")

    try:
        await db.execute(
            text("""
                INSERT INTO clonexa_day_closures_v2 (
                    id,
                    company_id,
                    closure_date,
                    start_time,
                    end_time,
                    responsible,
                    notes,
                    status,
                    summary_json,
                    source_modules,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :closure_date,
                    :start_time,
                    :end_time,
                    :responsible,
                    :notes,
                    :status,
                    :summary_json,
                    :source_modules,
                    now(),
                    now()
                )
            """),
            {
                "id": closure_id,
                "company_id": company_id,
                "closure_date": closure_date,
                "start_time": start_time,
                "end_time": end_time,
                "responsible": responsible,
                "notes": notes,
                "status": status,
                "summary_json": json.dumps(summary, ensure_ascii=False),
                "source_modules": json.dumps(source_modules, ensure_ascii=False),
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"save_closure_failed: {type(exc).__name__}: {exc}")

    return {
        "id": closure_id,
        "company_id": company_id,
        "date": closure_date,
        "start_time": start_time,
        "end_time": end_time,
        "status": status,
        "saved_at": datetime.utcnow().isoformat() + "Z",
    }


@router.get("/companies/{company_id}/closures")
async def list_closures(
    company_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    await _ensure_storage(db)

    limit = max(1, min(int(limit or 20), 100))

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                closure_date,
                start_time,
                end_time,
                responsible,
                notes,
                status,
                summary_json,
                source_modules,
                created_at::text AS created_at,
                updated_at::text AS updated_at
            FROM clonexa_day_closures_v2
            WHERE company_id = :company_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"company_id": company_id, "limit": limit},
    )

    rows = []
    for row in result.mappings().all():
        item = dict(row)
        item["date"] = item.pop("closure_date", "")
        item["summary"] = _json_load(item.pop("summary_json", "{}"))
        item["source_modules"] = _json_load(item.get("source_modules", "[]"))
        rows.append(item)

    return rows
''', encoding="utf-8")

js = client_path.read_text(encoding="utf-8-sig")

# 1) Fix de fecha/hora tolerante
js = re.sub(
r'''function eventMinutes\(row\) \{.*?\n  \}''',
r'''function parseEventDate(row) {
    const raw = valueDate(row);
    if (!raw) return null;

    const direct = new Date(raw);
    if (!Number.isNaN(direct.getTime())) return direct;

    const s = String(raw).trim();

    let m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4}),?\s+(\d{1,2}):(\d{2})/);
    if (m) {
      let year = Number(m[3]);
      if (year < 100) year += 2000;
      return new Date(year, Number(m[2]) - 1, Number(m[1]), Number(m[4]), Number(m[5]));
    }

    m = s.match(/^(\d{4})-(\d{2})-(\d{2}).*?(\d{2}):(\d{2})/);
    if (m) {
      return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
    }

    return null;
  }

  function ymd(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, "0");
    const d = String(dateObj.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function eventMinutes(row) {
    const parsed = parseEventDate(row);
    if (!parsed) return null;
    return parsed.getHours() * 60 + parsed.getMinutes();
  }''',
js,
flags=re.DOTALL
)

js = re.sub(
r'''function inShift\(row, date, start, end\) \{.*?\n  \}''',
r'''function inShift(row, date, start, end) {
    const parsed = parseEventDate(row);

    if (!parsed) return true;

    if (ymd(parsed) !== date) return false;

    const m = parsed.getHours() * 60 + parsed.getMinutes();
    return m >= minutesFromTime(start) && m <= minutesFromTime(end);
  }''',
js,
flags=re.DOTALL
)

# 2) Mejorar fmt
js = re.sub(
r'''function fmt\(value\) \{.*?\n  \}''',
r'''function fmt(value) {
    if (!value) return "—";
    const parsed = parseEventDate({ created_at: value });
    if (parsed) return parsed.toLocaleString();
    return String(value);
  }''',
js,
flags=re.DOTALL
)

# 3) Insertar historial de cierres guardados
insert_functions = r'''

  async function loadSavedClosures() {
    const target = document.querySelector("[data-day-saved-closures]");
    if (!target) return;

    const companyId = companyIdFromUrl();
    const rows = await safeApi(`/day-closing-safe/companies/${encodeURIComponent(companyId)}/closures?limit=12`) || [];

    if (!Array.isArray(rows) || !rows.length) {
      target.innerHTML = `
        <section class="client-panel">
          <div class="client-eyebrow">HISTORIAL DE CIERRES</div>
          <h2>Cierres guardados</h2>
          <p class="client-muted">Aún no hay cierres guardados para esta empresa.</p>
        </section>
      `;
      return;
    }

    target.innerHTML = `
      <section class="client-panel">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start">
          <div>
            <div class="client-eyebrow">HISTORIAL DE CIERRES</div>
            <h2>Cierres guardados</h2>
            <p class="client-muted">Aquí el dueño ve los cierres guardados por jornada.</p>
          </div>
          <span class="client-badge">${rows.length} cierres</span>
        </div>

        <div class="client-table-wrap" style="margin-top:16px">
          <table class="client-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Jornada</th>
                <th>Responsable</th>
                <th>Eventos</th>
                <th>Personas</th>
                <th>Materiales</th>
                <th>Observaciones</th>
                <th>Guardado</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((row) => {
                const summary = row.summary || {};
                const metrics = summary.metrics || {};
                return `
                  <tr>
                    <td>${h(row.date || "")}</td>
                    <td>${h(row.start_time || "")} - ${h(row.end_time || "")}</td>
                    <td>${h(row.responsible || "—")}</td>
                    <td>${h(n(metrics.events))}</td>
                    <td>${h(n(metrics.people))}</td>
                    <td>${h(n(metrics.materials))}</td>
                    <td>${h(row.notes || "—")}</td>
                    <td>${h(row.created_at || "")}</td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }
'''

js = js.replace(
"  document.addEventListener(\"click\", async (event) => {",
insert_functions + "\n  document.addEventListener(\"click\", async (event) => {"
)

# 4) Agregar contenedor de historial después del reporte
js = js.replace(
"            <div data-day-report></div>",
"            <div data-day-report></div>\n            <div data-day-saved-closures></div>"
)

# 5) Cargar historial al renderizar y después de guardar
js = js.replace(
"    await generateReport();",
"    await generateReport();\n    await loadSavedClosures();",
1
)

js = js.replace(
"      showNotice(`${t(\"saved\")} ID: ${response.id}`);",
"      showNotice(`${t(\"saved\")} ID: ${response.id}`);\n      await loadSavedClosures();"
)

client_path.write_text(js, encoding="utf-8")

router = router_path.read_text(encoding="utf-8-sig")
if "day_closing_safe_router" not in router:
    router += '''

# CLONEXA safe day closing save router
from app.api.v1.endpoints import day_closing_safe as day_closing_safe_router
api_router.include_router(day_closing_safe_router.router, prefix="/day-closing-safe", tags=["day_closing_safe"])
'''
router_path.write_text(router, encoding="utf-8")

print("PATCH_OK: 022B-R5 Day Closing data parser + saved history installed")
