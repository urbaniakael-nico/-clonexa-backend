from pathlib import Path
import re

path = Path("app/api/v1/endpoints/references_v1.py")
src = path.read_text(encoding="utf-8-sig")

if "REF_03A_REFERENCES_FLOW_ENGINE_SAFE" in src:
    print("REF_03A already applied")
    raise SystemExit(0)

append = r'''

# CLONEXA REF_03A_REFERENCES_FLOW_ENGINE_SAFE
async def ensure_reference_flow_storage(db: AsyncSession) -> None:
    await ensure_storage(db)

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_work_sessions (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz NULL,
            duration_minutes numeric NOT NULL DEFAULT 0,
            status text NOT NULL DEFAULT 'active',
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_work_sessions_company_employee_status
        ON reference_work_sessions (company_id, employee_id, status)
    """))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS reference_production_closures (
            id text PRIMARY KEY,
            company_id text NOT NULL,
            employee_id text NOT NULL,
            employee_name text NULL,
            telegram_user_id text NULL,
            reference_id text NULL,
            reference_name text NOT NULL,
            size text NOT NULL,
            quantity_finished integer NOT NULL DEFAULT 0,
            notes text NULL,
            closed_at timestamptz NOT NULL DEFAULT now(),
            source_channel text NOT NULL DEFAULT 'telegram',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_reference_production_closures_company_ref_size
        ON reference_production_closures (company_id, reference_name, size)
    """))

    await db.commit()


async def _reference_lookup(
    db: AsyncSession,
    *,
    company_id: str,
    reference_id: str | None = None,
    name: str | None = None,
    size: str | None = None,
) -> dict[str, Any] | None:
    await ensure_reference_flow_storage(db)

    params: dict[str, Any] = {"company_id": company_id}
    where = ["company_id = :company_id", "bot_active IS TRUE"]

    if clean(reference_id):
        where.append("id = :reference_id")
        params["reference_id"] = clean(reference_id)

    if clean(name):
        where.append("lower(name) = lower(:name)")
        params["name"] = clean(name)

    if clean(size):
        where.append("lower(size) = lower(:size)")
        params["size"] = clean(size)

    result = await db.execute(
        text(f"""
            SELECT id, company_id, name, size, initial_quantity, bot_active
            FROM product_references
            WHERE {" AND ".join(where)}
            ORDER BY name ASC, size ASC
            LIMIT 1
        """),
        params,
    )

    row = result.mappings().first()
    return dict(row) if row else None


async def _close_active_reference_session_sql(
    db: AsyncSession,
    *,
    company_id: str,
    employee_id: str,
    status: str,
) -> int:
    result = await db.execute(
        text("""
            UPDATE reference_work_sessions
            SET
                ended_at = now(),
                duration_minutes = GREATEST(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 0),
                status = :status,
                updated_at = now()
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
        """),
        {
            "company_id": company_id,
            "employee_id": employee_id,
            "status": status,
        },
    )
    return int(result.rowcount or 0)


@router.post("/companies/{company_id}/flow/start-reference")
async def flow_start_reference(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia activa para bot no encontrada.")

    session_id = str(uuid4())

    try:
        closed_previous = await _close_active_reference_session_sql(
            db,
            company_id=company_id,
            employee_id=employee_id,
            status="closed_by_new_start",
        )

        await db.execute(
            text("""
                INSERT INTO reference_work_sessions (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    started_at,
                    status,
                    source_channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    now(),
                    'active',
                    'telegram',
                    now(),
                    now()
                )
            """),
            {
                "id": session_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_start_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_session_started",
        "session_id": session_id,
        "closed_previous": closed_previous,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
    }


@router.post("/companies/{company_id}/flow/switch-reference")
async def flow_switch_reference(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia activa para bot no encontrada.")

    session_id = str(uuid4())

    try:
        closed_previous = await _close_active_reference_session_sql(
            db,
            company_id=company_id,
            employee_id=employee_id,
            status="switched",
        )

        await db.execute(
            text("""
                INSERT INTO reference_work_sessions (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    started_at,
                    status,
                    source_channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    now(),
                    'active',
                    'telegram',
                    now(),
                    now()
                )
            """),
            {
                "id": session_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_switch_reference_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_session_switched",
        "session_id": session_id,
        "closed_previous": closed_previous,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
    }


@router.post("/companies/{company_id}/flow/close-production")
async def flow_close_production(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    employee_id = clean(payload.get("employee_id"))
    employee_name = clean(payload.get("employee_name"))
    telegram_user_id = clean(payload.get("telegram_user_id"))
    reference_id = clean(payload.get("reference_id"))
    reference_name = clean(payload.get("reference_name") or payload.get("name"))
    size = clean(payload.get("size"))
    notes = clean(payload.get("notes"))
    quantity_finished = to_int(payload.get("quantity_finished"), 0)

    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id requerido.")

    if not size and not reference_id:
        raise HTTPException(status_code=422, detail="size requerido si no se envía reference_id.")

    ref = await _reference_lookup(
        db,
        company_id=company_id,
        reference_id=reference_id,
        name=reference_name,
        size=size,
    )

    if not ref:
        raise HTTPException(status_code=404, detail="Referencia/talla activa para bot no encontrada.")

    closure_id = str(uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO reference_production_closures (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    size,
                    quantity_finished,
                    notes,
                    closed_at,
                    source_channel,
                    created_at
                )
                VALUES (
                    :id,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    :size,
                    :quantity_finished,
                    :notes,
                    now(),
                    'telegram',
                    now()
                )
            """),
            {
                "id": closure_id,
                "company_id": company_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "telegram_user_id": telegram_user_id,
                "reference_id": clean(ref.get("id")),
                "reference_name": clean(ref.get("name")),
                "size": clean(ref.get("size")),
                "quantity_finished": quantity_finished,
                "notes": notes,
            },
        )

        await db.commit()

    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"flow_close_production_failed: {type(exc).__name__}: {exc}")

    return {
        "ok": True,
        "action": "reference_production_closed",
        "closure_id": closure_id,
        "company_id": company_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "telegram_user_id": telegram_user_id,
        "reference_id": clean(ref.get("id")),
        "reference_name": clean(ref.get("name")),
        "size": clean(ref.get("size")),
        "quantity_finished": quantity_finished,
    }


@router.get("/companies/{company_id}/flow/active-session")
async def flow_active_reference_session(
    company_id: str,
    employee_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_reference_flow_storage(db)
    await require_references_module(db, company_id)

    result = await db.execute(
        text("""
            SELECT
                id,
                company_id,
                employee_id,
                employee_name,
                telegram_user_id,
                reference_id,
                reference_name,
                started_at::text AS started_at,
                ended_at::text AS ended_at,
                duration_minutes,
                status,
                source_channel,
                created_at::text AS created_at,
                updated_at::text AS updated_at
            FROM reference_work_sessions
            WHERE company_id = :company_id
              AND employee_id = :employee_id
              AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {
            "company_id": company_id,
            "employee_id": clean(employee_id),
        },
    )

    row = result.mappings().first()

    return {
        "company_id": company_id,
        "employee_id": clean(employee_id),
        "active": bool(row),
        "session": dict(row) if row else None,
    }
'''

src = src.rstrip() + "\n" + append + "\n"
path.write_text(src, encoding="utf-8")

print("REF_03A_REFERENCES_FLOW_ENGINE_SAFE_OK")
