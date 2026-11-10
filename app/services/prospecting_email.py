"""Correos de prospeccion de Nexa: plantillas por tipo de negocio (sin precios), enlaces con utm y
pie legal (Ley 2300 de 2023 / Ley 1581 de 2012).

Tres segmentos:
- carta  (restaurante, comidas rapidas, cafe, panaderia): la CARTA EN VIDEO CON QR.
- bar    : las 5 fugas de dinero (inventario, pedidos QR, mesas abiertas, caja, turnos).
- taller : nomina en 5 minutos y costo por prenda.

Todo correo lleva: por que le escribimos (correo publicado en su web), quien escribe, y el enlace
"No quiero recibir más correos" (baja inmediata y permanente). Puro: no toca la base.
"""
from __future__ import annotations

import html
from urllib.parse import quote, urlencode

WA_NUMBER = "573144798220"
DEFAULT_LANDING = "https://www.clonexa.com.co/"
DEFAULT_BACKEND = "https://clonexa-backend-production.up.railway.app"
GIF_PATH = "clonexa-media/carta-video.gif"

SEGMENT_OF = {
    "restaurante": "carta", "comidas_rapidas": "carta", "cafe": "carta", "panaderia": "carta",
    "bar": "bar", "taller": "taller",
}
TYPE_SLUG = {"restaurante": "restaurante", "comidas_rapidas": "comidas-rapidas", "cafe": "cafe",
             "panaderia": "panaderia", "bar": "bar", "taller": "taller"}
PAGE_OF_SEGMENT = {"carta": "", "bar": "bares", "taller": "talleres-y-fabricas"}
ANCHOR_OF_SEGMENT = {"carta": "#carta-video", "bar": "", "taller": ""}
WA_TEXT = {
    "carta": "Hola, vi la carta video (código {code})",
    "bar": "Hola, vi lo de las fugas de dinero del bar (código {code})",
    "taller": "Hola, vi lo de la nómina del taller (código {code})",
}

PINK = "#ff2d6f"
INK = "#1d1424"
MUTED = "#6b5d73"


def segment(business_type: str) -> str:
    return SEGMENT_OF.get(business_type, "carta")


def campaign(zone_slug: str, business_type: str) -> str:
    return f"{zone_slug or 'sin-zona'}-{TYPE_SLUG.get(business_type, business_type or 'negocio')}"


def utm_query(zone_slug: str, business_type: str, code: str) -> str:
    return urlencode({"utm_source": "email", "utm_medium": "prospeccion",
                      "utm_campaign": campaign(zone_slug, business_type), "utm_content": code})


def demo_url(landing: str, zone_slug: str, business_type: str, code: str) -> str:
    seg = segment(business_type)
    base = (landing or DEFAULT_LANDING).rstrip("/") + "/"
    page = PAGE_OF_SEGMENT[seg]
    return f"{base}{page}?{utm_query(zone_slug, business_type, code)}{ANCHOR_OF_SEGMENT[seg]}"


def wa_url(business_type: str, code: str, number: str = WA_NUMBER) -> str:
    return f"https://wa.me/{number}?text={quote(WA_TEXT[segment(business_type)].format(code=code))}"


def unsub_url(backend: str, token: str) -> str:
    return f"{(backend or DEFAULT_BACKEND).rstrip('/')}/api/v1/prospecting/baja?t={quote(token)}"


def gif_url(landing: str) -> str:
    return (landing or DEFAULT_LANDING).rstrip("/") + "/" + GIF_PATH


def _subject(seg: str, name: str, followup: bool) -> str:
    base = {
        "carta": f"{name}: tu carta en video con QR",
        "bar": f"{name}: 5 fugas de dinero que se pueden cerrar esta semana",
        "taller": f"{name}: la nómina en 5 minutos y el costo real de cada prenda",
    }[seg]
    return f"Re: {base}" if followup else base


def _paragraphs(seg: str, name: str, followup: bool) -> list[str]:
    if followup:
        return {
            "carta": [f"Hola, equipo de {name}:",
                      "Les escribí hace una semana sobre la carta en video con QR. Lo resumo en una línea: "
                      "el cliente escanea el QR de la mesa, ve el plato en video antes de pedir y pide desde su celular.",
                      "Si les sirve, les muestro cómo quedaría con sus propios platos. Si no, no les vuelvo a escribir."],
            "bar": [f"Hola, equipo de {name}:",
                    "Les escribí hace una semana sobre las fugas de dinero más comunes en un bar "
                    "(inventario, pedidos, mesas abiertas, caja y turnos).",
                    "Si quieren, en 20 minutos les muestro dónde se va la plata en una noche normal. Si no, no les vuelvo a escribir."],
            "taller": [f"Hola, equipo de {name}:",
                       "Les escribí hace una semana sobre la nómina en 5 minutos y el costo por prenda.",
                       "Si les sirve, les muestro cómo se ve con sus referencias. Si no, no les vuelvo a escribir."],
        }[seg]
    return {
        "carta": [f"Hola, equipo de {name}:",
                  "Imaginen esto: sus clientes escanean el QR de la mesa y ven sus platos en video, de frente y de perfil, "
                  "y piden desde el celular. Sin descargar nada.",
                  "Un plato que se ve bien se vende solo. Con Clonexa la carta en video se arma con fotos y clips de su "
                  "propio celular, y el pedido llega directo a la cocina.",
                  "¿Les muestro cómo quedaría con sus platos?"],
        "bar": [f"Hola, equipo de {name}:",
                "En casi todos los bares la plata se escapa por los mismos 5 lados:",
                "1) inventario que no cuadra con lo vendido, 2) pedidos que no quedan anotados, 3) mesas que quedan "
                "abiertas o mal cobradas, 4) caja que no cuadra al cierre y 5) turnos sin control.",
                "Clonexa los cierra en una sola herramienta: pedidos por QR desde la mesa, cuenta exacta por mesa, "
                "inventario que se descuenta solo y cierre de caja por noche.",
                "¿Les muestro en 20 minutos cómo se vería en su bar?"],
        "taller": [f"Hola, equipo de {name}:",
                   "Dos cosas que le quitan tiempo y plata a un taller de confección: la nómina por prenda o por "
                   "turno, y no saber cuánto cuesta de verdad cada prenda.",
                   "Con Clonexa la nómina sale en 5 minutos (marcación desde el celular, horas y pagos listos) y "
                   "cada referencia muestra su costo real con el tiempo de producción.",
                   "¿Les muestro cómo se vería con sus referencias?"],
    }[seg]


def _button(url: str, label: str, color: str) -> str:
    return (f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;background:{color};color:#ffffff;'
            'text-decoration:none;font-weight:700;font-size:15px;padding:12px 20px;border-radius:10px;margin:6px 6px 6px 0">'
            f"{html.escape(label)}</a>")


def render(prospect: dict, *, followup: bool, settings: dict, zone_slug: str) -> dict:
    """{subject, html, text, to}. prospect: name, business_type, code, unsub_token, email."""
    name = " ".join(str(prospect.get("name") or "su negocio").split())[:120]
    btype = prospect.get("business_type") or "restaurante"
    seg = segment(btype)
    code = prospect.get("code") or ""
    landing = settings.get("landing_url") or DEFAULT_LANDING
    backend = settings.get("backend_url") or DEFAULT_BACKEND
    signature = settings.get("signature") or "Nicolás Gómez · Clonexa"
    demo = demo_url(landing, zone_slug, btype, code)
    wa = wa_url(btype, code, settings.get("wa_number") or WA_NUMBER)
    baja = unsub_url(backend, prospect.get("unsub_token") or "")
    paras = _paragraphs(seg, name, followup)
    subject = _subject(seg, name, followup)

    demo_label = "Ver demo de la carta video" if seg == "carta" else "Ver cómo funciona"
    image = ""
    if seg == "carta" and not followup:
        image = (f'<a href="{html.escape(demo, quote=True)}"><img src="{html.escape(gif_url(landing), quote=True)}" width="220" '
                 'alt="Carta en video con QR de Clonexa" style="display:block;width:220px;max-width:100%;border-radius:16px;'
                 'border:0;margin:8px 0 14px"></a>')
    body_html = "".join(f'<p style="margin:0 0 12px;font-size:15px;line-height:1.5;color:{INK}">{html.escape(p)}</p>'
                        for p in paras)
    legal = (f"Te escribimos porque el correo de {name} aparece publicado en su página web. "
             "Es un solo correo y, como máximo, un recordatorio. Clonexa · Bogotá, Colombia.")
    html_doc = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>{html.escape(subject)}</title></head>"
        '<body style="margin:0;padding:0;background:#f6f3f8">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f3f8"><tr><td align="center" style="padding:20px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px">'
        '<tr><td style="padding:24px 24px 8px;font-family:Segoe UI,Arial,sans-serif">'
        f"{body_html}{image}"
        f"<div>{_button(demo, demo_label, PINK)}{_button(wa, 'Escríbenos por WhatsApp', '#1f9d55')}</div>"
        f'<p style="margin:16px 0 4px;font-size:15px;color:{INK}">{html.escape(signature)}</p>'
        "</td></tr>"
        '<tr><td style="padding:12px 24px 22px;font-family:Segoe UI,Arial,sans-serif">'
        f'<p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:{MUTED}">{html.escape(legal)}</p>'
        f'<p style="margin:0;font-size:12px"><a href="{html.escape(baja, quote=True)}" style="color:{MUTED};text-decoration:underline">'
        "No quiero recibir más correos</a></p>"
        "</td></tr></table></td></tr></table></body></html>"
    )
    text_doc = "\n\n".join(paras) + (
        f"\n\n{demo_label}: {demo}\nEscríbenos por WhatsApp: {wa}\n\n{signature}\n\n{legal}\n"
        f"No quiero recibir más correos: {baja}\n")
    return {"subject": subject, "html": html_doc, "text": text_doc, "to": prospect.get("email") or "",
            "demo_url": demo, "wa_url": wa, "unsub_url": baja, "segment": seg}


def unsubscribed_page(name: str = "", already: bool = False) -> str:
    who = f" a {html.escape(name)}" if name else ""
    msg = ("Ya estabas fuera de la lista." if already else f"Listo: no le volveremos a escribir{who}.")
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Baja de correos · Clonexa</title><meta name=\"robots\" content=\"noindex\"></head>"
        '<body style="font-family:Segoe UI,Arial,sans-serif;background:#f6f3f8;color:#1d1424;margin:0;padding:32px 16px">'
        '<main style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:24px">'
        '<h1 style="font-size:20px;margin:0 0 10px">No recibirás más correos de Clonexa</h1>'
        f'<p style="font-size:15px;line-height:1.5">{msg} Tu correo quedó en nuestra lista de exclusión permanente.</p>'
        '<p style="font-size:13px;color:#6b5d73">Si fue un error, escríbenos a este mismo correo y lo revisamos.</p>'
        "</main></body></html>"
    )


def invalid_link_page() -> str:
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Enlace no válido · Clonexa</title><meta name="robots" content="noindex"></head>'
        '<body style="font-family:Segoe UI,Arial,sans-serif;background:#f6f3f8;color:#1d1424;padding:32px 16px">'
        '<main style="max-width:480px;margin:0 auto;background:#fff;border-radius:16px;padding:24px">'
        '<h1 style="font-size:20px;margin:0 0 10px">Este enlace no es válido</h1>'
        '<p style="font-size:15px;line-height:1.5">Responde al correo con la palabra NO y te quitamos de la lista de inmediato.</p>'
        "</main></body></html>"
    )
