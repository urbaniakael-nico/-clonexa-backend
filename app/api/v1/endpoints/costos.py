"""Modulo COSTOS (049I): egresos, proveedores, cuentas por pagar, caja chica,
recurrentes, presupuesto, exportacion y ARQUEO de caja a ciegas.

Solo empresas con el modulo "costos" (hoy ASADERO EL SOCIO, migracion 021x).
Todos los endpoints exigen sesion de la empresa (o Admin V2) y el modulo:
- dueño (company_admin/dueño) y administrador/gerente registran libremente;
  por encima del tope configurable el egreso queda pendiente del dueño;
- el cajero solo registra gastos pagados con el efectivo del cajon (siempre
  pendientes de aprobacion) y hace su arqueo a ciegas.
Las compras de insumos suben la existencia y recalculan el costo promedio
ponderado cuando el egreso queda aprobado. Nada se digita dos veces: las
ventas salen de los pedidos y la nomina del modulo de nomina.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_company_user_for_tenant, require_enabled_module
from app.services import carta as carta_engine
from app.services import costos as engine
from app.services import media_storage
from app.services.session_cutoff import load_policy, zone
from app.web.admin_v2_routes import _active_session as active_admin_v2_session

router = APIRouter()
MODULE_CODE = "costos"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _f(value: Any) -> float:
    return float(engine.money(value))


# ---------------------------------------------------------------- auth ---
async def _actor(company_id: uuid.UUID, request: Request, authorization: str | None, db: AsyncSession) -> dict:
    await require_enabled_module(db, company_id, MODULE_CODE)
    if await active_admin_v2_session(request, db):
        return {"id": "", "name": "Admin V2", "kind": "owner", "role": "admin_v2"}
    user = await require_company_user_for_tenant(db, authorization, company_id)
    role = str(getattr(user, "role", "") or "")
    settings = getattr(user, "settings_json", None) or {}
    mini = settings.get("mini_panel") if isinstance(settings, dict) and isinstance(settings.get("mini_panel"), dict) else {}
    kind = engine.role_kind(role)
    if kind == "other" and str(mini.get("type") or "") == "caja":
        kind = "cashier"
    return {"id": str(user.id), "name": _clean(getattr(user, "full_name", "") or getattr(user, "email", "") or "Usuario", 180),
            "kind": kind, "role": role}


async def require_costos_user(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                              db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(company_id, request, authorization, db)
    if actor["kind"] == "other":
        raise HTTPException(status_code=403, detail="role_not_allowed")
    return actor


async def require_costos_manager(company_id: uuid.UUID, request: Request, authorization: str | None = Header(default=None),
                                 db: AsyncSession = Depends(get_db)) -> dict:
    actor = await _actor(company_id, request, authorization, db)
    if actor["kind"] not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Solo el dueño o el administrador.")
    return actor


async def costos_enabled(db: AsyncSession, company_id: Any) -> bool:
    try:
        await require_enabled_module(db, uuid.UUID(str(company_id)), MODULE_CODE)
        return True
    except HTTPException:
        return False
    except Exception:
        return False


# ------------------------------------------------------------ helpers ---
async def load_settings(db: AsyncSession, company_id: uuid.UUID) -> dict:
    result = await db.execute(text("""
        SELECT cm.settings FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:company_id AS uuid) AND LOWER(m.code) = 'costos' LIMIT 1
    """), {"company_id": str(company_id)})
    row = result.mappings().first()
    raw = row["settings"] if row else {}
    if isinstance(raw, str):
        raw = json.loads(raw or "{}")
    return engine.settings_of(raw)


async def default_center(db: AsyncSession, company_id: uuid.UUID) -> str:
    result = await db.execute(text("""
        SELECT id FROM cost_centers WHERE company_id = CAST(:company_id AS uuid) AND active IS TRUE
        ORDER BY is_default DESC, created_at LIMIT 1
    """), {"company_id": str(company_id)})
    row = result.mappings().first()
    if row:
        return str(row["id"])
    new_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO cost_centers (id, company_id, name, is_default) VALUES (CAST(:id AS uuid), CAST(:company_id AS uuid), 'Principal', true)
        ON CONFLICT (company_id, name) DO NOTHING
    """), {"id": new_id, "company_id": str(company_id)})
    return new_id


async def _today(db: AsyncSession, company_id: uuid.UUID) -> date:
    policy = await load_policy(db, company_id)
    return datetime.now(timezone.utc).astimezone(zone(policy["timezone"])).date()


def _expense_payload(row: dict, lines: list[dict] | None = None, has_attachment: bool = False) -> dict:
    return {
        "id": str(row["id"]), "expense_date": row["expense_date"].isoformat() if row.get("expense_date") else None,
        "category": row["category"], "category_label": engine.CATEGORIES.get(row["category"], row["category"]),
        "supplier_id": str(row["supplier_id"]) if row.get("supplier_id") else None, "supplier_name": row.get("supplier_name") or "",
        "description": row.get("description") or "", "subtotal": _f(row["subtotal"]), "iva": _f(row["iva"]),
        "retention": _f(row["retention"]), "total": _f(row["total"]), "payment_method": row["payment_method"],
        "paid_from": row["paid_from"], "status": row["status"],
        "due_date": row["due_date"].isoformat() if row.get("due_date") else None,
        "paid": bool(row.get("paid_at")) or row["payment_method"] != "credito",
        "cost_center_id": str(row["cost_center_id"]) if row.get("cost_center_id") else None,
        "created_by_name": row.get("created_by_name") or "", "created_by_kind": row.get("created_by_kind") or "",
        "approved_by_name": row.get("approved_by_name") or "", "rejected_reason": row.get("rejected_reason") or "",
        "inventory_applied": bool(row.get("inventory_applied")), "has_attachment": has_attachment,
        "lines": lines or [],
    }


async def _fetch_expense(db: AsyncSession, company_id: uuid.UUID, expense_id: Any) -> dict:
    try:
        clean = str(uuid.UUID(str(expense_id)))
    except ValueError:
        raise HTTPException(status_code=404, detail="Egreso no encontrado.")
    row = (await db.execute(text("SELECT * FROM expenses WHERE id = CAST(:id AS uuid) AND company_id = CAST(:company_id AS uuid)"),
                            {"id": clean, "company_id": str(company_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Egreso no encontrado.")
    return dict(row)


async def _lines(db: AsyncSession, company_id: uuid.UUID, expense_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT l.*, COALESCE(NULLIF(i.name_reference, ''), NULLIF(i.name, ''), i.sku) AS insumo
        FROM expense_lines l LEFT JOIN inventory_items i ON i.id = l.inventory_item_id AND i.company_id = l.company_id
        WHERE l.company_id = CAST(:company_id AS uuid) AND l.expense_id = CAST(:id AS uuid)
    """), {"company_id": str(company_id), "id": expense_id})).mappings().all()
    return [{"inventory_item_id": str(r["inventory_item_id"]), "insumo": r.get("insumo") or "Insumo",
             "quantity": float(r["quantity"]), "purchase_unit": r["purchase_unit"], "unit_price": float(r["unit_price"]),
             "total": _f(r["total"])} for r in rows]


async def apply_purchase(db: AsyncSession, company_id: uuid.UUID, expense: dict, iva_is_cost: bool) -> None:
    """Compra aprobada -> sube existencia y recalcula el costo promedio
    ponderado de cada insumo (en su unidad de consumo). Una sola vez."""
    if expense.get("inventory_applied") or expense.get("status") != "aprobado":
        return
    lines = (await db.execute(text("SELECT * FROM expense_lines WHERE company_id = CAST(:c AS uuid) AND expense_id = CAST(:e AS uuid)"),
                              {"c": str(company_id), "e": str(expense["id"])})).mappings().all()
    subtotal = engine.dec(expense.get("subtotal"))
    iva_factor = (Decimal("1") + engine.dec(expense.get("iva")) / subtotal) if (iva_is_cost and subtotal > 0) else Decimal("1")
    for line in lines:
        item = (await db.execute(text("""
            SELECT id, current_stock, min_stock, avg_cost, units_per_purchase, status FROM inventory_items
            WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) FOR UPDATE
        """), {"id": str(line["inventory_item_id"]), "c": str(company_id)})).mappings().first()
        if not item:
            continue
        qty = engine.dec(line["consumption_qty"])
        unit_cost = engine.dec(line["unit_cost"]) * iva_factor
        new_avg = carta_engine.weighted_average(item["current_stock"], item["avg_cost"], qty, unit_cost)
        before = engine.dec(item["current_stock"])
        after = before + qty
        await db.execute(text("""
            UPDATE inventory_items
               SET current_stock = :after, avg_cost = :avg, entry_price = :entry,
                   status = CASE WHEN :after > min_stock THEN 'active' ELSE status END, updated_at = now()
             WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
        """), {"after": after, "avg": new_avg, "entry": engine.dec(line["unit_price"]) * iva_factor,
               "id": str(line["inventory_item_id"]), "c": str(company_id)})
        await db.execute(text("""
            INSERT INTO inventory_movements (id, company_id, item_id, movement_type, quantity_delta, stock_before, stock_after,
                                             source_module, source_ref, notes, created_at, updated_at)
            VALUES (CAST(:mid AS uuid), CAST(:c AS uuid), CAST(:id AS uuid), 'purchase', :qty, :before, :after,
                    'costos', :ref, :notes, now(), now())
        """), {"mid": str(uuid.uuid4()), "c": str(company_id), "id": str(line["inventory_item_id"]), "qty": qty,
               "before": before, "after": after, "ref": str(expense["id"]),
               "notes": f"Compra {expense.get('supplier_name') or ''}".strip()})
    await db.execute(text("UPDATE expenses SET inventory_applied = true, updated_at = now() WHERE id = CAST(:e AS uuid) AND company_id = CAST(:c AS uuid)"),
                     {"e": str(expense["id"]), "c": str(company_id)})


async def open_cashier_session(db: AsyncSession, company_id: uuid.UUID, user_id: str | None = None) -> dict | None:
    """Turno de caja abierto (del cajero, o el ultimo abierto de la empresa)."""
    params = {"company_id": str(company_id)}
    where = ""
    if user_id:
        where = "AND user_id = CAST(:user_id AS uuid)"
        params["user_id"] = user_id
    row = (await db.execute(text(f"""
        SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions
        WHERE company_id = CAST(:company_id AS uuid) AND panel_type = 'caja' AND status IN ('active', 'break') {where}
        ORDER BY started_at DESC LIMIT 1
    """), params)).mappings().first()
    return dict(row) if row else None


# --------------------------------------------------------- configuracion ---
@router.get("/companies/{company_id}/settings")
async def get_settings(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_costos_manager)) -> dict:
    centers = (await db.execute(text("SELECT id, name, is_default, active FROM cost_centers WHERE company_id = CAST(:c AS uuid) ORDER BY is_default DESC, name"),
                                {"c": str(company_id)})).mappings().all()
    return {"settings": await load_settings(db, company_id), "categories": engine.CATEGORIES,
            "payment_methods": engine.PAYMENT_METHODS, "paid_from": engine.PAID_FROM,
            "cost_centers": [{"id": str(c["id"]), "name": c["name"], "is_default": c["is_default"], "active": c["active"]} for c in centers],
            "actor": actor}


class SettingsIn(BaseModel):
    approval_threshold: float = Field(ge=0)
    drawer_base: float = Field(ge=0)
    iva_is_cost: bool = True


@router.put("/companies/{company_id}/settings")
async def save_settings(company_id: uuid.UUID, payload: SettingsIn, db: AsyncSession = Depends(get_db),
                        actor: dict = Depends(require_costos_manager)) -> dict:
    if actor["kind"] != "owner":
        raise HTTPException(status_code=403, detail="El tope de aprobación y la base del cajón los define el dueño.")
    current = await load_settings(db, company_id)
    current.update(payload.model_dump())
    await db.execute(text("""
        UPDATE company_modules SET settings = COALESCE(settings, '{}'::jsonb) || CAST(:s AS jsonb), updated_at = now()
        WHERE company_id = CAST(:c AS uuid) AND module_id = (SELECT id FROM modules WHERE LOWER(code) = 'costos' LIMIT 1)
    """), {"s": json.dumps(current), "c": str(company_id)})
    await db.commit()
    return await get_settings(company_id, db, actor)


class CenterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


@router.post("/companies/{company_id}/cost-centers")
async def create_center(company_id: uuid.UUID, payload: CenterIn, db: AsyncSession = Depends(get_db),
                        actor: dict = Depends(require_costos_manager)) -> dict:
    await default_center(db, company_id)
    await db.execute(text("INSERT INTO cost_centers (company_id, name) VALUES (CAST(:c AS uuid), :n) ON CONFLICT (company_id, name) DO NOTHING"),
                     {"c": str(company_id), "n": _clean(payload.name, 120)})
    await db.commit()
    return await get_settings(company_id, db, actor)


# ------------------------------------------------------------ proveedores ---
class SupplierIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=180)
    nit: str = Field(default="", max_length=40)
    contact_name: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=60)
    email: str = Field(default="", max_length=160)
    payment_terms: str = Field(default="", max_length=240)
    credit_days: int = Field(default=0, ge=0, le=365)
    active: bool = True


@router.get("/companies/{company_id}/suppliers")
async def list_suppliers(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    rows = (await db.execute(text("""
        SELECT s.*, COALESCE(SUM(e.total) FILTER (WHERE e.status <> 'rechazado'), 0) AS purchased,
               COUNT(e.id) FILTER (WHERE e.status <> 'rechazado') AS purchases, MAX(e.expense_date) AS last_purchase
        FROM suppliers s LEFT JOIN expenses e ON e.supplier_id = s.id AND e.company_id = s.company_id
        WHERE s.company_id = CAST(:c AS uuid) GROUP BY s.id ORDER BY lower(s.name)
    """), {"c": str(company_id)})).mappings().all()
    return {"suppliers": [{"id": str(r["id"]), "name": r["name"], "nit": r["nit"], "contact_name": r["contact_name"],
                           "phone": r["phone"], "email": r["email"], "payment_terms": r["payment_terms"],
                           "credit_days": r["credit_days"], "active": r["active"], "purchased": _f(r["purchased"]),
                           "purchases": int(r["purchases"] or 0),
                           "last_purchase": r["last_purchase"].isoformat() if r.get("last_purchase") else None} for r in rows]}


@router.post("/companies/{company_id}/suppliers")
async def create_supplier(company_id: uuid.UUID, payload: SupplierIn, db: AsyncSession = Depends(get_db),
                          actor: dict = Depends(require_costos_manager)) -> dict:
    await db.execute(text("""
        INSERT INTO suppliers (company_id, name, nit, contact_name, phone, email, payment_terms, credit_days, active)
        VALUES (CAST(:c AS uuid), :name, :nit, :contact_name, :phone, :email, :payment_terms, :credit_days, :active)
    """), {"c": str(company_id), **{k: (_clean(v, 240) if isinstance(v, str) else v) for k, v in payload.model_dump().items()}})
    await db.commit()
    return await list_suppliers(company_id, db, actor)


@router.put("/companies/{company_id}/suppliers/{supplier_id}")
async def update_supplier(company_id: uuid.UUID, supplier_id: uuid.UUID, payload: SupplierIn, db: AsyncSession = Depends(get_db),
                          actor: dict = Depends(require_costos_manager)) -> dict:
    result = await db.execute(text("""
        UPDATE suppliers SET name = :name, nit = :nit, contact_name = :contact_name, phone = :phone, email = :email,
               payment_terms = :payment_terms, credit_days = :credit_days, active = :active, updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"c": str(company_id), "id": str(supplier_id), **{k: (_clean(v, 240) if isinstance(v, str) else v) for k, v in payload.model_dump().items()}})
    if not getattr(result, "rowcount", 1):
        raise HTTPException(status_code=404, detail="Proveedor no encontrado.")
    await db.commit()
    return await list_suppliers(company_id, db, actor)


@router.get("/companies/{company_id}/price-variation")
async def price_variation(company_id: uuid.UUID, inventory_item_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          _a: dict = Depends(require_costos_manager)) -> dict:
    rows = (await db.execute(text("""
        SELECT e.expense_date AS date, e.created_at, e.supplier_name, s.name AS supplier, l.unit_cost, l.unit_price, l.purchase_unit
        FROM expense_lines l JOIN expenses e ON e.id = l.expense_id AND e.company_id = l.company_id
        LEFT JOIN suppliers s ON s.id = e.supplier_id
        WHERE l.company_id = CAST(:c AS uuid) AND l.inventory_item_id = CAST(:i AS uuid) AND e.status <> 'rechazado'
    """), {"c": str(company_id), "i": str(inventory_item_id)})).mappings().all()
    purchases = engine.price_variation([{**dict(r), "supplier": r.get("supplier") or r.get("supplier_name") or "Sin proveedor",
                                         "date": r["date"].isoformat() if r.get("date") else ""} for r in rows])
    by_supplier: dict[str, list[float]] = {}
    for p in purchases:
        by_supplier.setdefault(p["supplier"], []).append(p["unit_cost"])
    return {"purchases": [{k: v for k, v in p.items() if k in {"date", "supplier", "unit_cost", "unit_price", "purchase_unit", "change_pct"}}
                          for p in purchases],
            "by_supplier": [{"supplier": k, "avg_unit_cost": round(sum(v) / len(v), 4), "purchases": len(v)} for k, v in by_supplier.items()]}


# --------------------------------------------------------------- egresos ---
class ExpenseLineIn(BaseModel):
    inventory_item_id: str
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)


class ExpenseIn(BaseModel):
    expense_date: date | None = None
    category: str
    supplier_id: str | None = None
    supplier_name: str = Field(default="", max_length=180)
    description: str = Field(default="", max_length=1000)
    subtotal: float | None = Field(default=None, ge=0)
    iva: float = Field(default=0, ge=0)
    retention: float = Field(default=0, ge=0)
    payment_method: str = "efectivo"
    paid_from: str = "banco"
    due_date: date | None = None
    cost_center_id: str | None = None
    petty_fund_id: str | None = None
    lines: list[ExpenseLineIn] = Field(default_factory=list)


async def create_expense_row(db: AsyncSession, company_id: uuid.UUID, payload: ExpenseIn, actor: dict, *,
                             recurring_id: str | None = None) -> dict:
    if payload.category not in engine.CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoría inválida.")
    if payload.payment_method not in engine.PAYMENT_METHODS or payload.paid_from not in engine.PAID_FROM:
        raise HTTPException(status_code=400, detail="Método de pago inválido.")
    if actor["kind"] == "cashier" and (payload.paid_from != "cajon" or payload.lines):
        raise HTTPException(status_code=403, detail="Desde la caja solo se registran gastos pagados con el efectivo del cajón.")
    settings = await load_settings(db, company_id)
    today = await _today(db, company_id)
    insumos = await _insumos(db, company_id) if payload.lines else {}
    lines = []
    for line in payload.lines:
        item = insumos.get(line.inventory_item_id)
        if not item:
            raise HTTPException(status_code=400, detail="Insumo no encontrado en tu inventario.")
        consumption_qty = carta_engine.to_consumption(line.quantity, item)
        line_total = engine.money(Decimal(str(line.quantity)) * Decimal(str(line.unit_price)))
        unit_cost = (line_total / consumption_qty) if consumption_qty > 0 else Decimal("0")
        lines.append({"inventory_item_id": line.inventory_item_id, "quantity": line.quantity,
                      "purchase_unit": item.get("purchase_unit") or "unidad", "unit_price": line.unit_price,
                      "total": line_total, "consumption_qty": consumption_qty, "unit_cost": unit_cost})
    subtotal = payload.subtotal if payload.subtotal is not None else float(sum((l["total"] for l in lines), Decimal("0")))
    try:
        t = engine.totals(subtotal, payload.iva, payload.retention)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Revisa los valores: la retención no puede superar el valor.") from exc
    if t["total"] <= 0:
        raise HTTPException(status_code=400, detail="El egreso debe tener un valor.")
    if payload.payment_method == "credito" and not payload.due_date:
        raise HTTPException(status_code=400, detail="Una compra a crédito necesita fecha de vencimiento.")
    session_id = None
    if payload.paid_from == "cajon":
        session = await open_cashier_session(db, company_id, actor["id"] if actor["kind"] == "cashier" else None)
        if not session:
            raise HTTPException(status_code=409, detail="No hay un turno de caja abierto para sacar ese efectivo del cajón.")
        session_id = str(session["id"])
    status_value = engine.initial_status(actor["kind"], t["total"], settings["approval_threshold"])
    expense_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO expenses (id, company_id, cost_center_id, expense_date, category, supplier_id, supplier_name, description,
                              subtotal, iva, retention, total, payment_method, paid_from, status, due_date, paid_at,
                              recurring_id, cashier_session_id, petty_fund_id, created_by_id, created_by_name, created_by_kind,
                              approved_by_name, approved_at)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:cc AS uuid), :d, :category, CAST(NULLIF(:supplier_id, '') AS uuid),
                :supplier_name, :description, :subtotal, :iva, :retention, :total, :pm, :pf, :status, :due,
                CASE WHEN :pm = 'credito' THEN NULL ELSE now() END, CAST(NULLIF(:rec, '') AS uuid), CAST(NULLIF(:sess, '') AS uuid),
                CAST(NULLIF(:fund, '') AS uuid), :by_id, :by_name, :by_kind,
                CASE WHEN :status = 'aprobado' THEN :by_name ELSE '' END, CASE WHEN :status = 'aprobado' THEN now() ELSE NULL END)
    """), {"id": expense_id, "c": str(company_id), "cc": payload.cost_center_id or await default_center(db, company_id),
           "d": payload.expense_date or today, "category": payload.category, "supplier_id": payload.supplier_id or "",
           "supplier_name": _clean(payload.supplier_name, 180), "description": _clean(payload.description, 1000),
           **{k: t[k] for k in ("subtotal", "iva", "retention", "total")}, "pm": payload.payment_method, "pf": payload.paid_from,
           "status": status_value, "due": payload.due_date, "rec": recurring_id or "", "sess": session_id or "",
           "fund": payload.petty_fund_id or "", "by_id": actor["id"], "by_name": actor["name"], "by_kind": actor["kind"]})
    for line in lines:
        await db.execute(text("""
            INSERT INTO expense_lines (company_id, expense_id, inventory_item_id, quantity, purchase_unit, unit_price, total, consumption_qty, unit_cost)
            VALUES (CAST(:c AS uuid), CAST(:e AS uuid), CAST(:i AS uuid), :q, :pu, :up, :t, :cq, :uc)
        """), {"c": str(company_id), "e": expense_id, "i": line["inventory_item_id"], "q": line["quantity"], "pu": line["purchase_unit"],
               "up": line["unit_price"], "t": line["total"], "cq": line["consumption_qty"], "uc": line["unit_cost"]})
    expense = await _fetch_expense(db, company_id, expense_id)
    await apply_purchase(db, company_id, expense, settings["iva_is_cost"])
    return await _fetch_expense(db, company_id, expense_id)


async def _insumos(db: AsyncSession, company_id: uuid.UUID) -> dict[str, dict]:
    from app.api.v1.endpoints.carta import load_insumos

    return await load_insumos(db, company_id)


@router.get("/companies/{company_id}/insumos")
async def list_insumos(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    """Insumos para registrar compras (con su unidad de compra)."""
    items = await _insumos(db, company_id)
    return {"insumos": [{"id": k, "name": v["name"], "item_type": v.get("item_type") or "venta_directa",
                         "purchase_unit": v.get("purchase_unit") or "unidad", "consumption_unit": v.get("consumption_unit") or "unidad",
                         "units_per_purchase": float(v.get("units_per_purchase") or 1)} for k, v in items.items()]}


@router.post("/companies/{company_id}/expenses")
async def create_expense(company_id: uuid.UUID, payload: ExpenseIn, db: AsyncSession = Depends(get_db),
                         actor: dict = Depends(require_costos_user)) -> dict:
    expense = await create_expense_row(db, company_id, payload, actor)
    await db.commit()
    return _expense_payload(expense, await _lines(db, company_id, str(expense["id"])))


@router.get("/companies/{company_id}/expenses")
async def list_expenses(company_id: uuid.UUID, start: date | None = None, end: date | None = None,
                        status: str | None = None, db: AsyncSession = Depends(get_db),
                        actor: dict = Depends(require_costos_manager)) -> dict:
    await generate_recurring(db, company_id)
    today = await _today(db, company_id)
    start = start or today.replace(day=1)
    end = end or today
    params = {"c": str(company_id), "s": start, "e": end}
    where = ""
    if status:
        where = "AND e.status = :status"
        params["status"] = status
    rows = (await db.execute(text(f"""
        SELECT e.*, (a.image_bytes IS NOT NULL) AS has_attachment FROM expenses e
        LEFT JOIN expense_attachments a ON a.expense_id = e.id AND a.company_id = e.company_id
        WHERE e.company_id = CAST(:c AS uuid) AND e.expense_date BETWEEN :s AND :e {where}
        ORDER BY e.expense_date DESC, e.created_at DESC LIMIT 500
    """), params)).mappings().all()
    items = [_expense_payload(dict(r), has_attachment=bool(r.get("has_attachment"))) for r in rows]
    return {"start": start.isoformat(), "end": end.isoformat(), "expenses": items,
            "total": _f(sum(Decimal(str(i["total"])) for i in items if i["status"] != "rechazado"))}


class DecisionIn(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.post("/companies/{company_id}/expenses/{expense_id}/approve")
async def approve_expense(company_id: uuid.UUID, expense_id: str, db: AsyncSession = Depends(get_db),
                          actor: dict = Depends(require_costos_manager)) -> dict:
    expense = await _fetch_expense(db, company_id, expense_id)
    settings = await load_settings(db, company_id)
    if expense["status"] != "pendiente":
        raise HTTPException(status_code=409, detail="Ese egreso ya no está pendiente.")
    if not engine.can_approve(actor["kind"], expense["total"], settings["approval_threshold"]):
        raise HTTPException(status_code=403, detail="Por su valor, este egreso lo aprueba el dueño.")
    await db.execute(text("""
        UPDATE expenses SET status = 'aprobado', approved_by_name = :n, approved_at = now(), updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'pendiente'
    """), {"n": actor["name"], "id": str(expense["id"]), "c": str(company_id)})
    await apply_purchase(db, company_id, {**expense, "status": "aprobado"}, settings["iva_is_cost"])
    await db.commit()
    return _expense_payload(await _fetch_expense(db, company_id, expense_id), await _lines(db, company_id, str(expense["id"])))


@router.post("/companies/{company_id}/expenses/{expense_id}/reject")
async def reject_expense(company_id: uuid.UUID, expense_id: str, payload: DecisionIn, db: AsyncSession = Depends(get_db),
                         actor: dict = Depends(require_costos_manager)) -> dict:
    expense = await _fetch_expense(db, company_id, expense_id)
    settings = await load_settings(db, company_id)
    if expense["status"] != "pendiente":
        raise HTTPException(status_code=409, detail="Ese egreso ya no está pendiente.")
    if not engine.can_approve(actor["kind"], expense["total"], settings["approval_threshold"]):
        raise HTTPException(status_code=403, detail="Por su valor, este egreso lo decide el dueño.")
    if not _clean(payload.reason):
        raise HTTPException(status_code=400, detail="Escribe por qué se rechaza.")
    await db.execute(text("""
        UPDATE expenses SET status = 'rechazado', rejected_reason = :r, approved_by_name = :n, approved_at = now(), updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'pendiente'
    """), {"r": _clean(payload.reason), "n": actor["name"], "id": str(expense["id"]), "c": str(company_id)})
    await db.commit()
    return _expense_payload(await _fetch_expense(db, company_id, expense_id))


class PayIn(BaseModel):
    paid_from: str = "banco"


@router.post("/companies/{company_id}/expenses/{expense_id}/pay")
async def pay_expense(company_id: uuid.UUID, expense_id: str, payload: PayIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_costos_manager)) -> dict:
    expense = await _fetch_expense(db, company_id, expense_id)
    if expense["payment_method"] != "credito" or expense.get("paid_at"):
        raise HTTPException(status_code=409, detail="Ese egreso no es una cuenta por pagar pendiente.")
    if payload.paid_from not in {"banco", "caja_chica", "cajon"}:
        raise HTTPException(status_code=400, detail="Origen del pago inválido.")
    session_id = ""
    if payload.paid_from == "cajon":
        session = await open_cashier_session(db, company_id)
        if not session:
            raise HTTPException(status_code=409, detail="No hay un turno de caja abierto para pagar con el efectivo del cajón.")
        session_id = str(session["id"])
    await db.execute(text("""
        UPDATE expenses SET paid_at = now(), paid_from = :pf, cashier_session_id = COALESCE(cashier_session_id, CAST(NULLIF(:s, '') AS uuid)),
               updated_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"pf": payload.paid_from, "s": session_id, "id": str(expense["id"]), "c": str(company_id)})
    await db.commit()
    return _expense_payload(await _fetch_expense(db, company_id, expense_id))


@router.get("/companies/{company_id}/payables")
async def payables(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    today = await _today(db, company_id)
    rows = (await db.execute(text("""
        SELECT * FROM expenses WHERE company_id = CAST(:c AS uuid) AND payment_method = 'credito'
          AND paid_at IS NULL AND status <> 'rechazado' ORDER BY due_date NULLS LAST
    """), {"c": str(company_id)})).mappings().all()
    items = []
    for r in rows:
        item = _expense_payload(dict(r))
        item["overdue"] = bool(r["due_date"] and r["due_date"] < today)
        item["due_this_week"] = engine.due_this_week(r["due_date"], today)
        items.append(item)
    return {"payables": items, "total": _f(sum(Decimal(str(i["total"])) for i in items)),
            "due_this_week_total": _f(sum(Decimal(str(i["total"])) for i in items if i["due_this_week"]))}


@router.post("/companies/{company_id}/expenses/{expense_id}/attachment")
async def upload_attachment(company_id: uuid.UUID, expense_id: str, image: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                            actor: dict = Depends(require_costos_user)) -> dict:
    expense = await _fetch_expense(db, company_id, expense_id)
    if actor["kind"] == "cashier" and expense.get("created_by_id") != actor["id"]:
        raise HTTPException(status_code=403, detail="Solo puedes adjuntar el soporte de tus propios gastos.")
    raw = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="La foto es demasiado grande.")
    settings = await load_settings(db, company_id)
    used = (await db.execute(text("SELECT COALESCE(SUM(size_bytes), 0) AS used FROM expense_attachments WHERE company_id = CAST(:c AS uuid)"),
                             {"c": str(company_id)})).mappings().first()
    if int((used or {}).get("used") or 0) > int(settings["attachments_quota_mb"]) * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Se llenó el cupo de soportes de la empresa.")
    await db.execute(text("""
        INSERT INTO expense_attachments (company_id, expense_id) VALUES (CAST(:c AS uuid), CAST(:e AS uuid))
        ON CONFLICT (company_id, expense_id) DO NOTHING
    """), {"c": str(company_id), "e": str(expense["id"])})
    await media_storage.save_image(db, table="expense_attachments", key_columns={"company_id": str(company_id), "expense_id": str(expense["id"])},
                                   raw=raw, content_type=(image.content_type or "").lower())
    await db.execute(text("UPDATE expense_attachments SET size_bytes = COALESCE(length(image_bytes), 0) WHERE company_id = CAST(:c AS uuid) AND expense_id = CAST(:e AS uuid)"),
                     {"c": str(company_id), "e": str(expense["id"])})
    await db.commit()
    return {"ok": True}


@router.get("/companies/{company_id}/expenses/{expense_id}/attachment")
async def get_attachment(company_id: uuid.UUID, expense_id: str, db: AsyncSession = Depends(get_db),
                         _a: dict = Depends(require_costos_manager)) -> Response:
    expense = await _fetch_expense(db, company_id, expense_id)
    image = await media_storage.get_image(db, table="expense_attachments", key_columns={"company_id": str(company_id), "expense_id": str(expense["id"])})
    if not image:
        raise HTTPException(status_code=404, detail="Sin soporte.")
    return Response(content=image[0], media_type=image[1])


# ------------------------------------------------------------ caja chica ---
class FundIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(..., ge=0)
    responsible_name: str = Field(default="", max_length=160)


class ReplenishIn(BaseModel):
    amount: float = Field(..., gt=0)
    note: str = Field(default="", max_length=500)


@router.get("/companies/{company_id}/petty-cash")
async def petty_cash(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    rows = (await db.execute(text("""
        SELECT f.*,
               COALESCE((SELECT SUM(amount) FROM petty_cash_moves m WHERE m.fund_id = f.id), 0) AS replenished,
               COALESCE((SELECT SUM(total) FROM expenses e WHERE e.petty_fund_id = f.id AND e.company_id = f.company_id
                          AND e.paid_from = 'caja_chica' AND e.status <> 'rechazado'), 0) AS spent
        FROM petty_cash_funds f WHERE f.company_id = CAST(:c AS uuid) ORDER BY f.created_at
    """), {"c": str(company_id)})).mappings().all()
    return {"funds": [{"id": str(r["id"]), "name": r["name"], "amount": _f(r["amount"]), "responsible_name": r["responsible_name"],
                       "active": r["active"], "replenished": _f(r["replenished"]), "spent": _f(r["spent"]),
                       "balance": _f(engine.dec(r["amount"]) + engine.dec(r["replenished"]) - engine.dec(r["spent"])),
                       "to_replenish": _f(engine.dec(r["spent"]) - engine.dec(r["replenished"]))} for r in rows]}


@router.post("/companies/{company_id}/petty-cash")
async def create_fund(company_id: uuid.UUID, payload: FundIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_costos_manager)) -> dict:
    await db.execute(text("""
        INSERT INTO petty_cash_funds (company_id, cost_center_id, name, amount, responsible_name)
        VALUES (CAST(:c AS uuid), CAST(:cc AS uuid), :n, :a, :r)
    """), {"c": str(company_id), "cc": await default_center(db, company_id), "n": _clean(payload.name, 120), "a": payload.amount,
           "r": _clean(payload.responsible_name, 160)})
    await db.commit()
    return await petty_cash(company_id, db, actor)


@router.post("/companies/{company_id}/petty-cash/{fund_id}/replenish")
async def replenish_fund(company_id: uuid.UUID, fund_id: uuid.UUID, payload: ReplenishIn, db: AsyncSession = Depends(get_db),
                         actor: dict = Depends(require_costos_manager)) -> dict:
    exists = (await db.execute(text("SELECT id FROM petty_cash_funds WHERE id = CAST(:f AS uuid) AND company_id = CAST(:c AS uuid)"),
                               {"f": str(fund_id), "c": str(company_id)})).mappings().first()
    if not exists:
        raise HTTPException(status_code=404, detail="Caja chica no encontrada.")
    await db.execute(text("""
        INSERT INTO petty_cash_moves (company_id, fund_id, amount, note, created_by_name) VALUES (CAST(:c AS uuid), CAST(:f AS uuid), :a, :n, :by)
    """), {"c": str(company_id), "f": str(fund_id), "a": payload.amount, "n": _clean(payload.note), "by": actor["name"]})
    await db.commit()
    return await petty_cash(company_id, db, actor)


# ------------------------------------------------------------ recurrentes ---
class RecurringIn(BaseModel):
    category: str
    supplier_id: str | None = None
    supplier_name: str = Field(default="", max_length=180)
    description: str = Field(default="", max_length=500)
    subtotal: float = Field(..., gt=0)
    iva: float = Field(default=0, ge=0)
    retention: float = Field(default=0, ge=0)
    payment_method: str = "transferencia"
    paid_from: str = "banco"
    day_of_month: int = Field(default=1, ge=1, le=28)
    active: bool = True


@router.get("/companies/{company_id}/recurring")
async def list_recurring(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    rows = (await db.execute(text("SELECT * FROM recurring_expenses WHERE company_id = CAST(:c AS uuid) ORDER BY day_of_month, category"),
                             {"c": str(company_id)})).mappings().all()
    return {"recurring": [{"id": str(r["id"]), "category": r["category"], "category_label": engine.CATEGORIES.get(r["category"], r["category"]),
                           "supplier_name": r["supplier_name"], "description": r["description"], "subtotal": _f(r["subtotal"]),
                           "iva": _f(r["iva"]), "retention": _f(r["retention"]), "payment_method": r["payment_method"],
                           "paid_from": r["paid_from"], "day_of_month": r["day_of_month"], "active": r["active"],
                           "last_generated_month": r["last_generated_month"]} for r in rows]}


@router.post("/companies/{company_id}/recurring")
async def create_recurring(company_id: uuid.UUID, payload: RecurringIn, db: AsyncSession = Depends(get_db),
                           actor: dict = Depends(require_costos_manager)) -> dict:
    if payload.category not in engine.CATEGORIES or payload.paid_from == "cajon":
        raise HTTPException(status_code=400, detail="Categoría u origen inválido para un gasto recurrente.")
    await db.execute(text("""
        INSERT INTO recurring_expenses (company_id, cost_center_id, category, supplier_id, supplier_name, description, subtotal, iva,
                                        retention, payment_method, paid_from, day_of_month, active)
        VALUES (CAST(:c AS uuid), CAST(:cc AS uuid), :category, CAST(NULLIF(:sid, '') AS uuid), :sn, :d, :sub, :iva, :ret, :pm, :pf, :day, :active)
    """), {"c": str(company_id), "cc": await default_center(db, company_id), "category": payload.category, "sid": payload.supplier_id or "",
           "sn": _clean(payload.supplier_name, 180), "d": _clean(payload.description), "sub": payload.subtotal, "iva": payload.iva,
           "ret": payload.retention, "pm": payload.payment_method, "pf": payload.paid_from, "day": payload.day_of_month, "active": payload.active})
    await db.commit()
    return await list_recurring(company_id, db, actor)


async def generate_recurring(db: AsyncSession, company_id: uuid.UUID, today: date | None = None) -> int:
    """Crea los gastos recurrentes del mes que ya tocan (idempotente)."""
    today = today or await _today(db, company_id)
    rows = (await db.execute(text("SELECT * FROM recurring_expenses WHERE company_id = CAST(:c AS uuid) AND active IS TRUE"),
                             {"c": str(company_id)})).mappings().all()
    created = 0
    system = {"id": "", "name": "Gasto recurrente", "kind": "manager", "role": "sistema"}
    for r in rows:
        if not engine.recurring_due(r["day_of_month"], r["last_generated_month"], today):
            continue
        claimed = await db.execute(text("""
            UPDATE recurring_expenses SET last_generated_month = :m
            WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND last_generated_month <> :m
        """), {"m": today.strftime("%Y-%m"), "id": str(r["id"]), "c": str(company_id)})
        if not getattr(claimed, "rowcount", 1):
            continue
        due = today + timedelta(days=15) if r["payment_method"] == "credito" else None
        await create_expense_row(db, company_id, ExpenseIn(
            expense_date=today.replace(day=max(1, min(28, int(r["day_of_month"])))), category=r["category"],
            supplier_id=str(r["supplier_id"]) if r.get("supplier_id") else None, supplier_name=r["supplier_name"],
            description=r["description"] or "Gasto recurrente", subtotal=float(r["subtotal"]), iva=float(r["iva"]),
            retention=float(r["retention"]), payment_method=r["payment_method"], paid_from=r["paid_from"], due_date=due,
            cost_center_id=str(r["cost_center_id"]) if r.get("cost_center_id") else None,
        ), system, recurring_id=str(r["id"]))
        created += 1
    if created:
        await db.commit()
    return created


async def run_recurring_all(db: AsyncSession) -> None:
    """Desde el ciclo de fondo: genera los recurrentes de cada empresa con Costos."""
    rows = (await db.execute(text("""
        SELECT cm.company_id FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE LOWER(m.code) = 'costos' AND cm.enabled IS TRUE
    """))).mappings().all()
    for row in rows:
        await generate_recurring(db, uuid.UUID(str(row["company_id"])))


# ------------------------------------------------------------ presupuesto ---
class BudgetIn(BaseModel):
    budgets: dict[str, float]


async def _budget_rows(db: AsyncSession, company_id: uuid.UUID, month: date) -> list[dict]:
    budgets = {r["category"]: r["monthly_amount"] for r in (await db.execute(text(
        "SELECT category, monthly_amount FROM budgets WHERE company_id = CAST(:c AS uuid)"), {"c": str(company_id)})).mappings().all()}
    first = month.replace(day=1)
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    real = {r["category"]: r["spent"] for r in (await db.execute(text("""
        SELECT category, SUM(subtotal + iva) AS spent FROM expenses
        WHERE company_id = CAST(:c AS uuid) AND status <> 'rechazado' AND expense_date >= :s AND expense_date < :e
        GROUP BY category
    """), {"c": str(company_id), "s": first, "e": nxt})).mappings().all()}
    return engine.budget_status(budgets, real)


@router.get("/companies/{company_id}/budget")
async def get_budget(company_id: uuid.UUID, month: date | None = None, db: AsyncSession = Depends(get_db),
                     _a: dict = Depends(require_costos_manager)) -> dict:
    month = month or await _today(db, company_id)
    return {"month": month.strftime("%Y-%m"), "rows": await _budget_rows(db, company_id, month), "categories": engine.CATEGORIES}


@router.put("/companies/{company_id}/budget")
async def save_budget(company_id: uuid.UUID, payload: BudgetIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_costos_manager)) -> dict:
    for category, amount in payload.budgets.items():
        if category not in engine.CATEGORIES or amount < 0:
            raise HTTPException(status_code=400, detail="Categoría o valor inválido.")
        await db.execute(text("""
            INSERT INTO budgets (company_id, category, monthly_amount) VALUES (CAST(:c AS uuid), :cat, :a)
            ON CONFLICT (company_id, category) DO UPDATE SET monthly_amount = EXCLUDED.monthly_amount, updated_at = now()
        """), {"c": str(company_id), "cat": category, "a": amount})
    await db.commit()
    return await get_budget(company_id, None, db, actor)


# ------------------------------------------------------------ exportar ---
@router.get("/companies/{company_id}/export")
async def export_csv(company_id: uuid.UUID, start: date, end: date, db: AsyncSession = Depends(get_db),
                     _a: dict = Depends(require_costos_manager)) -> Response:
    rows = (await db.execute(text("""
        SELECT e.*, s.nit, c.name AS center FROM expenses e
        LEFT JOIN suppliers s ON s.id = e.supplier_id LEFT JOIN cost_centers c ON c.id = e.cost_center_id
        WHERE e.company_id = CAST(:c AS uuid) AND e.expense_date BETWEEN :s AND :e ORDER BY e.expense_date, e.created_at
    """), {"c": str(company_id), "s": start, "e": end})).mappings().all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Fecha", "Categoría", "Proveedor", "NIT", "Descripción", "Subtotal", "IVA", "Retención", "Total pagado",
                     "Método de pago", "Origen", "Estado", "Pagado", "Vence", "Centro de costo", "Registró", "Aprobó"])
    for r in rows:
        writer.writerow([r["expense_date"].isoformat(), engine.CATEGORIES.get(r["category"], r["category"]), r["supplier_name"],
                         r.get("nit") or "", r["description"], _f(r["subtotal"]), _f(r["iva"]), _f(r["retention"]), _f(r["total"]),
                         engine.PAYMENT_METHODS.get(r["payment_method"], r["payment_method"]), engine.PAID_FROM.get(r["paid_from"], r["paid_from"]),
                         r["status"], "sí" if (r.get("paid_at") or r["payment_method"] != "credito") else "no",
                         r["due_date"].isoformat() if r.get("due_date") else "", r.get("center") or "", r["created_by_name"], r["approved_by_name"]])
    return Response(content="﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="egresos_{start}_{end}.csv"'})


# ------------------------------------------------------------ arqueo ---
async def expected_for_session(db: AsyncSession, company_id: uuid.UUID, session: dict, settings: dict) -> dict:
    """Lo que deberia haber en el cajon al cerrar ESTE turno de caja."""
    start = session["started_at"]
    end = session.get("ended_at") or datetime.now(timezone.utc)
    user_id = str(session.get("user_id") or "")
    sales = (await db.execute(text("""
        SELECT COALESCE(SUM(total), 0) AS total FROM hospitality_orders
        WHERE company_id = CAST(:c AS uuid) AND status = 'cerrado' AND payment_method = 'cash'
          AND closed_at >= :s AND closed_at <= :e
          AND (
                metadata->'closed_by'->>'id' = :u
             OR (metadata->'closed_by' IS NULL AND metadata->'cashier_sale'->'by'->>'id' = :u)
             OR (metadata->'closed_by' IS NULL AND metadata->'cashier_sale' IS NULL)
          )
    """), {"c": str(company_id), "s": start, "e": end, "u": user_id})).mappings().first()
    spent = (await db.execute(text("""
        SELECT COALESCE(SUM(total) FILTER (WHERE category <> 'retiro_dueno'), 0) AS expenses,
               COALESCE(SUM(total) FILTER (WHERE category = 'retiro_dueno'), 0) AS withdrawals
        FROM expenses WHERE company_id = CAST(:c AS uuid) AND cashier_session_id = CAST(:sid AS uuid)
          AND paid_from = 'cajon' AND status <> 'rechazado'
    """), {"c": str(company_id), "sid": str(session["id"])})).mappings().first()
    base = engine.dec(settings["drawer_base"])
    return {"base": base, "cash_sales": engine.money((sales or {}).get("total")),
            "drawer_expenses": engine.money((spent or {}).get("expenses")), "withdrawals": engine.money((spent or {}).get("withdrawals")),
            "expected": engine.expected_cash(base, (sales or {}).get("total"), (spent or {}).get("expenses"), (spent or {}).get("withdrawals")),
            "shift_start": start, "shift_end": session.get("ended_at")}


def _count_payload(row: dict, reveal: bool = True) -> dict:
    data = {"id": str(row["id"]), "cashier_name": row["cashier_name"], "counted": _f(row["counted"]), "status": row["status"],
            "observation": row.get("observation") or "", "blind": bool(row.get("blind")),
            "performed_by_name": row.get("performed_by_name") or "", "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "shift_start": row["shift_start"].isoformat() if row.get("shift_start") else None,
            "shift_end": row["shift_end"].isoformat() if row.get("shift_end") else None}
    if reveal:
        data.update({"base": _f(row["base"]), "cash_sales": _f(row["cash_sales"]), "drawer_expenses": _f(row["drawer_expenses"]),
                     "withdrawals": _f(row["withdrawals"]), "expected": _f(row["expected"]), "difference": _f(row["difference"]),
                     "result": engine.difference_label(row["difference"])})
    return data


async def _insert_count(db: AsyncSession, company_id: uuid.UUID, session: dict, counted: Decimal, denominations: dict,
                        observation: str, actor: dict, blind: bool) -> dict:
    settings = await load_settings(db, company_id)
    exp = await expected_for_session(db, company_id, session, settings)
    difference = engine.money(counted - exp["expected"])
    status_value = "cerrado" if difference == 0 or observation else "pendiente_observacion"
    cashier = (await db.execute(text("SELECT full_name FROM company_users WHERE id = CAST(:u AS uuid)"),
                                {"u": str(session.get("user_id") or uuid.UUID(int=0))})).mappings().first()
    count_id = str(uuid.uuid4())
    try:
        await db.execute(text("""
            INSERT INTO cash_counts (id, company_id, cost_center_id, cashier_session_id, cashier_user_id, cashier_name, shift_start, shift_end,
                                     base, cash_sales, drawer_expenses, withdrawals, expected, counted, difference, denominations,
                                     observation, status, blind, performed_by_name, performed_by_kind, closed_at)
            VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:cc AS uuid), CAST(:sid AS uuid), :uid, :cname, :ss, :se,
                    :base, :sales, :exp, :wd, :expected, :counted, :diff, CAST(:den AS jsonb), :obs, :status, :blind, :by, :kind,
                    CASE WHEN :status = 'cerrado' THEN now() ELSE NULL END)
        """), {"id": count_id, "c": str(company_id), "cc": await default_center(db, company_id), "sid": str(session["id"]),
               "uid": str(session.get("user_id") or ""), "cname": (cashier or {}).get("full_name") or actor["name"],
               "ss": exp["shift_start"], "se": exp["shift_end"], "base": exp["base"], "sales": exp["cash_sales"],
               "exp": exp["drawer_expenses"], "wd": exp["withdrawals"], "expected": exp["expected"], "counted": counted,
               "diff": difference, "den": json.dumps(denominations or {}), "obs": _clean(observation, 1000), "status": status_value,
               "blind": blind, "by": actor["name"], "kind": actor["kind"]})
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Este turno ya tiene su arqueo registrado.") from exc
    await db.commit()
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid)"), {"id": count_id})).mappings().first()
    return dict(row)


class BlindCountIn(BaseModel):
    counted: float | None = Field(default=None, ge=0)
    denominations: dict[str, int] | None = None


@router.get("/companies/{company_id}/caja/config")
async def cashier_config(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_costos_user)) -> dict:
    # Nunca incluye lo esperado: el arqueo del cajero es a ciegas.
    return {"enabled": True, "categories": {k: v for k, v in engine.CATEGORIES.items() if k not in {"compras", "retiro_dueno"}},
            "denominations": engine.DENOMINATIONS, "kind": actor["kind"]}


@router.get("/companies/{company_id}/caja/arqueo")
async def my_current_count(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_costos_user)) -> dict:
    """Arqueo ya registrado del turno abierto del cajero (para retomarlo si
    se recargo el panel). Si aun no conto, no devuelve nada esperado."""
    session = await open_cashier_session(db, company_id, actor["id"] or None)
    if not session:
        return {"count": None}
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND cashier_session_id = CAST(:s AS uuid)"),
                            {"c": str(company_id), "s": str(session["id"])})).mappings().first()
    if not row:
        return {"count": None}
    return {"count": {**_count_payload(dict(row)), "needs_observation": row["status"] == "pendiente_observacion"}}


@router.post("/companies/{company_id}/caja/arqueo")
async def blind_count(company_id: uuid.UUID, payload: BlindCountIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_costos_user)) -> dict:
    """El cajero digita lo que conto. Queda fijo; solo entonces se revela lo esperado."""
    session = await open_cashier_session(db, company_id, actor["id"] or None)
    if not session:
        raise HTTPException(status_code=409, detail="No tienes un turno de caja abierto.")
    try:
        from_denominations = engine.count_from_denominations({int(k): v for k, v in (payload.denominations or {}).items()})
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Revisa el conteo por billetes y monedas.") from exc
    counted = from_denominations if from_denominations is not None else (engine.money(payload.counted) if payload.counted is not None else None)
    if counted is None:
        raise HTTPException(status_code=400, detail="Digita cuánto efectivo contaste.")
    row = await _insert_count(db, company_id, session, counted, payload.denominations or {}, "", actor, blind=True)
    return {**_count_payload(row), "needs_observation": row["status"] == "pendiente_observacion"}


class ObservationIn(BaseModel):
    observation: str = Field(..., min_length=1, max_length=1000)


@router.post("/companies/{company_id}/caja/arqueo/{count_id}/observation")
async def count_observation(company_id: uuid.UUID, count_id: uuid.UUID, payload: ObservationIn, db: AsyncSession = Depends(get_db),
                            actor: dict = Depends(require_costos_user)) -> dict:
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid)"),
                            {"id": str(count_id), "c": str(company_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado.")
    if actor["kind"] == "cashier" and row["cashier_user_id"] != actor["id"]:
        raise HTTPException(status_code=403, detail="Ese arqueo no es tuyo.")
    if row["status"] != "pendiente_observacion":
        raise HTTPException(status_code=409, detail="Ese arqueo ya está cerrado.")
    if not _clean(payload.observation):
        raise HTTPException(status_code=400, detail="La observación es obligatoria cuando hay diferencia.")
    await db.execute(text("""
        UPDATE cash_counts SET observation = :o, status = 'cerrado', closed_at = now()
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND status = 'pendiente_observacion'
    """), {"o": _clean(payload.observation, 1000), "id": str(count_id), "c": str(company_id)})
    await db.commit()
    row = (await db.execute(text("SELECT * FROM cash_counts WHERE id = CAST(:id AS uuid)"), {"id": str(count_id)})).mappings().first()
    return _count_payload(dict(row))


@router.get("/companies/{company_id}/arqueos")
async def list_counts(company_id: uuid.UUID, start: date | None = None, end: date | None = None,
                      db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    today = await _today(db, company_id)
    start = start or today - timedelta(days=30)
    end = end or today
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT * FROM cash_counts WHERE company_id = CAST(:c AS uuid) AND created_at::date BETWEEN :s AND :e ORDER BY created_at DESC
    """), {"c": str(company_id), "s": start, "e": end})).mappings().all()]
    by_cashier: dict[str, dict] = {}
    for r in rows:
        row = by_cashier.setdefault(r["cashier_name"], {"cashier_name": r["cashier_name"], "counts": 0, "shortage": Decimal("0"), "surplus": Decimal("0")})
        row["counts"] += 1
        diff = engine.dec(r["difference"])
        if diff < 0:
            row["shortage"] += -diff
        elif diff > 0:
            row["surplus"] += diff
    return {"counts": [_count_payload(r) for r in rows],
            "by_cashier": [{**v, "shortage": _f(v["shortage"]), "surplus": _f(v["surplus"])} for v in
                           sorted(by_cashier.values(), key=lambda v: -v["shortage"])]}


@router.get("/companies/{company_id}/arqueos/pending")
async def pending_counts(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), _a: dict = Depends(require_costos_manager)) -> dict:
    """Turnos de caja cerrados sin arqueo (p. ej. los cerro el corte diario).
    Aqui SI se ve lo esperado: el dueño revisa, no cuenta su propio turno."""
    settings = await load_settings(db, company_id)
    rows = [dict(r) for r in (await db.execute(text("""
        SELECT s.id, s.user_id, s.started_at, s.ended_at, s.status, s.closed_reason, u.full_name
        FROM mini_panel_work_sessions s LEFT JOIN company_users u ON u.id = s.user_id
        WHERE s.company_id = CAST(:c AS uuid) AND s.panel_type = 'caja' AND s.status = 'finished'
          AND s.started_at >= now() - interval '45 days'
          AND NOT EXISTS (SELECT 1 FROM cash_counts k WHERE k.company_id = s.company_id AND k.cashier_session_id = s.id)
        ORDER BY s.started_at DESC
    """), {"c": str(company_id)})).mappings().all()]
    out = []
    for s in rows:
        exp = await expected_for_session(db, company_id, s, settings)
        out.append({"session_id": str(s["id"]), "cashier_name": s.get("full_name") or "Cajero",
                    "shift_start": s["started_at"].isoformat(), "shift_end": s["ended_at"].isoformat() if s.get("ended_at") else None,
                    "closed_reason": s.get("closed_reason") or "", "base": _f(exp["base"]), "cash_sales": _f(exp["cash_sales"]),
                    "drawer_expenses": _f(exp["drawer_expenses"]), "withdrawals": _f(exp["withdrawals"]), "expected": _f(exp["expected"])})
    return {"pending": out}


class AdminCountIn(BaseModel):
    session_id: str
    counted: float = Field(..., ge=0)
    observation: str = Field(default="", max_length=1000)


@router.post("/companies/{company_id}/arqueos/admin")
async def admin_count(company_id: uuid.UUID, payload: AdminCountIn, db: AsyncSession = Depends(get_db),
                      actor: dict = Depends(require_costos_manager)) -> dict:
    try:
        sid = str(uuid.UUID(payload.session_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    session = (await db.execute(text("""
        SELECT id, user_id, started_at, ended_at, status FROM mini_panel_work_sessions
        WHERE id = CAST(:id AS uuid) AND company_id = CAST(:c AS uuid) AND panel_type = 'caja' AND status = 'finished'
    """), {"id": sid, "c": str(company_id)})).mappings().first()
    if not session:
        raise HTTPException(status_code=404, detail="Turno de caja no encontrado o aún abierto.")
    settings = await load_settings(db, company_id)
    exp = await expected_for_session(db, company_id, dict(session), settings)
    if engine.money(Decimal(str(payload.counted)) - exp["expected"]) != 0 and not _clean(payload.observation):
        raise HTTPException(status_code=400, detail="Hay diferencia: la observación es obligatoria.")
    row = await _insert_count(db, company_id, dict(session), engine.money(payload.counted), {}, payload.observation, actor, blind=False)
    return _count_payload(row)


class CashierExpenseIn(BaseModel):
    category: str
    subtotal: float = Field(..., gt=0)
    description: str = Field(..., min_length=1, max_length=1000)
    supplier_name: str = Field(default="", max_length=180)


@router.post("/companies/{company_id}/caja/gastos")
async def cashier_expense(company_id: uuid.UUID, payload: CashierExpenseIn, db: AsyncSession = Depends(get_db),
                          actor: dict = Depends(require_costos_user)) -> dict:
    """Gasto pagado con el efectivo del cajon desde el panel de caja: queda
    pendiente de aprobacion y baja lo esperado en el arqueo de este turno."""
    if payload.category in {"compras", "retiro_dueno"}:
        raise HTTPException(status_code=400, detail="Esa categoría no se registra desde la caja.")
    expense = await create_expense_row(db, company_id, ExpenseIn(
        category=payload.category, subtotal=payload.subtotal, description=payload.description, supplier_name=payload.supplier_name,
        payment_method="efectivo", paid_from="cajon"), {**actor, "kind": "cashier" if actor["kind"] == "cashier" else actor["kind"]})
    await db.commit()
    return _expense_payload(expense)


# ------------------------------------------------------------ alertas ---
@router.get("/companies/{company_id}/alerts")
async def costos_alerts(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), actor: dict = Depends(require_costos_manager)) -> dict:
    await generate_recurring(db, company_id)
    pay = await payables(company_id, db, actor)
    pending = (await db.execute(text("""
        SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS total FROM expenses WHERE company_id = CAST(:c AS uuid) AND status = 'pendiente'
    """), {"c": str(company_id)})).mappings().first()
    budget = [r for r in await _budget_rows(db, company_id, await _today(db, company_id)) if r["over"]]
    counts = await pending_counts(company_id, db, actor)
    return {
        "pending_approvals": int((pending or {}).get("n") or 0), "pending_total": _f((pending or {}).get("total")),
        "due_this_week": [p for p in pay["payables"] if p["due_this_week"]], "due_this_week_total": pay["due_this_week_total"],
        "over_budget": budget, "pending_counts": len(counts["pending"]),
    }
