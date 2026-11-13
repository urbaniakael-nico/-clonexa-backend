"""Mensajes de prospeccion de Nexa (2026-11-13): firmados como CLONEXA, sin nombre de una persona.

UNA sola fuente para Instagram / Facebook (cola de hoy, se envian A MANO) y para el correo: primero va el
bumeran de 6 s del nicho y luego este texto. Plantillas por nicho con {negocio} y {enlace}; seguimiento
unico a los 7 dias con {gancho}. Saltos de linea tal cual. Todas terminan con la linea de baja.

Enlace corto en la landing: /r restaurantes, /b bares, /t talleres, /c campo, /s tiendas, /l transporte
+ el codigo del prospecto (la landing redirige a la pagina del nicho con los utm y cuenta la apertura).
Puro: no toca la base. Sin precios.
"""
from __future__ import annotations

import html
from typing import Any

SHORT_HOST = "clonexa.com.co"
SHORT_LETTER = {"restaurante": "r", "bar": "b", "taller": "t", "campo": "c", "tienda": "s", "transporte": "l"}
NICHE_OF_LETTER = {v: k for k, v in SHORT_LETTER.items()}
BAJA_LINE = "Si no quieren más mensajes, respondan NO."
SOCIAL = {"instagram": ("Instagram", "@clonexaapp", "https://www.instagram.com/clonexaapp"),
          "tiktok": ("TikTok", "@clonexxa", "https://www.tiktok.com/@clonexxa"),
          "facebook": ("Facebook", "Clonexa", "https://www.facebook.com/1397005896827159")}
# bumeran de 6 s por nicho (tienda y transporte: sin video por ahora)
BOOMERANG = {"restaurante": "restaurante", "bar": "bar", "taller": "taller", "campo": "campo"}
GANCHO = {"restaurante": "carta en video", "bar": "bar en vivo en 3D", "taller": "taller en vivo",
          "campo": "equipo en campo en vivo en 3D", "tienda": "inventario que avisa", "transporte": "conductores en vivo"}

TEMPLATES: dict[str, str] = {
    "restaurante": """¡Hola, {negocio}! 👋🔥
Somos CLONEXA 🚀
¿Y si sus clientes vieran cada plato EN VIDEO 🎥 con solo escanear el QR de la mesa? Así 👆

🍽️ Carta video con QR
👨‍🍳 Pedidos directo a cocina, sin papelitos
🛵 Domicilios en el mismo sistema

👉 {enlace}
📲 Síganos: @clonexaapp · TikTok @clonexxa
¿Les mostramos cómo quedaría su carta? 😉
Si no quieren más mensajes, respondan NO.""",
    "bar": """¡Qué más, {negocio}! 🍻
Somos CLONEXA 🚀
¿Se imaginan ver su bar funcionando EN VIVO EN 3D? 🎮 Mesas, barra y pedidos en tiempo real, desde el celular o el TV 📺 Así 👆

📲 Pedidos por QR desde la mesa
🧾 Cuenta exacta por mesa, cero peleas al pagar
🎶 Piden canciones desde el celular

👉 {enlace}
📲 Síganos: @clonexaapp
¿Les mostramos cómo se vería el suyo? 😎
Si no quieren más mensajes, respondan NO.""",
    "taller": """¡Hola, {negocio}! 🧵✨
Somos CLONEXA 🚀
Vean su taller EN VIVO 🎥: quién está cosiendo, qué lote va y cuántas prendas lleva 👆

✂️ Producción por lote
💸 Pago por horas en minutos, sin Excel

👉 {enlace}
📲 Síganos: @clonexaapp
¿Se lo mostramos en 2 minutos? 😉
Si no quieren más mensajes, respondan NO.""",
    "campo": """¡Hola, {negocio}! ⚡
Somos CLONEXA 🚀
Sus técnicos marcan entrada y salida con GPS 📍 y ustedes los ven EN VIVO EN 3D, sin llamar a nadie 👆

📋 Reporte diario por WhatsApp
🧰 Material por obra

👉 {enlace}
📲 Síganos: @clonexaapp
¿Les mostramos cómo funciona? 💪
Si no quieren más mensajes, respondan NO.""",
    "tienda": """¡Hola, {negocio}! 🛒
Somos CLONEXA 🚀
¿Y si supieran qué producto se va a acabar ANTES de que se acabe? 📦

🧾 Ventas desde el celular
📦 Inventario que se descuenta solo
🔔 Aviso cuando algo se está agotando

👉 {enlace}
📲 Síganos: @clonexaapp
¿Les mostramos cómo funciona? 😉
Si no quieren más mensajes, respondan NO.""",
    "transporte": """¡Hola, {negocio}! 🚚
Somos CLONEXA 🚀
Vean a sus conductores EN VIVO 📍: rutas, entregas y novedades en un solo panel, sin llamar a nadie.

🗺️ Rutas del día
✅ Entregas confirmadas desde el celular

👉 {enlace}
📲 Síganos: @clonexaapp
¿Les mostramos cómo funciona? 💪
Si no quieren más mensajes, respondan NO.""",
}
FOLLOWUP = """¡Hola de nuevo, {negocio}! 👋
Somos CLONEXA. Les dejamos otro ejemplo de {gancho} 👆
Si quieren verlo con su negocio, respondan SÍ y se lo mostramos en 2 minutos 🙌
Si no, no les escribimos más."""
SUBJECT = {"restaurante": "{negocio}: su carta en video con QR 🎥", "bar": "{negocio}: su bar en vivo en 3D 🎮",
           "taller": "{negocio}: su taller en vivo 🧵", "campo": "{negocio}: su equipo en campo, en vivo en 3D ⚡",
           "tienda": "{negocio}: el inventario que avisa antes de agotarse 🛒", "transporte": "{negocio}: sus conductores en vivo 🚚"}


def _niche(niche: str) -> str:
    return niche if niche in TEMPLATES else "restaurante"


def business_name(name: Any) -> str:
    return " ".join(str(name or "su negocio").split())[:80]


def short_link(niche: str, code: str, *, scheme: bool = False) -> str:
    """clonexa.com.co/<letra>/<codigo> (la landing lo redirige con los utm y cuenta la apertura)."""
    path = f"{SHORT_HOST}/{SHORT_LETTER[_niche(niche)]}/{code}"
    return f"https://{path}" if scheme else path


def first_message(*, name: Any, niche: str, link: str) -> str:
    return TEMPLATES[_niche(niche)].format(negocio=business_name(name), enlace=link)


def followup_message(*, name: Any, niche: str) -> str:
    return FOLLOWUP.format(negocio=business_name(name), gancho=GANCHO[_niche(niche)])


def text(*, name: Any, niche: str, code: str, followup: bool) -> str:
    return followup_message(name=name, niche=niche) if followup else first_message(name=name, niche=niche, link=short_link(niche, code))


def has_boomerang(niche: str) -> bool:
    return _niche(niche) in BOOMERANG


def subject(*, name: Any, niche: str, followup: bool) -> str:
    base = SUBJECT[_niche(niche)].format(negocio=business_name(name))
    return f"Re: {base}" if followup else base


def email_html_body(message: str, *, link_url: str, link_text: str) -> str:
    """El texto del mensaje en parrafos de correo (respeta los saltos de linea; el enlace corto va enlazado)."""
    out = []
    for block in message.split("\n\n"):
        lines = []
        for line in block.split("\n"):
            esc = html.escape(line)
            if link_text and link_text in line:
                esc = esc.replace(html.escape(link_text), f'<a href="{html.escape(link_url, quote=True)}" style="color:#7c3aed;font-weight:700">'
                                  f"{html.escape(link_text)}</a>")
            lines.append(esc)
        out.append("<br>".join(lines))
    return "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.55;color:#1d1424">{p}</p>' for p in out)


def signature_html() -> str:
    """CLONEXA · Instagram @clonexaapp · TikTok @clonexxa · Facebook Clonexa (con iconos enlazados)."""
    icon = {"instagram": "📸", "tiktok": "🎵", "facebook": "📘"}
    links = " · ".join(f'<a href="{html.escape(url, quote=True)}" style="color:#1d1424;text-decoration:none">{icon[k]} {html.escape(label)} '
                       f"{html.escape(handle)}</a>" for k, (label, handle, url) in SOCIAL.items())
    return f'<p style="margin:12px 0 0;font-size:14px;color:#1d1424"><b>CLONEXA</b> · {links}</p>'


def signature_text() -> str:
    return "CLONEXA · " + " · ".join(f"{label} {handle} ({url})" for label, handle, url in SOCIAL.values())
