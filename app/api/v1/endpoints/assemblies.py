from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

EVENT_STATUSES = {"draft", "active", "closed", "archived"}
AGENDA_STATUSES = {"pending", "active", "done", "skipped"}
VOTE_STATUSES = {"draft", "open", "closed"}
QUESTION_STATUSES = {"pending", "answered", "archived"}
VOTE_TYPES = {"decision", "yes_no", "true_false", "multiple", "participants"}
ASSEMBLY_QR_MODES = {"voting", "vote", "votacion", "participantes", "participants", "assembly", "asamblea", "assemblies", "asambleas"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _json_param(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")


def _status(value: Any, allowed: set[str], fallback: str) -> str:
    clean = _clean(value, 40).lower().replace(" ", "_")
    return clean if clean in allowed else fallback


def _event_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "company_id": str(row["company_id"]),
        "title": row.get("title") or "",
        "description": row.get("description") or "",
        "status": row.get("status") or "draft",
        "starts_at": _iso(row.get("starts_at")),
        "ends_at": _iso(row.get("ends_at")),
        "quorum_total": int(row.get("quorum_total") or 0),
        "quorum_required_percent": float(row.get("quorum_required_percent") or 0),
        "identity_mode": row.get("identity_mode") or "qr",
        "settings": _json(row.get("settings"), {}),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _agenda_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "title": row.get("title") or "",
        "notes": row.get("notes") or "",
        "position": int(row.get("position") or 0),
        "status": row.get("status") or "pending",
        "created_at": _iso(row.get("created_at")),
    }


def _question_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "vote_id": str(row.get("vote_id")) if row.get("vote_id") else "",
        "participant_name": row.get("participant_name") or "",
        "qr_key": row.get("qr_key") or "",
        "question": row.get("question") or "",
        "status": row.get("status") or "pending",
        "created_at": _iso(row.get("created_at")),
    }


def _attendee_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "attendee_name": row.get("attendee_name") or "",
        "document_ref": row.get("document_ref") or "",
        "qr_key": row.get("qr_key") or "",
        "present": bool(row.get("present")),
        "metadata": _json(row.get("metadata"), {}),
        "checked_in_at": _iso(row.get("checked_in_at")),
    }


def _normalized_kind(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
        .replace(" ", "_")
        .replace("-", "_")
    )


def _is_assembly_qr_mode(value: Any) -> bool:
    return _normalized_kind(value) in ASSEMBLY_QR_MODES


def _assembly_type_label(value: Any) -> str:
    kind = _normalized_kind(value)
    labels = {
        "housing": "Propietarios / conjuntos",
        "propietarios": "Propietarios / conjuntos",
        "vivienda": "Propietarios / conjuntos",
        "conjuntos": "Propietarios / conjuntos",
        "business": "Decisiones empresariales",
        "empresarial": "Decisiones empresariales",
        "empresa": "Decisiones empresariales",
        "sports": "Deportiva",
        "deportiva": "Deportiva",
        "deporte": "Deportiva",
        "generic": "General",
        "general": "General",
    }
    return labels.get(kind, "General")


def _assembly_field_schema(settings: dict[str, Any] | None) -> list[dict[str, Any]]:
    settings = settings if isinstance(settings, dict) else {}
    custom_fields = settings.get("fields")
    if isinstance(custom_fields, list) and custom_fields:
        fields = []
        for index, raw in enumerate(custom_fields[:12], start=1):
            if not isinstance(raw, dict):
                continue
            key = _clean(raw.get("key") or f"campo_{index}", 80).lower().replace(" ", "_")
            label = _clean(raw.get("label") or raw.get("name") or key, 120)
            if not key or not label:
                continue
            fields.append({
                "key": key,
                "label": label,
                "type": _clean(raw.get("type") or "text", 30) or "text",
                "required": bool(raw.get("required")),
                "placeholder": _clean(raw.get("placeholder") or "", 160),
            })
        if fields:
            has_name = any(field["key"] == "attendee_name" for field in fields)
            return ([{"key": "attendee_name", "label": "Nombre completo", "type": "text", "required": True, "placeholder": "Ej: Ana Perez"}] if not has_name else []) + fields

    kind = _normalized_kind(settings.get("assembly_type") or settings.get("type") or "generic")
    if kind in {"housing", "propietarios", "vivienda", "conjuntos"}:
        return [
            {"key": "attendee_name", "label": "Nombre completo", "type": "text", "required": True, "placeholder": "Ej: Ana Perez"},
            {"key": "document_ref", "label": "Documento", "type": "text", "required": True, "placeholder": "Cedula o NIT"},
            {"key": "unit", "label": "Casa / apto / unidad", "type": "text", "required": True, "placeholder": "Ej: Torre 2 - Apto 504"},
            {"key": "coefficient", "label": "Coeficiente", "type": "number", "required": False, "placeholder": "Opcional"},
            {"key": "role", "label": "Calidad", "type": "text", "required": False, "placeholder": "Propietario, apoderado, residente"},
        ]
    if kind in {"business", "empresarial", "empresa"}:
        return [
            {"key": "attendee_name", "label": "Nombre completo", "type": "text", "required": True, "placeholder": "Ej: Laura Gomez"},
            {"key": "document_ref", "label": "Documento / ID", "type": "text", "required": True, "placeholder": "Cedula, NIT o ID interno"},
            {"key": "company_area", "label": "Area / empresa", "type": "text", "required": True, "placeholder": "Ej: Operaciones"},
            {"key": "position", "label": "Cargo / rol", "type": "text", "required": False, "placeholder": "Ej: Socio, gerente, delegado"},
            {"key": "email", "label": "Correo", "type": "email", "required": False, "placeholder": "correo@empresa.com"},
        ]
    if kind in {"sports", "deportiva", "deporte"}:
        return [
            {"key": "attendee_name", "label": "Nombre completo", "type": "text", "required": True, "placeholder": "Ej: Carlos Rios"},
            {"key": "document_ref", "label": "Documento / carnet", "type": "text", "required": True, "placeholder": "Cedula o carnet"},
            {"key": "team", "label": "Club / equipo", "type": "text", "required": True, "placeholder": "Ej: Club Norte"},
            {"key": "category", "label": "Categoria", "type": "text", "required": False, "placeholder": "Ej: Senior, juvenil, femenino"},
            {"key": "phone", "label": "Telefono", "type": "tel", "required": False, "placeholder": "Numero de contacto"},
        ]
    return [
        {"key": "attendee_name", "label": "Nombre completo", "type": "text", "required": True, "placeholder": "Ej: Maria Perez"},
        {"key": "document_ref", "label": "Documento / ID", "type": "text", "required": True, "placeholder": "Identificacion"},
        {"key": "phone", "label": "Telefono", "type": "tel", "required": False, "placeholder": "Numero de contacto"},
        {"key": "email", "label": "Correo", "type": "email", "required": False, "placeholder": "correo@dominio.com"},
        {"key": "notes", "label": "Observacion", "type": "textarea", "required": False, "placeholder": "Dato adicional para la asamblea"},
    ]


class AssemblyEventIn(BaseModel):
    title: str = Field(default="Asamblea", max_length=180)
    description: str | None = Field(default="", max_length=1500)
    status: str = Field(default="active", max_length=40)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    quorum_total: int = Field(default=0, ge=0, le=100000)
    quorum_required_percent: float = Field(default=50, ge=0, le=100)
    identity_mode: str = Field(default="qr", max_length=40)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = _clean(value, 180)
        if not title:
            raise ValueError("title_required")
        return title


class AssemblyAgendaIn(BaseModel):
    title: str = Field(..., max_length=220)
    notes: str | None = Field(default="", max_length=1200)
    position: int = Field(default=0, ge=0, le=999)
    status: str = Field(default="pending", max_length=40)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = _clean(value, 220)
        if not title:
            raise ValueError("agenda_title_required")
        return title


class AssemblyVoteIn(BaseModel):
    title: str = Field(..., max_length=220)
    vote_type: str = Field(default="decision", max_length=40)
    options: list[str | dict[str, Any]] = Field(default_factory=list)
    status: str = Field(default="open", max_length=40)
    agenda_id: uuid.UUID | None = None
    opens_at: datetime | None = None
    closes_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = _clean(value, 220)
        if not title:
            raise ValueError("vote_title_required")
        return title


class AssemblyAttendeeIn(BaseModel):
    attendee_name: str = Field(..., max_length=180)
    document_ref: str | None = Field(default="", max_length=120)
    qr_key: str | None = Field(default="", max_length=120)
    present: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attendee_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = _clean(value, 180)
        if not name:
            raise ValueError("attendee_name_required")
        return name


class AssemblyQuestionIn(BaseModel):
    vote_id: uuid.UUID | None = None
    participant_name: str | None = Field(default="", max_length=180)
    qr_key: str | None = Field(default="", max_length=120)
    question: str = Field(..., max_length=300)
    status: str = Field(default="pending", max_length=40)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        question = _clean(value, 300)
        if not question:
            raise ValueError("question_required")
        return question


class AssemblyQuestionUpdateIn(BaseModel):
    status: str = Field(default="pending", max_length=40)


class AssemblyVoteResponseIn(BaseModel):
    qr_key: str | None = Field(default="", max_length=120)
    voter_name: str | None = Field(default="", max_length=180)
    choice_key: str = Field(..., max_length=120)
    choice_label: str | None = Field(default="", max_length=180)

    @field_validator("choice_key")
    @classmethod
    def clean_choice(cls, value: str) -> str:
        choice = _clean(value, 120)
        if not choice:
            raise ValueError("choice_required")
        return choice


async def _ensure_storage(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_events (
                id UUID PRIMARY KEY,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                status VARCHAR(40) NOT NULL DEFAULT 'active',
                starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ends_at TIMESTAMPTZ NULL,
                quorum_total INTEGER NOT NULL DEFAULT 0,
                quorum_required_percent NUMERIC(5,2) NOT NULL DEFAULT 50,
                identity_mode VARCHAR(40) NOT NULL DEFAULT 'qr',
                settings JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_events_company_status ON assembly_events(company_id, status, created_at DESC);"))

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_agenda_items (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES assembly_events(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(220) NOT NULL,
                notes TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(40) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_agenda_event ON assembly_agenda_items(event_id, position, created_at);"))

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_attendees (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES assembly_events(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                attendee_name VARCHAR(180) NOT NULL,
                document_ref VARCHAR(120) NOT NULL DEFAULT '',
                qr_key VARCHAR(120) NOT NULL DEFAULT '',
                present BOOLEAN NOT NULL DEFAULT TRUE,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("ALTER TABLE assembly_attendees ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_attendees_event ON assembly_attendees(event_id, present, checked_in_at DESC);"))

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_votes (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES assembly_events(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                agenda_id UUID NULL REFERENCES assembly_agenda_items(id) ON DELETE SET NULL,
                title VARCHAR(220) NOT NULL,
                vote_type VARCHAR(40) NOT NULL DEFAULT 'yes_no',
                options JSONB NOT NULL DEFAULT '[]'::jsonb,
                status VARCHAR(40) NOT NULL DEFAULT 'open',
                opens_at TIMESTAMPTZ NULL,
                closes_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_votes_event ON assembly_votes(event_id, status, created_at DESC);"))

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_vote_responses (
                id UUID PRIMARY KEY,
                vote_id UUID NOT NULL REFERENCES assembly_votes(id) ON DELETE CASCADE,
                event_id UUID NOT NULL REFERENCES assembly_events(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                qr_key VARCHAR(120) NOT NULL DEFAULT '',
                voter_name VARCHAR(180) NOT NULL DEFAULT '',
                choice_key VARCHAR(120) NOT NULL,
                choice_label VARCHAR(180) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_vote_responses_vote ON assembly_vote_responses(vote_id, choice_key);"))

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS assembly_questions (
                id UUID PRIMARY KEY,
                event_id UUID NOT NULL REFERENCES assembly_events(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                vote_id UUID NULL REFERENCES assembly_votes(id) ON DELETE CASCADE,
                participant_name VARCHAR(180) NOT NULL DEFAULT '',
                qr_key VARCHAR(120) NOT NULL DEFAULT '',
                question TEXT NOT NULL,
                status VARCHAR(40) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(text("ALTER TABLE assembly_questions ADD COLUMN IF NOT EXISTS vote_id UUID NULL REFERENCES assembly_votes(id) ON DELETE CASCADE;"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_questions_event ON assembly_questions(event_id, status, created_at DESC);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_questions_vote ON assembly_questions(vote_id, qr_key);"))


async def _company_exists(db: AsyncSession, company_id: uuid.UUID) -> bool:
    result = await db.execute(text("SELECT id FROM companies WHERE id = :company_id LIMIT 1"), {"company_id": str(company_id)})
    return result.first() is not None


async def _require_company(db: AsyncSession, company_id: uuid.UUID) -> None:
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company_not_found")


async def _get_event_row(db: AsyncSession, company_id: uuid.UUID, event_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text("SELECT * FROM assembly_events WHERE id = :event_id AND company_id = :company_id LIMIT 1"),
        {"event_id": str(event_id), "company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assembly_event_not_found")
    return dict(row)


async def _active_event_row(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any] | None:
    result = await db.execute(
        text(
            """
            SELECT *
            FROM assembly_events
            WHERE company_id = :company_id
              AND status IN ('active', 'draft', 'closed')
            ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 WHEN 'closed' THEN 2 ELSE 3 END, created_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


def _vote_options(vote_type: str, raw_options: list[Any] | None = None) -> list[dict[str, str]]:
    vote_type = _status(vote_type, VOTE_TYPES, "decision")
    if vote_type == "decision":
        return [
            {"key": "favor", "label": "A favor"},
            {"key": "against", "label": "En desacuerdo"},
            {"key": "abstain", "label": "No participa"},
        ]
    if vote_type == "yes_no":
        return [{"key": "yes", "label": "Si"}, {"key": "no", "label": "No"}]
    if vote_type == "true_false":
        return [{"key": "true", "label": "Verdadero"}, {"key": "false", "label": "Falso"}]
    options: list[dict[str, str]] = []
    for index, raw in enumerate(raw_options or [], start=1):
        if isinstance(raw, dict):
            label = _clean(raw.get("label") or raw.get("name") or raw.get("value") or "", 180)
            key = _clean(raw.get("key") or label or f"opcion_{index}", 120).lower().replace(" ", "_")
        else:
            label = _clean(raw, 180)
            key = _clean(label or f"opcion_{index}", 120).lower().replace(" ", "_")
        if label:
            options.append({"key": key or f"opcion_{index}", "label": label})
    if not options:
        options = [{"key": "opcion_1", "label": "Opcion 1"}, {"key": "opcion_2", "label": "Opcion 2"}]
    return options[:5]


async def _qr_config(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT cm.enabled, cm.settings, m.code
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = :company_id
              AND m.code IN ('qr', 'mesa_qr', 'mesas_qr', 'qr_mesas', 'hospitality_qr', 'voting_qr')
            ORDER BY cm.enabled DESC, cm.updated_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    if not row:
        return {"active": False, "mode": "", "count": 0, "max_capacity": 0, "base_url": ""}
    settings = _json(row["settings"], {})
    raw = settings.get("qr_config") if isinstance(settings, dict) else {}
    raw = raw if isinstance(raw, dict) else settings
    max_capacity = int(raw.get("max_capacity") or raw.get("capacity") or raw.get("limit") or raw.get("count") or 0)
    count = int(raw.get("table_count") or raw.get("count") or max_capacity or 0)
    return {
        "active": bool(row["enabled"]),
        "module_code": row["code"] or "qr",
        "mode": raw.get("mode") or "hospitality",
        "count": count,
        "max_capacity": max_capacity,
        "base_url": raw.get("base_url") or raw.get("public_base_url") or "",
    }


async def _event_summary_payload(db: AsyncSession, company_id: uuid.UUID, event_row: dict[str, Any] | None = None, full: bool = False) -> dict[str, Any]:
    if event_row is None:
        event_row = await _active_event_row(db, company_id)

    if not event_row:
        return {
            "ok": True,
            "company_id": str(company_id),
            "event": None,
            "summary": {"attendees": 0, "present": 0, "quorum_percent": 0, "agenda": 0, "votes": 0, "questions": 0, "responses": 0},
            "agenda": [],
            "attendees": [],
            "votes": [],
            "questions": [],
            "qr": await _qr_config(db, company_id),
        }

    event_id = str(event_row["id"])
    row_limit = 5000 if full else 80
    counts = await db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM assembly_attendees WHERE event_id = :event_id AND COALESCE(metadata->>'manager_role', '') = '') AS attendees,
              (SELECT COUNT(*) FROM assembly_attendees WHERE event_id = :event_id AND present IS TRUE AND COALESCE(metadata->>'manager_role', '') = '') AS present,
              (SELECT COUNT(*) FROM assembly_agenda_items WHERE event_id = :event_id) AS agenda,
              (SELECT COUNT(*) FROM assembly_votes WHERE event_id = :event_id) AS votes,
              (SELECT COUNT(*) FROM assembly_questions WHERE event_id = :event_id) AS questions,
              (SELECT COUNT(*) FROM assembly_vote_responses WHERE event_id = :event_id) AS responses
            """
        ),
        {"event_id": event_id},
    )
    c = dict(counts.mappings().first() or {})
    quorum_total = int(event_row.get("quorum_total") or 0)
    present = int(c.get("present") or 0)
    quorum_percent = round((present / quorum_total) * 100, 1) if quorum_total > 0 else 0

    agenda_rows = await db.execute(
        text("SELECT * FROM assembly_agenda_items WHERE event_id = :event_id ORDER BY position ASC, created_at ASC"),
        {"event_id": event_id},
    )
    attendees_rows = await db.execute(
        text("SELECT * FROM assembly_attendees WHERE event_id = :event_id ORDER BY checked_in_at DESC LIMIT :limit"),
        {"event_id": event_id, "limit": row_limit},
    )
    questions_rows = await db.execute(
        text("SELECT * FROM assembly_questions WHERE event_id = :event_id ORDER BY created_at DESC LIMIT :limit"),
        {"event_id": event_id, "limit": row_limit},
    )
    vote_rows = await db.execute(
        text("SELECT * FROM assembly_votes WHERE event_id = :event_id ORDER BY created_at ASC"),
        {"event_id": event_id},
    )

    votes = []
    for row in vote_rows.mappings().all():
        vote = dict(row)
        result = await db.execute(
            text(
                """
                SELECT choice_key, COALESCE(NULLIF(MAX(choice_label), ''), choice_key) AS choice_label, COUNT(*) AS total
                FROM assembly_vote_responses
                WHERE vote_id = :vote_id
                GROUP BY choice_key
                ORDER BY total DESC, choice_key ASC
                """
            ),
            {"vote_id": str(vote["id"])},
        )
        tally = {item["choice_key"]: int(item["total"] or 0) for item in result.mappings().all()}
        total = sum(tally.values())
        options = _json(vote.get("options"), [])
        option_payload = []
        for option in options:
            key = _clean(option.get("key") if isinstance(option, dict) else option, 120)
            label = _clean(option.get("label") if isinstance(option, dict) else option, 180) or key
            count = tally.get(key, 0)
            option_payload.append({"key": key, "label": label, "count": count, "percent": round((count / total) * 100, 1) if total else 0})
        votes.append(
            {
                "id": str(vote["id"]),
                "title": vote.get("title") or "",
                "vote_type": vote.get("vote_type") or "yes_no",
                "status": vote.get("status") or "open",
                "options": option_payload,
                "responses": total,
                "created_at": _iso(vote.get("created_at")),
                "opens_at": _iso(vote.get("opens_at")),
                "closes_at": _iso(vote.get("closes_at")),
            }
        )

    return {
        "ok": True,
        "company_id": str(company_id),
        "event": _event_payload(event_row),
        "summary": {
            "attendees": int(c.get("attendees") or 0),
            "present": present,
            "quorum_percent": quorum_percent,
            "agenda": int(c.get("agenda") or 0),
            "votes": int(c.get("votes") or 0),
            "questions": int(c.get("questions") or 0),
            "responses": int(c.get("responses") or 0),
        },
        "agenda": [_agenda_payload(dict(row)) for row in agenda_rows.mappings().all()],
        "attendees": [_attendee_payload(dict(row)) for row in attendees_rows.mappings().all()],
        "votes": votes,
        "questions": [_question_payload(dict(row)) for row in questions_rows.mappings().all()],
        "qr": await _qr_config(db, company_id),
    }


def _safe(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def _is_manager_attendee(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else _json(row.get("metadata"), {})
    return bool(metadata.get("manager_role"))


def _report_stat(label: str, value: Any) -> str:
    return f"<div class='stat'><span>{_safe(label)}</span><strong>{_safe(value)}</strong></div>"


def _report_vote_html(vote: dict[str, Any]) -> str:
    options = vote.get("options") if isinstance(vote.get("options"), list) else []
    rows = []
    for option in options:
        percent = max(0, min(100, float(option.get("percent") or 0)))
        rows.append(
            "<div class='vote-option'>"
            f"<div><b>{_safe(option.get('label'))}</b><em>{_safe(option.get('count') or 0)} respuesta(s) - {_safe(option.get('percent') or 0)}%</em></div>"
            f"<i><span style='width:{percent}%'></span></i>"
            "</div>"
        )
    return (
        "<article class='block'>"
        f"<h3>{_safe(vote.get('title') or 'Votacion')}</h3>"
        f"<p>{_safe(vote.get('status') or 'open')} - {_safe(vote.get('responses') or 0)} respuesta(s)</p>"
        f"{''.join(rows) if rows else '<p>Sin respuestas.</p>'}"
        "</article>"
    )


def _report_attendee_html(row: dict[str, Any], include_sensitive: bool = True) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    role = metadata.get("role_label") or metadata.get("manager_role") or metadata.get("role") or ""
    details = []
    if include_sensitive and row.get("document_ref"):
        details.append(f"Documento: {_safe(row.get('document_ref'))}")
    if include_sensitive and row.get("qr_key"):
        details.append(f"QR: {_safe(row.get('qr_key'))}")
    if role:
        details.append(f"Rol: {_safe(role)}")
    return (
        "<tr>"
        f"<td>{_safe(row.get('attendee_name') or 'Participante')}</td>"
        f"<td>{'Presente' if row.get('present') else 'Ausente'}</td>"
        f"<td>{' | '.join(details)}</td>"
        "</tr>"
    )


def _assembly_report_html(payload: dict[str, Any], mode: str = "basic") -> str:
    mode = _status(mode, {"complete", "basic", "votes"}, "basic")
    event = payload.get("event") or {}
    summary = payload.get("summary") or {}
    settings = event.get("settings") if isinstance(event.get("settings"), dict) else {}
    attendees = payload.get("attendees") if isinstance(payload.get("attendees"), list) else []
    managers = [row for row in attendees if _is_manager_attendee(row)]
    participants = [row for row in attendees if not _is_manager_attendee(row)]
    questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    answered_questions = [row for row in questions if str(row.get("status") or "").lower() == "answered"]
    votes = payload.get("votes") if isinstance(payload.get("votes"), list) else []
    title = event.get("title") or "Asamblea"
    basic = mode == "basic"
    votes_only = mode == "votes"
    sensitive = mode == "complete"

    attendee_table = ""
    if sensitive and not votes_only:
        attendee_rows = "".join(_report_attendee_html(row, True) for row in participants) or "<tr><td colspan='3'>Sin asistentes registrados.</td></tr>"
        manager_rows = "".join(_report_attendee_html(row, True) for row in managers) or "<tr><td colspan='3'>Sin gestores registrados.</td></tr>"
        attendee_table = (
            "<section class='section'><h2>Gestores de asamblea</h2><table><tbody>"
            f"{manager_rows}</tbody></table></section>"
            "<section class='section'><h2>Asistencia completa</h2><table><tbody>"
            f"{attendee_rows}</tbody></table></section>"
        )

    question_rows = ""
    if not votes_only:
        public_questions = answered_questions if basic else questions
        question_rows = "".join(
            "<article class='question'>"
            f"<h3>{_safe(row.get('question'))}</h3>"
            f"<p>{'Estado: ' + _safe(row.get('status')) if sensitive else 'Pregunta respondida en asamblea'}</p>"
            f"{'<small>Solicita: ' + _safe(row.get('participant_name') or row.get('qr_key') or 'Participante') + '</small>' if sensitive else ''}"
            "</article>"
            for row in public_questions
        ) or "<p>Sin preguntas seleccionadas para el acta.</p>"

    vote_html = "".join(_report_vote_html(vote) for vote in votes) or "<p>Sin votaciones registradas.</p>"
    notes = settings.get("minutes") or ""
    mode_label = {"complete": "Acta completa", "basic": "Acta publica basica", "votes": "Reporte de votaciones"}.get(mode, "Acta publica")

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_safe(mode_label)} - {_safe(title)}</title>
  <style>
    *{{box-sizing:border-box}} body{{margin:0;background:#f7f7fb;color:#111827;font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.35}}
    .page{{max-width:1100px;margin:0 auto;padding:34px}} .hero{{background:#111827;color:white;border-radius:22px;padding:26px;margin-bottom:18px}}
    .eyebrow{{letter-spacing:.14em;text-transform:uppercase;color:#9ae6b4;font-size:12px;font-weight:900}} h1{{font-size:42px;margin:8px 0 4px}} h2{{font-size:22px;margin:0 0 12px}} h3{{margin:0 0 6px}}
    .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}} .stat{{border:1px solid #d1d5db;border-radius:14px;padding:14px;background:white}}
    .stat span{{display:block;color:#6b7280;font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:900}} .stat strong{{display:block;font-size:24px;margin-top:6px}}
    .section,.block,.question{{border:1px solid #d1d5db;border-radius:16px;background:white;padding:16px;margin:14px 0}} .block p,.question p{{margin:0;color:#4b5563;font-weight:700}}
    table{{width:100%;border-collapse:collapse}} td,th{{border-bottom:1px solid #e5e7eb;padding:10px;text-align:left;vertical-align:top}} th{{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#6b7280}}
    .vote-option{{display:grid;gap:7px;margin:11px 0}} .vote-option div{{display:flex;justify-content:space-between;gap:16px}} .vote-option em{{font-style:normal;color:#4b5563;font-weight:800}}
    .vote-option i{{display:block;height:10px;border-radius:999px;background:#e5e7eb;overflow:hidden}} .vote-option span{{display:block;height:100%;background:linear-gradient(90deg,#0ea5e9,#22c55e)}}
    .actions{{display:flex;gap:10px;margin:18px 0}} button{{border:0;border-radius:999px;background:#111827;color:white;font-weight:900;padding:12px 18px;cursor:pointer}}
    @media print{{.actions{{display:none}} body{{background:white}} .page{{padding:0}} .hero,.section,.block,.question,.stat{{break-inside:avoid}}}}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">{_safe(mode_label)}</div>
      <h1>{_safe(title)}</h1>
      <p>{_safe(event.get('description') or '')}</p>
      <p>Estado: {_safe(event.get('status') or 'closed')} | Generado desde CLONEXA</p>
    </section>
    <div class="actions"><button onclick="window.print()">Imprimir / guardar PDF</button></div>
    <section class="grid">
      {_report_stat('Participantes', summary.get('present') or 0)}
      {_report_stat('Quorum', str(summary.get('quorum_percent') or 0) + '%')}
      {_report_stat('Votaciones', summary.get('votes') or 0)}
      {_report_stat('Respuestas', summary.get('responses') or 0)}
    </section>
    {attendee_table}
    <section class="section">
      <h2>Resultados de votaciones</h2>
      {vote_html}
    </section>
    {'' if votes_only else f"<section class='section'><h2>Preguntas y respuestas seleccionadas</h2>{question_rows}</section>"}
    {'' if votes_only else f"<section class='section'><h2>Observaciones y decisiones finales</h2><p>{_safe(notes)}</p></section>"}
  </main>
</body>
</html>"""


@router.get("/companies/{company_id}/summary")
async def assembly_summary(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _ensure_storage(db)
    await _require_company(db, company_id)
    return await _event_summary_payload(db, company_id)


@router.get("/companies/{company_id}/public")
async def assembly_public_context(
    company_id: uuid.UUID,
    participant: str = Query(default="", max_length=120),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _require_company(db, company_id)
    full = await _event_summary_payload(db, company_id)
    qr = full.get("qr") or await _qr_config(db, company_id)
    event_row = await _active_event_row(db, company_id)
    event = _event_payload(event_row) if event_row else None
    settings = event.get("settings") if isinstance(event, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    fields = _assembly_field_schema(settings)
    qr_mode = qr.get("mode") or ""
    participant_key = _clean(participant, 120)
    attendee = None
    if event_row and participant_key:
        attendee_result = await db.execute(
            text(
                """
                SELECT *
                FROM assembly_attendees
                WHERE event_id = :event_id
                  AND qr_key = :qr_key
                ORDER BY checked_in_at DESC
                LIMIT 1
                """
            ),
            {"event_id": str(event_row["id"]), "qr_key": participant_key},
        )
        attendee_row = attendee_result.mappings().first()
        attendee = _attendee_payload(dict(attendee_row)) if attendee_row else None

    participant_responses: dict[str, Any] = {}
    participant_questions: dict[str, Any] = {}
    if event_row and participant_key:
        response_result = await db.execute(
            text(
                """
                SELECT vote_id, qr_key, voter_name, choice_key, choice_label, created_at
                FROM assembly_vote_responses
                WHERE event_id = :event_id
                  AND qr_key = :qr_key
                ORDER BY created_at DESC
                """
            ),
            {"event_id": str(event_row["id"]), "qr_key": participant_key},
        )
        for row in response_result.mappings().all():
            participant_responses[str(row["vote_id"])] = {
                "vote_id": str(row["vote_id"]),
                "qr_key": row.get("qr_key") or "",
                "voter_name": row.get("voter_name") or "",
                "choice_key": row.get("choice_key") or "",
                "choice_label": row.get("choice_label") or "",
                "created_at": _iso(row.get("created_at")),
            }
        question_result = await db.execute(
            text(
                """
                SELECT *
                FROM assembly_questions
                WHERE event_id = :event_id
                  AND qr_key = :qr_key
                  AND vote_id IS NOT NULL
                ORDER BY created_at DESC
                """
            ),
            {"event_id": str(event_row["id"]), "qr_key": participant_key},
        )
        for row in question_result.mappings().all():
            question = _question_payload(dict(row))
            participant_questions[question["vote_id"]] = question

    return {
        "ok": True,
        "company_id": str(company_id),
        "assembly_mode": _is_assembly_qr_mode(qr_mode),
        "participant_label": participant_key,
        "qr": qr,
        "event": event,
        "assembly_type": settings.get("assembly_type") or "generic",
        "assembly_type_label": _assembly_type_label(settings.get("assembly_type") or "generic"),
        "fields": fields,
        "attendee": attendee,
        "summary": full.get("summary") or {},
        "votes": full.get("votes") or [],
        "questions": full.get("questions") or [],
        "participant_responses": participant_responses,
        "participant_questions": participant_questions,
    }


@router.get("/companies/{company_id}/events/{event_id}/report", response_class=HTMLResponse)
async def assembly_event_report(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    mode: str = Query(default="basic", max_length=40),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await _ensure_storage(db)
    event_row = await _get_event_row(db, company_id, event_id)
    payload = await _event_summary_payload(db, company_id, event_row, full=True)
    return HTMLResponse(_assembly_report_html(payload, mode))


@router.post("/companies/{company_id}/events", status_code=status.HTTP_201_CREATED)
async def create_assembly_event(
    company_id: uuid.UUID,
    payload: AssemblyEventIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _require_company(db, company_id)
    event_status = _status(payload.status, EVENT_STATUSES, "active")
    if event_status == "active":
        await db.execute(
            text("UPDATE assembly_events SET status = 'archived', updated_at = NOW() WHERE company_id = :company_id AND status = 'active'"),
            {"company_id": str(company_id)},
        )

    event_id = uuid.uuid4()
    result = await db.execute(
        text(
            """
            INSERT INTO assembly_events (
                id, company_id, title, description, status, starts_at, ends_at,
                quorum_total, quorum_required_percent, identity_mode, settings,
                created_at, updated_at
            )
            VALUES (
                :id, :company_id, :title, :description, :status, COALESCE(CAST(:starts_at AS TIMESTAMPTZ), NOW()), CAST(:ends_at AS TIMESTAMPTZ),
                :quorum_total, :quorum_required_percent, :identity_mode, CAST(:settings AS jsonb),
                NOW(), NOW()
            )
            RETURNING *
            """
        ),
        {
            "id": str(event_id),
            "company_id": str(company_id),
            "title": payload.title,
            "description": _clean(payload.description, 1500),
            "status": event_status,
            "starts_at": payload.starts_at,
            "ends_at": payload.ends_at,
            "quorum_total": payload.quorum_total,
            "quorum_required_percent": payload.quorum_required_percent,
            "identity_mode": _clean(payload.identity_mode, 40) or "qr",
            "settings": _json_param(payload.settings),
        },
    )
    row = dict(result.mappings().first())
    await db.commit()
    return await _event_summary_payload(db, company_id, row)


@router.patch("/companies/{company_id}/events/{event_id}")
async def update_assembly_event(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: AssemblyEventIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _require_company(db, company_id)
    await _get_event_row(db, company_id, event_id)
    event_status = _status(payload.status, EVENT_STATUSES, "active")
    if event_status == "active":
        await db.execute(
            text(
                """
                UPDATE assembly_events
                SET status = 'archived', updated_at = NOW()
                WHERE company_id = :company_id AND id <> :event_id AND status = 'active'
                """
            ),
            {"company_id": str(company_id), "event_id": str(event_id)},
        )
    result = await db.execute(
        text(
            """
            UPDATE assembly_events
            SET title = :title,
                description = :description,
                status = :status,
                starts_at = COALESCE(CAST(:starts_at AS TIMESTAMPTZ), starts_at),
                ends_at = CAST(:ends_at AS TIMESTAMPTZ),
                quorum_total = :quorum_total,
                quorum_required_percent = :quorum_required_percent,
                identity_mode = :identity_mode,
                settings = CAST(:settings AS jsonb),
                updated_at = NOW()
            WHERE id = :event_id AND company_id = :company_id
            RETURNING *
            """
        ),
        {
            "event_id": str(event_id),
            "company_id": str(company_id),
            "title": payload.title,
            "description": _clean(payload.description, 1500),
            "status": event_status,
            "starts_at": payload.starts_at,
            "ends_at": payload.ends_at,
            "quorum_total": payload.quorum_total,
            "quorum_required_percent": payload.quorum_required_percent,
            "identity_mode": _clean(payload.identity_mode, 40) or "qr",
            "settings": _json_param(payload.settings),
        },
    )
    row = dict(result.mappings().first())
    await db.commit()
    return await _event_summary_payload(db, company_id, row)


@router.post("/companies/{company_id}/events/{event_id}/agenda", status_code=status.HTTP_201_CREATED)
async def add_assembly_agenda(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: AssemblyAgendaIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _get_event_row(db, company_id, event_id)
    await db.execute(
        text(
            """
            INSERT INTO assembly_agenda_items (id, event_id, company_id, title, notes, position, status, created_at, updated_at)
            VALUES (:id, :event_id, :company_id, :title, :notes, :position, :status, NOW(), NOW())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "title": payload.title,
            "notes": _clean(payload.notes, 1200),
            "position": payload.position,
            "status": _status(payload.status, AGENDA_STATUSES, "pending"),
        },
    )
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))


@router.post("/companies/{company_id}/events/{event_id}/votes", status_code=status.HTTP_201_CREATED)
async def add_assembly_vote(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: AssemblyVoteIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _get_event_row(db, company_id, event_id)
    vote_type = _status(payload.vote_type, VOTE_TYPES, "decision")
    options = _vote_options(vote_type, payload.options)
    await db.execute(
        text(
            """
            INSERT INTO assembly_votes (
                id, event_id, company_id, agenda_id, title, vote_type, options, status, opens_at, closes_at, created_at, updated_at
            )
            VALUES (
                :id, :event_id, :company_id, :agenda_id, :title, :vote_type, CAST(:options AS jsonb), :status, CAST(:opens_at AS TIMESTAMPTZ), CAST(:closes_at AS TIMESTAMPTZ), NOW(), NOW()
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "agenda_id": str(payload.agenda_id) if payload.agenda_id else None,
            "title": payload.title,
            "vote_type": vote_type,
            "options": _json_param(options),
            "status": _status(payload.status, VOTE_STATUSES, "open"),
            "opens_at": payload.opens_at,
            "closes_at": payload.closes_at,
        },
    )
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))


@router.post("/companies/{company_id}/events/{event_id}/attendees", status_code=status.HTTP_201_CREATED)
async def add_assembly_attendee(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: AssemblyAttendeeIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _get_event_row(db, company_id, event_id)
    qr_key = _clean(payload.qr_key, 120)
    params = {
        "id": str(uuid.uuid4()),
        "event_id": str(event_id),
        "company_id": str(company_id),
        "attendee_name": payload.attendee_name,
        "document_ref": _clean(payload.document_ref, 120),
        "qr_key": qr_key,
        "present": bool(payload.present),
        "metadata": _json_param(payload.metadata),
    }
    existing_id = None
    if qr_key:
        existing = await db.execute(
            text("SELECT id FROM assembly_attendees WHERE event_id = :event_id AND qr_key = :qr_key ORDER BY checked_in_at DESC LIMIT 1"),
            {"event_id": str(event_id), "qr_key": qr_key},
        )
        existing_id = existing.scalar_one_or_none()

    if existing_id:
        params["id"] = str(existing_id)
        await db.execute(
            text(
                """
                UPDATE assembly_attendees
                SET attendee_name = :attendee_name,
                    document_ref = :document_ref,
                    present = :present,
                    metadata = CAST(:metadata AS jsonb),
                    checked_in_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id AND event_id = :event_id AND company_id = :company_id
                """
            ),
            params,
        )
    else:
        await db.execute(
            text(
                """
                INSERT INTO assembly_attendees (
                    id, event_id, company_id, attendee_name, document_ref, qr_key, present, metadata, checked_in_at, created_at, updated_at
                )
                VALUES (:id, :event_id, :company_id, :attendee_name, :document_ref, :qr_key, :present, CAST(:metadata AS jsonb), NOW(), NOW(), NOW())
                """
            ),
            params,
        )
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))


@router.post("/companies/{company_id}/events/{event_id}/questions", status_code=status.HTTP_201_CREATED)
async def add_assembly_question(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    payload: AssemblyQuestionIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _get_event_row(db, company_id, event_id)
    vote_id = str(payload.vote_id) if payload.vote_id else None
    if vote_id:
        vote_result = await db.execute(
            text("SELECT id FROM assembly_votes WHERE id = :vote_id AND event_id = :event_id AND company_id = :company_id LIMIT 1"),
            {"vote_id": vote_id, "event_id": str(event_id), "company_id": str(company_id)},
        )
        if not vote_result.first():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assembly_vote_not_found")
    qr_key = _clean(payload.qr_key, 120)
    if vote_id and qr_key:
        await db.execute(
            text("DELETE FROM assembly_questions WHERE event_id = :event_id AND vote_id = :vote_id AND qr_key = :qr_key"),
            {"event_id": str(event_id), "vote_id": vote_id, "qr_key": qr_key},
        )
    await db.execute(
        text(
            """
            INSERT INTO assembly_questions (
                id, event_id, company_id, vote_id, participant_name, qr_key, question, status, created_at, updated_at
            )
            VALUES (:id, :event_id, :company_id, :vote_id, :participant_name, :qr_key, :question, :status, NOW(), NOW())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "vote_id": vote_id,
            "participant_name": _clean(payload.participant_name, 180),
            "qr_key": qr_key,
            "question": payload.question,
            "status": _status(payload.status, QUESTION_STATUSES, "pending"),
        },
    )
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))


@router.patch("/companies/{company_id}/events/{event_id}/questions/{question_id}")
async def update_assembly_question(
    company_id: uuid.UUID,
    event_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: AssemblyQuestionUpdateIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    await _get_event_row(db, company_id, event_id)
    result = await db.execute(
        text(
            """
            UPDATE assembly_questions
            SET status = :status, updated_at = NOW()
            WHERE id = :question_id
              AND event_id = :event_id
              AND company_id = :company_id
            RETURNING id
            """
        ),
        {
            "question_id": str(question_id),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "status": _status(payload.status, QUESTION_STATUSES, "pending"),
        },
    )
    if not result.first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assembly_question_not_found")
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))


@router.post("/companies/{company_id}/votes/{vote_id}/responses", status_code=status.HTTP_201_CREATED)
async def add_assembly_vote_response(
    company_id: uuid.UUID,
    vote_id: uuid.UUID,
    payload: AssemblyVoteResponseIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _ensure_storage(db)
    result = await db.execute(
        text("SELECT * FROM assembly_votes WHERE id = :vote_id AND company_id = :company_id LIMIT 1"),
        {"vote_id": str(vote_id), "company_id": str(company_id)},
    )
    vote = result.mappings().first()
    if not vote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assembly_vote_not_found")
    event_id = vote["event_id"]
    qr_key = _clean(payload.qr_key, 120)
    if qr_key:
        await db.execute(
            text("DELETE FROM assembly_vote_responses WHERE vote_id = :vote_id AND qr_key = :qr_key"),
            {"vote_id": str(vote_id), "qr_key": qr_key},
        )
    await db.execute(
        text(
            """
            INSERT INTO assembly_vote_responses (
                id, vote_id, event_id, company_id, qr_key, voter_name, choice_key, choice_label, created_at, updated_at
            )
            VALUES (:id, :vote_id, :event_id, :company_id, :qr_key, :voter_name, :choice_key, :choice_label, NOW(), NOW())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "vote_id": str(vote_id),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "qr_key": qr_key,
            "voter_name": _clean(payload.voter_name, 180),
            "choice_key": payload.choice_key,
            "choice_label": _clean(payload.choice_label, 180) or payload.choice_key,
        },
    )
    await db.commit()
    return await _event_summary_payload(db, company_id, await _get_event_row(db, company_id, event_id))
