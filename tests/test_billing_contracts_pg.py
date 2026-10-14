"""Facturacion · Redactar contrato, Datos del proveedor y Recordatorio de pago.

Reglas puras + Postgres REAL (pgserver). Empresas demo ficticias; nada de
datos reales. El contrato "a mano" (como el de The Time Machine) no se toca.
"""
from __future__ import annotations

import asyncio
import importlib
import tempfile
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import billing
from app.services import billing_contract_pdf as cpdf
from app.services import billing_contracts as bc
from app.services import brand_media as media

TYPES = {"mensual", "minimo", "anual", "prueba"}
FORM = {"contract_type": "minimo", "start_date": "2026-11-01", "trial_days": 15, "min_months": 6, "currency": "COP",
        "pay_day_from": 15, "pay_day_to": 20,
        "tiers": [{"month_from": 1, "month_to": 2, "amount": 180000}, {"month_from": 3, "month_to": None, "amount": 220000}],
        "surcharge": {"amount": 50000, "from_month": 3}, "jurisdiction_city": "Bogotá", "sign_city": "",
        "client": {"legal_name": "", "doc_id": "", "representative": "", "address": "", "email": "", "phone": ""},
        "modules": [{"code": "hospitality", "name": "Hospitality", "line": "Mesas y pedidos."}]}
PROVIDER = {"name": "Proveedor Demo", "trade_name": "CLONEXA", "doc_id": "000-0", "email": "demo@clonexa.test", "phones": "+57 300 000 0000", "city": ""}


# ------------------------------------------------------------ reglas puras ---
def test_amounts_in_words_and_numbers():
    assert bc.amount_words(1300000, "COP") == "un millón trescientos mil pesos colombianos"
    assert bc.amount_words(1000000, "COP") == "un millón de pesos colombianos"
    assert bc.amount_words(221000, "COP") == "doscientos veintiún mil pesos colombianos"
    assert bc.amount_words(180000, "COP") == "ciento ochenta mil pesos colombianos"
    assert bc.amount_words(Decimal("1250.50"), "USD") == "mil doscientos cincuenta dólares estadounidenses con 50/100"
    assert bc.money_text(220000, "COP") == "$220.000 COP"
    assert bc.money_text(Decimal("1250.5"), "USD") == "US$1,250.50"


def test_tiers_and_minimum_commitment():
    data = bc.validate_draft(FORM, TYPES)
    assert bc.min_commitment(data["tiers"], 6) == Decimal("1240000"), "2 x 180.000 + 4 x 220.000"
    assert bc.min_commitment(data["tiers"], 0) == Decimal("0")
    assert data["paid_start"] == date(2026, 11, 16), "15 dias de prueba desde el 1: pagos desde el 16"
    rows = bc.schedule_rows(data)
    assert [int(r["amount"]) for r in rows] == [180000, 180000, 220000, 220000, 220000, 220000]
    assert rows[0]["window"] == "15–20 nov. 2026" and rows[0]["period"] == "Noviembre 2026"
    c = bc.compose(data, PROVIDER, {"name": "Bar Demo"}, "CX-2026-001", 1, "Mínimo de meses")
    assert c["commitment_text"] == "$1.240.000 COP" and c["commitment_words"] == "un millón doscientos cuarenta mil pesos colombianos"
    assert [t["label"] for t in c["tiers"]] == ["Meses 1 a 2", "Desde el mes 3"]


def test_draft_validation_like_validate_contract():
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**FORM, "currency": "EUR"}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**FORM, "trial_days": 91}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**FORM, "pay_day_from": 21}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**FORM, "tiers": [{"month_from": 2, "month_to": None, "amount": 1}]}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**FORM, "client": {**FORM["client"], "email": "no-es-correo"}}, TYPES)
    with pytest.raises(billing.BillingInvalid, match="activo"):
        bc.validate_draft(FORM, TYPES, active_codes={"inventory"})
    assert bc.validate_draft({**FORM, "currency": "USD"}, TYPES)["currency"] == "USD"


def _segments(c):
    for sec in c["sections"]:
        for b in sec["blocks"]:
            if b["type"] == "p":
                yield sec["title"], b["segments"]


def test_empty_client_fields_become_fill_lines_and_no_loose_fields():
    data = bc.validate_draft(FORM, TYPES)
    c = bc.compose(data, PROVIDER, {"name": "Bar Demo"}, "CX-2026-001", 1, "Mínimo de meses")
    parts = dict((t, s) for t, s in _segments(c))
    assert ("b", "") in parts["PARTES"], "cliente sin documento ni direccion: linea para llenar"
    text = " ".join(x for _t, segs in _segments(c) for k, x in segs if k == "t")
    assert "[" not in text and "{" not in text, "sin [CAMPOS] ni {campos} sueltos"
    assert "Bogotá, Colombia" in text and "$180.000 COP" in text and "ciento ochenta mil pesos colombianos" in text
    full = bc.validate_draft({**FORM, "sign_city": "Bogotá", "client": {"legal_name": "Demo S.A.S.", "doc_id": "900.000.000-1", "representative": "Persona Demo",
                                                                     "address": "Calle 1", "email": "demo@ejemplo.com", "phone": "+57 300 000 0000"}}, TYPES)
    c2 = bc.compose(full, {**PROVIDER, "city": "Bogotá"}, {"name": "Bar Demo"}, "CX-2026-001", 1, "Mínimo de meses")
    assert all(("b", "") not in segs for _t, segs in _segments(c2)), "con todo lleno no queda ninguna linea"
    assert c2["verification"] != c["verification"], "el codigo depende del contenido"
    assert bc.compose(full, {**PROVIDER, "city": "Bogotá"}, {"name": "Bar Demo"}, "CX-2026-001", 1, "x")["verification"] == c2["verification"]


def test_template_keeps_the_18_clauses_annexes_and_the_mora_rule():
    tpl = bc.load_template()
    titles = [s["title"] for s in tpl["sections"]]
    numbered = [t for t in titles if "." in t and t.split(".")[0] in {
        "PRIMERA", "SEGUNDA", "TERCERA", "CUARTA", "QUINTA", "SEXTA", "SÉPTIMA", "OCTAVA", "NOVENA", "DÉCIMA", "DÉCIMA PRIMERA", "DÉCIMA SEGUNDA",
        "DÉCIMA TERCERA", "DÉCIMA CUARTA", "DÉCIMA QUINTA", "DÉCIMA SEXTA", "DÉCIMA SÉPTIMA", "DÉCIMA OCTAVA"}]
    assert len(numbered) == 18
    assert any(t.startswith("ANEXO 1") for t in titles) and any(t.startswith("ANEXO 2") for t in titles) and "FIRMAS" in titles
    mora = " ".join(next(s for s in tpl["sections"] if s["title"].startswith("DÉCIMA TERCERA"))["paragraphs"])
    assert "requerir por escrito" in mora and "cinco (5) días hábiles" in mora
    assert "Hospitality" not in " ".join(" ".join(s["paragraphs"]) for s in tpl["sections"]), "el alcance sale de los modulos reales"
    for trial, months, sur in ((0, 0, None), (10, 12, {"amount": 1, "from_month": 2})):  # todas las ramas sin campos desconocidos
        data = bc.validate_draft({**FORM, "trial_days": trial, "min_months": months, "surcharge": sur or {}, "tiers": [{"month_from": 1, "month_to": None, "amount": 99}]}, TYPES)
        bc.compose(data, PROVIDER, {"name": "X"}, "CX-2026-009", 1, "Mensual")


def test_pdf_has_no_blank_pages_and_stamps_every_page():
    for currency in ("COP", "USD"):
        data = bc.validate_draft({**FORM, "currency": currency}, TYPES)
        c = bc.compose(data, PROVIDER, {"name": "Bar Demo"}, "CX-2026-001", 2, "Mínimo de meses")
        pdf, info = cpdf.render(c)
        assert billing.is_pdf(pdf) and info["pages"] >= 3
        assert sorted(info["body"]) == list(range(1, info["pages"] + 1)), f"cada pagina tiene contenido del cuerpo: {info['body']}"
        assert sorted(info["stamped"]) == list(range(1, info["pages"] + 1))
        for page, stamp in info["stamped"].items():
            assert "CX-2026-001" in stamp and "Versión 2" in stamp and c["verification"] in stamp and f"Página {page} de {info['pages']}" in stamp


def _contract(**kw):
    return {"status": "vigente", "reminder_enabled": True, "currency": "COP", **kw}


def _inst(amount=220000):
    return {"id": "i1", "period": date(2026, 10, 1), "amount": Decimal(amount), "due_from": date(2026, 10, 15), "due_date": date(2026, 10, 20), "voided": False}


def test_reminder_rule():
    k, i = _contract(), _inst()
    assert bc.reminder_for(k, i, Decimal(0), date(2026, 10, 14)) is None, "antes del dia de pago, nada"
    r = bc.reminder_for(k, i, Decimal(0), date(2026, 10, 15))
    assert r["state"] == "open" and r["balance"] == Decimal("220000") and not r["partial"]
    part = bc.reminder_for(k, i, Decimal("20000"), date(2026, 10, 18))
    assert part["balance"] == Decimal("200000") and part["partial"]
    assert bc.reminder_for(k, i, Decimal("220000"), date(2026, 10, 18)) is None, "cubierta (por validar o validado): nada"
    assert bc.reminder_for(k, i, Decimal(0), date(2026, 10, 21))["state"] == "overdue", "despues de la fecha limite cambia el texto"
    assert bc.reminder_for(k, i, Decimal(0), date(2026, 10, 31)) is not None and bc.reminder_for(k, i, Decimal(0), date(2026, 11, 1)) is None
    assert bc.reminder_for(_contract(reminder_enabled=False), i, Decimal(0), date(2026, 10, 16)) is None, "el interruptor lo apaga"
    assert bc.reminder_for(_contract(status="pausado"), i, Decimal(0), date(2026, 10, 16)) is None


# ---------------------------------------------------------- Postgres real ---
pgserver = pytest.importorskip("pgserver")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (id uuid PRIMARY KEY, name text NOT NULL, slug text, status text DEFAULT 'active', settings_json jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, name text, description text, category text,
  is_active boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS company_modules (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
  module_id uuid REFERENCES modules(id), enabled boolean DEFAULT true, settings jsonb DEFAULT '{}'::jsonb, activated_at timestamptz)
"""


def _migrations() -> list[str]:
    statements: list[str] = []

    class Op:
        def execute(self, sql):
            statements.append(str(sql))

    for name in ("023b_admin_audit_log", "024d_billing", "024l_billing_drafts"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_draft_")
    server = pgserver.get_server(folder, cleanup_mode="stop")
    url = server.get_uri().replace("postgresql://", "postgresql+asyncpg://", 1)

    async def setup():
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            for stmt in [s for s in SCHEMA.split(";") if s.strip()] + _migrations():
                await conn.execute(text(stmt))
        await engine.dispose()

    asyncio.run(setup())
    yield url


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


@pytest.fixture
def mem():
    store = Mem()
    media.set_backend(store)
    yield store
    media.set_backend(None)


async def put(key, data, content_type):
    media.put_private(key, data, content_type)


async def get(key):
    return media.backend().get(key)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    holder = {"d": date(2026, 11, 10)}
    monkeypatch.setattr(billing, "today_bogota", lambda: holder["d"])
    return holder


async def _session(url: str):
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("""TRUNCATE billing_contract_documents, billing_contract_files, billing_receipts, billing_payments, billing_installments,
            billing_price_tiers, billing_contracts, company_modules, modules, companies CASCADE"""))
    return engine, maker


async def _company(db, name: str, demo: bool = False, modules=()) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("""INSERT INTO companies (id, name, slug, settings_json, created_at) VALUES (CAST(:i AS uuid), :n, :s, CAST(:j AS jsonb), :c)"""),
                     {"i": cid, "n": name, "s": name.lower().replace(" ", "-"), "j": '{"kind": "demo"}' if demo else '{"kind": "registrada"}',
                      "c": datetime(2026, 9, 20, tzinfo=timezone.utc)})
    for code, enabled, activated in modules:
        await db.execute(text("""INSERT INTO modules (code, name, description) VALUES (:c, :n, :d) ON CONFLICT (code) DO NOTHING"""),
                         {"c": code, "n": code.replace("_", " ").title(), "d": f"Hace {code}. Mas detalle que no sale."})
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, activated_at)
            SELECT CAST(:i AS uuid), id, :e, :a FROM modules WHERE code = :c"""), {"i": cid, "c": code, "e": enabled, "a": activated})
    await db.commit()
    return cid


MODS = (("hospitality", True, datetime(2026, 10, 2, tzinfo=timezone.utc)), ("inventory", True, datetime(2026, 10, 1, tzinfo=timezone.utc)),
        ("crm", False, datetime(2026, 9, 1, tzinfo=timezone.utc)))


@pytest.mark.asyncio
async def test_candidates_prefill_generate_versions_and_ttm_untouched(pg_url, mem, today):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        ttm = await _company(db, "Bar Manual", modules=MODS)  # contrato hecho a mano, como The Time Machine
        await billing.save_contract(db, ttm, {"contract_type": "minimo", "start_date": "2026-09-01", "min_months": 6, "currency": "COP", "pay_day_from": 15,
                                              "pay_day_to": 20, "notes": "", "status": "vigente",
                                              "tiers": [{"month_from": 1, "month_to": 2, "amount": 250}, {"month_from": 3, "month_to": None, "amount": 200}]})
        before = await billing.get_contract(db, ttm)
        nuevo = await _company(db, "Bar Nuevo", modules=MODS)
        await _company(db, "Demo Uno", demo=True, modules=MODS)
        names = [c["name"] for c in await bc.draft_candidates(db)]
        assert names == ["Bar Nuevo"], "solo registradas sin contrato (ni demos ni la del contrato a mano)"

        pre = await bc.prefill(db, nuevo)
        assert [m["code"] for m in pre["modules"]] == ["hospitality", "inventory"], "solo modulos ACTIVOS"
        assert pre["modules"][0]["name"] == "Hospitality" and pre["modules"][0]["line"] == "Hace hospitality."
        assert pre["form"]["start_date"] == "2026-09-19", "fecha de creacion/activacion mas antigua (hora de Bogota)"

        form = {**FORM, "modules": pre["form"]["modules"]}
        doc = await bc.generate(db, nuevo, form, "admin", put, get)
        assert doc["number"] == "CX-2026-001" and doc["version"] == 1 and doc["commitment"] == Decimal("1240000")
        view = await billing.company_view(db, nuevo)
        assert view["contract"]["start_date"] == date(2026, 11, 16) and view["contract"]["reminder_enabled"] is True
        assert [int(i["amount"]) for i in view["installments"]][:3] == [180000, 180000, 220000], "quedan las cuotas"
        assert len(view["files"]) == 1 and mem.objects[billing.contract_file_key(nuevo, view["files"][0]["id"])].startswith(b"%PDF-")
        today["d"] = date(2026, 11, 22)
        assert any(a["company_id"] == nuevo and a["kind"] == "mora" for a in await billing.alerts(db)), "y sus alertas"

        doc2 = await bc.generate(db, nuevo, {**form, "tiers": [{"month_from": 1, "month_to": None, "amount": 250000}]}, "admin", put, get)
        assert (doc2["number"], doc2["version"]) == ("CX-2026-001", 2)
        hist = await bc.documents(db, nuevo)
        assert [(d["version"], d["is_current"]) for d in hist] == [(2, True), (1, False)], "la version 1 queda en el historial"
        assert len(await billing.contract_files(db, nuevo)) == 2

        with pytest.raises(billing.BillingConflict):
            await bc.generate(db, ttm, form, "admin", put, get)
        after = await billing.get_contract(db, ttm)
        assert after["tiers"] == before["tiers"] and after["start_date"] == before["start_date"], "el contrato a mano no cambia"
        assert await bc.documents(db, ttm) == []

        usd = await _company(db, "Bar Dolares", modules=MODS)
        d3 = await bc.generate(db, usd, {**form, "currency": "USD", "tiers": [{"month_from": 1, "month_to": None, "amount": "1250.50"}]}, "admin", put, get)
        assert d3["number"] == "CX-2026-002"
        assert (await billing.get_contract(db, usd))["currency"] == "USD"
        assert mem.objects and all(k.startswith(f"billing/{c}/contracts/") for k in mem.objects for c in (nuevo, usd) if c in k), "todo en la zona privada"
        assert all(k.startswith("billing/") for k in mem.objects)
    await engine.dispose()


@pytest.mark.asyncio
async def test_reminder_paid_void_toggle_and_alert(pg_url, mem, today):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        cid = await _company(db, "Bar Pago", modules=MODS)
        other = await _company(db, "Bar Otro", modules=MODS)
        await bc.generate(db, cid, {**FORM, "trial_days": 0, "start_date": "2026-10-01", "modules": [{"code": "hospitality", "name": "H", "line": ""}]}, "admin", put, get)
        await bc.generate(db, other, {**FORM, "trial_days": 0, "start_date": "2026-10-01", "modules": [{"code": "hospitality", "name": "H", "line": ""}]}, "admin", put, get)
        assert await bc.reminder(db, cid, date(2026, 11, 14)) is None, "antes del dia de pago"
        r = await bc.reminder(db, cid, date(2026, 11, 15))
        assert r and r["state"] == "open" and r["balance"] == Decimal("180000") and r["period"] == date(2026, 11, 1)

        png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
        with pytest.raises(billing.BillingInvalid):
            await bc.report_payment(db, cid, b"GIF89a", None, "dueno@demo", date(2026, 11, 15), put)
        with pytest.raises(billing.BillingInvalid):
            await bc.report_payment(db, cid, png, None, "dueno@demo", date(2026, 11, 15), put)  # PNG roto
        with pytest.raises(billing.BillingInvalid):
            await bc.report_payment(db, cid, b"%PDF-" + b"0" * bc.MAX_PROOF_BYTES + b"%%EOF", None, "dueno@demo", date(2026, 11, 15), put)
        part = await bc.report_payment(db, cid, b"%PDF-1.4\n%%EOF\n", "30000", "dueno@demo", date(2026, 11, 16), put)
        r = await bc.reminder(db, cid, date(2026, 11, 16))
        assert r["partial"] and r["balance"] == Decimal("150000"), "pago parcial: muestra el saldo"
        paid = await bc.report_payment(db, cid, b"%PDF-1.4\n%%EOF\n", None, "dueno@demo", date(2026, 11, 16), put)
        assert paid["amount"] == Decimal("150000")
        assert await bc.reminder(db, cid, date(2026, 11, 17)) is None, "con el pago por validar deja de salir"
        pays = await billing.payments(db, cid)
        assert {p["status"] for p in pays} == {"por_validar"} and all(p["source"] == "cliente" and p["has_proof"] for p in pays)
        assert any(k.startswith(f"billing/{cid}/proofs/") for k in mem.objects)
        assert any(a["company_id"] == cid and a["kind"] == "reportado" for a in await billing.alerts(db)), "aviso en la consola"
        assert await bc.payment_proof(db, other, paid["id"]) is None, "otra empresa no ve el comprobante"
        assert await bc.reminder(db, other, date(2026, 11, 17)) is not None, "la otra empresa sigue con su propio recordatorio"

        await billing.void_payment(db, cid, paid["id"], "No llegó el dinero", "admin")
        r = await bc.reminder(db, cid, date(2026, 11, 17))
        assert r and r["balance"] == Decimal("150000"), "anular el pago lo hace volver"
        assert (await bc.reminder(db, cid, date(2026, 11, 21)))["state"] == "overdue"
        await bc.set_reminder(db, cid, False)
        assert await bc.reminder(db, cid, date(2026, 11, 21)) is None, "el interruptor por contrato lo apaga"
        await bc.set_reminder(db, cid, True)
        assert await bc.reminder(db, cid, date(2026, 11, 21)) is not None
        assert part["installment_id"] == paid["installment_id"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_data_and_qr(pg_url, mem):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        p = await bc.get_provider(db)
        assert p["trade_name"] == "CLONEXA" and p["email"] == "clonexasaas@gmail.com", "valores iniciales de la migracion"
        saved = await bc.save_provider(db, {**PROVIDER, "name": "Clonexa S.A.S."}, "admin")
        assert saved["name"] == "Clonexa S.A.S."
        with pytest.raises(billing.BillingInvalid):
            await bc.save_provider(db, {**PROVIDER, "email": "x"}, "admin")
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
        raw = buf.getvalue()
        out = await bc.set_provider_qr(db, raw, "admin", put)
        assert out["has_qr"] and out["qr_key"].startswith("billing/_provider/")
        assert mem.objects[out["qr_key"]] == raw, "el QR se guarda tal cual (no se recorta ni se re-codifica)"
        got = await bc.provider_qr(db, get)
        assert got == (raw, "image/png")
        with pytest.raises(billing.BillingInvalid):
            await bc.set_provider_qr(db, b"<svg/>", "admin", put)
        await bc.save_provider(db, {**PROVIDER, **{k: v for k, v in p.items() if k in bc.PROVIDER_FIELDS}}, "admin")
    await engine.dispose()
