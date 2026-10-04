"""Tipo de empresa para la consola: demo | registrada.

Vive en companies.settings_json.kind (sin migracion de esquema). Si una
empresa aun no lo tiene, se deduce igual que la migracion de datos
023a_company_kind: las tres empresas vivas son "registrada" y el resto "demo".
"""
from __future__ import annotations

from typing import Any

DEMO = "demo"
REGISTERED = "registrada"
KINDS = (DEMO, REGISTERED)

# Mismas tres empresas que _CLONEXA_LIVE_COMPANY_IDS en app/main.py (una
# prueba revisa que no se separen). Nunca se pueden eliminar desde la consola.
LIVE_COMPANY_IDS = frozenset({
    "7625872c-f941-4479-a27b-f8443be953c5",  # ASADERO EL SOCIO
    "21a3065e-38ee-4fc3-96ed-ae1707a3b8e4",  # The Time Machine
    "d63cf68c-be5b-4a30-aee4-341973018db1",  # Velvet
})


def default_kind(company_id: Any) -> str:
    return REGISTERED if str(company_id) in LIVE_COMPANY_IDS else DEMO


def resolve_kind(company_id: Any, settings: Any) -> str:
    raw = settings.get("kind") if isinstance(settings, dict) else settings
    value = str(raw or "").strip().lower()
    return value if value in KINDS else default_kind(company_id)


def is_protected(company_id: Any) -> bool:
    return str(company_id) in LIVE_COMPANY_IDS
