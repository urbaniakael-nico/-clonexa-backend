import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.core.database import async_session_maker

DEMO_SLUGS = ["voltage", "radio-despecho", "mundo-case", "velvet"]


async def main() -> int:
    async with async_session_maker() as session:
        result = await session.execute(
            text("SELECT id, name, slug FROM companies WHERE slug = ANY(:slugs) ORDER BY slug"),
            {"slugs": DEMO_SLUGS},
        )
        companies = result.mappings().all()
        by_slug = {c["slug"]: c for c in companies}

        print("CLONEXA ADMIN V2 OWNER ACCESS CHECK")
        print("")

        total_owner = 0
        missing = 0
        multiple = 0

        labels = {
            "voltage": "Voltage",
            "radio-despecho": "Radio Despecho",
            "mundo-case": "Mundo Case",
            "velvet": "Velvet",
        }

        for slug in DEMO_SLUGS:
            company = by_slug.get(slug)
            print(f"{labels.get(slug, slug)}:")

            if not company:
                print("- company_id: MISSING")
                print("- owner access: MISSING")
                print("")
                missing += 1
                continue

            users_result = await session.execute(
                text(
                    '''
                    SELECT id, email, full_name, role, status, locked_until, created_at
                    FROM company_users
                    WHERE company_id = :company_id
                    ORDER BY
                      CASE WHEN role = 'company_admin' THEN 0 ELSE 1 END,
                      CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                      created_at ASC
                    '''
                ),
                {"company_id": company["id"]},
            )
            users = users_result.mappings().all()
            owners = [u for u in users if u["role"] == "company_admin"]

            if not owners:
                owner_state = "MISSING"
                missing += 1
                email = "-"
                status = "-"
                role = "-"
            elif len(owners) > 1:
                owner_state = "MULTIPLE"
                multiple += 1
                total_owner += len(owners)
                selected = owners[0]
                email = selected["email"]
                status = selected["status"]
                role = selected["role"]
            else:
                owner_state = "OK"
                total_owner += 1
                selected = owners[0]
                email = selected["email"]
                status = selected["status"]
                role = selected["role"]

            print(f"- company_id: {company['id']}")
            print(f"- owner access: {owner_state}")
            print(f"- email: {email}")
            print(f"- status: {status}")
            print(f"- role: {role}")
            print("")

        print(f"total companies: {len(companies)}")
        print(f"total owner accesses: {total_owner}")
        print(f"missing owner accesses: {missing}")
        print(f"multiple owner accesses: {multiple}")

        if missing or multiple:
            return 1

        print("status: OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
