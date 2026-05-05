from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db

router = APIRouter()


class GpsPerimeterIn(BaseModel):
    slot: int = Field(ge=1, le=5)
    name: str | None = None
    latitude_min: float | None = None
    latitude_max: float | None = None
    longitude_min: float | None = None
    longitude_max: float | None = None
    is_active: bool = True


class GpsPerimetersPayload(BaseModel):
    perimeters: list[GpsPerimeterIn] = Field(default_factory=list, max_length=5)


async def ensure_gps_storage(db: AsyncSession) -> None:
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_gps_perimeters (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            slot integer NOT NULL,
            name varchar(140) NOT NULL DEFAULT '',
            latitude_min numeric(12,8) NULL,
            latitude_max numeric(12,8) NULL,
            longitude_min numeric(12,8) NULL,
            longitude_max numeric(12,8) NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_company_gps_perimeters_company_slot UNIQUE (company_id, slot),
            CONSTRAINT ck_company_gps_perimeters_slot CHECK (slot >= 1 AND slot <= 5)
        );
    """))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_gps_perimeters_company ON company_gps_perimeters(company_id);"))
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_company_gps_perimeters_active ON company_gps_perimeters(company_id, is_active);"))
    await db.commit()


def dec_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def perimeter_row_out(row: dict[str, Any]) -> dict[str, Any]:
    def f(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    return {
        "id": str(row.get("id")) if row.get("id") is not None else None,
        "company_id": str(row.get("company_id")) if row.get("company_id") is not None else None,
        "slot": int(row.get("slot") or 0),
        "name": row.get("name") or "",
        "latitude_min": f(row.get("latitude_min")),
        "latitude_max": f(row.get("latitude_max")),
        "longitude_min": f(row.get("longitude_min")),
        "longitude_max": f(row.get("longitude_max")),
        "is_active": bool(row.get("is_active")),
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def point_inside(latitude: float, longitude: float, perimeter: dict[str, Any]) -> bool:
    try:
        lat_min = float(perimeter.get("latitude_min"))
        lat_max = float(perimeter.get("latitude_max"))
        lng_min = float(perimeter.get("longitude_min"))
        lng_max = float(perimeter.get("longitude_max"))
    except Exception:
        return False

    if lat_min > lat_max:
        lat_min, lat_max = lat_max, lat_min
    if lng_min > lng_max:
        lng_min, lng_max = lng_max, lng_min

    return lat_min <= latitude <= lat_max and lng_min <= longitude <= lng_max


def validate_against_perimeters(latitude: float, longitude: float, perimeters: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        item for item in perimeters
        if item.get("is_active")
        and item.get("latitude_min") is not None
        and item.get("latitude_max") is not None
        and item.get("longitude_min") is not None
        and item.get("longitude_max") is not None
    ]
    if not valid:
        return {"status": "unconfigured", "label": "Sin perímetro", "perimeter": None}

    for perimeter in valid:
        if point_inside(latitude, longitude, perimeter):
            return {
                "status": "inside",
                "label": "Dentro de perímetro",
                "perimeter": {
                    "id": str(perimeter.get("id")),
                    "slot": perimeter.get("slot"),
                    "name": perimeter.get("name") or f"Punto {perimeter.get('slot')}",
                },
            }

    return {"status": "outside", "label": "Fuera de perímetro", "perimeter": None}


@router.get("/companies/{company_id}/perimeters")
async def list_gps_perimeters(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await ensure_gps_storage(db)
    result = await db.execute(
        text("""
            SELECT id, company_id, slot, name, latitude_min, latitude_max, longitude_min, longitude_max, is_active, updated_at
            FROM company_gps_perimeters
            WHERE company_id = :company_id
            ORDER BY slot ASC
        """),
        {"company_id": str(company_id)},
    )
    rows = [perimeter_row_out(dict(row)) for row in result.mappings().all()]
    by_slot = {row["slot"]: row for row in rows}
    perimeters = []
    for slot in range(1, 6):
        perimeters.append(by_slot.get(slot) or {
            "id": None,
            "company_id": str(company_id),
            "slot": slot,
            "name": f"Punto {slot}",
            "latitude_min": None,
            "latitude_max": None,
            "longitude_min": None,
            "longitude_max": None,
            "is_active": slot == 1,
            "updated_at": None,
        })

    return {"company_id": str(company_id), "perimeters": perimeters}


@router.put("/companies/{company_id}/perimeters")
async def save_gps_perimeters(
    company_id: UUID,
    payload: GpsPerimetersPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await ensure_gps_storage(db)

    seen: set[int] = set()
    for item in payload.perimeters[:5]:
        if item.slot in seen:
            raise HTTPException(status_code=422, detail=f"Slot duplicado: {item.slot}")
        seen.add(item.slot)

        lat_min = dec_or_none(item.latitude_min)
        lat_max = dec_or_none(item.latitude_max)
        lng_min = dec_or_none(item.longitude_min)
        lng_max = dec_or_none(item.longitude_max)

        await db.execute(
            text("""
                INSERT INTO company_gps_perimeters (
                    company_id,
                    slot,
                    name,
                    latitude_min,
                    latitude_max,
                    longitude_min,
                    longitude_max,
                    is_active,
                    updated_at
                )
                VALUES (
                    :company_id,
                    :slot,
                    :name,
                    :latitude_min,
                    :latitude_max,
                    :longitude_min,
                    :longitude_max,
                    :is_active,
                    now()
                )
                ON CONFLICT (company_id, slot)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    latitude_min = EXCLUDED.latitude_min,
                    latitude_max = EXCLUDED.latitude_max,
                    longitude_min = EXCLUDED.longitude_min,
                    longitude_max = EXCLUDED.longitude_max,
                    is_active = EXCLUDED.is_active,
                    updated_at = now()
            """),
            {
                "company_id": str(company_id),
                "slot": int(item.slot),
                "name": (item.name or f"Punto {item.slot}").strip()[:140],
                "latitude_min": lat_min,
                "latitude_max": lat_max,
                "longitude_min": lng_min,
                "longitude_max": lng_max,
                "is_active": bool(item.is_active),
            },
        )

    await db.commit()
    return await list_gps_perimeters(company_id, db)


async def load_perimeters(db: AsyncSession, company_id: UUID) -> list[dict[str, Any]]:
    await ensure_gps_storage(db)
    result = await db.execute(
        text("""
            SELECT id, company_id, slot, name, latitude_min, latitude_max, longitude_min, longitude_max, is_active, updated_at
            FROM company_gps_perimeters
            WHERE company_id = :company_id
            ORDER BY slot ASC
        """),
        {"company_id": str(company_id)},
    )
    return [perimeter_row_out(dict(row)) for row in result.mappings().all()]


@router.get("/companies/{company_id}/summary")
async def gps_summary(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    perimeters = await load_perimeters(db, company_id)

    active_result = await db.execute(
        text("""
            SELECT DISTINCT employee_id
            FROM workforce_attendance_status
            WHERE company_id = :company_id
              AND status IN ('working', 'on_break')
        """),
        {"company_id": str(company_id)},
    )
    active_employee_ids = {str(row[0]) for row in active_result.all() if row[0] is not None}

    latest_result = await db.execute(
        text("""
            SELECT DISTINCT ON (employee_id)
                id,
                company_id,
                employee_id,
                employee_name,
                employee_role,
                latitude,
                longitude,
                payload_json,
                occurred_at
            FROM workforce_attendance_events
            WHERE company_id = :company_id
              AND module_code = 'gps'
              AND event_type IN ('gps_location', 'gps_ping')
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            ORDER BY employee_id, occurred_at DESC, created_at DESC
        """),
        {"company_id": str(company_id)},
    )

    inside = 0
    outside = 0
    unconfigured = 0
    sent = 0
    people = []

    for row in latest_result.mappings().all():
        item = dict(row)
        employee_id = str(item.get("employee_id") or "")
        if active_employee_ids and employee_id not in active_employee_ids:
            continue

        try:
            lat = float(item.get("latitude"))
            lng = float(item.get("longitude"))
        except Exception:
            continue

        # Siempre recalcular contra los perímetros actuales.
        # Si el usuario corrige o crea el perímetro después de recibir la ubicación,
        # el CRM/GPS debe actualizar dentro/fuera sin exigir reenviar ubicación.
        validation = validate_against_perimeters(lat, lng, perimeters)
        status = validation["status"]

        sent += 1
        if status == "inside":
            inside += 1
        elif status == "outside":
            outside += 1
        else:
            unconfigured += 1

        people.append({
            "employee_id": employee_id,
            "employee_name": item.get("employee_name"),
            "employee_role": item.get("employee_role"),
            "latitude": lat,
            "longitude": lng,
            "coordinates": f"{lat:.6f}, {lng:.6f}",
            "gps_status": status,
            "gps_label": validation.get("label"),
            "perimeter": validation.get("perimeter"),
            "occurred_at": item.get("occurred_at").isoformat() if item.get("occurred_at") else None,
        })

    return {
        "company_id": str(company_id),
        "active_people": len(active_employee_ids),
        "sent_location": sent,
        "inside": inside,
        "outside": outside,
        "unconfigured": unconfigured,
        "perimeters": perimeters,
        "people": people,
    }
