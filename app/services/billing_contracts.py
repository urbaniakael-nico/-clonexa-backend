"""Facturacion · Redactar contrato, Datos del proveedor y Recordatorio de pago.

Se apoya en app/services/billing.py (no lo reemplaza): el contrato redactado se
guarda con billing.save_contract (cuotas y alertas como cualquier otro) y su
PDF con billing.add_contract_file (bucket, zona privada).

Reglas (puras, probadas sin base):
- Fecha de inicio = inicio del servicio. Con dias de prueba, los periodos
  pagados empiezan despues de la prueba (inicio + dias); la cuota 1 es el mes
  de ese dia (la misma regla de billing.schedule_for).
- Compromiso minimo = suma de las cuotas 1..permanencia segun los tramos.
- Numero CX-AAAA-NNN (consecutivo del ano), version y codigo de verificacion
  (hash corto del contenido). Editar => version siguiente; la anterior queda.
- El texto legal sale de contract_templates/contrato_clonexa_es.txt (editable);
  un dato opcional vacio sale como linea para llenar a mano.
- Recordatorio: contrato vigente con "Recordatorio en el panel" encendido; se
  muestra desde pay_day_from hasta el fin del mes de la cuota del mes (fecha
  LOCAL de la empresa) si los pagos por validar + validados no cubren su valor.
  Nunca suspende ni bloquea nada.
Toda consulta filtra por company_id.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import billing
from app.services.billing import BillingConflict, BillingInvalid

TEMPLATE = Path(__file__).resolve().parent / "contract_templates" / "contrato_clonexa_es.txt"
CURRENCIES = ("COP", "USD")
MAX_PROOF_BYTES = 5 * 1024 * 1024
MAX_QR_BYTES = 5 * 1024 * 1024
BLANK = None  # valor de un campo opcional vacio: linea para llenar a mano
PROVIDER_FIELDS = {"name": 160, "trade_name": 80, "doc_id": 60, "email": 160, "phones": 300, "city": 80}
CLIENT_FIELDS = {"legal_name": 160, "doc_id": 40, "representative": 120, "address": 200, "email": 160, "phone": 40}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^[0-9+()\-.\s]{5,40}$")
MONTHS_SHORT = ("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic.")


# ------------------------------------------------------------ texto ---
_UNITS = ("cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece",
          "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós",
          "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve")
_TENS = ("", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")
_HUNDREDS = ("", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
             "ochocientos", "novecientos")


def _below_thousand(n: int) -> str:
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    parts = [_HUNDREDS[hundreds]] if hundreds else []
    if rest:
        if rest < 30:
            parts.append(_UNITS[rest])
        else:
            tens, unit = divmod(rest, 10)
            parts.append(_TENS[tens] + (f" y {_UNITS[unit]}" if unit else ""))
    return " ".join(parts)


def words_es(n: int) -> str:
    """Numero entero en letras (espanol): 1300000 -> "un millón trescientos mil"."""
    n = int(n)
    if n < 0:
        return "menos " + words_es(-n)
    if n < 1000:
        return _below_thousand(n) if n else "cero"
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = "mil" if thousands == 1 else f"{_apocope(_below_thousand(thousands))} mil"
        return head + (f" {_below_thousand(rest)}" if rest else "")
    if n < 1_000_000_000_000:
        millions, rest = divmod(n, 1_000_000)
        head = "un millón" if millions == 1 else f"{_apocope(words_es(millions))} millones"
        return head + (f" {words_es(rest)}" if rest else "")
    return str(n)


def _apocope(words: str) -> str:
    """"veintiuno" -> "veintiún", "uno" -> "un" delante de mil/millones/sustantivo."""
    if words.endswith("veintiuno"):
        return words[:-len("veintiuno")] + "veintiún"
    if words.endswith("uno"):
        return words[:-3] + "un"
    return words


def amount_words(value: Any, currency: str) -> str:
    d = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    whole = int(d)
    cents = int((d - whole) * 100)
    noun = "pesos colombianos" if currency == "COP" else "dólares estadounidenses"
    base = _apocope(words_es(whole))
    if base.endswith(("millón", "millones")):
        base += " de"
    out = f"{base} {noun}"
    if cents:
        out += f" con {cents:02d}/100"
    return out


def money_text(value: Any, currency: str) -> str:
    d = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    if currency == "USD":
        return f"US${d:,.2f}"
    whole = f"{int(d):,}".replace(",", ".")
    cents = int((d - int(d)) * 100)
    return f"${whole}{f',{cents:02d}' if cents else ''} COP"


def date_long(d: date) -> str:
    return f"{d.day} de {billing.MONTHS_ES[d.month - 1]} de {d.year}"


def month_long(d: date) -> str:
    return f"{billing.MONTHS_ES[d.month - 1]} de {d.year}"


def window_text(due_from: date, due_to: date) -> str:
    return f"{due_from.day}–{due_to.day} {MONTHS_SHORT[due_from.month - 1]} {due_from.year}"


def month_end(d: date) -> date:
    return billing.add_months(d.replace(day=1), 1) - timedelta(days=1)


# --------------------------------------------------------- validacion ---
def _text(raw: dict, name: str, limit: int, field: Optional[str] = None) -> str:
    value = str(raw.get(name) or "").strip()
    if len(value) > limit:
        raise BillingInvalid(field or name, f"máximo {limit} caracteres")
    return value


def validate_provider(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise BillingInvalid("proveedor", "datos inválidos")
    out = {k: _text(raw, k, n) for k, n in PROVIDER_FIELDS.items()}
    if not out["name"]:
        raise BillingInvalid("name", "escribe el nombre del proveedor")
    if out["email"] and not _EMAIL.match(out["email"]):
        raise BillingInvalid("email", "correo inválido")
    return out


def validate_draft(raw: dict, types: set[str], active_codes: Optional[set[str]] = None) -> dict:
    """Formulario de "Redactar contrato" -> datos limpios. Lo economico pasa por
    billing.validate_contract (mismas reglas que el contrato de siempre)."""
    if not isinstance(raw, dict):
        raise BillingInvalid("contrato", "datos inválidos")
    currency = str(raw.get("currency") or "COP").strip().upper()
    if currency not in CURRENCIES:
        raise BillingInvalid("currency", "moneda COP o USD")
    try:
        start = date.fromisoformat(str(raw.get("start_date") or ""))
    except ValueError:
        raise BillingInvalid("start_date", "fecha inválida (AAAA-MM-DD)") from None
    trial = raw.get("trial_days", 0)
    try:
        trial = int(trial or 0)
    except (TypeError, ValueError):
        raise BillingInvalid("trial_days", "debe ser un número entero") from None
    if not 0 <= trial <= 90:
        raise BillingInvalid("trial_days", "entre 0 y 90 días")
    paid_start = start + timedelta(days=trial)
    core = billing.validate_contract({"contract_type": raw.get("contract_type"), "start_date": paid_start.isoformat(),
                                      "min_months": raw.get("min_months", 0), "currency": currency,
                                      "pay_day_from": raw.get("pay_day_from"), "pay_day_to": raw.get("pay_day_to"),
                                      "notes": raw.get("notes") or "", "status": "vigente", "tiers": raw.get("tiers")}, types)
    surcharge = None
    sur = raw.get("surcharge") if isinstance(raw.get("surcharge"), dict) else {}
    if sur.get("amount") not in (None, "", 0, "0"):
        amount = billing.money(sur.get("amount"))
        try:
            frm = int(sur.get("from_month") or 0)
        except (TypeError, ValueError):
            raise BillingInvalid("surcharge.from_month", "debe ser un número entero") from None
        if not 1 <= frm <= 120:
            raise BillingInvalid("surcharge.from_month", "desde el mes 1 al 120")
        if amount > 0:
            surcharge = {"amount": amount, "from_month": frm}
    client_raw = raw.get("client") if isinstance(raw.get("client"), dict) else {}
    client = {k: _text(client_raw, k, n, f"client.{k}") for k, n in CLIENT_FIELDS.items()}
    if client["email"] and not _EMAIL.match(client["email"]):
        raise BillingInvalid("client.email", "correo inválido")
    if client["phone"] and not _PHONE.match(client["phone"]):
        raise BillingInvalid("client.phone", "teléfono inválido")
    modules = []
    for i, m in enumerate(raw.get("modules") or []):
        if not isinstance(m, dict):
            raise BillingInvalid(f"modules[{i}]", "módulo inválido")
        code = _text(m, "code", 60, f"modules[{i}].code").lower()
        if not code:
            continue
        if active_codes is not None and code not in active_codes:
            raise BillingInvalid(f"modules[{i}]", "ese módulo no está activo en la empresa")
        modules.append({"code": code, "name": _text(m, "name", 80, f"modules[{i}].name") or code,
                        "line": _text(m, "line", 200, f"modules[{i}].line")})
    if len(modules) > 40:
        raise BillingInvalid("modules", "máximo 40 módulos")
    if not modules:
        raise BillingInvalid("modules", "elige al menos un módulo del alcance")
    return {"contract_type": core["contract_type"], "start_date": start, "trial_days": trial, "paid_start": paid_start,
            "min_months": core["min_months"], "currency": currency, "pay_day_from": core["pay_day_from"],
            "pay_day_to": core["pay_day_to"], "tiers": core["tiers"], "surcharge": surcharge, "notes": core["notes"],
            "jurisdiction_city": _text(raw, "jurisdiction_city", 80), "sign_city": _text(raw, "sign_city", 80),
            "client": client, "modules": modules}


def contract_payload(data: dict) -> dict:
    """Lo que guarda billing.save_contract (cuotas desde el primer periodo pagado)."""
    return {"contract_type": data["contract_type"], "start_date": data["paid_start"].isoformat(), "min_months": data["min_months"],
            "currency": data["currency"], "pay_day_from": data["pay_day_from"], "pay_day_to": data["pay_day_to"],
            "notes": data["notes"], "status": "vigente",
            "tiers": [{"month_from": t["month_from"], "month_to": t["month_to"], "amount": str(t["amount"])} for t in data["tiers"]]}


def to_json(data: dict) -> dict:
    """Datos del formulario -> JSON (fechas ISO, montos en texto)."""
    def conv(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v
    return conv(data)


def form_from_json(stored: dict) -> dict:
    """Lo guardado en un documento -> cuerpo del formulario (para editar = version 2)."""
    form = dict(stored or {})
    form.pop("paid_start", None)
    return form


# ------------------------------------------------------------ calculos ---
def min_commitment(tiers: list[dict], min_months: int) -> Decimal:
    return sum((billing.tier_amount(tiers, seq) for seq in range(1, int(min_months) + 1)), Decimal("0"))


def schedule_rows(data: dict) -> list[dict]:
    """Tabla de cuotas del PDF: hasta la permanencia (o hasta ver todos los tramos)."""
    tiers = data["tiers"]
    count = max(int(data["min_months"]), max(t["month_from"] for t in tiers), 3)
    count = min(count, 24)
    contract = {"start_date": data["paid_start"], "pay_day_from": data["pay_day_from"], "pay_day_to": data["pay_day_to"]}
    upto = billing.add_months(data["paid_start"].replace(day=1), count - 1)
    rows = []
    ordered = sorted(tiers, key=lambda t: t["month_from"])
    for inst in billing.schedule_for(contract, tiers, upto):
        idx = next(i for i, t in enumerate(ordered) if t["month_from"] <= inst["seq"] and (t["month_to"] is None or inst["seq"] <= t["month_to"]))
        if len(ordered) == 1:
            tier_name = "Tarifa mensual"
        elif idx == 0:
            tier_name = "Tarifa inicial"
        elif idx == len(ordered) - 1:
            tier_name = "Tarifa base"
        else:
            tier_name = f"Tramo {idx + 1}"
        note = tier_name + (" · permanencia mínima" if inst["seq"] <= int(data["min_months"]) else " · mes a mes")
        rows.append({"seq": inst["seq"], "period": billing.period_label(inst["period"]), "window": window_text(inst["due_from"], inst["due_date"]),
                     "amount": inst["amount"], "amount_text": money_text(inst["amount"], data["currency"]), "note": note})
    return rows


def tiers_view(data: dict) -> list[dict]:
    out = []
    for t in sorted(data["tiers"], key=lambda t: t["month_from"]):
        if t["month_to"] is None:
            label = f"Desde el mes {t['month_from']}" if t["month_from"] > 1 else "Todos los meses"
        elif t["month_to"] == t["month_from"]:
            label = f"Mes {t['month_from']}"
        else:
            label = f"Meses {t['month_from']} a {t['month_to']}"
        out.append({"label": label, "amount": t["amount"], "amount_text": money_text(t["amount"], data["currency"]),
                    "words": amount_words(t["amount"], data["currency"])})
    return out


def tiers_sentence(data: dict) -> str:
    views = tiers_view(data)
    if len(views) == 1:
        v = views[0]
        return f"una tarifa mensual de {v['words']} ({v['amount_text']})"
    parts = []
    for v, t in zip(views, sorted(data["tiers"], key=lambda t: t["month_from"])):
        if t["month_to"] is None:
            span = f"desde el mes {t['month_from']} en adelante"
        elif t["month_to"] == t["month_from"]:
            span = f"el mes {t['month_from']}"
        else:
            span = f"del mes {t['month_from']} al mes {t['month_to']}"
        parts.append(f"{span}, {v['words']} ({v['amount_text']}) mensuales")
    return "; ".join(parts[:-1]) + "; y " + parts[-1]


def verification_code(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    h = hashlib.sha256(raw).hexdigest().upper()
    return f"{h[:5]}-{h[5:10]}"


# ----------------------------------------------------------- plantilla ---
def load_template(path: Path = TEMPLATE) -> dict:
    """{"title", "subtitle", "sections": [{"title", "paragraphs": [str]}]}."""
    title = subtitle = ""
    sections: list[dict] = []
    buf: list[str] = []

    def flush():
        if buf and sections:
            para = " ".join(x.strip() for x in buf).strip()
            if para:
                sections[-1]["paragraphs"].append(para)
        buf.clear()

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(";;"):
            continue
        if line.startswith("@titulo "):
            title = line[8:].strip()
            continue
        if line.startswith("@subtitulo "):
            subtitle = line[11:].strip()
            continue
        if line.startswith("== "):
            flush()
            sections.append({"title": line[3:].strip(), "paragraphs": []})
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return {"title": title, "subtitle": subtitle, "sections": sections}


_FIELD = re.compile(r"\{([a-z_]+)\}")
_COND = re.compile(r"^\{([?!])([a-z_]+)\}\s*")
_BLOCK = re.compile(r"^\[\[([A-Z]+)\]\]$")


def fill(paragraph: str, values: dict) -> list[tuple[str, str]]:
    """Parrafo -> segmentos [("t", texto) | ("b", "") | ("s", "")]: "b" = linea para
    llenar (dato opcional vacio), "s" = espacio corto ({_}: dia, mes, ano)."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in _FIELD.finditer(paragraph):
        if m.start() > pos:
            out.append(("t", paragraph[pos:m.start()]))
        key = m.group(1)
        if key == "_":
            out.append(("s", ""))  # espacio corto (dia, mes, ano)
        else:
            if key not in values:
                raise KeyError(f"campo desconocido en la plantilla: {key}")
            value = values[key]
            out.append(("b", "") if value in (None, "") else ("t", str(value)))
        pos = m.end()
    if pos < len(paragraph):
        out.append(("t", paragraph[pos:]))
    return out


def render_sections(template: dict, values: dict, flags: dict) -> list[dict]:
    sections = []
    for sec in template["sections"]:
        blocks = []
        for para in sec["paragraphs"]:
            cond = _COND.match(para)
            if cond:
                want = bool(flags.get(cond.group(2)))
                if (cond.group(1) == "?") != want:
                    continue
                para = para[cond.end():]
            block = _BLOCK.match(para.strip())
            if block:
                blocks.append({"type": "block", "name": block.group(1)})
            else:
                blocks.append({"type": "p", "segments": fill(para, values)})
        sections.append({"title": sec["title"], "blocks": blocks})
    return sections


# ----------------------------------------------------------- composicion ---
def public_login_url() -> str:
    base = str(os.getenv("PUBLIC_BASE_URL") or os.getenv("APP_PUBLIC_URL") or "").strip().rstrip("/")
    return f"{base}/login" if base.startswith(("http://", "https://")) else ""


def compose(data: dict, provider: dict, company: dict, number: str, version: int, type_label: str,
            template: Optional[dict] = None) -> dict:
    """Todo lo que dibuja el PDF (y la vista previa), ya calculado."""
    cur = data["currency"]
    client = data["client"]
    trial = int(data["trial_days"])
    min_months = int(data["min_months"])
    first_period = data["paid_start"].replace(day=1)
    commitment = min_commitment(data["tiers"], min_months)
    sur = data.get("surcharge")
    values = {
        "proveedor_nombre": provider.get("name") or None, "proveedor_marca": provider.get("trade_name") or "CLONEXA",
        "proveedor_documento": (f"NIT/documento No. {provider['doc_id']}" if provider.get("doc_id") else None),
        "proveedor_ciudad": provider.get("city") or None, "proveedor_correo": provider.get("email") or None,
        "proveedor_telefonos": provider.get("phones") or None,
        "cliente_empresa": company["name"], "cliente_razon_social": client["legal_name"] or None,
        "cliente_representante": client["representative"] or None,
        "cliente_documento": (f"CC/NIT No. {client['doc_id']}" if client["doc_id"] else None),
        "cliente_direccion": client["address"] or None, "cliente_correo": client["email"] or None, "cliente_telefono": client["phone"] or None,
        "prueba_dias": trial, "prueba_dias_letras": words_es(trial), "prueba_desde": date_long(data["start_date"]),
        "prueba_hasta": date_long(data["start_date"] + timedelta(days=max(trial, 1) - 1)), "inicio_pagos": date_long(data["paid_start"]),
        "tramos_texto": tiers_sentence(data), "pago_desde": data["pay_day_from"], "pago_hasta": data["pay_day_to"],
        "compromiso": money_text(commitment, cur), "compromiso_letras": amount_words(commitment, cur),
        "permanencia": min_months, "permanencia_letras": words_es(min_months),
        "fin_permanencia": date_long(month_end(billing.add_months(first_period, max(min_months, 1) - 1))),
        "recargo": money_text(sur["amount"], cur) if sur else "", "recargo_letras": amount_words(sur["amount"], cur) if sur else "",
        "recargo_desde": sur["from_month"] if sur else "",
        "recargo_desde_fecha": month_long(billing.add_months(first_period, sur["from_month"] - 1)) if sur else "",
        "ciudad_jurisdiccion": (f"{data['jurisdiction_city']}, Colombia" if data["jurisdiction_city"] else None),
        "ciudad_firma": data["sign_city"] or None,
    }
    flags = {"prueba": trial > 0, "permanencia": min_months > 0, "recargo": bool(sur), "varios_tramos": len(data["tiers"]) > 1}
    template = template or load_template()
    sections = render_sections(template, values, flags)
    content = {"data": to_json(data), "provider": {k: provider.get(k, "") for k in PROVIDER_FIELDS}, "company": company["name"],
               "number": number, "version": version}
    end_label = date_long(month_end(billing.add_months(first_period, max(min_months, 1) - 1))) if min_months else "mes a mes"
    return {
        "title": template["title"], "subtitle": fill(template["subtitle"], values),
        "number": number, "version": version, "verification": verification_code(content),
        "currency": cur, "type_label": type_label, "company_name": company["name"],
        "provider": {k: provider.get(k, "") for k in PROVIDER_FIELDS},
        "client": client,
        "vigencia": {"start": date_long(data["start_date"]), "trial": f"{trial} día{'s' if trial != 1 else ''}" if trial else "Sin prueba",
                     "paid_start": date_long(data["paid_start"]), "min_months": min_months, "end": end_label, "type": type_label},
        "pago": {"window": f"Del {data['pay_day_from']} al {data['pay_day_to']} de cada mes", "currency": cur, "channel": "QR del Anexo 2"},
        "tiers": tiers_view(data), "commitment": commitment, "commitment_text": money_text(commitment, cur),
        "commitment_words": amount_words(commitment, cur),
        "surcharge": ({"amount_text": money_text(sur["amount"], cur), "from_month": sur["from_month"]} if sur else None),
        "modules": data["modules"], "schedule": schedule_rows(data), "sections": sections,
        "access": [("Empresa / establecimiento", company["name"]), ("Enlace de aplicación", public_login_url() or None),
                   ("Usuario entregado", None), ("Clave", "Entregada por canal seguro separado"), ("Fecha de entrega", None),
                   ("Canal de soporte", " · ".join(x for x in (provider.get("phones"), provider.get("email")) if x) or None),
                   ("Responsable del cliente", " · ".join(x for x in (client["representative"], client["email"], client["phone"]) if x) or None)],
        "qr_caption": ("Imagen original entregada por CLONEXA. No fue recortada ni modificada. Verificación de pago y soporte: "
                       + (" · ".join(x for x in (provider.get("phones"), provider.get("email")) if x) or "canales oficiales de CLONEXA") + "."),
        "signatures": {"provider": [("Nombre", provider.get("name") or None), ("NIT/documento", provider.get("doc_id") or None),
                                    ("Correo", provider.get("email") or None)],
                       "client": [("Nombre", client["representative"] or None), ("CC/NIT", client["doc_id"] or None),
                                  ("Correo", client["email"] or None)]},
        "contact": " · ".join(x for x in (provider.get("trade_name") or "CLONEXA", provider.get("email"), (provider.get("phones") or "").split("·")[0].strip()) if x),
    }


# ----------------------------------------------------------------- base ---
async def get_provider(db: AsyncSession) -> dict:
    row = (await db.execute(text("""
        SELECT name, trade_name, doc_id, email, phones, city, qr_key, qr_type, updated_by, updated_at FROM billing_provider WHERE id = 1
    """))).mappings().first()
    if not row:
        return {**{k: "" for k in PROVIDER_FIELDS}, "trade_name": "CLONEXA", "qr_key": None, "qr_type": None, "has_qr": False}
    out = dict(row)
    out["has_qr"] = bool(out.get("qr_key"))
    return out


async def save_provider(db: AsyncSession, raw: dict, actor: str) -> dict:
    data = validate_provider(raw)
    await db.execute(text("""
        INSERT INTO billing_provider (id, name, trade_name, doc_id, email, phones, city, updated_by, updated_at)
        VALUES (1, :name, :trade_name, :doc_id, :email, :phones, :city, :by, now())
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, trade_name = EXCLUDED.trade_name, doc_id = EXCLUDED.doc_id,
            email = EXCLUDED.email, phones = EXCLUDED.phones, city = EXCLUDED.city, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {**data, "by": actor[:200]})
    await db.commit()
    return await get_provider(db)


def image_kind(raw: bytes) -> Optional[str]:
    from app.services import brand_media

    kind = brand_media.sniff(raw)
    return {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}.get(kind or "")


def check_image(raw: bytes, limit: int) -> str:
    """Imagen real (firma + PIL), sin re-codificar: el QR se guarda tal cual se entrego."""
    if not raw:
        raise BillingInvalid("archivo", "el archivo está vacío")
    if len(raw) > limit:
        raise BillingInvalid("archivo", f"pesa más de {limit // (1024 * 1024)} MB")
    kind = image_kind(raw)
    if not kind:
        raise BillingInvalid("archivo", "solo PNG, JPG o WebP")
    import io

    from PIL import Image

    from app.services import brand_media

    Image.MAX_IMAGE_PIXELS = brand_media.MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > brand_media.MAX_PIXELS:
                raise BillingInvalid("archivo", "la imagen es demasiado grande")
            img.verify()
    except BillingInvalid:
        raise
    except Exception:
        raise BillingInvalid("archivo", "no se pudo leer la imagen") from None
    return kind


def provider_qr_key(kind: str) -> str:
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[kind]
    return f"billing/_provider/qr-{uuid.uuid4()}.{ext}"


async def set_provider_qr(db: AsyncSession, raw: bytes, actor: str, put: Callable) -> dict:
    kind = check_image(raw, MAX_QR_BYTES)
    key = provider_qr_key(kind)
    await put(key, raw, kind)
    await db.execute(text("""
        INSERT INTO billing_provider (id, qr_key, qr_type, updated_by, updated_at) VALUES (1, :k, :t, :by, now())
        ON CONFLICT (id) DO UPDATE SET qr_key = EXCLUDED.qr_key, qr_type = EXCLUDED.qr_type, updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"k": key, "t": kind, "by": actor[:200]})
    await db.commit()
    return await get_provider(db)


async def provider_qr(db: AsyncSession, get: Callable) -> Optional[tuple[bytes, str]]:
    p = await get_provider(db)
    if not p.get("qr_key"):
        return None
    try:
        return await get(p["qr_key"]), p.get("qr_type") or "image/png"
    except Exception:
        return None


async def safely(db: AsyncSession, fn: Callable, default: Any = None) -> Any:
    """Lectura opcional (logo, tema) dentro de un SAVEPOINT: si falla, la
    transaccion sigue sana y se usa `default`."""
    try:
        async with db.begin_nested():
            return await fn()
    except Exception:
        return default


async def draft_candidates(db: AsyncSession) -> list[dict]:
    """Empresas registradas (no demos) SIN contrato."""
    with_contract = {r["cid"] for r in (await db.execute(text("SELECT company_id::text AS cid FROM billing_contracts"))).mappings().all()}
    return [c for c in await billing.registered_companies(db) if c["id"] not in with_contract]


async def active_modules(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT LOWER(m.code) AS code, COALESCE(NULLIF(TRIM(m.name), ''), m.code) AS name, COALESCE(m.description, '') AS description,
               cm.activated_at
        FROM company_modules cm JOIN modules m ON m.id = cm.module_id
        WHERE cm.company_id = CAST(:c AS uuid) AND cm.enabled IS TRUE AND COALESCE(m.is_active, TRUE) IS TRUE
        ORDER BY m.name
    """), {"c": company_id})).mappings().all()
    out = []
    for r in rows:
        desc = re.split(r"(?<=[.!?])\s", str(r["description"] or "").strip(), maxsplit=1)[0].strip()
        out.append({"code": r["code"], "name": str(r["name"])[:80], "line": (desc or "Módulo habilitado en CLONEXA.")[:200],
                    "activated_at": r["activated_at"]})
    return out


async def prefill(db: AsyncSession, company_id: str, today: Optional[date] = None) -> dict:
    from app.services import panel_logo

    company = (await db.execute(text("SELECT id::text AS id, name, created_at FROM companies WHERE id = CAST(:c AS uuid)"),
                                {"c": company_id})).mappings().first()
    modules = await active_modules(db, company_id)
    dates = [m["activated_at"] for m in modules if m.get("activated_at")] + ([company["created_at"]] if company and company["created_at"] else [])
    start = min(dates).astimezone(billing.TZ).date() if dates else (today or billing.today_bogota())
    got = await safely(db, lambda: panel_logo.panel_logo(db, company_id), {"url": ""})
    logo = (got or {}).get("url") or ""
    return {"company": {"id": company_id, "name": company["name"] if company else ""}, "logo_url": logo,
            "modules": [{k: m[k] for k in ("code", "name", "line")} for m in modules],
            "form": {"contract_type": "minimo", "start_date": start.isoformat(), "trial_days": 0, "min_months": 6, "currency": "COP",
                     "pay_day_from": 1, "pay_day_to": 5, "tiers": [{"month_from": 1, "month_to": None, "amount": 0}],
                     "surcharge": {"amount": "", "from_month": ""}, "jurisdiction_city": "", "sign_city": "",
                     "client": {k: "" for k in CLIENT_FIELDS}, "modules": [{k: m[k] for k in ("code", "name", "line")} for m in modules]}}


async def current_document(db: AsyncSession, company_id: str) -> Optional[dict]:
    row = (await db.execute(text("""
        SELECT id::text AS id, number, version, verification, data, file_id::text AS file_id, created_at, created_by
        FROM billing_contract_documents WHERE company_id = CAST(:c AS uuid) AND is_current IS TRUE ORDER BY version DESC LIMIT 1
    """), {"c": company_id})).mappings().first()
    return dict(row) if row else None


async def documents(db: AsyncSession, company_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id::text AS id, number, version, verification, file_id::text AS file_id, is_current, created_at, created_by
        FROM billing_contract_documents WHERE company_id = CAST(:c AS uuid) ORDER BY version DESC
    """), {"c": company_id})).mappings().all()
    return [dict(r) for r in rows]


async def next_number(db: AsyncSession, year: int) -> str:
    n = int((await db.execute(text("SELECT COUNT(DISTINCT number) FROM billing_contract_documents WHERE number LIKE :p"),
                              {"p": f"CX-{year}-%"})).scalar() or 0)
    return f"CX-{year}-{n + 1:03d}"


async def _type_label(db: AsyncSession, code: str) -> str:
    return next((t["label"] for t in await billing.contract_types(db, active_only=False) if t["code"] == code), code)


async def _logo_png(db: AsyncSession, company_id: str) -> Optional[bytes]:
    """El logo de la EMPRESA (panel_logo), en PNG para el PDF. Nunca se cambia aqui."""
    from app.services import panel_logo

    raw = await safely(db, lambda: panel_logo.panel_logo_bytes(db, company_id))
    if not raw:
        return None
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(raw)) as img:
            buf = io.BytesIO()
            img.convert("RGBA").save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


async def build(db: AsyncSession, company_id: str, raw: dict, get: Optional[Callable] = None, *, number: Optional[str] = None,
                version: Optional[int] = None) -> tuple[dict, dict, bytes]:
    """(datos, composicion, pdf) sin guardar nada. Sin numero: el que tendria."""
    from app.services import billing_contract_pdf

    company = (await db.execute(text("SELECT id::text AS id, name FROM companies WHERE id = CAST(:c AS uuid)"), {"c": company_id})).mappings().first()
    if not company:
        raise BillingInvalid("empresa", "no existe")
    types = {t["code"] for t in await billing.contract_types(db)}
    active = {m["code"] for m in await active_modules(db, company_id)}
    data = validate_draft(raw, types, active)
    provider = await get_provider(db)
    current = await current_document(db, company_id)
    if number is None:
        number = current["number"] if current else await next_number(db, billing.today_bogota().year)
        version = (int(current["version"]) + 1) if current else 1
    composed = compose(data, provider, dict(company), number, int(version or 1), await _type_label(db, data["contract_type"]))
    qr = await provider_qr(db, get) if get else None
    pdf, _pages = billing_contract_pdf.render(composed, client_logo=await _logo_png(db, company_id), qr=qr[0] if qr else None)
    return data, composed, pdf


async def generate(db: AsyncSession, company_id: str, raw: dict, actor: str, put: Callable, get: Optional[Callable] = None) -> dict:
    """Crea (o versiona) el contrato redactado: contrato + cuotas, PDF al bucket,
    numero/version/verificacion. Un contrato hecho a mano (sin documento
    redactado, p. ej. The Time Machine) NO se toca."""
    contract = await billing.get_contract(db, company_id)
    current = await current_document(db, company_id)
    if contract and not current:
        raise BillingConflict("Esta empresa ya tiene un contrato registrado a mano; no se reemplaza desde Redactar contrato.")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('billing_contract_number'))"))
    number = current["number"] if current else await next_number(db, billing.today_bogota().year)
    version = (int(current["version"]) + 1) if current else 1
    data, composed, pdf = await build(db, company_id, raw, get, number=number, version=version)
    doc_id = str(uuid.uuid4())
    await db.execute(text("""
        INSERT INTO billing_contract_documents (id, company_id, number, version, verification, data, is_current, created_by)
        VALUES (CAST(:i AS uuid), CAST(:c AS uuid), :n, :v, :h, CAST(:d AS jsonb), false, :by)
    """), {"i": doc_id, "c": company_id, "n": number, "v": version, "h": composed["verification"],
           "d": json.dumps({**to_json(data), "provider": composed["provider"]}, ensure_ascii=False), "by": actor[:200]})
    await db.commit()  # reserva numero y version (UNIQUE)
    async def put_pdf(key: str, raw: bytes) -> None:
        await put(key, raw, "application/pdf")

    try:
        await billing.save_contract(db, company_id, contract_payload(data))
        saved = await billing.add_contract_file(db, company_id, pdf, f"{number}-v{version}.pdf", actor, put_pdf)
    except Exception:
        await db.rollback()
        await db.execute(text("DELETE FROM billing_contract_documents WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)"),
                         {"i": doc_id, "c": company_id})
        await db.commit()
        raise
    await db.execute(text("UPDATE billing_contract_documents SET is_current = false WHERE company_id = CAST(:c AS uuid)"), {"c": company_id})
    await db.execute(text("""
        UPDATE billing_contract_documents SET is_current = true, file_id = CAST(:f AS uuid) WHERE id = CAST(:i AS uuid) AND company_id = CAST(:c AS uuid)
    """), {"f": saved["id"], "i": doc_id, "c": company_id})
    await db.commit()
    return {"id": doc_id, "number": number, "version": version, "verification": composed["verification"], "file": saved,
            "commitment": composed["commitment"]}


async def set_reminder(db: AsyncSession, company_id: str, enabled: bool) -> bool:
    row = (await db.execute(text("""
        UPDATE billing_contracts SET reminder_enabled = :e WHERE company_id = CAST(:c AS uuid) RETURNING reminder_enabled
    """), {"e": bool(enabled), "c": company_id})).first()
    if not row:
        await db.rollback()
        raise BillingConflict("La empresa no tiene contrato.")
    await db.commit()
    return bool(row[0])


# ---------------------------------------------------------- recordatorio ---
def reminder_for(contract: Optional[dict], inst: Optional[dict], covered: Decimal, today: date) -> Optional[dict]:
    """Regla pura del recordatorio (today = fecha LOCAL de la empresa)."""
    if not contract or contract.get("status") != "vigente" or contract.get("reminder_enabled") is False:
        return None
    if not inst or inst.get("voided"):
        return None
    amount = Decimal(str(inst["amount"]))
    if amount <= 0 or not inst["due_from"] <= today <= month_end(inst["period"]):
        return None
    if covered >= amount:
        return None
    return {"installment_id": inst["id"], "period": inst["period"], "amount": amount, "balance": amount - covered,
            "partial": covered > 0, "due_date": inst["due_date"], "state": "overdue" if today > inst["due_date"] else "open",
            "currency": contract.get("currency") or "COP"}


async def covered_by_installment(db: AsyncSession, company_id: str, installment_id: str) -> Decimal:
    """Pagos por validar + validados de la cuota (lo anulado no cuenta)."""
    total = (await db.execute(text("""
        SELECT COALESCE(SUM(amount), 0) FROM billing_payments
        WHERE company_id = CAST(:c AS uuid) AND installment_id = CAST(:i AS uuid) AND status IN ('por_validar', 'validado')
    """), {"c": company_id, "i": installment_id})).scalar()
    return Decimal(str(total or 0))


async def reminder(db: AsyncSession, company_id: str, today: date) -> Optional[dict]:
    if not await billing.is_registered(db, company_id):
        return None
    contract = await billing.get_contract(db, company_id)
    if not contract or contract["status"] != "vigente" or not contract.get("reminder_enabled", True):
        return None
    await billing.sync_installments(db, company_id, today)
    row = (await db.execute(text("""
        SELECT id::text AS id, seq, period, amount, due_from, due_date, voided FROM billing_installments
        WHERE company_id = CAST(:c AS uuid) AND contract_id = CAST(:k AS uuid) AND period = :p
    """), {"c": company_id, "k": contract["id"], "p": today.replace(day=1)})).mappings().first()
    if not row:
        return None
    inst = dict(row)
    return reminder_for(contract, inst, await covered_by_installment(db, company_id, inst["id"]), today)


def proof_kind(raw: bytes) -> Optional[str]:
    if billing.is_pdf(raw):
        return "application/pdf"
    return image_kind(raw)


def proof_key(company_id: str, payment_id: str, kind: str) -> str:
    ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[kind]
    return f"billing/{uuid.UUID(company_id)}/proofs/{uuid.UUID(payment_id)}.{ext}"


async def report_payment(db: AsyncSession, company_id: str, raw: bytes, amount: Any, actor: str, today: date, put: Callable) -> dict:
    """ "Ya pague": comprobante (imagen o PDF, max 5 MB) al bucket y un pago POR
    VALIDAR de la cuota del recordatorio. Desde ahi el recordatorio deja de salir
    para esa cuota (salvo que el pago se anule)."""
    if not raw:
        raise BillingInvalid("archivo", "adjunta la foto o el PDF del comprobante")
    if len(raw) > MAX_PROOF_BYTES:
        raise BillingInvalid("archivo", "el comprobante pesa más de 5 MB")
    kind = proof_kind(raw)
    if not kind:
        raise BillingInvalid("archivo", "solo imagen (PNG, JPG, WebP) o PDF")
    if kind != "application/pdf":
        check_image(raw, MAX_PROOF_BYTES)
    current = await reminder(db, company_id, today)
    if not current:
        raise BillingConflict("No hay una mensualidad pendiente para reportar.")
    value = current["balance"] if amount in (None, "") else billing.money(amount)
    if value <= 0:
        raise BillingInvalid("amount", "el valor debe ser mayor que cero")
    payment_id = str(uuid.uuid4())
    key = proof_key(company_id, payment_id, kind)
    await put(key, raw, kind)
    await db.execute(text("""
        INSERT INTO billing_payments (id, company_id, installment_id, amount, paid_on, method, reference, note, created_by, source, proof_key, proof_type)
        VALUES (CAST(:id AS uuid), CAST(:c AS uuid), CAST(:i AS uuid), :a, :p, 'transferencia', '', :n, :by, 'cliente', :k, :t)
    """), {"id": payment_id, "c": company_id, "i": current["installment_id"], "a": value, "p": today,
           "n": "Reportado por el cliente desde su panel (comprobante adjunto).", "by": actor[:200], "k": key, "t": kind})
    await db.commit()
    return {"id": payment_id, "amount": value, "installment_id": current["installment_id"]}


async def payment_proof(db: AsyncSession, company_id: str, payment_id: str) -> Optional[dict]:
    try:
        pid = str(uuid.UUID(str(payment_id)))
    except ValueError:
        return None
    row = (await db.execute(text("""
        SELECT proof_key, proof_type FROM billing_payments WHERE id = CAST(:p AS uuid) AND company_id = CAST(:c AS uuid) AND proof_key IS NOT NULL
    """), {"p": pid, "c": company_id})).mappings().first()
    return dict(row) if row else None
