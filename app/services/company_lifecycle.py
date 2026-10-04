"""Ciclo de vida de empresas para la Consola v2+: clonar como demo y eliminar
definitivamente. Todo pasa por un "store" (PgStore en produccion, uno en
memoria en las pruebas) para que la logica se pruebe sin base de datos.

CLONAR COMO DEMO copia SOLO configuracion, con una LISTA BLANCA explicita:
cualquier tabla nueva queda fuera por defecto. Nunca se copian pedidos,
ventas, clientes, empleados, nomina, inventario con saldos, sesiones,
usuarios, bots ni tokens. Ninguna fila copiada conserva el company_id de
origen y las claves con forma de secreto se quitan de los JSON.

ELIMINAR DEFINITIVO reutiliza _company_table_delete / _company_table_count del
reset operativo sobre TODAS las tablas con company_id (incluidas las de
imagenes), en el orden que permitan las llaves foraneas, y al final borra la
fila de companies. Las tablas de auditoria se conservan.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
SECRET_KEY = re.compile(r"token|secret|password|passwd|api[_-]?key|private[_-]?key|webhook|credential|access[_-]?key|signing",
                        re.IGNORECASE)


@dataclass(frozen=True)
class CloneSpec:
    table: str
    remap: dict[str, str] = field(default_factory=dict)   # columna -> tabla clonada a la que apunta
    nullify: tuple[str, ...] = ()                         # columnas que apuntan a datos NO copiados
    scrub: tuple[str, ...] = ()                           # columnas JSON donde se quitan secretos
    drop_data_urls: tuple[str, ...] = ()                  # columnas con imagenes data: (pesadas)


# LISTA BLANCA. El orden importa: una tabla va despues de aquellas a las que apunta.
CLONE_WHITELIST: tuple[CloneSpec, ...] = (
    CloneSpec("company_package_assignments", scrub=("settings", "settings_json")),
    CloneSpec("company_modules", scrub=("settings", "settings_json")),
    CloneSpec("company_branding", scrub=("custom_css_json",), drop_data_urls=("logo_url",)),
    CloneSpec("company_localization"),
    CloneSpec("company_crm_layout", scrub=("settings_json",)),
    CloneSpec("company_crm_launchpad_cards", scrub=("settings_json",)),
    CloneSpec("roles"),
    # Carta: categorias (arbol) y platos, SIN imagenes (viven en
    # hospitality_product_images, que no se copia) y sin el insumo de
    # inventario (el inventario no se copia).
    CloneSpec("carta_categories", remap={"parent_id": "carta_categories"}),
    CloneSpec("carta_items", remap={"category_id": "carta_categories"}, nullify=("inventory_item_id",)),
)
CLONE_TABLES = tuple(spec.table for spec in CLONE_WHITELIST)
# settings_json de companies: solo marca y localizacion.
CLONE_SETTINGS_KEYS = ("branding", "company_branding", "experience", "client_settings")
# Nunca se tocan al eliminar: son el registro de lo que paso.
PURGE_KEEP_TABLES = frozenset({"companies", "admin_audit_log", "clonexa_company_operational_reset_audit"})
# Tablas que guardan imagenes (image_bytes) por empresa: se borran con ella.
IMAGE_TABLES = frozenset({"hospitality_categories", "hospitality_product_images", "carta_purchase_invoices",
                          "fixed_expense_receipts", "expense_attachments", "sanitation_attachments",
                          "whatsapp_delivery_payment_qr"})


# --------------------------------------------------------------- helpers ---
def scrub_secrets(value: Any) -> Any:
    """Copia de un JSON sin las claves con forma de secreto (token, password...)."""
    if isinstance(value, dict):
        return {k: scrub_secrets(v) for k, v in value.items() if not SECRET_KEY.search(str(k))}
    if isinstance(value, list):
        return [scrub_secrets(v) for v in value]
    return value


def _strip_data_urls(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("" if k in ("logo_url", "logo") and str(v or "").startswith("data:") else _strip_data_urls(v))
                for k, v in value.items()}
    return value


def clone_settings(settings: Any, source_id: Any) -> dict:
    """settings_json de la demo: marca y localizacion del origen, kind=demo."""
    store = settings if isinstance(settings, dict) else {}
    out: dict[str, Any] = {}
    for key in CLONE_SETTINGS_KEYS:
        value = store.get(key)
        if key == "experience" and isinstance(value, dict):
            value = {"branding": value.get("branding")} if isinstance(value.get("branding"), dict) else None
        if isinstance(value, dict):
            out[key] = _strip_data_urls(scrub_secrets(value))
    out["kind"] = "demo"
    out["cloned_from"] = {"company_id": str(source_id)}
    return out


def _check_identifier(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"Nombre de tabla o columna invalido: {name!r}")
    return name


# ----------------------------------------------------------------- clonar ---
async def clone_config(store: "Store", source_id: Any, target_id: Any) -> dict[str, int]:
    """Copia la lista blanca de source_id a target_id. Devuelve filas por tabla."""
    source, target = str(source_id), str(target_id)
    columns = await store.columns(CLONE_TABLES)
    id_maps: dict[str, dict[str, str]] = {}
    copied: dict[str, int] = {}
    for spec in CLONE_WHITELIST:
        cols = columns.get(spec.table)
        if not cols or "company_id" not in cols:
            continue  # la tabla no existe en esta base: nada que copiar
        rows = await store.rows(spec.table, source)
        mapping = id_maps.setdefault(spec.table, {})
        if "id" in cols:
            for row in rows:
                mapping[str(row["id"])] = str(uuid.uuid4())
        pending = list(rows)
        done = 0
        while pending:
            progressed = False
            waiting = []
            for row in pending:
                self_ref = [c for c, t in spec.remap.items() if t == spec.table and row.get(c) is not None]
                if any(str(row[c]) in mapping and not store.has_inserted(spec.table, mapping[str(row[c])]) for c in self_ref):
                    waiting.append(row)  # su padre aun no esta copiado
                    continue
                await store.insert(spec.table, _cloned_row(spec, row, cols, target, id_maps), cols)
                done += 1
                progressed = True
            if not progressed:  # ciclo: se copian sin padre
                for row in waiting:
                    clean = {**row, **{c: None for c, t in spec.remap.items() if t == spec.table}}
                    await store.insert(spec.table, _cloned_row(spec, clean, cols, target, id_maps), cols)
                    done += 1
                break
            pending = waiting
        copied[spec.table] = done
    return copied


def _cloned_row(spec: CloneSpec, row: dict, cols: dict[str, str], target: str, id_maps: dict) -> dict:
    out = {}
    for col in cols:
        if col not in row:
            continue
        value = row[col]
        if col == "company_id":
            value = target
        elif col == "id" and str(row["id"]) in id_maps.get(spec.table, {}):
            value = id_maps[spec.table][str(row["id"])]
        elif col in spec.remap:
            value = id_maps.get(spec.remap[col], {}).get(str(value)) if value is not None else None
        elif col in spec.nullify:
            value = None
        elif col in spec.scrub:
            value = scrub_secrets(value)
        elif col in spec.drop_data_urls and str(value or "").startswith("data:"):
            value = None
        out[col] = value
    return out


# ---------------------------------------------------------------- eliminar ---
async def purge_plan(store: "Store", company_id: Any) -> list[dict]:
    """Filas que borraria, por tabla (solo las que tienen filas)."""
    plan = []
    for table in await store.company_tables():
        if table in PURGE_KEEP_TABLES:
            continue
        rows = await store.count(table, company_id)
        if rows:
            plan.append({"table": table, "rows": rows, "images": table in IMAGE_TABLES})
    return plan


class PurgeBlocked(Exception):
    def __init__(self, tables: list[str]):
        super().__init__(", ".join(tables))
        self.tables = tables


async def purge_execute(store: "Store", company_id: Any) -> list[dict]:
    """Borra todas las filas de la empresa y luego la empresa. Si una llave
    foranea impide borrar una tabla, la reintenta despues de las demas; si
    no hay forma, PurgeBlocked (quien llama hace rollback de todo)."""
    remaining = [t for t in await store.company_tables() if t not in PURGE_KEEP_TABLES]
    deleted: dict[str, int] = {}
    while remaining:
        failed = []
        for table in remaining:
            try:
                deleted[table] = deleted.get(table, 0) + await store.delete(table, company_id)
            except DBAPIError:
                failed.append(table)
        if not failed:
            break
        if len(failed) == len(remaining):
            raise PurgeBlocked(failed)
        remaining = failed
    await store.delete_company(company_id)
    return [{"table": t, "rows": n, "images": t in IMAGE_TABLES} for t, n in sorted(deleted.items()) if n]


# ------------------------------------------------------------------ stores ---
class Store:
    """Interfaz minima que usan clonar y eliminar."""

    async def columns(self, tables: Iterable[str]) -> dict[str, dict[str, str]]: ...
    async def rows(self, table: str, company_id: str) -> list[dict]: ...
    async def insert(self, table: str, row: dict, types: dict[str, str]) -> None: ...
    def has_inserted(self, table: str, row_id: str) -> bool: ...
    async def company_tables(self) -> list[str]: ...
    async def count(self, table: str, company_id: Any) -> int: ...
    async def delete(self, table: str, company_id: Any) -> int: ...
    async def delete_company(self, company_id: Any) -> None: ...


class PgStore(Store):
    def __init__(self, db: AsyncSession):
        self.db = db
        self._inserted: set[tuple[str, str]] = set()

    async def columns(self, tables):
        rows = (await self.db.execute(text("""
            SELECT c.table_name, c.column_name, c.udt_name
            FROM information_schema.columns c
            JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
              AND c.table_name = ANY(CAST(:names AS text[]))
            ORDER BY c.table_name, c.ordinal_position
        """), {"names": list(tables)})).mappings().all()
        out: dict[str, dict[str, str]] = {}
        for r in rows:
            out.setdefault(str(r["table_name"]), {})[str(r["column_name"])] = str(r["udt_name"])
        return out

    async def rows(self, table, company_id):
        _check_identifier(table)
        result = await self.db.execute(text(f"SELECT * FROM {table} WHERE company_id::text = :company_id"),
                                       {"company_id": str(company_id)})
        return [dict(r) for r in result.mappings().all()]

    async def insert(self, table, row, types):
        _check_identifier(table)
        names, values, params = [], [], {}
        for i, (col, value) in enumerate(row.items()):
            _check_identifier(col)
            udt = types.get(col, "")
            key = f"p{i}"
            names.append(col)
            if udt in ("json", "jsonb"):
                values.append(f"CAST(:{key} AS {udt})")
                params[key] = None if value is None else (value if isinstance(value, str) else json.dumps(value, default=str))
            elif udt == "uuid":
                values.append(f"CAST(:{key} AS uuid)")
                params[key] = None if value is None else str(value)
            else:
                values.append(f":{key}")
                params[key] = value
        await self.db.execute(text(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(values)})"), params)
        if "id" in row:
            self._inserted.add((table, str(row["id"])))

    def has_inserted(self, table, row_id):
        return (table, str(row_id)) in self._inserted

    async def company_tables(self):
        rows = (await self.db.execute(text("""
            SELECT c.table_name FROM information_schema.columns c
            JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.column_name = 'company_id'
            ORDER BY c.table_name
        """))).mappings().all()
        return [str(r["table_name"]) for r in rows if _IDENT.match(str(r["table_name"]))]

    async def count(self, table, company_id):
        from app.api.v1.endpoints.companies import _company_table_count

        return await _company_table_count(self.db, _check_identifier(table), uuid.UUID(str(company_id)))

    async def delete(self, table, company_id):
        from app.api.v1.endpoints.companies import _company_table_delete

        async with self.db.begin_nested():  # un fallo de llave foranea solo deshace esta tabla
            return await _company_table_delete(self.db, _check_identifier(table), uuid.UUID(str(company_id)))

    async def delete_company(self, company_id):
        await self.db.execute(text("DELETE FROM companies WHERE id = CAST(:id AS uuid)"), {"id": str(company_id)})
