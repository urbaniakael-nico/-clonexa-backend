"""Facturacion contra Postgres REAL con asyncpg (pgserver), mas las reglas puras.

Contrato de ejemplo: "The Time Machine", minimo 6 meses, 250 los meses 1-2 y
200 desde el 3, paga del 15 al 20; octubre de 2026 es su segundo pago.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import time
import uuid
from datetime import date
from decimal import Decimal

import pytest

pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.services import billing, billing_pdf  # noqa: E402
from app.services import brand_media as media  # noqa: E402
from tests.test_brand_pg import BASE_SCHEMA  # noqa: E402

TTM = {"contract_type": "minimo", "start_date": "2026-09-01", "min_months": 6, "currency": "COP", "pay_day_from": 15, "pay_day_to": 20,
       "notes": "", "status": "vigente", "tiers": [{"month_from": 1, "month_to": 2, "amount": 250}, {"month_from": 3, "month_to": None, "amount": 200}]}


def _migrations() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    for name in ("023b_admin_audit_log", "024d_billing"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_bill_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in BASE_SCHEMA.split(";") if s.strip()] + _migrations():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


async def _session(url: str):
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE billing_contract_files, billing_receipts, billing_payments, billing_installments, billing_price_tiers, billing_contracts, companies CASCADE"))
    return engine, maker


async def _company(db, name: str, demo: bool = False) -> str:
    cid = str(uuid.uuid4())
    settings = '{"kind": "demo"}' if demo else '{"kind": "registrada"}'
    await db.execute(text("INSERT INTO companies (id, name, slug, settings_json) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb))"),
                     {"i": cid, "n": name, "s": name.lower().replace(" ", "-"), "j": settings})
    await db.commit()
    return cid


@pytest.fixture(autouse=True)
def today(monkeypatch):
    holder = {"d": date(2026, 10, 5)}
    monkeypatch.setattr(billing, "today_bogota", lambda: holder["d"])
    return holder


# ----------------------------------------------------------- reglas puras ---
def test_example_contract_tiers_and_window():
    c = billing.validate_contract(TTM, {"mensual", "minimo", "anual", "prueba"})
    items = billing.schedule_for(c, c["tiers"], date(2027, 3, 1))
    assert [int(i["amount"]) for i in items] == [250, 250, 200, 200, 200, 200, 200]
    second = items[1]
    assert second["period"] == date(2026, 10, 1) and second["due_from"] == date(2026, 10, 15) and second["due_date"] == date(2026, 10, 20)


def test_mora_only_after_the_20th_without_a_validated_payment():
    inst = {"amount": Decimal("250"), "due_from": date(2026, 10, 15), "due_date": date(2026, 10, 20)}
    assert billing.status_of(inst, Decimal("0"), date(2026, 10, 10))["status"] == "pendiente"
    w = billing.status_of(inst, Decimal("0"), date(2026, 10, 17))
    assert w["status"] == "en_ventana" and w["days_left"] == 3
    assert billing.status_of(inst, Decimal("0"), date(2026, 10, 20))["status"] == "en_ventana", "el 20 todavia esta en ventana"
    late = billing.status_of(inst, Decimal("0"), date(2026, 10, 23))
    assert late["status"] == "en_mora" and late["days_late"] == 3
    assert billing.status_of(inst, Decimal("250"), date(2026, 10, 23))["status"] == "pagada"


def test_contract_and_payment_validation():
    types = {"mensual", "minimo"}
    with pytest.raises(billing.BillingInvalid):
        billing.validate_contract({**TTM, "pay_day_from": 21}, types)
    with pytest.raises(billing.BillingInvalid):
        billing.validate_contract({**TTM, "tiers": [{"month_from": 2, "month_to": None, "amount": 1}]}, types)
    with pytest.raises(billing.BillingInvalid):
        billing.validate_contract({**TTM, "contract_type": "inventado"}, types)
    ok = {"installment_id": str(uuid.uuid4()), "amount": 250, "paid_on": "2026-10-16", "method": "transferencia", "reference": "TRX-8812"}
    assert billing.validate_payment(ok)["reference"] == "TRX-8812"
    with pytest.raises(billing.BillingInvalid, match="tarjeta"):
        billing.validate_payment({**ok, "reference": "4111 1111 1111 1111"})
    with pytest.raises(billing.BillingInvalid):
        billing.validate_payment({**ok, "amount": 0})


def test_only_real_pdfs_are_accepted():
    pdf = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    assert billing.is_pdf(pdf)
    assert not billing.is_pdf(b"\x89PNG\r\n\x1a\n" + b"x" * 100), "una imagen renombrada a .pdf no pasa"
    assert not billing.is_pdf(b"hola %PDF-1.4 %%EOF"), "la firma va al inicio"
    assert not billing.is_pdf(b"%PDF-1.4 sin cierre"), "PDF truncado"


# ---------------------------------------------------------- Postgres real ---
@pytest.mark.asyncio
async def test_installments_and_mora_on_real_postgres(pg_url, today):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        ttm = await _company(db, "The Time Machine")
        await billing.save_contract(db, ttm, TTM)
        view = await billing.company_view(db, ttm)
        items = view["installments"]
        assert [(i["seq"], int(i["amount"])) for i in items[:4]] == [(1, 250), (2, 250), (3, 200), (4, 200)]
        october = items[1]
        assert october["period"] == date(2026, 10, 1) and october["due_date"] == date(2026, 10, 20)
        assert view["summary"]["months_done"] == 2 and view["summary"]["min_months"] == 6, "mes 2 de 6"
        assert view["summary"]["state"] == "en_mora", "septiembre ya vencio sin pago"
        sept = await billing.register_payment(db, ttm, {"installment_id": items[0]["id"], "amount": 250, "paid_on": "2026-09-18", "method": "transferencia"}, "admin")
        await billing.validate_payment_and_issue(db, ttm, sept["id"], "admin")
        assert (await billing.company_view(db, ttm))["summary"]["state"] == "al_dia", "octubre todavia no abre su ventana"
        # el 18: en ventana y "vence en 2 dias"
        today["d"] = date(2026, 10, 18)
        s = (await billing.company_view(db, ttm))["summary"]
        assert s["state"] == "en_ventana" and any(a["kind"] == "vence" and a["days"] == 2 for a in s["alerts"])
        # el 22 sin pago validado: en mora (tambien en la base, por el ciclo diario)
        today["d"] = date(2026, 10, 22)
        await billing.refresh_statuses(db, ttm, today["d"])
        stored = (await db.execute(text("SELECT status FROM billing_installments WHERE company_id = CAST(:c AS uuid) AND seq = 2"), {"c": ttm})).scalar()
        assert stored == "en_mora"
        s = (await billing.company_view(db, ttm))["summary"]
        assert s["state"] == "en_mora" and s["days_late"] >= 2
        # registrar no basta: hasta validar sigue en mora
        for seq in (2,):
            inst = next(i for i in (await billing.company_view(db, ttm))["installments"] if i["seq"] == seq)
            pay = await billing.register_payment(db, ttm, {"installment_id": inst["id"], "amount": 250, "paid_on": "2026-10-22", "method": "nequi"}, "admin")
            assert (await billing.company_view(db, ttm))["summary"]["state"] == "en_mora"
            await billing.validate_payment_and_issue(db, ttm, pay["id"], "admin")
        assert (await billing.company_view(db, ttm))["summary"]["state"] == "al_dia"
        assert (await db.execute(text("SELECT status FROM billing_installments WHERE company_id = CAST(:c AS uuid) AND seq = 2"), {"c": ttm})).scalar() == "pagada"
        # cambiar el contrato no toca cuotas ya pagadas
        await billing.save_contract(db, ttm, {**TTM, "tiers": [{"month_from": 1, "month_to": None, "amount": 300}]})
        items = (await billing.company_view(db, ttm))["installments"]
        assert int(items[0]["amount"]) == 250 and int(items[2]["amount"]) == 300
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_numbers_never_repeat_even_concurrently(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        a = await _company(db, "Uno")
        await billing.save_contract(db, a, {**TTM, "start_date": "2026-01-01"})
        items = (await billing.company_view(db, a))["installments"]
        pays = [await billing.register_payment(db, a, {"installment_id": i["id"], "amount": i["amount"], "paid_on": "2026-10-01", "method": "efectivo"}, "admin")
                for i in items[:6]]

    async def validate(pid):
        async with maker() as s:
            try:
                return (await billing.validate_payment_and_issue(s, a, pid, "admin"))["number"]
            except billing.BillingConflict:
                return None

    # seis pagos distintos validados a la vez + el mismo pago validado dos veces a la vez
    numbers = await asyncio.gather(*[validate(p["id"]) for p in pays[:5]], validate(pays[5]["id"]), validate(pays[5]["id"]))
    issued = [n for n in numbers if n is not None]
    assert len(issued) == 6 and len(set(issued)) == 6, "uno por pago; nunca repetido"
    async with maker() as db:
        assert (await db.execute(text("SELECT COUNT(*) FROM billing_receipts WHERE company_id = CAST(:c AS uuid)"), {"c": a})).scalar() == 6
        # anular: el comprobante queda (anulado) y su numero no vuelve a salir
        voided = await billing.void_payment(db, a, pays[0]["id"], "Pago devuelto por el banco", "admin")
        row = (await db.execute(text("SELECT status, number FROM billing_receipts WHERE payment_id = CAST(:p AS uuid)"), {"p": pays[0]["id"]})).mappings().first()
        assert row["status"] == "anulado" and billing.receipt_code(row["number"]) == voided["code"]
        with pytest.raises(billing.BillingInvalid):
            await billing.void_payment(db, a, pays[1]["id"], "", "admin")
        inst = (await billing.company_view(db, a))["installments"][0]
        assert inst["status"] != "pagada", "anulado el pago, la cuota vuelve a deberse"
        again = await billing.register_payment(db, a, {"installment_id": inst["id"], "amount": inst["amount"], "paid_on": "2026-10-02", "method": "efectivo"}, "admin")
        new = await billing.validate_payment_and_issue(db, a, again["id"], "admin")
        assert new["number"] > max(issued), "el numero anulado no se reutiliza"
        r = await billing.receipt(db, a, new["receipt_id"])
        pdf = billing_pdf.render(r)
        assert pdf.startswith(b"%PDF-") and billing.is_pdf(pdf)
        old = await billing.receipt(db, a, (await db.execute(text("SELECT id::text FROM billing_receipts WHERE payment_id = CAST(:p AS uuid)"), {"p": pays[0]["id"]})).scalar())
        assert old["status"] == "anulado" and billing.is_pdf(billing_pdf.render(old))
    await engine.dispose()


@pytest.mark.asyncio
async def test_tenant_isolation_and_demos_on_real_postgres(pg_url):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        a = await _company(db, "Alfa")
        b = await _company(db, "Beta")
        demo = await _company(db, "Demo Uno", demo=True)
        await billing.save_contract(db, a, TTM)
        await billing.save_contract(db, b, TTM)
        inst_a = (await billing.company_view(db, a))["installments"][0]
        pay = await billing.register_payment(db, a, {"installment_id": inst_a["id"], "amount": 250, "paid_on": "2026-09-16", "method": "efectivo"}, "admin")
        with pytest.raises(billing.BillingInvalid):
            await billing.register_payment(db, b, {"installment_id": inst_a["id"], "amount": 250, "paid_on": "2026-09-16", "method": "efectivo"}, "admin")
        with pytest.raises(billing.BillingConflict):
            await billing.validate_payment_and_issue(db, b, pay["id"], "admin")
        issued = await billing.validate_payment_and_issue(db, a, pay["id"], "admin")
        assert await billing.receipt(db, b, issued["receipt_id"]) is None, "B no lee el comprobante de A"
        assert await billing.receipt(db, a, issued["receipt_id"]) is not None

        class Mem:
            def __init__(self):
                self.objects = {}

            def put(self, k, d):
                self.objects[k] = d

            def get(self, k):
                return self.objects[k]

            def list(self, p):
                return [k for k in self.objects if k.startswith(p)]

            def delete(self, keys):
                for k in keys:
                    self.objects.pop(k, None)

        mem = Mem()
        media.set_backend(mem)
        try:
            async def put(key, data):
                media.put_private(key, data, "application/pdf")

            pdf = b"%PDF-1.5\n%%EOF\n"
            f1 = await billing.add_contract_file(db, a, pdf, "c.pdf", "admin", put)
            f2 = await billing.add_contract_file(db, a, pdf + b" ", "c2.pdf", "admin", put)
            files = await billing.contract_files(db, a)
            assert [f["version"] for f in files] == [2, 1] and [f["is_current"] for f in files] == [True, False], "reemplazar guarda la anterior"
            assert await billing.contract_file(db, b, f1["id"]) is None, "B no ve el contrato de A"
            assert all(k.startswith(f"billing/{a}/") for k in mem.objects)
            with pytest.raises(billing.BillingInvalid):
                await billing.add_contract_file(db, a, b"GIF89a....", "x.pdf", "admin", put)
            with pytest.raises(billing.BillingInvalid):
                await billing.add_contract_file(db, a, b"%PDF-" + b"0" * (billing.MAX_PDF_BYTES + 1), "big.pdf", "admin", put)
            mem.objects[f"brand/{a}/x.webp"] = b"img"
            mem.objects[f"billing/{b}/contracts/z.pdf"] = b"%PDF"
            assert media.delete_company(a) == 3, "el purge borra imagenes, contratos y comprobantes de A"
            assert list(mem.objects) == [f"billing/{b}/contracts/z.pdf"], "y nada de B"
            assert f2["version"] == 2
        finally:
            media.set_backend(None)

        names = [c["company"]["name"] for c in (await billing.board(db))["cards"]]
        assert "Demo Uno" not in names and {"Alfa", "Beta"} <= set(names), "las demos no aparecen en Facturacion"
        assert not await billing.is_registered(db, demo)
    await engine.dispose()


@pytest.mark.asyncio
async def test_board_kpis_and_alerts_on_real_postgres(pg_url, today):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        a = await _company(db, "Alfa")
        await _company(db, "Sin contrato")
        await billing.save_contract(db, a, TTM)
        today["d"] = date(2026, 10, 22)
        data = await billing.board(db)
        assert data["kpis"]["overdue"] == Decimal("500"), "septiembre y octubre en mora"
        assert data["kpis"]["expected_monthly"] == Decimal("250")
        assert len(data["charts"]["by_month"]) == 12 and data["charts"]["by_type"] == [{"label": "Mínimo de meses", "count": 1}]
        al = await billing.alerts(db)
        assert {x["kind"] for x in al} == {"mora"} and all(x["company_id"] == a for x in al)
        card = next(c for c in data["cards"] if c["company"]["id"] == a)
        assert card["summary"]["state"] == "en_mora"
        none = next(c for c in data["cards"] if c["company"]["name"] == "Sin contrato")
        assert none["summary"]["state"] == "sin_contrato"
    await engine.dispose()
