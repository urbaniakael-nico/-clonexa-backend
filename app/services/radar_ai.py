"""NEXUS · Radar: peticion a Claude (con busqueda web) y validacion estricta de lo que responde.

- Modelo: Claude Sonnet 5.5 (bueno para investigar, sin exceso de tokens), effort medium, busqueda web
  web_search_20260209 con maximo 8 busquedas por informe, ubicacion aproximada Bogota.
- La salida estructurada de la API no se combina con las citas de la busqueda web, asi que la respuesta es
  un JSON en texto y AQUI se valida: cada idea debe traer al menos una fuente con URL y fecha, y esa URL
  debe ser una de las que la busqueda web devolvio en ESTE informe (nada inventado). La que no, se descarta.
- Costo estimado: tokens de entrada/salida a precio de lista de Sonnet 5.5 + US$10 por 1.000 busquedas.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

from app.services import radar as rd

MODEL = "claude-sonnet-5-5"
MAX_SEARCHES = 8
PRICE_IN, PRICE_OUT, PRICE_CACHE_READ, PRICE_CACHE_WRITE = 2.0, 10.0, 0.10, 2.5   # US$ por millon de tokens (lista)
PRICE_SEARCH = 10.0 / 1000                                                        # US$ por busqueda
DATE_RE = re.compile(r"^\d{4}(-\d{2}){0,2}$")

SYSTEM = """Eres NEXUS, el radar de innovación de Clonexa. Clonexa es un software en la nube hecho en Bogotá (Colombia) para negocios:
restaurantes y bares (pedidos por QR, cocina, caja, carta en video, juegos en vivo), talleres de confección y fábricas
pequeñas (producción por lote, nómina), empresas con personal en campo (turnos con GPS y bot de Telegram, materiales),
transporte, tiendas y call centers. Usa WhatsApp Cloud API, Telegram, n8n, Railway, Claude y three.js (oficina 3D y
"Negocio en vivo 3D"). Vende en Colombia y LatAm.

Tu trabajo: buscar en la web novedades RECIENTES y REALES que le sirvan a Clonexa y proponer ideas accionables.

REGLAS
- Usa la búsqueda web. Cada idea debe tener al menos una fuente: una URL que hayas visto en los resultados de la búsqueda,
  con su fecha de publicación (AAAA-MM-DD; si solo sabes el mes, AAAA-MM). Si no tienes fuente, no propongas la idea.
- Nada inventado: ni cifras, ni fechas, ni convocatorias. Si una convocatoria tiene fecha de cierre publicada, ponla en
  fecha_limite (AAAA-MM-DD); si no está publicada, null.
- No repitas ideas de la lista "YA PROPUESTAS".
- Prefiere lo de los últimos 3 meses. Escribe en español de Colombia, corto y claro.
- impacto / esfuerzo / costo: "alto", "medio" o "bajo" para Clonexa. costo_estimado: texto corto (p. ej. "US$0", "incluido en el plan actual").
- categoria: una de herramientas, competencia, fondos, normas, nichos, otra. nicho (si aplica): restaurante, bar, taller,
  campo, transporte, tienda; si no aplica, "".

SALIDA: al final, SOLO un objeto JSON (sin texto antes ni después, sin ```):
{"ideas": [{"titulo": "...", "resumen": "máx. 2 frases", "por_que": "por qué le sirve a Clonexa, 1-2 frases",
  "categoria": "...", "nicho": "", "fuentes": [{"url": "https://...", "titulo": "...", "fecha": "AAAA-MM-DD"}],
  "impacto": "alto|medio|bajo", "esfuerzo": "alto|medio|bajo", "costo": "alto|medio|bajo", "costo_estimado": "...",
  "fecha_limite": null}]}"""


def build_request(*, tipo: str, tema: str, temas: list[dict], excluded: list[str], n: int, hoy: date) -> dict:
    vigila = "\n".join(f"- {t['nombre']}: {t['descripcion']}" for t in temas) or "- Herramientas, competencia, fondos, normas e ideas por nicho."
    foco = (f"TEMA DE ESTE INFORME (a pedido): {tema}\nTrae {n} ideas sobre ese tema." if tipo == "a_pedido" and tema else
            f"INFORME SEMANAL: trae {n} ideas repartidas entre los temas que vigilas (al menos 3 temas distintos).")
    ya = "\n".join(f"- {t}" for t in excluded[:120]) or "- (ninguna)"
    user = (f"Hoy es {hoy.isoformat()} (Bogotá).\n\nTEMAS QUE VIGILAS:\n{vigila}\n\n{foco}\n"
            f"Propón un poco más de {n} candidatas (hasta {n + 2}) por si alguna se descarta.\n\nYA PROPUESTAS (no repetir):\n{ya}")
    return {"model": MODEL, "max_tokens": 16000,
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            "output_config": {"effort": "medium"},
            "fallbacks": "default",
            "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES,
                       "user_location": {"type": "approximate", "country": "CO", "city": "Bogotá", "region": "Bogotá D.C.",
                                         "timezone": "America/Bogota"}}],
            "messages": [{"role": "user", "content": user}]}


def continuation(request: dict, response: dict) -> dict:
    """pause_turn: se reenvia la conversacion con lo que Claude ya hizo para que termine."""
    return {**request, "messages": request["messages"] + [{"role": "assistant", "content": response.get("content") or []}]}


def _blocks(responses: list[dict]) -> list[dict]:
    out = []
    for r in responses:
        out += [b for b in (r.get("content") or []) if isinstance(b, dict)]
    return out


def search_urls(responses: list[dict]) -> set[str]:
    urls = set()
    for b in _blocks(responses):
        if b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
            for res in b["content"]:
                if isinstance(res, dict) and res.get("url"):
                    urls.add(rd.norm_url(res["url"]))
        for c in b.get("citations") or []:
            if isinstance(c, dict) and c.get("url"):
                urls.add(rd.norm_url(c["url"]))
    return urls


def final_text(responses: list[dict]) -> str:
    texts = [b.get("text", "") for b in _blocks(responses[-1:]) if b.get("type") == "text"]
    return "".join(texts).strip()


def parse_json(textv: str) -> Optional[dict]:
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (textv or "").strip())
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        v = json.loads(t[i:j + 1])
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _clean(v: Any, n: int) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(v or "")).split())[:n]


def _level(v: Any) -> str:
    v = rd.fold(v)
    return v if v in rd.LEVELS else "medio"


def _date(v: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10]) if v and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)[:10]) else None
    except ValueError:
        return None


def validate(data: Optional[dict], urls: set[str]) -> tuple[list[dict], int]:
    """(ideas validas, descartadas). Sin fuente real con fecha -> descartada."""
    ideas, discarded = [], 0
    for raw in (data or {}).get("ideas") or []:
        if not isinstance(raw, dict):
            discarded += 1
            continue
        fuentes = []
        for f in raw.get("fuentes") or []:
            if not isinstance(f, dict):
                continue
            url, fecha = str(f.get("url") or "").strip(), str(f.get("fecha") or "").strip()
            if not url.startswith(("https://", "http://")) or not DATE_RE.match(fecha):
                continue
            if rd.norm_url(url) not in urls:
                continue          # no salio en la busqueda de este informe: puede ser inventada
            fuentes.append({"url": url[:500], "titulo": _clean(f.get("titulo"), 160), "fecha": fecha})
        titulo = _clean(raw.get("titulo"), 160)
        if not fuentes or len(titulo) < 6:
            discarded += 1
            continue
        cat = rd.fold(raw.get("categoria")).replace(" ", "")
        ideas.append({"titulo": titulo, "resumen": _clean(raw.get("resumen"), 600), "por_que": _clean(raw.get("por_que"), 600),
                      "categoria": cat if cat in rd.CATEGORIES else "otra", "nicho": _clean(raw.get("nicho"), 30).lower(),
                      "fuentes": fuentes[:3], "impacto": _level(raw.get("impacto")), "esfuerzo": _level(raw.get("esfuerzo")),
                      "costo": _level(raw.get("costo")), "costo_estimado": _clean(raw.get("costo_estimado"), 120),
                      "fecha_limite": _date(raw.get("fecha_limite"))})
    return ideas, discarded


def usage_of(responses: list[dict]) -> dict:
    ti = to = cr = cw = searches = 0
    model = ""
    for r in responses:
        u = r.get("usage") or {}
        ti += int(u.get("input_tokens") or 0)
        to += int(u.get("output_tokens") or 0)
        cr += int(u.get("cache_read_input_tokens") or 0)
        cw += int(u.get("cache_creation_input_tokens") or 0)
        searches += int(((u.get("server_tool_use") or {}).get("web_search_requests")) or 0)
        model = r.get("model") or model
    cost = (ti * PRICE_IN + to * PRICE_OUT + cr * PRICE_CACHE_READ + cw * PRICE_CACHE_WRITE) / 1_000_000 + searches * PRICE_SEARCH
    return {"input_tokens": ti + cr + cw, "output_tokens": to, "busquedas": searches, "costo_usd": round(cost, 4), "modelo": model}


def api_error(responses: list[dict]) -> str:
    for r in responses:
        if not isinstance(r, dict):
            return "respuesta vacía"
        if r.get("type") == "error" or r.get("error"):
            e = r.get("error") or {}
            return str((e.get("message") if isinstance(e, dict) else e) or "error de Claude")[:200]
        if r.get("stop_reason") == "refusal":
            return "Claude declinó el informe"
    if not responses:
        return "sin respuesta de Claude"
    return ""


def header(tipo: str, tema: str, n: int, discarded: int, cost: float) -> str:
    title = "Radar de la semana" if tipo == "semanal" else f"Radar a pedido · {rd.esc(tema[:80])}"
    if not n:
        return f"🛰️ <b>{title}</b> · sin ideas nuevas con fuente real ({discarded} descartadas). Costo ~US${cost:.2f}."
    return f"🛰️ <b>{title} · {n} {'idea' if n == 1 else 'ideas'}</b>\nOrdenadas por puntaje · {discarded} descartadas · costo ~US${cost:.2f}"
