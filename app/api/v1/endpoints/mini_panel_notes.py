from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

try:
    from app.services.auth_service import decode_access_token
except Exception:  # pragma: no cover
    decode_access_token = None


router = APIRouter()

NOTES_ALIASES = {
    "notes",
    "notas",
    "nota",
    "notas_agenda",
    "notas_o_agenda",
    "recordatorio",
    "recordatorios",
    "reminder",
    "reminders",
    "calendar",
    "calendario",
}

PANEL_ALIASES = {
    "venta": "sales",
    "ventas": "sales",
    "sales": "sales",
    "store": "stores",
    "stores": "stores",
    "tienda": "stores",
    "tiendas": "stores",
    "inventory": "inventory",
    "inventario": "inventory",
    "logistics": "logistics",
    "logistica": "logistics",
    "field": "logistics",
    "call": "call_center",
    "call_center": "call_center",
    "callcenter": "call_center",
    "llamadas": "call_center",
    "external": "external",
    "externo": "external",
    "externos": "external",
}

VALID_TYPES = {"note", "reminder", "event"}
VALID_STATUS = {"active", "done", "archived"}

BOGOTA = ZoneInfo("America/Bogota")


class MiniPanelNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    note_date: date
    note_time: time
    note_type: str = "reminder"
    store_employee_id: str | None = Field(default=None, max_length=80)
    store_employee_name: str | None = Field(default=None, max_length=180)
    store_user_id: str | None = Field(default=None, max_length=80)
    store_slot_id: str | None = Field(default=None, max_length=80)
    store_slot_name: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("El titulo es obligatorio.")
        return clean

    @field_validator("note_type")
    @classmethod
    def _clean_type(cls, value: str) -> str:
        clean = str(value or "reminder").strip().lower()
        if clean not in VALID_TYPES:
            raise ValueError("Tipo invalido.")
        return clean


class MiniPanelNoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    note_date: date | None = None
    note_time: time | None = None
    note_type: str | None = None
    status: str | None = None

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("El titulo es obligatorio.")
        return clean

    @field_validator("note_type")
    @classmethod
    def _clean_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = str(value or "").strip().lower()
        if clean not in VALID_TYPES:
            raise ValueError("Tipo invalido.")
        return clean

    @field_validator("status")
    @classmethod
    def _clean_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = str(value or "").strip().lower()
        if clean not in VALID_STATUS:
            raise ValueError("Estado invalido.")
        return clean


def _database_url() -> str:
    raw = (
        os.getenv("DATABASE_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URI")
        or os.getenv("DB_URL")
        or ""
    ).strip()

    if raw:
        raw = raw.replace("postgresql+asyncpg://", "postgresql://")
        raw = raw.replace("postgres+asyncpg://", "postgresql://")
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://") :]
        return raw

    host = os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST") or "db"
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or "5432"
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or "clonexa"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or "clonexa"
    database = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "clonexa"
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _connect() -> asyncpg.Connection:
    try:
        return await asyncpg.connect(_database_url())
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No fue posible conectar a PostgreSQL: {exc}",
        )


def _norm(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    out = []
    last_sep = False
    for ch in text:
        if ch.isalnum():
            out.append(ch)
            last_sep = False
        elif not last_sep:
            out.append("_")
            last_sep = True
    return "".join(out).strip("_")


def _panel(value: str) -> str:
    normalized = _norm(value)
    return PANEL_ALIASES.get(normalized, normalized or "sales")


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}
    return {}


def _scheduled_at(note_date: date, note_time: time) -> datetime:
    return datetime.combine(note_date, note_time).replace(tzinfo=BOGOTA)


def _date_range(value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min).replace(tzinfo=BOGOTA)
    end = datetime.combine(value, time.max).replace(tzinfo=BOGOTA)
    return start, end


def _display_date(value: date) -> str:
    return f"{value.day:02d}/{value.month:02d}/{value.year}"


def _clean_text_023w(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _note_metadata_payload_023w(payload: Any) -> dict[str, Any]:
    actor = {
        "employee_id": _clean_text_023w(getattr(payload, "store_employee_id", ""), 80),
        "name": _clean_text_023w(getattr(payload, "store_employee_name", ""), 180),
        "user_id": _clean_text_023w(getattr(payload, "store_user_id", ""), 80),
        "store_id": _clean_text_023w(getattr(payload, "store_slot_id", ""), 80),
        "store_name": _clean_text_023w(getattr(payload, "store_slot_name", ""), 120),
    }
    actor = {key: value for key, value in actor.items() if value}
    return {"store_actor": actor} if actor else {}



# CLONEXA_022D_MINIPANEL_USER_SCOPE_START
def _scope_user_id_022d(access: dict[str, Any] | None) -> uuid.UUID | None:
    """Return user_id only for real Mini Panel sessions.

    /client calls without Authorization and must see consolidated company data.
    Mini Panel calls with token and must see only records created by that user.
    """
    if not isinstance(access, dict):
        return None
    if str(access.get("source") or "") == "client_universal":
        return None
    if access.get("mini_panel") is not True:
        return None
    raw_user_id = access.get("user_id") or access.get("sub") or access.get("id")
    if not raw_user_id:
        return None
    try:
        return uuid.UUID(str(raw_user_id))
    except Exception:
        return None
# CLONEXA_022D_MINIPANEL_USER_SCOPE_END

def _extract_token(authorization: str | None) -> str:
    raw = str(authorization or "").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token requerido.")
    if raw.lower().startswith("bearer "):
        return raw.split(" ", 1)[1].strip()
    return raw


async def _require_access(conn: asyncpg.Connection, company_id: uuid.UUID, authorization: str | None) -> dict[str, Any]:
    # CLONEXA_021D_UNIVERSAL_ACCESS_START
    # /client no maneja token de mini panel. Para módulos universales se permite
    # acceso operativo por company_id cuando la empresa existe. La habilitación real
    # del módulo se valida después en _require_*_enabled.
    if not str(authorization or "").strip():
        company_row = await conn.fetchrow(
            "SELECT id, name, slug FROM companies WHERE id = $1::uuid LIMIT 1",
            company_id,
        )
        if company_row:
            return {
                "company_id": str(company_row["id"]),
                "user_id": None,
                "full_name": "Panel principal",
                "email": None,
                "source": "client_universal",
            }
    # CLONEXA_021D_UNIVERSAL_ACCESS_END
    if decode_access_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Servicio de autenticacion no disponible.")

    token = _extract_token(authorization)
    payload = decode_access_token(token)

    raw_company = payload.get("company_id") or payload.get("tenant_id") or payload.get("company")
    if raw_company and str(raw_company) == str(company_id):
        return payload

    raw_user_id = payload.get("sub") or payload.get("user_id") or payload.get("id")
    if raw_user_id:
        try:
            user_uuid = uuid.UUID(str(raw_user_id))
        except Exception:
            user_uuid = None

        if user_uuid:
            row = await conn.fetchrow(
                """
                SELECT id, company_id, status, full_name, email
                FROM company_users
                WHERE id = $1::uuid
                  AND company_id = $2::uuid
                LIMIT 1
                """,
                user_uuid,
                company_id,
            )
            if row and str(row["status"]).lower() == "active":
                return {
                    **payload,
                    "company_id": str(row["company_id"]),
                    "user_id": str(row["id"]),
                    "full_name": row["full_name"],
                    "email": row["email"],
                }

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso no autorizado para esta empresa.")



# CLONEXA_021D_UNIVERSAL_ACCESS_START
async def _company_has_universal_notes_module_021d(conn: asyncpg.Connection, company_id: uuid.UUID) -> bool:
    rows = await conn.fetch(
        """
        SELECT m.code, m.name
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = $1::uuid
          AND cm.enabled = TRUE
        """,
        company_id,
    )

    for row in rows:
        code = _norm(row["code"])
        name = _norm(row["name"])
        if code in NOTES_ALIASES or name in NOTES_ALIASES:
            return True

    return False
# CLONEXA_021D_UNIVERSAL_ACCESS_END

async def _require_notes_enabled(conn: asyncpg.Connection, company_id: uuid.UUID, panel_type: str) -> None:
    # CLONEXA_021D_UNIVERSAL_ACCESS_START
    # Si el módulo está activo en el panel principal de la empresa, también queda
    # funcional en /client y disponible para mini paneles adaptables.
    if await _company_has_universal_notes_module_021d(conn, company_id):
        return
    # CLONEXA_021D_UNIVERSAL_ACCESS_END
    row = await conn.fetchrow(
        """
        SELECT cm.settings
        FROM company_modules cm
        JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = $1::uuid
          AND cm.enabled = TRUE
          AND (
            lower(m.code) = 'mini_panel'
            OR lower(m.name) LIKE '%mini%panel%'
            OR lower(m.name) LIKE '%creacion%mini%'
            OR lower(m.name) LIKE '%creaciÃ³n%mini%'
          )
        LIMIT 1
        """,
        company_id,
    )

    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Mini Panel no esta activo para esta empresa.")

    settings = _json(row["settings"])
    config = settings.get("mini_panel_modules") if isinstance(settings.get("mini_panel_modules"), dict) else settings
    panels = config.get("panels") if isinstance(config.get("panels"), dict) else {}
    selected = _panel(panel_type)

    panel = (
        panels.get(selected)
        or panels.get(f"{selected}s")
        or panels.get("store" if selected == "stores" else "")
        or {}
    )

    modules = panel.get("modules") if isinstance(panel.get("modules"), list) else []
    normalized = {_norm(item) for item in modules}
    if not (normalized & NOTES_ALIASES):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Notas no esta asignado a este mini panel.")


def _note_payload(row: asyncpg.Record) -> dict[str, Any]:
    scheduled = row["scheduled_at"]
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    local = scheduled.astimezone(BOGOTA)
    metadata = _json(row["metadata"])
    store_actor = metadata.get("store_actor") if isinstance(metadata.get("store_actor"), dict) else {}
    actor_label = str(store_actor.get("name") or "").strip()

    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "panel_type": row["panel_type"],
        "title": row["title"],
        "description": row["description"] or "",
        "note_type": row["note_type"],
        "status": row["status"],
        "note_date": local.date().isoformat(),
        "note_time": local.strftime("%H:%M"),
        "scheduled_at": local.isoformat(),
        "display_time": local.strftime("%H:%M"),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_label": actor_label or row["created_by_label"] or "",
        "metadata": metadata,
        "store_actor": store_actor,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


async def _summary_payload(conn: asyncpg.Connection, company_id: uuid.UUID, panel_type: str, selected_date: date, scope_user_id_022d: uuid.UUID | None = None) -> dict[str, Any]:
    start, end = _date_range(selected_date)
    count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM mini_panel_notes
        WHERE company_id = $1::uuid
          AND panel_type = $2
          AND status = 'active'
          AND scheduled_at BETWEEN $3 AND $4
          AND ($5::uuid IS NULL OR created_by = $5::uuid)
        """,
        company_id,
        _panel(panel_type),
        start,
        end,
        scope_user_id_022d,
    )

    next_rows = await conn.fetch(
        """
        SELECT *
        FROM mini_panel_notes
        WHERE company_id = $1::uuid
          AND panel_type = $2
          AND status = 'active'
          AND scheduled_at >= NOW()
          AND ($3::uuid IS NULL OR created_by = $3::uuid)
        ORDER BY scheduled_at ASC
        LIMIT 5
        """,
        company_id,
        _panel(panel_type),
        scope_user_id_022d,
    )
    upcoming = [_note_payload(row) for row in next_rows]
    next_note = upcoming[0] if upcoming else None

    count_int = int(count or 0)
    label = f"{_display_date(selected_date)} Â· {count_int} {'recordatorio' if count_int == 1 else 'recordatorios'}"
    next_label = "Sin proximos recordatorios"
    if next_note:
        next_label = f"Proximo: {next_note['note_date']} {next_note['display_time']} Â· {next_note['title']}"

    return {
        "date": selected_date.isoformat(),
        "count": count_int,
        "label": label,
        "next": next_note,
        "next_label": next_label,
        "upcoming": upcoming,
    }


@router.get("/companies/{company_id}/summary")
async def get_notes_summary(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    date_value: date | None = Query(default=None, alias="date"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    selected_date = date_value or datetime.now(BOGOTA).date()
    conn = await _connect()
    try:
        access_022d = await _require_access(conn, company_id, authorization)
        scope_user_id_022d = _scope_user_id_022d(access_022d)
        await _require_notes_enabled(conn, company_id, panel_type)
        return await _summary_payload(conn, company_id, panel_type, selected_date, scope_user_id_022d)
    finally:
        await conn.close()


@router.get("/companies/{company_id}")
async def list_notes(
    company_id: uuid.UUID,
    panel_type: str = Query("sales"),
    date_value: date | None = Query(default=None, alias="date"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    selected_date = date_value or datetime.now(BOGOTA).date()
    start, end = _date_range(selected_date)
    conn = await _connect()
    try:
        access_022d = await _require_access(conn, company_id, authorization)
        scope_user_id_022d = _scope_user_id_022d(access_022d)
        await _require_notes_enabled(conn, company_id, panel_type)

        day_rows = await conn.fetch(
            """
            SELECT *
            FROM mini_panel_notes
            WHERE company_id = $1::uuid
              AND panel_type = $2
              AND status <> 'archived'
              AND scheduled_at BETWEEN $3 AND $4
              AND ($5::uuid IS NULL OR created_by = $5::uuid)
            ORDER BY scheduled_at ASC, created_at ASC
            """,
            company_id,
            _panel(panel_type),
            start,
            end,
            scope_user_id_022d,
        )

        summary = await _summary_payload(conn, company_id, panel_type, selected_date, scope_user_id_022d)
        return {
            **summary,
            "items": [_note_payload(row) for row in day_rows],
        }
    finally:
        await conn.close()


@router.post("/companies/{company_id}", status_code=status.HTTP_201_CREATED)
async def create_note(
    company_id: uuid.UUID,
    payload: MiniPanelNoteCreate,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        user = await _require_access(conn, company_id, authorization)
        await _require_notes_enabled(conn, company_id, panel_type)

        scheduled = _scheduled_at(payload.note_date, payload.note_time)
        raw_user_id = user.get("user_id") or user.get("sub") or user.get("id")
        created_by = None
        try:
            created_by = uuid.UUID(str(raw_user_id)) if raw_user_id else None
        except Exception:
            created_by = None
        metadata = _note_metadata_payload_023w(payload)
        actor = metadata.get("store_actor") if isinstance(metadata.get("store_actor"), dict) else {}
        creator_label = str(actor.get("name") or user.get("full_name") or user.get("email") or "").strip()

        row = await conn.fetchrow(
            """
            INSERT INTO mini_panel_notes (
                company_id,
                panel_type,
                title,
                description,
                note_type,
                status,
                scheduled_at,
                created_by,
                created_by_label,
                metadata,
                created_at,
                updated_at
            )
            VALUES ($1::uuid, $2, $3, $4, $5, 'active', $6, $7::uuid, $8, $9::jsonb, NOW(), NOW())
            RETURNING *
            """,
            company_id,
            _panel(panel_type),
            payload.title,
            payload.description,
            payload.note_type,
            scheduled,
            created_by,
            creator_label,
            json.dumps(metadata, ensure_ascii=False),
        )
        return {"ok": True, "note": _note_payload(row)}
    finally:
        await conn.close()


@router.patch("/companies/{company_id}/{note_id}")
async def update_note(
    company_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: MiniPanelNoteUpdate,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        access_022d = await _require_access(conn, company_id, authorization)
        scope_user_id_022d = _scope_user_id_022d(access_022d)
        await _require_notes_enabled(conn, company_id, panel_type)

        current = await conn.fetchrow(
            """
            SELECT *
            FROM mini_panel_notes
            WHERE id = $1::uuid
              AND company_id = $2::uuid
              AND panel_type = $3
              AND ($4::uuid IS NULL OR created_by = $4::uuid)
            LIMIT 1
            """,
            note_id,
            company_id,
            _panel(panel_type),
            scope_user_id_022d,
        )
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota no encontrada.")

        next_date = payload.note_date or current["scheduled_at"].astimezone(BOGOTA).date()
        next_time = payload.note_time or current["scheduled_at"].astimezone(BOGOTA).time().replace(tzinfo=None)
        scheduled = _scheduled_at(next_date, next_time)

        status_value = payload.status if payload.status is not None else current["status"]
        completed_at = current["completed_at"]
        if status_value == "done" and completed_at is None:
            completed_at = datetime.now(timezone.utc)
        if status_value == "active":
            completed_at = None

        row = await conn.fetchrow(
            """
            UPDATE mini_panel_notes
            SET title = $4,
                description = $5,
                note_type = $6,
                status = $7,
                scheduled_at = $8,
                completed_at = $9,
                updated_at = NOW()
            WHERE id = $1::uuid
              AND company_id = $2::uuid
              AND panel_type = $3
              AND ($10::uuid IS NULL OR created_by = $10::uuid)
            RETURNING *
            """,
            note_id,
            company_id,
            _panel(panel_type),
            payload.title if payload.title is not None else current["title"],
            payload.description if payload.description is not None else current["description"],
            payload.note_type if payload.note_type is not None else current["note_type"],
            status_value,
            scheduled,
            completed_at,
            scope_user_id_022d,
        )
        return {"ok": True, "note": _note_payload(row)}
    finally:
        await conn.close()


@router.post("/companies/{company_id}/{note_id}/complete")
async def complete_note(
    company_id: uuid.UUID,
    note_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        access_022d = await _require_access(conn, company_id, authorization)
        scope_user_id_022d = _scope_user_id_022d(access_022d)
        await _require_notes_enabled(conn, company_id, panel_type)
        row = await conn.fetchrow(
            """
            UPDATE mini_panel_notes
            SET status = 'done',
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $1::uuid
              AND company_id = $2::uuid
              AND panel_type = $3
              AND status <> 'archived'
              AND ($4::uuid IS NULL OR created_by = $4::uuid)
            RETURNING *
            """,
            note_id,
            company_id,
            _panel(panel_type),
            scope_user_id_022d,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota no encontrada.")
        return {"ok": True, "note": _note_payload(row)}
    finally:
        await conn.close()


@router.delete("/companies/{company_id}/{note_id}")
async def archive_note(
    company_id: uuid.UUID,
    note_id: uuid.UUID,
    panel_type: str = Query("sales"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    conn = await _connect()
    try:
        access_022d = await _require_access(conn, company_id, authorization)
        scope_user_id_022d = _scope_user_id_022d(access_022d)
        await _require_notes_enabled(conn, company_id, panel_type)
        row = await conn.fetchrow(
            """
            UPDATE mini_panel_notes
            SET status = 'archived',
                updated_at = NOW()
            WHERE id = $1::uuid
              AND company_id = $2::uuid
              AND panel_type = $3
              AND ($4::uuid IS NULL OR created_by = $4::uuid)
            RETURNING *
            """,
            note_id,
            company_id,
            _panel(panel_type),
            scope_user_id_022d,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota no encontrada.")
        return {"ok": True, "note": _note_payload(row)}
    finally:
        await conn.close()
