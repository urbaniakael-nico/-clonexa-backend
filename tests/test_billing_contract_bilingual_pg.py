"""Facturacion · contrato bilingue (español | ingles), Zelle y "Redactar desde este contrato".

Reglas puras + Postgres REAL (pgserver). Datos ficticios. La plantilla española
y los contratos que ya existen generan EXACTAMENTE lo mismo que antes (huella
del texto y del PDF tomada antes del cambio).
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import re
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
ZELLE = {"zelle_name": "Titular Demo", "zelle_contact": "zelle@demo.test"}
FULL = {"legal_name": "Demo S.A.S.", "doc_id": "900.000.000-1", "representative": "Persona Demo", "address": "Calle 1", "email": "demo@ejemplo.com",
        "phone": "+57 300 000 0000"}
USD_MONTHLY = {**FORM, "contract_type": "mensual", "trial_days": 0, "min_months": 3, "currency": "USD", "pay_day_from": 1, "pay_day_to": 5,
               "surcharge": {}, "tiers": [{"month_from": 1, "month_to": None, "amount": 1500}]}
BI = {**USD_MONTHLY, "language": "es_en", "payment_method": "zelle",
      "modules": [{"code": "payroll", "name": "Nómina", "line": "Cálculo de horas.", "name_en": "Payroll", "line_en": "Calculation of hours."}]}


@pytest.fixture(autouse=True)
def no_public_url(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)


# ------------------------------------------------- texto en ingles ---
def test_english_words_amounts_and_dates():
    assert bc.words_en(1500) == "one thousand five hundred"
    assert bc.words_en(21) == "twenty-one" and bc.words_en(101) == "one hundred one" and bc.words_en(0) == "zero"
    assert bc.words_en(1_300_000) == "one million three hundred thousand"
    assert bc.words_en(4500) == "four thousand five hundred"
    assert bc.amount_words_en(1500, "USD") == "one thousand five hundred United States dollars"
    assert bc.amount_words_en(Decimal("1250.50"), "USD") == "one thousand two hundred fifty United States dollars and 50/100"
    assert bc.amount_words_en(1, "USD") == "one United States dollar"
    assert bc.amount_words_en(1300000, "COP") == "one million three hundred thousand Colombian pesos"
    assert bc.money_text_en(1500, "USD") == "USD 1,500.00" and bc.money_text_en(1300000, "COP") == "COP 1,300,000"
    # columna ES del bilingue (lo que pidio el dueño, letra por letra)
    assert f"{bc.amount_words_bi(1500, 'USD')} ({bc.money_text_bi(1500, 'USD')})" == \
        "mil quinientos dólares de los Estados Unidos de América (USD 1.500)"
    assert bc.money_text_bi(Decimal("1250.5"), "USD") == "USD 1.250,50"
    assert bc.amount_words_bi(1000000, "COP") == "un millón de pesos colombianos"
    assert bc.date_long_en(date(2026, 11, 1)) == "November 1, 2026" and bc.date_long(date(2026, 11, 1)) == "1 de noviembre de 2026"
    assert bc.month_long_en(date(2027, 1, 1)) == "January 2027"
    assert bc.window_text_en(date(2026, 11, 1), date(2026, 11, 5)) == "Nov 1–5, 2026"
    # las de siempre no cambian
    assert bc.amount_words(Decimal("1250.50"), "USD") == "mil doscientos cincuenta dólares estadounidenses con 50/100"
    assert bc.money_text(Decimal("1250.5"), "USD") == "US$1,250.50"


# ------------------------------------- el español queda exactamente igual ---
GOLDEN = {  # huella tomada ANTES del cambio (commit 5635e9a): texto compuesto y PDF
    "base": (FORM, "f7b2e70f4f3684c21fffdd9059c0630ae9e2b49d66ff63fca599086bc322ec55",
             "3fd497c788edd60b2e446c9cf29dbbc67413a02413158cc78395d2cbbc3994c2", "A0009-C765A"),
    "usd": ({**FORM, "currency": "USD", "tiers": [{"month_from": 1, "month_to": None, "amount": "1250.50"}]},
            "f7d145e8be745a4a2560e45bb27a82a1d7b7b238b0a20a463f0f523817399110",
            "30c0683c506207e880ebb97d0c188e548e7c2ed3103d045248d0862b029452e4", "811CD-E5F85"),
    "sin_prueba": ({**FORM, "trial_days": 0, "min_months": 0, "surcharge": {}, "tiers": [{"month_from": 1, "month_to": None, "amount": 99}]},
                   "51c0089b7904cbd4fe564e3e7c12fcb4833680634e07feeea4a4b53f0b46057d",
                   "c565f276796e71ff832f25c67c3dd11bd3c3d8ef8c50998f9b2c4a56e6a8454b", "1B732-0D746"),
    "lleno": ({**FORM, "sign_city": "Bogotá", "client": FULL}, "ce98036463f793fb5ecc707dd442a15c51672ab78b95996104d0aca98e4a23b6",
              "297a839c32e29717c4ad5e74319b93de86a272e17ad8e7ab7854d41dded184b4", "7DC3A-478A4"),
    "usd_mensual": (USD_MONTHLY, "7534b4ccf7dcf214e5eb972d1f020115a2fe4615b78674528ed629fd51b02fd4",
                    "defb35b54b11e36f2a48998a8511e24e9d1d4f34b6dc78c2637d068eb4ab7f18", "C84C4-A0093"),
}


@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_spanish_template_generates_exactly_the_same_text_and_pdf(case):
    form, text_hash, pdf_hash, verification = GOLDEN[case]
    for extra in ({}, {"language": "es", "payment_method": "qr"}):  # el formulario nuevo manda los valores por defecto
        data = bc.validate_draft({**form, **extra}, TYPES)
        assert "language" not in data and "payment_method" not in data, "un contrato en español guarda lo mismo que antes"
        c = bc.compose(data, PROVIDER, {"name": "Bar Demo"}, "CX-2026-001", 1, "Mínimo de meses")
        assert c["verification"] == verification
        assert hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest() == text_hash
        assert "bilingual" not in c
        import reportlab
        if reportlab.Version == "4.2.5":  # la huella del PDF depende de la version de reportlab
            assert hashlib.sha256(cpdf.render(c)[0]).hexdigest() == pdf_hash


def test_spanish_template_file_is_untouched():
    tpl = bc.load_template()
    assert set(tpl) == {"title", "subtitle", "sections"} and all(set(s) == {"title", "paragraphs"} for s in tpl["sections"])
    raw = bc.TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(raw.encode()).hexdigest() == "4d3c0091e79dd57f6c3f6017dcca1fba90df0ee04f094d113cca06cd7f101b4e", \
        "la plantilla española no se toca (la bilingue es otro archivo)"


# ------------------------------------------------------ plantilla bilingue ---
def _texts(c, key):
    for sec in c["sections"]:
        for b in sec["blocks"]:
            if b["type"] == "p":
                yield sec["title"], "".join(x if k == "t" else "____" for k, x in b[key])


def _all(c, key):
    return " ".join(t for _s, t in _texts(c, key))


def test_bilingual_template_every_section_has_es_and_en():
    tpl = bc.load_template(bc.TEMPLATE_BI)
    assert tpl["title_en"] == "SOFTWARE LICENSE AND TECHNOLOGY SERVICES AGREEMENT" and tpl["subtitle_en"]
    es_tpl = bc.load_template()
    assert [s["title"] for s in tpl["sections"]][:19] == [s["title"] for s in es_tpl["sections"]][:19], "mismas 18 clausulas en el mismo orden"
    titles = [s["title"] for s in tpl["sections"]]
    assert "DÉCIMA NOVENA. CESIÓN A LA SOCIEDAD CLONEXA" in titles and "VIGÉSIMA. IDIOMA" in titles
    for sec in tpl["sections"]:
        assert sec.get("title_en"), sec["title"]
        for i, para in enumerate(sec["paragraphs"]):
            if re.fullmatch(r"(\{[?!][a-z_]+\}\s*)?\[\[[A-Z]+\]\]", para.strip()):
                continue
            assert i in sec.get("en", {}), f"«{sec['title']}» párrafo {i} sin traducción"


@pytest.mark.parametrize("variant", [
    {}, {"payment_method": "qr"}, {"trial_days": 10, "surcharge": {"amount": 100, "from_month": 2}},
    {"min_months": 0, "tiers": [{"month_from": 1, "month_to": 2, "amount": 1200}, {"month_from": 3, "month_to": None, "amount": "1500.50"}]},
    {"currency": "COP", "payment_method": "qr", "tiers": [{"month_from": 1, "month_to": None, "amount": 1300000}]},
])
def test_bilingual_compose_has_es_and_en_without_loose_fields(variant):
    data = bc.validate_draft({**BI, **variant}, TYPES)
    c = bc.compose(data, {**PROVIDER, **ZELLE}, {"name": "Empresa Demo"}, "CX-2026-009", 1, "Mensual")
    assert c["bilingual"] is True and c["title_en"]
    for sec in c["sections"]:
        assert sec["title_en"]
        for b in sec["blocks"]:
            if b["type"] == "p":
                assert b["segments_en"], f"{sec['title']}: sin columna EN"
    es, en = _all(c, "segments"), _all(c, "segments_en")
    for text in (es, en):
        assert "{" not in text and "}" not in text and "[[" not in text, "sin {campos} ni [[bloques]] sueltos"
    assert "prevalece la versión en español" in es and "the Spanish version shall prevail" in en
    assert "se ceda a la sociedad Clonexa cuando quede constituida" in es and "assignment of this contract to the company Clonexa" in en
    assert "no cambia el precio ni las condiciones" in es and "does not change the price" in en
    assert "Ley 1581 de 2012" in es and "Law 1581 of 2012" in en
    assert "incluida la ubicación GPS durante el turno" in es and "including GPS location during their shift" in en
    assert "Ley 527 de 1999" in es and "firma electrónica como válida y vinculante" in es and "valid and binding between them" in en
    assert "cada parte asume sus propios impuestos" in es and "each party shall bear its own taxes" in en
    assert "jueces competentes de Bogotá D.C., Colombia" in es and "competent courts of Bogotá D.C., Colombia" in en
    assert "República de Colombia" in es and "Republic of Colombia" in en


def test_bilingual_amounts_and_dates_in_both_languages():
    data = bc.validate_draft(BI, TYPES)
    c = bc.compose(data, {**PROVIDER, **ZELLE}, {"name": "Empresa Demo"}, "CX-2026-009", 1, "Mensual")
    es, en = _all(c, "segments"), _all(c, "segments_en")
    assert "mil quinientos dólares de los Estados Unidos de América (USD 1.500)" in es
    assert "one thousand five hundred United States dollars (USD 1,500.00)" in en
    assert "cuatro mil quinientos dólares de los Estados Unidos de América (USD 4.500)" in es, "compromiso: 3 x 1.500"
    assert "four thousand five hundred United States dollars (USD 4,500.00)" in en
    assert "1 de noviembre de 2026" in es and "November 1, 2026" in en
    assert "31 de enero de 2027" in es and "January 31, 2027" in en, "fin de la permanencia minima"
    assert [r["amount_text"] for r in c["schedule"]] == ["USD 1,500.00"] * 3
    assert c["schedule"][0]["period"] == "Noviembre 2026 / November 2026" and c["schedule"][0]["window"] == "1–5 nov. 2026 / Nov 1–5, 2026"
    assert c["vigencia"]["type"] == "Mensual / Monthly" and c["pago"]["channel"] == "Zelle (Anexo 2) / Zelle (Annex 2)"
    assert c["modules"][0]["name_en"] == "Payroll"


def test_zelle_annex_has_holder_and_contact_without_qr_or_accounts():
    data = bc.validate_draft(BI, TYPES)
    c = bc.compose(data, {**PROVIDER, **ZELLE}, {"name": "Empresa Demo"}, "CX-2026-009", 1, "Mensual")
    annex = next(s for s in c["sections"] if s["title"].startswith("ANEXO 2"))
    assert all(b["type"] == "p" for b in annex["blocks"]), "con Zelle no hay bloque QR"
    es = "".join(x for b in annex["blocks"] for k, x in b["segments"] if k == "t")
    en = "".join(x for b in annex["blocks"] for k, x in b["segments_en"] if k == "t")
    assert "Zelle al titular Titular Demo" in es and "zelle@demo.test" in es and "«Empresa Demo - noviembre 2026»" in es
    assert "account holder Titular Demo" in en and "«Empresa Demo - November 2026»" in en
    assert "verificar siempre estos datos por los canales oficiales" in es and "always verify these details" in en
    assert "QR" not in es + en and not re.search(r"\d{6,}", es + en), "sin QR ni numeros de cuenta"
    assert c["zelle"] == ZELLE
    pdf, info = cpdf.render(c, qr=b"no-se-usa")
    assert billing.is_pdf(pdf)
    # sin datos de Zelle: linea para llenar
    blank = bc.compose(data, PROVIDER, {"name": "Empresa Demo"}, "CX-2026-009", 1, "Mensual")
    annex = next(s for s in blank["sections"] if s["title"].startswith("ANEXO 2"))
    assert ("b", "") in annex["blocks"][0]["segments"] and ("b", "") in annex["blocks"][0]["segments_en"]
    # QR elegido en el bilingue: el Anexo 2 de siempre con el bloque QR
    qr = bc.compose(bc.validate_draft({**BI, "payment_method": "qr"}, TYPES), PROVIDER, {"name": "Empresa Demo"}, "CX-2026-009", 1, "Mensual")
    annex = next(s for s in qr["sections"] if s["title"].startswith("ANEXO 2"))
    assert [b.get("name") for b in annex["blocks"] if b["type"] == "block"] == ["QR"]
    assert "mediante el siguiente QR" in " ".join(x for b in annex["blocks"] if b["type"] == "p" for k, x in b["segments"] if k == "t")
    assert qr["zelle"] is None and qr["verification"] != c["verification"]


def test_language_and_payment_validation():
    with pytest.raises(billing.BillingInvalid, match="bilingüe"):
        bc.validate_draft({**USD_MONTHLY, "payment_method": "zelle"}, TYPES)  # Zelle con la plantilla española: no
    with pytest.raises(billing.BillingInvalid, match="USD"):
        bc.validate_draft({**BI, "currency": "COP"}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**BI, "language": "fr"}, TYPES)
    with pytest.raises(billing.BillingInvalid):
        bc.validate_draft({**BI, "payment_method": "tarjeta"}, TYPES)
    es = bc.validate_draft({**FORM, "modules": BI["modules"]}, TYPES)
    assert "name_en" not in es["modules"][0], "en español el modulo guarda lo mismo que antes"
    assert bc.validate_draft(BI, TYPES)["modules"][0]["line_en"] == "Calculation of hours."
    assert bc.validate_draft({**BI, "modules": [{"code": "x", "name": "X", "line": "L"}]}, TYPES)["modules"][0]["name_en"] == "X"
    with pytest.raises(billing.BillingInvalid):
        bc.validate_provider({**PROVIDER, "zelle_contact": "no es correo ni teléfono"})
    assert bc.validate_provider({**PROVIDER, "zelle_contact": "+1 346 000 0000"})["zelle_contact"] == "+1 346 000 0000"
    assert bc.modules_en()["payroll"] == ["Payroll", "Calculation of hours, cutoffs, overtime, deductions and payments."]


def test_bilingual_pdf_two_columns_stamps_and_single_signature_block():
    for pay in ("zelle", "qr"):
        data = bc.validate_draft({**BI, "payment_method": pay, "client": FULL, "sign_city": "Houston"}, TYPES)
        c = bc.compose(data, {**PROVIDER, **ZELLE}, {"name": "Empresa Demo"}, "CX-2026-009", 2, "Mensual")
        pdf, info = cpdf.render(c)
        assert billing.is_pdf(pdf) and info["pages"] >= 5
        assert sorted(info["body"]) == list(range(1, info["pages"] + 1)), f"sin paginas en blanco: {info['body']}"
        for page, stamp in info["stamped"].items():
            assert "CX-2026-009" in stamp and "Versión / Version 2" in stamp and c["verification"] in stamp
            assert f"Página {page} de {info['pages']} / Page {page} of {info['pages']}" in stamp
        firmas = [s for s in c["sections"] if s["title"] == "FIRMAS"]
        assert len(firmas) == 1 and [b.get("name") for b in firmas[0]["blocks"] if b["type"] == "block"] == ["FIRMAS"]


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

    for name in ("023b_admin_audit_log", "024d_billing", "024l_billing_drafts", "024v_billing_bilingual"):
        module = importlib.import_module(f"migrations.versions.{name}")
        module.op = Op()
        module.upgrade()
    return statements


@pytest.fixture(scope="module")
def pg_url():
    folder = tempfile.mkdtemp(prefix="cx_pg_bilingual_")
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
    monkeypatch.setattr(billing, "today_bogota", lambda: date(2026, 10, 27))


async def _session(url: str):
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("""TRUNCATE billing_contract_history, billing_contract_documents, billing_contract_files, billing_receipts, billing_payments,
            billing_installments, billing_price_tiers, billing_contracts, company_modules, modules, companies CASCADE"""))
    return engine, maker


async def _company(db, name: str) -> str:
    cid = str(uuid.uuid4())
    await db.execute(text("""INSERT INTO companies (id, name, slug, settings_json, created_at) VALUES (CAST(:i AS uuid), :n, :s, '{"kind": "registrada"}', :c)"""),
                     {"i": cid, "n": name, "s": name.lower().replace(" ", "-"), "c": datetime(2026, 9, 20, tzinfo=timezone.utc)})
    for code in ("payroll", "gps"):
        await db.execute(text("INSERT INTO modules (code, name, description) VALUES (:c, :n, :d) ON CONFLICT (code) DO NOTHING"),
                         {"c": code, "n": {"payroll": "Nómina", "gps": "GPS"}[code], "d": f"Hace {code}."})
        await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, activated_at)
            SELECT CAST(:i AS uuid), id, true, :a FROM modules WHERE code = :c"""), {"i": cid, "c": code, "a": datetime(2026, 10, 1, tzinfo=timezone.utc)})
    await db.commit()
    return cid


MANUAL = {"contract_type": "mensual", "start_date": "2026-11-01", "min_months": 3, "currency": "USD", "pay_day_from": 1, "pay_day_to": 5,
          "notes": "", "status": "vigente", "tiers": [{"month_from": 1, "month_to": None, "amount": "1500"}]}


@pytest.mark.asyncio
async def test_redraft_from_manual_contract_keeps_history_and_no_duplicate_installments(pg_url, mem):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        await bc.save_provider(db, {**PROVIDER, **ZELLE}, "admin")
        cid = await _company(db, "Empresa USD")
        await billing.save_contract(db, cid, MANUAL)
        assert len(await billing.installments(db, cid, date(2026, 10, 27))) == 2, "como VOLTAGE: noviembre y diciembre"
        assert await bc.manual_redraftable(db, cid) is True

        pre = await bc.prefill(db, cid)
        assert pre["form"]["language"] == "es" and pre["form"]["payment_method"] == "qr", "por defecto: español y QR"
        assert pre["modules"][0]["name_en"] == "Payroll" or pre["modules"][1]["name_en"] == "Payroll"
        form = bc.form_from_manual(await billing.get_contract(db, cid), pre["form"])
        assert {k: form[k] for k in ("contract_type", "start_date", "min_months", "currency", "pay_day_from", "pay_day_to")} == \
            {"contract_type": "mensual", "start_date": "2026-11-01", "min_months": 3, "currency": "USD", "pay_day_from": 1, "pay_day_to": 5}
        assert form["tiers"] == [{"month_from": 1, "month_to": None, "amount": "1500.00"}] and form["from_manual"] is True

        with pytest.raises(billing.BillingConflict, match="registrado a mano"):
            await bc.generate(db, cid, {**form, "from_manual": False}, "admin", put, get)  # sin "desde este contrato": el bloqueo de siempre
        _data, preview, pdf = await bc.build(db, cid, {**form, "language": "es_en", "payment_method": "zelle"}, get)
        assert preview["bilingual"] and preview["number"] == "CX-2026-001" and preview["version"] == 1 and billing.is_pdf(pdf)
        assert await bc.history(db, cid) == [], "la vista previa no guarda nada"

        before = await billing.get_contract(db, cid)
        doc = await bc.generate(db, cid, {**form, "language": "es_en", "payment_method": "zelle"}, "admin", put, get)
        assert (doc["number"], doc["version"]) == ("CX-2026-001", 1), "el redactado es la version 1"
        docs = await bc.documents(db, cid)
        assert [(d["version"], d["is_current"]) for d in docs] == [(1, True)]
        stored = (await bc.current_document(db, cid))["data"]
        assert stored["language"] == "es_en" and stored["payment_method"] == "zelle" and stored["zelle"] == ZELLE
        hist = await bc.history(db, cid)
        assert len(hist) == 1 and hist[0]["source"] == "manual" and hist[0]["replaced_by"] == doc["id"]
        snap = hist[0]["snapshot"]
        assert snap["start_date"] == "2026-11-01" and snap["currency"] == "USD" and snap["tiers"][0]["amount"] == "1500.00" and snap["installments"] == 2
        after = await billing.get_contract(db, cid)
        assert after["id"] == before["id"], "mismo contrato (las alertas y el tablero siguen)"
        insts = await billing.installments(db, cid, date(2026, 10, 27))
        periods = [i["period"] for i in insts]
        assert len(periods) == len(set(periods)) == 2 and [i["seq"] for i in insts] == [1, 2], "cuotas recalculadas sin duplicar"
        assert all(Decimal(str(i["amount"])) == Decimal("1500") for i in insts)
        assert await bc.manual_redraftable(db, cid) is False, "ya es redactado: se edita con versiones"
        doc2 = await bc.generate(db, cid, {**form, "language": "es_en", "payment_method": "zelle", "from_manual": False}, "admin", put, get)
        assert doc2["version"] == 2 and len(await bc.history(db, cid)) == 1

        # con pagos registrados: sigue el bloqueo de siempre y nada cambia
        paid = await _company(db, "Empresa Con Pago")
        await billing.save_contract(db, paid, MANUAL)
        inst = (await billing.installments(db, paid, date(2026, 10, 27)))[0]
        await billing.register_payment(db, paid, {"installment_id": inst["id"], "amount": "1500", "paid_on": "2026-11-02", "method": "transferencia"},
                                       "admin")
        assert await bc.manual_redraftable(db, paid) is False
        with pytest.raises(billing.BillingConflict, match="registrado a mano"):
            await bc.generate(db, paid, {**bc.form_from_manual(await billing.get_contract(db, paid), pre["form"])}, "admin", put, get)
        assert await bc.history(db, paid) == [] and await bc.documents(db, paid) == []
        assert len(await billing.installments(db, paid, date(2026, 10, 27))) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_zelle_fields(pg_url, mem):
    engine, maker = await _session(pg_url)
    async with maker() as db:
        await db.execute(text("UPDATE billing_provider SET zelle_name = DEFAULT, zelle_contact = DEFAULT WHERE id = 1"))
        await db.commit()
        p = await bc.get_provider(db)
        assert p["zelle_name"] == "" and p["zelle_contact"] == "", "vacios hasta que se llenen (valor inicial de la migracion)"
        saved = await bc.save_provider(db, {**PROVIDER, **ZELLE}, "admin")
        assert (saved["zelle_name"], saved["zelle_contact"]) == ("Titular Demo", "zelle@demo.test")
        saved = await bc.save_provider(db, PROVIDER, "admin")
        assert saved["zelle_name"] == "", "el formulario de siempre (sin Zelle) los deja vacios"
    await engine.dispose()
