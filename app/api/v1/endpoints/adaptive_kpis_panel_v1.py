from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.adaptive_kpis_v1 import adaptive_kpis_summary

router = APIRouter()

MAX_PANEL_KPIS = 4


def clean(value: Any) -> str:
    return str(value or "").strip()


async def ensure_storage(db: AsyncSession) -> None:
    await db.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto";'))

    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS company_kpi_panel_config (
            company_id uuid PRIMARY KEY,
            selected_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))


async def load_selected_keys(db: AsyncSession, company_id: str) -> list[str]:
    await ensure_storage(db)

    result = await db.execute(
        text("""
            SELECT selected_keys
            FROM company_kpi_panel_config
            WHERE company_id::text = :company_id
            LIMIT 1
        """),
        {"company_id": company_id},
    )

    row = result.mappings().first()

    if not row:
        return []

    value = row["selected_keys"]

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []

    if not isinstance(value, list):
        return []

    return [clean(item) for item in value if clean(item)][:MAX_PANEL_KPIS]


async def save_selected_keys(db: AsyncSession, company_id: str, keys: list[str]) -> None:
    await ensure_storage(db)

    clean_keys = []
    for key in keys:
        value = clean(key)
        if value and value not in clean_keys:
            clean_keys.append(value)

    clean_keys = clean_keys[:MAX_PANEL_KPIS]

    await db.execute(
        text("""
            INSERT INTO company_kpi_panel_config (
                company_id,
                selected_keys,
                created_at,
                updated_at
            )
            VALUES (
                CAST(:company_id AS uuid),
                CAST(:selected_keys AS jsonb),
                now(),
                now()
            )
            ON CONFLICT (company_id)
            DO UPDATE SET
                selected_keys = EXCLUDED.selected_keys,
                updated_at = now()
        """),
        {
            "company_id": company_id,
            "selected_keys": json.dumps(clean_keys, ensure_ascii=False),
        },
    )

    await db.commit()


def build_panel_response(summary: dict[str, Any], selected_keys: list[str]) -> dict[str, Any]:
    items = summary.get("items") or []

    if not selected_keys:
        selected_keys = [clean(item.get("key")) for item in items[:MAX_PANEL_KPIS] if clean(item.get("key"))]

    selected_set = set(selected_keys)

    indexed = {clean(item.get("key")): item for item in items if clean(item.get("key"))}

    top_cards = []
    for key in selected_keys:
        if key in indexed:
            item = dict(indexed[key])
            item["panel_visible"] = True
            top_cards.append(item)

    enriched_items = []
    for item in items:
        row = dict(item)
        row["panel_visible"] = clean(item.get("key")) in selected_set
        enriched_items.append(row)

    sections = []
    for section in summary.get("sections") or []:
        section_row = dict(section)
        section_items = []
        for item in section_row.get("items") or []:
            row = dict(item)
            row["panel_visible"] = clean(item.get("key")) in selected_set
            section_items.append(row)

        section_row["items"] = section_items
        sections.append(section_row)

    return {
        **summary,
        "max_panel_kpis": MAX_PANEL_KPIS,
        "selected_keys": selected_keys,
        "top_cards": top_cards,
        "items": enriched_items,
        "sections": sections,
    }


@router.get("/companies/{company_id}/panel")
async def get_kpi_panel(
    company_id: str,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    preset: str | None = Query("7d"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    summary = await adaptive_kpis_summary(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        preset=preset,
        db=db,
    )

    selected_keys = await load_selected_keys(db, company_id)

    return build_panel_response(summary, selected_keys)


@router.put("/companies/{company_id}/panel")
async def update_kpi_panel(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    selected_keys = payload.get("selected_keys") or []

    if not isinstance(selected_keys, list):
        raise HTTPException(status_code=422, detail="selected_keys debe ser una lista.")

    await save_selected_keys(db, company_id, selected_keys)

    summary = await adaptive_kpis_summary(
        company_id=company_id,
        date_from=None,
        date_to=None,
        preset="7d",
        db=db,
    )

    return build_panel_response(summary, await load_selected_keys(db, company_id))


@router.post("/companies/{company_id}/panel/toggle")
async def toggle_kpi_panel_item(
    company_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    key = clean(payload.get("key"))
    visible = bool(payload.get("visible"))

    if not key:
        raise HTTPException(status_code=422, detail="key requerido.")

    selected = await load_selected_keys(db, company_id)

    if visible:
        if key not in selected:
            if len(selected) >= MAX_PANEL_KPIS:
                raise HTTPException(status_code=409, detail=f"Máximo {MAX_PANEL_KPIS} KPIs visibles en panel.")
            selected.append(key)
    else:
        selected = [item for item in selected if item != key]

    await save_selected_keys(db, company_id, selected)

    summary = await adaptive_kpis_summary(
        company_id=company_id,
        date_from=None,
        date_to=None,
        preset="7d",
        db=db,
    )

    return build_panel_response(summary, await load_selected_keys(db, company_id))
