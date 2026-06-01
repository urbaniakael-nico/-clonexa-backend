from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()

EVENT_STATUSES = {"draft", "active", "closed", "archived"}
AGENDA_STATUSES = {"pending", "active", "done", "skipped"}
VOTE_STATUSES = {"draft", "open", "closed"}
QUESTION_STATUSES = {"pending", "answered", "archived"}
VOTE_TYPES = {"yes_no", "true_false", "multiple", "participants"}


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
        "checked_in_at": _iso(row.get("checked_in_at")),
    }


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
    vote_type: str = Field(default="yes_no", max_length=40)
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

    @field_validator("attendee_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        name = _clean(value, 180)
        if not name:
            raise ValueError("attendee_name_required")
        return name


class AssemblyQuestionIn(BaseModel):
    participant_name: str | None = Field(default="", max_length=180)
    qr_key: str | None = Field(default="", max_length=120)
    question: str = Field(..., max_length=1600)
    status: str = Field(default="pending", max_length=40)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        question = _clean(value, 1600)
        if not question:
            raise ValueError("question_required")
        return question


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
                checked_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
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
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_assembly_questions_event ON assembly_questions(event_id, status, created_at DESC);"))


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
              AND status IN ('active', 'draft')
            ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


def _vote_options(vote_type: str, raw_options: list[Any] | None = None) -> list[dict[str, str]]:
    vote_type = _status(vote_type, VOTE_TYPES, "yes_no")
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


async def _event_summary_payload(db: AsyncSession, company_id: uuid.UUID, event_row: dict[str, Any] | None = None) -> dict[str, Any]:
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
    counts = await db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM assembly_attendees WHERE event_id = :event_id) AS attendees,
              (SELECT COUNT(*) FROM assembly_attendees WHERE event_id = :event_id AND present IS TRUE) AS present,
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
        text("SELECT * FROM assembly_attendees WHERE event_id = :event_id ORDER BY checked_in_at DESC LIMIT 80"),
        {"event_id": event_id},
    )
    questions_rows = await db.execute(
        text("SELECT * FROM assembly_questions WHERE event_id = :event_id ORDER BY created_at DESC LIMIT 80"),
        {"event_id": event_id},
    )
    vote_rows = await db.execute(
        text("SELECT * FROM assembly_votes WHERE event_id = :event_id ORDER BY created_at DESC"),
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


@router.get("/companies/{company_id}/summary")
async def assembly_summary(company_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await _ensure_storage(db)
    await _require_company(db, company_id)
    return await _event_summary_payload(db, company_id)


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
    vote_type = _status(payload.vote_type, VOTE_TYPES, "yes_no")
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
    await db.execute(
        text(
            """
            INSERT INTO assembly_attendees (
                id, event_id, company_id, attendee_name, document_ref, qr_key, present, checked_in_at, created_at, updated_at
            )
            VALUES (:id, :event_id, :company_id, :attendee_name, :document_ref, :qr_key, :present, NOW(), NOW(), NOW())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "attendee_name": payload.attendee_name,
            "document_ref": _clean(payload.document_ref, 120),
            "qr_key": _clean(payload.qr_key, 120),
            "present": bool(payload.present),
        },
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
    await db.execute(
        text(
            """
            INSERT INTO assembly_questions (
                id, event_id, company_id, participant_name, qr_key, question, status, created_at, updated_at
            )
            VALUES (:id, :event_id, :company_id, :participant_name, :qr_key, :question, :status, NOW(), NOW())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_id": str(event_id),
            "company_id": str(company_id),
            "participant_name": _clean(payload.participant_name, 180),
            "qr_key": _clean(payload.qr_key, 120),
            "question": payload.question,
            "status": _status(payload.status, QUESTION_STATUSES, "pending"),
        },
    )
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
