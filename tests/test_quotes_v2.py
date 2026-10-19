"""Cotizaciones y cuentas de cobro v2 (interruptor quotes_v2), contra Postgres real.

- Desde produccion: trae los cierres del periodo por referencia y talla, no repite
  los ya cobrados (aviso con el CB) y al archivar la cuenta se liberan.
- Valor por prenda: orden operacional, luego precio de la referencia, luego a mano.
- Totales con descuento y retencion (la retencion no resta), numeracion CT/CB y PDF.
- Clientes de documentos anteriores y pago del ultimo uso.
- Cierre de dia (la misma consulta de siempre) y reporte cobrado / por cobrar.
- Otra empresa no ve nada; con el interruptor apagado, 404; rutas con sesion.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services import quotes_v2 as svc
from tests.test_crm_lab_pg import _migration, company, employee, pg_url, reference, run  # noqa: F401  (fixture de Postgres real)

QUOTES_DDL = """
CREATE TABLE IF NOT EXISTS company_users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, full_name text, email text, status text DEFAULT 'active');
CREATE TABLE IF NOT EXISTS mini_panel_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    panel_type VARCHAR(50) NOT NULL DEFAULT 'sales', quote_number VARCHAR(80) NOT NULL, client_name VARCHAR(220) NOT NULL,
    client_document VARCHAR(80), client_address VARCHAR(260), client_phone VARCHAR(80), client_email VARCHAR(180),
    items JSONB NOT NULL DEFAULT '[]'::jsonb, discounts JSONB NOT NULL DEFAULT '[]'::jsonb, payment JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT, signature_data_url TEXT, subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0, discount_total NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total NUMERIC(14, 2) NOT NULL DEFAULT 0, status VARCHAR(30) NOT NULL DEFAULT 'issued', converted_at TIMESTAMPTZ, archived_at TIMESTAMPTZ,
    created_by UUID NULL, created_by_label VARCHAR(180), metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (company_id, quote_number))
"""


async def setup(db, name: str, on: bool = True) -> str:
    from zoneinfo import ZoneInfo

    from app.services import company_locale

    company_locale.CURRENT_TZ.set(ZoneInfo("UTC"))  # pgserver no trae la base de zonas horarias
    for stmt in [s for s in QUOTES_DDL.split(";") if s.strip()] + _migration("024q_quotes_v2") + _migration("024q_quotes_v2"):  # idempotente
        await db.execute(text(stmt))
    await db.commit()
    cid = await company(db, name)
    await db.execute(text("INSERT INTO modules (code, name, category) VALUES ('cotizacion', 'Cotizaciones', 'x') ON CONFLICT (code) DO NOTHING"))
    await db.execute(text("""INSERT INTO company_modules (company_id, module_id, enabled, settings)
        SELECT CAST(:i AS uuid), id, true, CAST(:s AS jsonb) FROM modules WHERE code = 'cotizacion'"""),
                     {"i": cid, "s": '{"quotes_v2": true}' if on else "{}"})
    await db.commit()
    return cid


async def close(db, cid: str, ref_id: str, name: str, size: str, qty: int, when: datetime) -> str:
    cl = str(uuid.uuid4())
    await db.execute(text("""INSERT INTO reference_production_closures (id, company_id, employee_id, reference_id, reference_name, size,
        quantity_finished, closed_at, source_channel) VALUES (:i, :c, 'e', :r, :n, :s, :q, :t, 'telegram')"""),
                     {"i": cl, "c": cid, "r": ref_id, "n": name, "s": size, "q": qty, "t": when})
    await db.commit()
    return cl


NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.date()


def body(lines, origin="production", **over):
    return {"origin": origin, "client": {"name": "Bombón SAS", "document": "900123", "phone": "300", "address": "Cra 1", "email": "a@b.co"},
            "lines": lines, "discounts": [], "payment": {"method": "transferencia", "name": "Bancolombia", "data": "Ahorros 123"}, **over}


def test_desde_produccion_no_cobra_dos_veces_y_archivar_libera(pg_url):  # noqa: F811
    async def go(db):
        cid = await setup(db, "VelvetCobro")
        other = await setup(db, "OtraCobro")
        pant = await reference(db, cid, "PANT SET", cut=20)
        await reference(db, other, "PANT SET", cut=20)
        await close(db, cid, pant["S"], "PANT SET", "S", 4, NOW)
        await close(db, cid, pant["M"], "PANT SET", "M", 6, NOW)
        await close(db, cid, pant["M"], "PANT SET", "M", 9, NOW - timedelta(days=40))  # fuera del periodo
        await db.execute(text("INSERT INTO reference_op_settings (company_id, group_key, value_per_garment) VALUES (:c, 'pantset', 12000)"), {"c": cid})
        await db.commit()

        prod = await svc.from_production(db, cid, TODAY - timedelta(days=6), TODAY)
        assert len(prod["lines"]) == 1
        line = prod["lines"][0]
        assert line["quantity"] == 10 and [s["size"] for s in line["sizes"]] == ["S", "M"] and line["description"] == "PANT SET · S 4 / M 6"
        assert line["unit_price"] == 12000 and line["price_source"] == "op_order" and prod["already_charged"] == []

        line["quantity"] = 999  # la pantalla no decide la cantidad de una linea de produccion
        doc = await svc.create(db, cid, body([line], period={"from": str(TODAY), "to": str(TODAY)}), "Dueña")
        assert doc["document_type"] == "account" and doc["document_number"].startswith(f"CB-{TODAY.year}-")
        assert doc["subtotal"] == 120000 and doc["total"] == 120000 and doc["charged_closures"] == 2
        assert doc["items"][0]["quantity"] == 10 and doc["items"][0]["sizes"] == [{"size": "S", "quantity": 4}, {"size": "M", "quantity": 6}]

        again = await svc.from_production(db, cid, TODAY - timedelta(days=6), TODAY)
        assert again["lines"] == [] and again["already_charged"] == [{"document": doc["document_number"], "quantity": 10}]
        with pytest.raises(svc.QuoteError) as e:
            await svc.create(db, cid, body([line]), "Dueña")
        assert e.value.status == 409 and doc["document_number"] in e.value.detail

        with pytest.raises(svc.QuoteError) as e:  # cierres de otra empresa
            other_cl = await close(db, other, "x", "PANT SET", "S", 1, NOW)
            await svc.create(db, cid, body([{**line, "closure_ids": [other_cl]}]), "Dueña")
        assert e.value.status == 422

        archived = await svc.archive(db, cid, doc["id"])
        assert archived["status"] == "archived" and archived["charged_closures"] == 0
        freed = await svc.from_production(db, cid, TODAY - timedelta(days=6), TODAY)
        assert freed["lines"][0]["quantity"] == 10 and freed["already_charged"] == []
        n = (await db.execute(text("SELECT count(*) FROM quote_closure_charges WHERE company_id = CAST(:c AS uuid) AND released_reason = 'archived'"),
                              {"c": cid})).scalar_one()
        assert n == 2, "el historial del cobro queda"
        assert (await svc.from_production(db, other, TODAY - timedelta(days=6), TODAY))["lines"][0]["quantity"] == 1, "solo esa empresa"

    run(pg_url, go)


def test_valor_por_prenda_con_su_respaldo(pg_url):  # noqa: F811
    async def go(db):
        cid = await setup(db, "VelvetValor")
        a = await reference(db, cid, "Aurora", sizes=("M",))
        await reference(db, cid, "Choco", sizes=("M",))
        await reference(db, cid, "Sin precio", sizes=("M",))
        await db.execute(text("UPDATE product_references SET unit_price = 8000 WHERE company_id = :c AND name IN ('Aurora', 'Choco')"), {"c": cid})
        await db.execute(text("INSERT INTO reference_op_settings (company_id, group_key, value_per_garment) VALUES (:c, 'aurora', 15000)"), {"c": cid})
        await db.commit()
        values = await svc.unit_values(db, cid)
        assert svc.pick_value(values, "aurora") == {"value": 15000.0, "source": "op_order"}
        assert svc.pick_value(values, "choco") == {"value": 8000.0, "source": "reference"}
        assert svc.pick_value(values, "sinprecio") == {"value": None, "source": "manual"}
        refs = {r["name"]: r for r in await svc.reference_options(db, cid)}
        assert refs["Aurora"]["unit_price"] == 15000 and refs["Sin precio"]["price_source"] == "manual"
        assert refs["Aurora"]["sizes"][0]["size"] == "M"
        with pytest.raises(svc.QuoteError) as e:  # sin valor no se emite
            await svc.create(db, cid, body([{"description": "Sin precio · M 3", "quantity": 3, "unit_price": None}], origin="references"), "x")
        assert e.value.status == 422
        assert a

    run(pg_url, go)


def test_totales_numeracion_cliente_pago_y_pdf(pg_url):  # noqa: F811
    async def go(db):
        cid = await setup(db, "VelvetTotales")
        lines = [{"description": "Aurora · M 10", "quantity": 10, "unit_price": 15000, "key": "aurora", "sizes": [{"size": "M", "quantity": 10}]},
                 {"description": "Transporte", "quantity": 1, "unit_price": 20000}]
        doc = await svc.create(db, cid, body(lines, origin="references", discounts=[
            {"name": "Pronto pago", "value": 10000, "kind": "discount"}, {"name": "Retefuente", "percent": 4, "kind": "retention"}]), "Dueña")
        assert doc["document_type"] == "quote" and doc["quote_number"] == f"CT-{TODAY.year}-0001"
        assert doc["subtotal"] == 170000 and doc["discount_total"] == 10000 and doc["retention"] == 6800
        assert doc["total"] == 160000, "la retencion no resta del total (misma regla actual)"
        second = await svc.create(db, cid, body([{"description": "Manual", "quantity": 1, "unit_price": 1}], origin="manual",
                                                client={"name": "Otro cliente"}, payment={"method": "efectivo"}), "Dueña")
        assert second["quote_number"] == f"CT-{TODAY.year}-0002"
        conv = await svc.convert(db, cid, doc["id"])
        assert conv["document_number"] == f"CB-{TODAY.year}-0001" and conv["status"] == "converted"

        d = await svc.defaults(db, cid)
        assert d["payment"]["method"] == "efectivo", "el pago del ultimo uso"
        bombon = next(c for c in d["clients"] if c["client_name"] == "Bombón SAS")
        assert bombon == {"client_name": "Bombón SAS", "client_document": "900123", "client_phone": "300", "client_address": "Cra 1", "client_email": "a@b.co"}

        pdf, name = await svc.pdf(db, cid, conv["id"], None, {"name": "VELVET"})
        assert pdf.startswith(b"%PDF") and name == f"CB-{TODAY.year}-0001.pdf"
        with pytest.raises(svc.QuoteError):
            await svc.create(db, cid, body([], origin="manual"), "x")
        with pytest.raises(svc.QuoteError):
            await svc.create(db, cid, body(lines, origin="manual", client={"name": " "}), "x")

    run(pg_url, go)


def test_historial_reporte_y_cierre_de_dia(pg_url):  # noqa: F811
    import asyncpg

    from app.api.v1.endpoints import day_closing

    async def go(db):
        cid = await setup(db, "VelvetHist")
        one = [{"description": "Aurora · M 2", "quantity": 2, "unit_price": 50000}]
        a = await svc.create(db, cid, body(one, origin="manual", document_type="account"), "Dueña")
        b = await svc.create(db, cid, body(one, origin="manual", document_type="account", client={"name": "Cliente B"}), "Dueña")
        c = await svc.create(db, cid, body(one, origin="references"), "Dueña")
        await svc.mark_paid(db, cid, a["id"], "Dueña")
        with pytest.raises(svc.QuoteError):
            await svc.mark_paid(db, cid, c["id"], "Dueña")  # una cotizacion no se paga
        h = await svc.history(db, cid, "", "active")
        assert {x["id"] for x in h["documents"]} == {b["id"], c["id"]}
        assert h["totals"]["paid"] == {"count": 1, "amount": 100000.0} and h["totals"]["active"]["count"] == 2
        assert [x["id"] for x in (await svc.history(db, cid, "cliente b", "all"))["documents"]] == [b["id"]]
        rep = await svc.report(db, cid, TODAY, TODAY)
        assert (rep["collected"], rep["pending"], rep["billed"], rep["quoted"]) == (100000.0, 100000.0, 200000.0, 100000.0)
        assert {x["client_name"] for x in rep["by_client"]} == {"Bombón SAS", "Cliente B"}
        await svc.archive(db, cid, b["id"])
        assert (await svc.history(db, cid, "", "archived"))["documents"][0]["id"] == b["id"]
        return cid

    cid = run(pg_url, go)

    async def closing():
        conn = await asyncpg.connect(pg_url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            rows, _ = await day_closing._quote_rows(conn, uuid.UUID(cid), "client", NOW - timedelta(hours=1), NOW + timedelta(hours=1))
        finally:
            await conn.close()
        return rows

    rows = asyncio.run(closing())
    assert sum(r["quotes_count"] for r in rows) == 2 and sum(r["quotes_amount"] for r in rows) == 200000, "el Cierre de dia lee los documentos (sin los archivados)"


def test_firma_en_el_bucket_no_en_postgres(pg_url):  # noqa: F811
    import base64
    import io

    from PIL import Image

    from app.services import brand_media

    class Mem:
        def __init__(self):
            self.data = {}

        def put(self, key, data, **_):
            self.data[key] = data

        def get(self, key):
            return self.data[key]

        def delete(self, keys):
            pass

        def list(self, prefix):
            return [k for k in self.data if k.startswith(prefix)]

    mem = Mem()
    brand_media.set_backend(mem)
    buf = io.BytesIO()
    Image.new("RGBA", (300, 100), (0, 0, 0, 255)).save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    async def go(db):
        cid = await setup(db, "VelvetFirma")
        sig = await svc.save_signature(db, cid, data_url, "Dueña")
        key = f"billing/{cid}/signatures/{sig['id']}.png"
        assert key in mem.data and mem.data[key].startswith(b"\x89PNG")
        d = await svc.defaults(db, cid)
        assert d["signature"] == {"id": sig["id"]}
        doc = await svc.create(db, cid, body([{"description": "X", "quantity": 1, "unit_price": 1}], origin="manual", signature_id=sig["id"]), "Dueña")
        stored = (await db.execute(text("SELECT signature_data_url, metadata FROM mini_panel_quotes WHERE id = CAST(:i AS uuid)"), {"i": doc["id"]})).mappings().first()
        assert stored["signature_data_url"] is None and stored["metadata"]["quotes_v2"]["signature_id"] == sig["id"], "en Postgres solo la clave"
        pdf, _ = await svc.pdf(db, cid, doc["id"], "account", {"name": "VELVET"})
        assert pdf.startswith(b"%PDF")
        with pytest.raises(svc.QuoteError):
            await svc.save_signature(db, cid, "data:image/svg+xml;base64,PHN2Zz4=", "x")
        other = await setup(db, "OtraFirma")
        with pytest.raises(svc.QuoteError):  # la firma de otra empresa no sirve
            await svc.create(db, other, body([{"description": "X", "quantity": 1, "unit_price": 1}], origin="manual", signature_id=sig["id"]), "x")

    try:
        run(pg_url, go)
    finally:
        brand_media.set_backend(None)


def test_interruptor_apagado_y_otra_empresa(pg_url):  # noqa: F811
    async def go(db):
        on = await setup(db, "VelvetOn2")
        off = await setup(db, "OtraOff2", on=False)
        assert await svc.is_on(db, on) is True and await svc.is_on(db, off) is False
        doc = await svc.create(db, on, body([{"description": "X", "quantity": 1, "unit_price": 1}], origin="manual"), "x")
        with pytest.raises(svc.QuoteError) as e:
            await svc.get(db, off, doc["id"])
        assert e.value.status == 404
        assert (await svc.history(db, off, "", "all"))["documents"] == []

    run(pg_url, go)


# ---------------------------------------------------------------- rutas
@pytest.mark.asyncio
async def test_rutas_con_sesion_e_interruptor(monkeypatch):
    import app.api.v1.endpoints.companies as companies
    from app.api.v1.endpoints import quotes_v2 as api

    cid = uuid.uuid4()
    req = SimpleNamespace(headers={}, cookies={}, client=None)
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(side_effect=HTTPException(status_code=401, detail="no_session")))
    with pytest.raises(HTTPException) as e:
        await api.owner(cid, req, None, db=None)
    assert e.value.status_code == 401
    monkeypatch.setattr(companies, "require_admin_v2_or_tenant_company_admin", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "is_on", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as e:
        await api.owner(cid, req, "Bearer x", db=None)
    assert e.value.status_code == 404
    for r in api.router.routes:
        assert api.owner in [d.call for d in r.dependant.dependencies], f"{r.path} sin sesión"


def test_resumen_puro():
    rows = [{"client_name": "A", "client_document": "1", "status": "converted", "total": 100, "metadata": json.dumps({"paid_at": "x"})},
            {"client_name": "A", "client_document": "1", "status": "converted", "total": 50, "metadata": {}},
            {"client_name": "B", "client_document": "", "status": "issued", "total": 30, "metadata": {}}]
    out = svc.summarize(rows, date(2026, 10, 1), date(2026, 10, 19))
    assert (out["collected"], out["pending"], out["billed"], out["quoted"]) == (100, 50, 150, 30)
    assert out["by_client"][0] == {"client_name": "A", "client_document": "1", "quoted": 0.0, "billed": 150.0, "collected": 100.0, "pending": 50.0}
