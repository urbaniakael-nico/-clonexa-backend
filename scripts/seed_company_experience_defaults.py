from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from app.core.database import async_session_maker
except Exception:
    from app.core.database import async_session_maker

from app.models.core import Company
from app.services.company_experience import ensure_company_experience_defaults, get_company_experience


async def main() -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(Company))
        companies = list(result.scalars().all())

        if not companies:
            print("[WARN] No hay empresas para seed.")
            return

        for company in companies:
            name = getattr(company, "name", None) or getattr(company, "slug", None) or str(company.id)
            seed_result = await ensure_company_experience_defaults(db, company.id)
            exp = await get_company_experience(db, company.id)
            print(
                f"[OK] {name} | {company.id} | "
                f"created={seed_result.get('created')} | "
                f"launchpad={len(exp.get('launchpad_cards', []))} "
                f"widgets={len(exp.get('widgets', []))} "
                f"sections={len(exp.get('sections', []))} "
                f"actions={len(exp.get('actions', []))} "
                f"fields={len(exp.get('field_configs', []))} "
                f"alerts={len(exp.get('alert_rules', []))}"
            )

        print(f"[DONE] Defaults procesados para {len(companies)} empresas. Idempotente: puedes correrlo de nuevo.")


if __name__ == "__main__":
    asyncio.run(main())
