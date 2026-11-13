"""Correos de prospeccion de Nexa: plantillas por tipo de negocio (sin precios), enlaces con utm y
pie legal (Ley 2300 de 2023 / Ley 1581 de 2012).

Un segmento por nicho (025p):
- carta      (restaurante, comidas rapidas, cafe, panaderia): la CARTA EN VIDEO CON QR -> /restaurantes#carta-video.
- bar        : las 5 fugas de dinero (inventario, pedidos QR, mesas abiertas, caja, turnos) -> /bares.
- taller     (talleres de confeccion y fabricas pequenas): nomina en 5 minutos y costo por prenda -> /talleres-y-fabricas.
- campo      (electricos, telecomunicaciones, construccion, instaladores, aseo, vigilancia): turnos con GPS y bot,
               cortes por WhatsApp, materiales, nomina -> /personal-en-campo.
- transporte : rutas, despachos y llamadas -> pagina principal #soluciones (no hay pagina propia).
- tienda     : ventas e inventario -> pagina principal #soluciones (no hay pagina propia).
Todos mencionan Negocio en vivo 3D en una linea.

Todo correo lleva: por que le escribimos (correo publicado en su web), quien escribe, y el enlace
"No quiero recibir más correos" (baja inmediata y permanente). Puro: no toca la base.
"""
from __future__ import annotations

import html
from urllib.parse import quote, urlencode

from app.services import prospecting_messages as pm
from app.services import prospecting_niches as pn

WA_NUMBER = "573144798220"
DEFAULT_LANDING = "https://www.clonexa.com.co/"
DEFAULT_BACKEND = "https://clonexa-backend-production.up.railway.app"
GIF_PATH = "clonexa-media/carta-video.gif"

# segmento de la plantilla = nicho (restaurantes y comidas se llama "carta" desde 025i)
SEGMENT_OF_NICHE = {"restaurante": "carta", "bar": "bar", "taller": "taller", "campo": "campo", "transporte": "transporte",
                    "tienda": "tienda"}
NICHE_OF_SEGMENT = {v: k for k, v in SEGMENT_OF_NICHE.items()}
SEGMENT_OF = {t: SEGMENT_OF_NICHE[pn.niche_of(t)] for t in pn.TYPES}
TYPE_SLUG = pn.TYPE_SLUG
WA_TEXT = {
    "carta": "Hola, vi la carta video (código {code})",
    "bar": "Hola, vi lo de las fugas de dinero del bar (código {code})",
    "taller": "Hola, vi lo de la nómina del taller (código {code})",
    "campo": "Hola, vi lo del control del personal en campo (código {code})",
    "transporte": "Hola, vi lo de las rutas y despachos (código {code})",
    "tienda": "Hola, vi lo de las ventas e inventario de la tienda (código {code})",
}
LIVE3D_LINE = pn.LIVE3D_LINE

PINK = "#ff2d6f"
INK = "#1d1424"
MUTED = "#6b5d73"


def segment(business_type: str) -> str:
    return SEGMENT_OF.get(business_type) or SEGMENT_OF_NICHE.get(business_type, "carta")


def campaign(zone_slug: str, business_type: str) -> str:
    return pn.campaign(zone_slug, business_type)


def utm_query(zone_slug: str, business_type: str, code: str) -> str:
    return urlencode({"utm_source": "email", "utm_medium": "prospeccion",
                      "utm_campaign": campaign(zone_slug, business_type), "utm_content": code})


def demo_url(landing: str, zone_slug: str, business_type: str, code: str, source: str = "email") -> str:
    """Pagina de la landing del nicho (/restaurantes, /bares, /talleres-y-fabricas, /personal-en-campo) o la
    principal con #seccion si el nicho no tiene pagina. Siempre con utm."""
    q = {"utm_source": source, "utm_medium": "prospeccion", "utm_campaign": campaign(zone_slug, business_type), "utm_content": code}
    return pn.landing_url(landing or DEFAULT_LANDING, pn.niche_of(business_type), q)


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
        "campo": f"{name}: su personal en campo, con turnos y GPS desde el celular",
        "transporte": f"{name}: rutas, despachos y personal en una sola herramienta",
        "tienda": f"{name}: ventas e inventario que cuadran, desde el celular",
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
            "campo": [f"Hola, equipo de {name}:",
                      "Les escribí hace una semana sobre el control del personal en campo (turnos con GPS, materiales y nómina).",
                      "Si les sirve, en 20 minutos les muestro cómo se vería con su equipo. Si no, no les vuelvo a escribir."],
            "transporte": [f"Hola, equipo de {name}:",
                           "Les escribí hace una semana sobre llevar rutas, despachos, llamadas y turnos en una sola herramienta.",
                           "Si les sirve, en 20 minutos les muestro cómo se vería en su operación. Si no, no les vuelvo a escribir."],
            "tienda": [f"Hola, equipo de {name}:",
                       "Les escribí hace una semana sobre las ventas y el inventario de la tienda desde el celular.",
                       "Si les sirve, en 20 minutos les muestro cómo se vería en su tienda. Si no, no les vuelvo a escribir."],
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
        "campo": [f"Hola, equipo de {name}:",
                  "Cuando el equipo trabaja en la calle, lo difícil es saber quién empezó, dónde está y cuántas horas lleva.",
                  "Con Clonexa cada persona inicia y cierra su turno desde el celular o un bot de Telegram, con GPS por zona de "
                  "trabajo; los cortes llegan por WhatsApp, las órdenes de materiales quedan con número y las horas salen listas "
                  "para la nómina.",
                  "¿Les muestro cómo se vería con su equipo?"],
        "transporte": [f"Hola, equipo de {name}:",
                       "En transporte y logística la información queda regada: despachos en un cuaderno, llamadas en el celular "
                       "y turnos en otra hoja.",
                       "Clonexa lo junta en una sola herramienta: despachos y llamadas registrados con su resultado, turnos del "
                       "personal desde el celular y reportes del día.",
                       "¿Les muestro cómo se vería en su operación?"],
        "tienda": [f"Hola, equipo de {name}:",
                   "En una tienda o minimercado la plata se pierde en lo que no cuadra: ventas sin registrar, inventario que "
                   "no coincide y turnos sin control.",
                   "Con Clonexa ven las ventas del día, el inventario que se descuenta con cada venta y los turnos del equipo, "
                   "desde el celular y sin equipos especiales.",
                   "¿Les muestro cómo se vería en su tienda?"],
    }[seg]


def _button(url: str, label: str, color: str) -> str:
    return (f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;background:{color};color:#ffffff;'
            'text-decoration:none;font-weight:700;font-size:15px;padding:12px 20px;border-radius:10px;margin:6px 6px 6px 0">'
            f"{html.escape(label)}</a>")


def boomerang_gif_url(landing: str, niche: str) -> str:
    """GIF liviano del bumeran del nicho (publico, en la landing). Tienda y transporte: sin bumeran por ahora."""
    return (landing or DEFAULT_LANDING).rstrip("/") + f"/clonexa-media/bumeran-{niche}.gif"


def render(prospect: dict, *, followup: bool, settings: dict, zone_slug: str) -> dict:
    """{subject, html, text, to}. prospect: name, business_type, code, unsub_token, email.
    2026-11-13: mismo texto y tono que Instagram/Facebook (prospecting_messages), firmado como CLONEXA, con el GIF del
    bumeran del nicho en lugar del video, el enlace corto y el enlace de baja."""
    name = pm.business_name(prospect.get("name"))
    btype = prospect.get("business_type") or "restaurante"
    seg = segment(btype)
    niche = pn.niche_of(btype)
    code = prospect.get("code") or ""
    landing = settings.get("landing_url") or DEFAULT_LANDING
    backend = settings.get("backend_url") or DEFAULT_BACKEND
    link = pm.short_link(niche, code, scheme=True)
    link_text = pm.short_link(niche, code)
    wa = wa_url(btype, code, settings.get("wa_number") or WA_NUMBER)
    baja = unsub_url(backend, prospect.get("unsub_token") or "")
    message = pm.followup_message(name=name, niche=niche) if followup else pm.first_message(name=name, niche=niche, link=link_text)
    subject = pm.subject(name=name, niche=niche, followup=followup)
    image = ""
    if pm.has_boomerang(niche):
        image = (f'<a href="{html.escape(link, quote=True)}"><img src="{html.escape(boomerang_gif_url(landing, niche), quote=True)}" width="260" '
                 f'alt="{html.escape(name)} en vivo con Clonexa" style="display:block;width:260px;max-width:100%;border-radius:16px;'
                 'border:0;margin:0 0 16px"></a>')
    legal = (f"Le escribimos porque el correo de {name} aparece publicado en su página web. "
             "Es un solo correo y, como máximo, un recordatorio. Clonexa · Bogotá, Colombia.")
    html_doc = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>{html.escape(subject)}</title></head>"
        '<body style="margin:0;padding:0;background:#f6f3f8">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f3f8"><tr><td align="center" style="padding:20px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px">'
        '<tr><td style="padding:24px 24px 8px;font-family:Segoe UI,Arial,sans-serif">'
        f"{image}{pm.email_html_body(message, link_url=link, link_text=link_text)}"
        f"{'' if followup else _button(link, 'Ver cómo funciona', PINK)}"
        f"{pm.signature_html()}"
        "</td></tr>"
        '<tr><td style="padding:12px 24px 22px;font-family:Segoe UI,Arial,sans-serif">'
        f'<p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:{MUTED}">{html.escape(legal)}</p>'
        f'<p style="margin:0;font-size:12px"><a href="{html.escape(baja, quote=True)}" style="color:{MUTED};text-decoration:underline">'
        "No quiero recibir más correos</a></p>"
        "</td></tr></table></td></tr></table></body></html>"
    )
    text_doc = message.replace(link_text, link) + f"\n\n{pm.signature_text()}\n\n{legal}\nNo quiero recibir más correos: {baja}\n"
    return {"subject": subject, "html": html_doc, "text": text_doc, "to": prospect.get("email") or "",
            "demo_url": link, "wa_url": wa, "unsub_url": baja, "segment": seg, "niche": niche}


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
