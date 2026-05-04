from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.company_experience import (
    create_collection_item,
    delete_collection_item,
    ensure_company_experience_defaults,
    get_company_experience,
    list_collection,
    update_branding,
    update_collection_item,
    update_localization,
)

router = APIRouter()


@router.get("/{company_id}/experience")
async def get_experience(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await get_company_experience(db, company_id)


@router.put("/{company_id}/experience")
async def put_experience(
    company_id: UUID,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if "branding" in payload and isinstance(payload["branding"], dict):
        await update_branding(db, company_id, payload["branding"])
    if "localization" in payload and isinstance(payload["localization"], dict):
        await update_localization(db, company_id, payload["localization"])
    return await get_company_experience(db, company_id)


@router.post("/{company_id}/experience/ensure-defaults")
async def ensure_defaults(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    counts = await ensure_company_experience_defaults(db, company_id)
    data = await get_company_experience(db, company_id)
    return {"ok": True, "counts": counts, "experience": data}


@router.get("/{company_id}/branding")
async def get_branding(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return (await get_company_experience(db, company_id)).get("branding", {})


@router.put("/{company_id}/branding")
async def put_branding(
    company_id: UUID,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await update_branding(db, company_id, payload)


@router.get("/{company_id}/localization")
async def get_localization(company_id: UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return (await get_company_experience(db, company_id)).get("localization", {})


@router.put("/{company_id}/localization")
async def put_localization(
    company_id: UUID,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await update_localization(db, company_id, payload)


COLLECTION_ENDPOINTS = {
    "launchpad-cards": "launchpad_cards",
    "crm-widgets": "widgets",
    "crm-sections": "sections",
    "crm-actions": "actions",
    "field-configs": "field_configs",
    "alert-rules": "alert_rules",
}


async def _list(company_id: UUID, collection: str, db: AsyncSession):
    return await list_collection(db, company_id, collection)


async def _create(company_id: UUID, collection: str, payload: dict[str, Any], db: AsyncSession):
    return await create_collection_item(db, company_id, collection, payload)


async def _update(company_id: UUID, collection: str, item_id: UUID, payload: dict[str, Any], db: AsyncSession):
    row = await update_collection_item(db, company_id, collection, item_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="item_not_found")
    return row


async def _delete(company_id: UUID, collection: str, item_id: UUID, db: AsyncSession):
    return await delete_collection_item(db, company_id, collection, item_id)


@router.get("/{company_id}/launchpad-cards")
async def list_launchpad_cards(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "launchpad_cards", db)


@router.post("/{company_id}/launchpad-cards")
async def create_launchpad_card(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "launchpad_cards", payload, db)


@router.put("/{company_id}/launchpad-cards/{item_id}")
async def update_launchpad_card(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "launchpad_cards", item_id, payload, db)


@router.delete("/{company_id}/launchpad-cards/{item_id}")
async def delete_launchpad_card(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "launchpad_cards", item_id, db)


@router.get("/{company_id}/crm-widgets")
async def list_widgets(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "widgets", db)


@router.post("/{company_id}/crm-widgets")
async def create_widget(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "widgets", payload, db)


@router.put("/{company_id}/crm-widgets/{item_id}")
async def update_widget(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "widgets", item_id, payload, db)


@router.delete("/{company_id}/crm-widgets/{item_id}")
async def delete_widget(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "widgets", item_id, db)


@router.get("/{company_id}/crm-sections")
async def list_sections(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "sections", db)


@router.post("/{company_id}/crm-sections")
async def create_section(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "sections", payload, db)


@router.put("/{company_id}/crm-sections/{item_id}")
async def update_section(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "sections", item_id, payload, db)


@router.delete("/{company_id}/crm-sections/{item_id}")
async def delete_section(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "sections", item_id, db)


@router.get("/{company_id}/crm-actions")
async def list_actions(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "actions", db)


@router.post("/{company_id}/crm-actions")
async def create_action(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "actions", payload, db)


@router.put("/{company_id}/crm-actions/{item_id}")
async def update_action(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "actions", item_id, payload, db)


@router.delete("/{company_id}/crm-actions/{item_id}")
async def delete_action(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "actions", item_id, db)


@router.get("/{company_id}/field-configs")
async def list_field_configs(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "field_configs", db)


@router.post("/{company_id}/field-configs")
async def create_field_config(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "field_configs", payload, db)


@router.put("/{company_id}/field-configs/{item_id}")
async def update_field_config(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "field_configs", item_id, payload, db)


@router.delete("/{company_id}/field-configs/{item_id}")
async def delete_field_config(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "field_configs", item_id, db)


@router.get("/{company_id}/alert-rules")
async def list_alerts(company_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _list(company_id, "alert_rules", db)


@router.post("/{company_id}/alert-rules")
async def create_alert(company_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _create(company_id, "alert_rules", payload, db)


@router.put("/{company_id}/alert-rules/{item_id}")
async def update_alert(company_id: UUID, item_id: UUID, payload: dict[str, Any] = Body(default_factory=dict), db: AsyncSession = Depends(get_db)):
    return await _update(company_id, "alert_rules", item_id, payload, db)


@router.delete("/{company_id}/alert-rules/{item_id}")
async def delete_alert(company_id: UUID, item_id: UUID, db: AsyncSession = Depends(get_db)):
    return await _delete(company_id, "alert_rules", item_id, db)
