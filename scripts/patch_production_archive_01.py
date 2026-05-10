from pathlib import Path
import re

prod = Path("app/api/v1/endpoints/production_v1.py")
client = Path("app/web/client.js")

src = prod.read_text(encoding="utf-8-sig")

if "import json" not in src:
    src = src.replace("from __future__ import annotations\n", "from __future__ import annotations\n\nimport json\n", 1)

if "import uuid" not in src:
    src = src.replace("import json\n", "import json\nimport uuid\n", 1)

src = src.replace(
    "from fastapi import APIRouter, Depends, Query, Response",
    "from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response",
)

# 1) Storage: columnas de archivo + snapshots.
storage_marker = '    await db.execute(text("""\n        CREATE INDEX IF NOT EXISTS ix_reference_work_sessions_company_status'
archive_storage = r'''
    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_at timestamptz NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_by text NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archive_reason text NULL
    """))

    await db.execute(text("""
        ALTER TABLE product_references
        ADD COLUMN IF NOT EXISTS archived_snapshot_id text NULL
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS production_archive_snapshots (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            reference_id text NULL,
            reference_name text NULL,
            size text NULL,
            snapshot_type text NOT NULL DEFAULT 'reference_archive',
            date_from date NULL,
            date_to date NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_product_references_company_archived
        ON product_references (company_id, archived_at)
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_production_archive_snapshots_company_created
        ON production_archive_snapshots (company_id, created_at DESC)
    """))

'''
if "production_archive_snapshots" not in src:
    if storage_marker not in src:
        raise SystemExit("No encontré marker de ensure_storage para insertar archivo.")
    src = src.replace(storage_marker, archive_storage + storage_marker, 1)

# 2) Reemplazar reference_rows para soportar active/archived/all.
start = src.find("async def reference_rows(")
end = src.find("\n\nasync def closures_rows(", start)
if start == -1 or end == -1:
    raise SystemExit("No pude ubicar reference_rows")

new_reference_rows = r'''async def reference_rows(db: AsyncSession, company_id: str, view: str = "active") -> list[dict[str, Any]]:
    view = clean(view or "active").lower()
    if view not in {"active", "archived", "all"}:
        view = "active"

    where = ["pr.company_id::text = :company_id"]
    params: dict[str, Any] = {"company_id": company_id}

    if view == "active":
        where.append("pr.archived_at IS NULL")
    elif view == "archived":
        where.append("pr.archived_at IS NOT NULL")

    rows = await safe_rows(
        db,
        f"""
        SELECT
            pr.id,
            pr.name,
            pr.size,
            COALESCE(pr.initial_quantity, 0) AS initial_quantity,
            COALESCE(pr.bot_active, false) AS bot_active,
            pr.activation_date::text AS activation_date,
            pr.archived_at::text AS archived_at,
            COALESCE(pr.archived_by, '') AS archived_by,
            COALESCE(pr.archive_reason, '') AS archive_reason,
            COALESCE(pr.archived_snapshot_id, '') AS archived_snapshot_id,
            COALESCE((
                SELECT sum(c.quantity_finished)
                FROM reference_production_closures c
                WHERE c.company_id::text = :company_id
                  AND (
                    c.reference_id = pr.id
                    OR (
                        lower(COALESCE(c.reference_name, '')) = lower(COALESCE(pr.name, ''))
                        AND lower(COALESCE(c.size, '')) = lower(COALESCE(pr.size, ''))
                    )
                  )
            ), 0) AS finished_quantity
        FROM product_references pr
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE WHEN pr.archived_at IS NULL THEN 0 ELSE 1 END,
            pr.name ASC,
            pr.size ASC
        """,
        params,
    )

    output = []

    for row in rows:
        initial = intval(row.get("initial_quantity"))
        finished = intval(row.get("finished_quantity"))
        pending = max(initial - finished, 0)
        over_finished = max(finished - initial, 0)
        progress = round((finished / initial) * 100, 2) if initial > 0 else 0

        output.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "size": row.get("size"),
            "initial_quantity": initial,
            "finished_quantity": finished,
            "pending_quantity": pending,
            "over_finished_quantity": over_finished,
            "progress_percent": progress,
            "bot_active": bool(row.get("bot_active")),
            "activation_date": row.get("activation_date"),
            "archived": bool(row.get("archived_at")),
            "archived_at": row.get("archived_at"),
            "archived_by": row.get("archived_by"),
            "archive_reason": row.get("archive_reason"),
            "archived_snapshot_id": row.get("archived_snapshot_id"),
        })

    return output
'''
src = src[:start] + new_reference_rows + src[end:]

# 3) production_summary: agregar view y pasar a reference_rows.
src = src.replace(
    '''    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),''',
    '''    preset: str | None = Query("7d"),
    view: str | None = Query("active"),
    db: AsyncSession = Depends(get_db),''',
    1,
)

src = src.replace(
    '''    refs = await reference_rows(db, company_id)''',
    '''    refs = await reference_rows(db, company_id, view or "active")''',
    1,
)

# 4) Export CSV: soportar view y pasar al summary.
src = src.replace(
    '''    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        db=db,
    )''',
    '''    preset: str | None = Query("7d"),
    view: str | None = Query("active"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    data = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        view=view,
        db=db,
    )''',
    1,
)

# 5) Agregar endpoints de archivar/restaurar antes del export.csv.
archive_routes = r'''

@router.post("/companies/{company_id}/references/{reference_id}/archive")
async def production_archive_reference(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    reason = clean(payload.get("reason")) or "Archivado desde Producción"
    archived_by = clean(payload.get("archived_by")) or "client_panel"
    preset = clean(payload.get("preset")) or "7d"
    date_from = clean(payload.get("date_from")) or None
    date_to = clean(payload.get("date_to")) or None

    ref_rows = await safe_rows(
        db,
        """
        SELECT to_jsonb(pr) AS row
        FROM product_references pr
        WHERE pr.company_id::text = :company_id
          AND pr.id::text = :reference_id
        LIMIT 1
        """,
        {
            "company_id": company_id,
            "reference_id": reference_id,
        },
    )

    if not ref_rows or not isinstance(ref_rows[0].get("row"), dict):
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    ref = ref_rows[0]["row"]
    reference_name = clean(ref.get("name"))
    size = clean(ref.get("size"))

    snapshot_id = str(uuid.uuid4())

    # Snapshot antes de archivar. Usa view=all para no perder contexto.
    snapshot_payload = await production_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        view="all",
        db=db,
    )

    await db.execute(
        text("""
            INSERT INTO production_archive_snapshots (
                id,
                company_id,
                reference_id,
                reference_name,
                size,
                snapshot_type,
                date_from,
                date_to,
                payload,
                created_at
            )
            VALUES (
                :id,
                :company_id,
                :reference_id,
                :reference_name,
                :size,
                'reference_archive',
                CAST(:date_from AS date),
                CAST(:date_to AS date),
                CAST(:payload AS jsonb),
                now()
            )
        """),
        {
            "id": snapshot_id,
            "company_id": company_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
            "size": size,
            "date_from": snapshot_payload.get("date_from"),
            "date_to": snapshot_payload.get("date_to"),
            "payload": json.dumps(snapshot_payload, default=str),
        },
    )

    # Cierra sesiones activas de esta referencia para que no sigan corriendo.
    await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = COALESCE(ended_at, now()),
                status = CASE
                    WHEN lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL THEN 'closed'
                    ELSE status
                END,
                duration_minutes = CASE
                    WHEN ended_at IS NULL THEN GREATEST(
                        COALESCE(duration_minutes, 0),
                        CEIL(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0)::int
                    )
                    ELSE COALESCE(duration_minutes, 0)
                END,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND (
                    reference_id::text = :reference_id
                    OR lower(COALESCE(reference_name, '')) = lower(:reference_name)
              )
              AND (lower(COALESCE(status, '')) = 'active' OR ended_at IS NULL)
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "reference_name": reference_name,
        },
    )

    # Archivar = ocultar del panel operativo y apagar del bot.
    await db.execute(
        text("""
            UPDATE product_references
            SET
                bot_active = false,
                archived_at = now(),
                archived_by = :archived_by,
                archive_reason = :reason,
                archived_snapshot_id = :snapshot_id,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND id::text = :reference_id
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "archived_by": archived_by,
            "reason": reason,
            "snapshot_id": snapshot_id,
        },
    )

    await db.commit()

    return {
        "ok": True,
        "action": "reference_archived",
        "company_id": company_id,
        "reference_id": reference_id,
        "reference_name": reference_name,
        "size": size,
        "snapshot_id": snapshot_id,
        "panel_visible": False,
        "bot_active": False,
        "message": "Referencia archivada. No se borró información; quedó disponible en histórico/reportes.",
    }


@router.post("/companies/{company_id}/references/{reference_id}/restore")
async def production_restore_reference(
    company_id: str,
    reference_id: str,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    bot_active = bool(payload.get("bot_active", True))

    result = await db.execute(
        text("""
            UPDATE product_references
            SET
                archived_at = NULL,
                archived_by = NULL,
                archive_reason = NULL,
                archived_snapshot_id = NULL,
                bot_active = :bot_active,
                updated_at = now()
            WHERE company_id::text = :company_id
              AND id::text = :reference_id
            RETURNING id, name, size, bot_active
        """),
        {
            "company_id": company_id,
            "reference_id": reference_id,
            "bot_active": bot_active,
        },
    )

    row = result.mappings().first()
    if not row:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Referencia no encontrada.")

    await db.commit()

    return {
        "ok": True,
        "action": "reference_restored",
        "company_id": company_id,
        "reference_id": row["id"],
        "reference_name": row["name"],
        "size": row["size"],
        "bot_active": bool(row["bot_active"]),
        "panel_visible": True,
    }


@router.get("/companies/{company_id}/archive-snapshots")
async def production_archive_snapshots(
    company_id: str,
    limit: int = Query(100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_storage(db)

    rows = await safe_rows(
        db,
        """
        SELECT
            id,
            company_id,
            reference_id,
            reference_name,
            size,
            snapshot_type,
            date_from::text AS date_from,
            date_to::text AS date_to,
            created_at::text AS created_at
        FROM production_archive_snapshots
        WHERE company_id::text = :company_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        {
            "company_id": company_id,
            "limit": limit,
        },
    )

    return {
        "ok": True,
        "company_id": company_id,
        "items": rows,
    }
'''

if "production_archive_reference" not in src:
    marker = '@router.get("/companies/{company_id}/export.csv")'
    if marker not in src:
        raise SystemExit("No encontré export.csv para insertar rutas de archivo.")
    src = src.replace(marker, archive_routes + "\n" + marker, 1)

prod.write_text(src, encoding="utf-8")

# =========================
# FRONTEND
# =========================

js = client.read_text(encoding="utf-8-sig")

# Asegura que summary/export lleven view.
js = js.replace(
    "/summary?",
    '/summary?view=${encodeURIComponent(state.productionReferenceView || "active")}&'
)

js = js.replace(
    "/export.csv?",
    '/export.csv?view=${encodeURIComponent(state.productionReferenceView || "all")}&'
)

def replace_js_function_by_line(text: str, name: str, replacement: str) -> str:
    lines = text.splitlines(keepends=True)
    start_idx = None

    for i, line in enumerate(lines):
        if line.startswith(f"  function {name}("):
            start_idx = i
            break

    if start_idx is None:
        raise SystemExit(f"No encontré función JS {name}")

    end_idx = None
    for j in range(start_idx + 1, len(lines)):
        if lines[j].startswith("  function ") or lines[j].startswith("  async function "):
            end_idx = j
            break

    if end_idx is None:
        raise SystemExit(f"No encontré fin de función JS {name}")

    return "".join(lines[:start_idx]) + replacement + "\n" + "".join(lines[end_idx:])

new_references_table = r'''  function productionReferencesTable(rows) {
    const items = Array.isArray(rows) ? rows : [];
    const view = state.productionReferenceView || "active";

    const toolbar = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 14px;flex-wrap:wrap">
        <div class="client-muted">Panel operativo: activas. Histórico: archivadas/todas.</div>
        <label style="display:flex;align-items:center;gap:8px">
          <span class="client-muted">Vista</span>
          <select data-production-view-select style="padding:9px 12px;border-radius:12px;background:rgba(0,0,0,.22);color:inherit;border:1px solid rgba(255,255,255,.16)">
            <option value="active" ${view === "active" ? "selected" : ""}>Activas</option>
            <option value="archived" ${view === "archived" ? "selected" : ""}>Archivadas</option>
            <option value="all" ${view === "all" ? "selected" : ""}>Todas</option>
          </select>
        </label>
      </div>
    `;

    if (!items.length) {
      return `${toolbar}<div class="client-muted">Sin referencias en esta vista.</div>`;
    }

    return `
      ${toolbar}
      <div style="overflow:auto">
        <table class="client-table" style="width:100%;border-collapse:collapse">
          <thead>
            <tr>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Referencia</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Talla</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Inicial</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Terminada</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Pendiente</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Avance</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Estado</th>
              <th style="text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,.12)">Acción</th>
            </tr>
          </thead>
          <tbody>
            ${items.map((row) => {
              const archived = !!row.archived;
              return `
                <tr>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)"><strong>${h(row.name || "")}</strong></td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.size || "")}</td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.initial_quantity ?? 0)}</td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.finished_quantity ?? 0)}</td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.pending_quantity ?? 0)}</td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">${h(row.progress_percent ?? 0)}%</td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">
                    ${archived ? `<span style="padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.08)">Archivada</span>` : `<span style="padding:6px 10px;border-radius:999px;background:rgba(0,255,180,.12)">Activa</span>`}
                  </td>
                  <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,.08)">
                    ${archived
                      ? `<button class="client-btn" type="button" data-production-restore-reference="${h(row.id)}">Restaurar</button>`
                      : `<button class="client-btn client-btn-primary" type="button" data-production-archive-reference="${h(row.id)}" data-production-reference-name="${h(row.name || "")}">Exportar y archivar</button>`
                    }
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    `;
  }
'''

js = replace_js_function_by_line(js, "productionReferencesTable", new_references_table)

archive_js = r'''
  async function archiveProductionReference(referenceId, referenceName) {
    const confirmed = window.confirm(
      `Exportar y archivar "${referenceName || "esta referencia"}"?\n\nNo se borrará información. La referencia saldrá del panel operativo, se apagará del bot y quedará en histórico.`
    );

    if (!confirmed) return;

    await api(`/production-v1/companies/${state.companyId}/references/${encodeURIComponent(referenceId)}/archive`, {
      method: "POST",
      body: JSON.stringify({
        reason: "Exportada y archivada desde panel Producción",
        archived_by: "client_panel",
        preset: state.productionPreset || "7d",
        date_from: state.productionDateFrom || null,
        date_to: state.productionDateTo || null,
      }),
    });

    state.productionReferenceView = "active";
    await renderProductionModule();
  }

  async function restoreProductionReference(referenceId) {
    const confirmed = window.confirm("Restaurar referencia al panel operativo y al bot?");
    if (!confirmed) return;

    await api(`/production-v1/companies/${state.companyId}/references/${encodeURIComponent(referenceId)}/restore`, {
      method: "POST",
      body: JSON.stringify({ bot_active: true }),
    });

    state.productionReferenceView = "active";
    await renderProductionModule();
  }

'''

if "archiveProductionReference" not in js:
    marker = "  async function renderProductionModule()"
    if marker not in js:
        raise SystemExit("No encontré renderProductionModule para insertar helpers.")
    js = js.replace(marker, archive_js + marker, 1)

listener_js = r'''
  if (!window.__cxProductionArchive01Bound) {
    window.__cxProductionArchive01Bound = true;

    document.addEventListener("change", async (event) => {
      const viewSelect = event.target.closest("[data-production-view-select]");
      if (viewSelect) {
        state.productionReferenceView = viewSelect.value || "active";
        await renderProductionModule();
      }
    }, true);

    document.addEventListener("click", async (event) => {
      const archiveBtn = event.target.closest("[data-production-archive-reference]");
      if (archiveBtn) {
        event.preventDefault();
        await archiveProductionReference(
          archiveBtn.dataset.productionArchiveReference,
          archiveBtn.dataset.productionReferenceName || ""
        );
        return;
      }

      const restoreBtn = event.target.closest("[data-production-restore-reference]");
      if (restoreBtn) {
        event.preventDefault();
        await restoreProductionReference(restoreBtn.dataset.productionRestoreReference);
      }
    }, true);
  }

'''

if "__cxProductionArchive01Bound" not in js:
    marker = "  async function renderProductionModule()"
    js = js.replace(marker, listener_js + marker, 1)

client.write_text(js, encoding="utf-8")

print("PRODUCTION_ARCHIVE_01_OK")
