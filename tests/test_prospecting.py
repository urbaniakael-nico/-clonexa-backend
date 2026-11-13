"""Prospeccion de Nexa: reglas puras (sin base).

- Cadenas fuera, correos solo del negocio (nada personal ni adivinado), redes sociales no son web.
- Horario legal (L-V 8:00-17:00 Bogota, sin festivos), respuesta NO, codigo del prospecto.
- Plantillas: asunto con el nombre, utm exactos, boton de WhatsApp con el codigo, enlace de baja, sin precios.
- IP: se ubica con la base offline y se guarda recortada + hash (nunca completa).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app.services import ip_geo
from app.services import prospecting as ps
from app.services import prospecting_email as pe

CHAINS = ["El Corral", "Frisby", "KFC", "McDonald's", "Crepes & Waffles", "Juan Valdez", "Presto", "Subway", "Domino's"]


@pytest.mark.parametrize("name", ["Hamburguesas El Corral Kennedy", "FRISBY Américas", "KFC - Plaza de las Américas",
                                  "McDonalds Castilla", "Crepes and Waffles", "Juan Valdez Café", "Domino's Pizza Timiza",
                                  "Subway Techo"])
def test_cadenas_fuera(name):
    assert ps.is_chain(name, CHAINS)


@pytest.mark.parametrize("name", ["Asadero El Corralito de Doña Rosa", "Panadería La Espiga", "Bar La Esquina",
                                  "Restaurante Prestofino", "Confecciones Marlen"])
def test_negocios_pequenos_pasan(name):
    assert not ps.is_chain(name, ["El Corral", "Frisby", "KFC", "Presto"])


def test_correo_del_dominio_de_su_web_y_buzones_genericos():
    assert ps.business_email_ok("pedidos@laespiga.com.co", "https://www.laespiga.com.co/", "Panadería La Espiga") == (True, "dominio_propio")
    assert ps.business_email_ok("contacto.laespiga@gmail.com", "https://laespiga.wixsite.com/x", "Panadería La Espiga")[0]
    assert ps.business_email_ok("reservas@gmail.com", "", "Bar Uno")[0]


def test_correos_personales_y_ajenos_no():
    # nombre de persona en gmail: posible correo personal
    assert ps.business_email_ok("juan.perez1987@gmail.com", "https://laespiga.com.co", "Panadería La Espiga") == (False, "posible_personal")
    # el correo del disenador de la web (otro dominio)
    assert ps.business_email_ok("soporte@agenciaweb.com", "https://laespiga.com.co", "La Espiga")[0] is False
    assert ps.business_email_ok("noreply@laespiga.com.co", "https://laespiga.com.co", "La Espiga")[0] is False
    assert ps.business_email_ok("logo@2x.png", "https://laespiga.com.co", "La Espiga")[0] is False
    assert ps.business_email_ok("user@example.com", "", "X")[0] is False


def test_extraer_correo_de_la_pagina_y_link_de_contacto():
    page = """<html><body><script>var x="tracking@sentry.io"</script>
      <a href="mailto:Hola@LaEspiga.com.co?subject=hola">Escríbenos</a> juan.perez1987@gmail.com
      <a href="/contactenos">Contáctenos</a><a href="https://otro.com/contacto">otro</a></body></html>"""
    assert ps.best_email(page, "https://laespiga.com.co/", "Panadería La Espiga") == ("hola@laespiga.com.co", "dominio_propio")
    assert ps.contact_link(page, "https://laespiga.com.co/") == "https://laespiga.com.co/contactenos"
    assert ps.best_email("<p>juan.perez1987@gmail.com</p>", "https://laespiga.com.co/", "La Espiga") is None


def test_scan_web_va_a_contacto_y_redes_no_son_web():
    pages = {"https://laespiga.com.co/": '<a href="/contacto">Contacto</a>',
             "https://laespiga.com.co/contacto": "<p>Escríbenos: ventas@laespiga.com.co</p>"}

    async def fake(url):
        return url, pages.get(url, "")

    res = asyncio.run(ps.scan_website("https://laespiga.com.co/", "La Espiga", fetch=fake))
    assert res == {"email": "ventas@laespiga.com.co", "why": "dominio_propio", "source_url": "https://laespiga.com.co/contacto",
                   "status": "encontrado", "channels": {}}
    assert asyncio.run(ps.scan_website("https://instagram.com/laespiga", "La Espiga", fetch=fake))["status"] == "sin_web"
    assert asyncio.run(ps.scan_website("", "La Espiga", fetch=fake))["status"] == "sin_web"


def test_fetch_no_va_a_ips_privadas():
    assert asyncio.run(ps.fetch_page("http://127.0.0.1:8000/")) == ("", "")
    assert asyncio.run(ps.fetch_page("http://169.254.169.254/latest/meta-data")) == ("", "")
    assert asyncio.run(ps.fetch_page("file:///etc/passwd")) == ("", "")


def _bog(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ps.BOGOTA).astimezone(timezone.utc)


def test_horario_legal_lunes_a_viernes_8_a_17_sin_festivos():
    assert ps.in_legal_window(_bog(2026, 11, 10, 8, 0))       # martes 8:00
    assert ps.in_legal_window(_bog(2026, 11, 10, 16, 59))
    assert not ps.in_legal_window(_bog(2026, 11, 10, 7, 59))
    assert not ps.in_legal_window(_bog(2026, 11, 10, 17, 0))
    assert not ps.in_legal_window(_bog(2026, 11, 14, 10))     # sabado
    assert not ps.in_legal_window(_bog(2026, 11, 15, 10))     # domingo
    assert not ps.in_legal_window(_bog(2026, 11, 16, 10))     # festivo (Independencia de Cartagena, lunes 16)
    assert not ps.in_legal_window(_bog(2026, 12, 8, 10))      # festivo fijo


def test_respuesta_no_y_baja():
    assert ps.is_negative("No")
    assert ps.is_negative("No gracias, no nos interesa\n\nEl lun, Clonexa escribió:\n> hola")
    assert ps.is_negative("Por favor quítenme de su lista")
    assert ps.is_negative("", "Re: dar de baja")
    assert not ps.is_negative("Hola, ¿cuánto cuesta? No sé cómo funciona el QR, ¿me explican?")
    assert not ps.is_negative("Sí, me interesa la demo\n> No quiero recibir más correos")  # el texto citado no cuenta


def test_codigo_del_prospecto_en_el_mensaje():
    assert ps.code_in("Hola, vi la carta video (código K7M2QD)") == "K7M2QD"
    assert ps.code_in("hola vi lo del bar codigo: ab12cd gracias") == "AB12CD"
    assert ps.code_in("hola, quiero info") == ""
    assert all(ch in ps.CODE_ALPHABET for ch in ps.new_code()) and len(ps.new_code()) == 6


def test_zona_circulo_y_poligono():
    z = {"kind": "circle", "center_lat": 4.62171, "center_lng": -74.15262, "radius_m": 750}
    assert ps.in_zone(z, 4.6220, -74.1530)
    assert not ps.in_zone(z, 4.70, -74.05)
    poly = {"kind": "polygon", "polygon": [[4.60, -74.16], [4.64, -74.16], [4.64, -74.13], [4.60, -74.13]]}
    assert ps.in_zone(poly, 4.62, -74.15) and not ps.in_zone(poly, 4.65, -74.15)


def test_tipo_desde_google():
    assert ps.classify_type({"primaryType": "fast_food_restaurant"}, "restaurante") == "comidas_rapidas"
    assert ps.classify_type({"primaryType": "bakery"}, "cafe") == "panaderia"
    assert ps.classify_type({"primaryType": "clothing_store"}, "taller") == "taller"
    assert ps.classify_type({"primaryType": "", "types": ["bar"]}, "bar") == "bar"


def test_peticion_a_places_con_zona_y_pagina():
    z = {"name": "Kennedy Central", "city": "Bogotá", "center_lat": 4.6, "center_lng": -74.1, "radius_m": 700}
    r = ps.places_request(z, "panaderia", "TOKEN")
    assert r["url"].endswith("places:searchText") and "places.websiteUri" in r["field_mask"] and "nextPageToken" in r["field_mask"]
    assert r["body"]["textQuery"] == "panaderías en Kennedy Central, Bogotá"
    assert r["body"]["includedType"] == "bakery" and r["body"]["pageToken"] == "TOKEN"
    assert "includedType" not in ps.places_request(z, "taller")["body"]


P = {"name": "Panadería La Espiga", "business_type": "panaderia", "code": "K7M2QD", "unsub_token": "tok_123", "email": "hola@laespiga.com.co"}


PAGE_OF = {"carta": "/restaurantes", "bar": "/bares", "taller": "/talleres-y-fabricas", "campo": "/personal-en-campo",
           "transporte": "/", "tienda": "/"}


@pytest.mark.parametrize("btype,segment", [("restaurante", "carta"), ("comidas_rapidas", "carta"), ("cafe", "carta"),
                                           ("panaderia", "carta"), ("bar", "bar"), ("taller", "taller"), ("fabrica", "taller"),
                                           ("electrico", "campo"), ("telecom", "campo"), ("construccion", "campo"),
                                           ("instalador", "campo"), ("aseo", "campo"), ("vigilancia", "campo"),
                                           ("transporte", "transporte"), ("tienda", "tienda")])
def test_plantillas_utm_whatsapp_y_baja(btype, segment):
    mail = pe.render({**P, "business_type": btype}, followup=False, settings=ps.DEFAULT_SETTINGS, zone_slug="kennedy-central")
    assert mail["segment"] == segment and mail["to"] == "hola@laespiga.com.co"
    assert mail["subject"].startswith("Panadería La Espiga")
    demo = urlparse(mail["demo_url"])
    q = parse_qs(demo.query)
    assert q == {"utm_source": ["email"], "utm_medium": ["prospeccion"],
                 "utm_campaign": [f"kennedy-central-{pe.TYPE_SLUG[btype]}"], "utm_content": ["K7M2QD"]}
    assert demo.netloc == "www.clonexa.com.co" and demo.path == PAGE_OF[segment], "pagina de su nicho (o la principal)"
    if segment in ("transporte", "tienda"):
        assert demo.fragment == "soluciones", "nicho sin pagina: principal con #seccion"
    assert "Negocio en vivo 3D" in mail["html"] and "Negocio en vivo 3D" in mail["text"]
    wa = urlparse(mail["wa_url"])
    assert wa.netloc == "wa.me" and wa.path == "/573144798220"
    assert "(código K7M2QD)" in unquote(parse_qs(wa.query)["text"][0])
    if segment == "carta":
        assert unquote(parse_qs(wa.query)["text"][0]) == "Hola, vi la carta video (código K7M2QD)"
        assert demo.fragment == "carta-video" and "carta-video.gif" in mail["html"]
        assert "de frente y de perfil" in mail["html"]
    assert mail["unsub_url"].endswith("/api/v1/prospecting/baja?t=tok_123")
    assert "No quiero recibir más correos" in mail["html"] and mail["unsub_url"] in mail["text"]
    assert "Nicolás Gómez · Clonexa" in mail["html"]
    assert not re.search(r"\$\s?\d|precio|COP|USD", mail["html"], re.I), "sin precios"


def test_seguimiento_es_corto_y_promete_no_insistir():
    mail = pe.render(P, followup=True, settings=ps.DEFAULT_SETTINGS, zone_slug="timiza")
    assert mail["subject"].startswith("Re: ") and "no les vuelvo a escribir" in mail["text"]
    assert "carta-video.gif" not in mail["html"]


def test_correo_oculto_en_el_mapa():
    assert ps.mask_email("hola@laespiga.com.co") == "h•••@laespiga.com.co"
    assert ps.mask_email("") == ""


def test_puntaje_de_zona_pesa_lo_cercano_a_cliente():
    assert ps.zone_score({"prospectos": 10}) < ps.zone_score({"prospectos": 1, "respondieron": 1})
    assert ps.zone_score({"clientes": 1}) > ps.zone_score({"demos": 1})


# ---------------------------------------------------------------- IP
class FakeReader:
    def get(self, ip):
        return {"190.24.10.10": {"country": {"iso_code": "CO"}, "subdivisions": [{"names": {"en": "Bogota D.C."}}],
                                 "city": {"names": {"en": "Bogotá"}}, "location": {"latitude": 4.61, "longitude": -74.08}}}.get(ip)


def test_ip_se_ubica_y_no_se_guarda_completa():
    ip_geo.set_reader(FakeReader())
    try:
        g = ip_geo.locate_and_mask("190.24.10.10")
        assert g["ip_address"] == "190.24.10.0" and "190.24.10.10" not in str(g)
        assert len(g["ip_hash"]) == 32 and g["ip_hash"] == ip_geo.ip_hash("190.24.10.10")
        assert (g["country"], g["region"], g["city"], g["lat"], g["lng"], g["geo_source"]) == ("CO", "Bogota D.C.", "Bogotá", 4.61, -74.08, "dbip")
        assert ip_geo.locate_and_mask("10.0.0.5")["geo_source"] == ""          # privada: no se busca
        assert ip_geo.truncate("2800:e2:2780:1234::1") == "2800:e2:2780::/48"
        assert ip_geo.truncate("181.49.3.7:5555") == "181.49.3.0"
        assert ip_geo.truncate("no-ip") == "" and ip_geo.ip_hash("") == ""
    finally:
        ip_geo.set_reader(None)
        ip_geo._STATE.update({"reader": None, "path": None, "failed": False})


def test_sin_base_no_rompe(monkeypatch, tmp_path):
    monkeypatch.setenv("IP_GEO_DB", str(tmp_path / "no-existe.mmdb"))
    ip_geo._STATE.update({"reader": None, "path": None, "failed": False})
    g = ip_geo.locate_and_mask("190.24.10.10")
    assert g["geo_source"] == "" and g["ip_address"] == "190.24.10.0" and g["lat"] is None
    ip_geo._STATE.update({"reader": None, "path": None, "failed": False})


def test_dockerfile_descarga_dbip_con_atribucion():
    from pathlib import Path

    docker = Path(__file__).resolve().parents[1].joinpath("Dockerfile").read_text(encoding="utf-8")
    assert "download.db-ip.com/free/dbip-city-lite-" in docker and "IP Geolocation by DB-IP" in docker
    assert ip_geo.DEFAULT_PATH in docker.replace("/app/data/geo/dbip-city-lite.mmdb", ip_geo.DEFAULT_PATH)


# ------------------------------------------------------------------ 025p: nichos
from app.services import prospecting_niches as pn  # noqa: E402


def test_cada_tipo_tiene_nicho_y_las_zonas_viejas_no_cambian():
    assert set(pn.TYPES) >= {"taller", "fabrica", "electrico", "telecom", "construccion", "instalador", "aseo", "vigilancia", "transporte", "tienda"}
    assert {pn.niche_of(t) for t in pn.TYPES} == set(pn.NICHES)
    assert pn.zone_types({"niches": []}) == list(pn.LEGACY_TYPES), "Kennedy/Techo/Hipotecho buscan lo mismo que antes"
    assert set(pn.zone_types({"niches": ["campo"]})) == {"electrico", "telecom", "construccion", "instalador", "aseo", "vigilancia"}
    assert pn.priority("restaurante") == 1 and pn.priority("taller") == 1 and pn.priority("tienda") == 2
    assert sum(pn.DEFAULT_SEARCH_LIMITS.values()) <= pn.DAILY_MAX_SEARCHES
    assert set(pn.MISSING_PAGES) == {"transporte", "tienda"}, "paginas que faltan en la landing (no se inventan)"
    assert pn.landing_url("https://www.clonexa.com.co/", "tienda", {"utm_source": "email"}) == "https://www.clonexa.com.co/?utm_source=email#soluciones"
    assert pn.landing_url("https://www.clonexa.com.co", "campo", {"a": "b"}) == "https://www.clonexa.com.co/personal-en-campo?a=b"


def test_vigencia_regla_inicial_12_meses():
    at = datetime(2026, 11, 12, tzinfo=timezone.utc)
    hours = {"weekdayDescriptions": ["lunes: 8–18"]}
    assert pn.vigencia({"businessStatus": "OPERATIONAL", "regularOpeningHours": hours, "userRatingCount": 8}, at=at)["estado"] == "activo"
    v = pn.vigencia({"businessStatus": "OPERATIONAL", "userRatingCount": 40}, at=at)
    assert v["estado"] == "por_verificar" and "sin horario" in v["motivo"]
    assert pn.vigencia({"businessStatus": "OPERATIONAL", "regularOpeningHours": hours, "userRatingCount": 1}, at=at)["estado"] == "por_verificar"
    assert pn.vigencia({"businessStatus": "CLOSED_TEMPORARILY", "regularOpeningHours": hours, "userRatingCount": 90}, at=at)["estado"] == "por_verificar"
    old = {"businessStatus": "OPERATIONAL", "regularOpeningHours": hours, "userRatingCount": 30, "reviews": [{"publishTime": "2024-05-01T00:00:00Z"}]}
    assert pn.vigencia(old, at=at)["estado"] == "por_verificar", "si hay fecha de resena, manda la fecha"
    new = {**old, "reviews": [{"publishTime": "2026-09-01T00:00:00Z"}]}
    assert pn.vigencia(new, at=at)["estado"] == "activo"
    grew = pn.vigencia({"businessStatus": "OPERATIONAL", "userRatingCount": 3}, at=at, prev_count=2, prev_at=at)
    assert grew["estado"] == "activo" and grew["last_activity_at"] == at, "resenas nuevas desde el ultimo refresco"


def test_field_mask_de_vigencia_no_sube_el_sku():
    assert "places.reviews" not in ps.FIELD_MASK and "reviews" not in ps.DETAIL_FIELD_MASK, "Atmosphere apagado"
    assert "places.regularOpeningHours" in ps.FIELD_MASK and "places.userRatingCount" in ps.FIELD_MASK


def test_canales_publicos_solo_perfiles_reales():
    c = pn.classify_link
    assert c("https://www.instagram.com/ConfeccionesMarta/?hl=es") == ("instagram", "@confeccionesmarta", "https://www.instagram.com/confeccionesmarta/")
    assert c("https://instagram.com/p/Cx123/") is None and c("https://www.instagram.com/explore/") is None
    assert c("https://www.instagram.com/clonexaapp/") is None, "nunca nuestra propia cuenta"
    assert c("https://web.facebook.com/ElectricosRL") == ("facebook", "electricosrl", "https://www.facebook.com/ElectricosRL")
    assert c("https://www.facebook.com/sharer/sharer.php?u=x") is None and c("https://facebook.com/groups/abc") is None
    assert c("https://www.facebook.com/profile.php?id=1000123") == ("facebook", "1000123", "https://www.facebook.com/profile.php?id=1000123")
    assert c("https://www.tiktok.com/@taller.marta") == ("tiktok", "@taller.marta", "https://www.tiktok.com/@taller.marta")
    assert c("https://wa.me/573001112233?text=hola") == ("whatsapp", "573001112233", "https://wa.me/573001112233")
    assert c("https://api.whatsapp.com/send?phone=573001112233") == ("whatsapp", "573001112233", "https://wa.me/573001112233")
    assert c("whatsapp://send?phone=573001112233")[0] == "whatsapp"
    assert c("https://wa.link/abc") is None and c("mailto:x@y.co") is None
    html = ('<a href="https://www.facebook.com/sharer.php?u=1">Compartir</a><a href="https://www.facebook.com/TallerMarta">FB</a>'
            '<a href="https://instagram.com/tallermarta">IG</a> escribenos https://wa.me/573001112233')
    ch = pn.extract_channels(html, "https://tallermarta.co/contacto")
    assert set(ch) == {"facebook", "instagram", "whatsapp"} and all(v["source"] == "https://tallermarta.co/contacto" for v in ch.values())
    assert ch["facebook"]["value"] == "tallermarta"
    assert pn.channel_from_website("https://www.instagram.com/rosa3") == ("instagram", {"value": "@rosa3", "url": "https://www.instagram.com/rosa3/", "source": "google:website"})
    assert pn.social_keys({"instagram": {"value": "@a"}, "web": {"value": "a.co"}}) == ["instagram:@a"]


def test_escaneo_de_la_web_trae_correo_y_redes_con_su_fuente():
    pages = {"https://tallermarta.co/": '<a href="https://instagram.com/tallermarta">IG</a><a href="/contacto">Contáctenos</a>',
             "https://tallermarta.co/contacto": '<p>info@tallermarta.co</p><a href="https://wa.me/573001112233">WhatsApp</a>'}

    async def fetch(url):
        return url, pages.get(url, "")

    r = asyncio.run(ps.scan_website("https://tallermarta.co/", "Taller Marta", fetch=fetch))
    assert r["email"] == "info@tallermarta.co" and r["source_url"] == "https://tallermarta.co/contacto"
    assert r["channels"]["instagram"]["source"] == "https://tallermarta.co/"
    assert r["channels"]["whatsapp"]["source"] == "https://tallermarta.co/contacto"
    assert ps.google_channels({"websiteUri": "https://facebook.com/TallerX", "nationalPhoneNumber": "601 234 5678"}) == {
        "phone": {"value": "601 234 5678", "url": "tel:6012345678", "source": "google:telefono"},
        "facebook": {"value": "tallerx", "url": "https://www.facebook.com/TallerX", "source": "google:website"}}


def test_costo_estimado_por_sku():
    e = pn.estimate_cost({"places_text": 700, "places_details": 40}, {"places_text": 1200})
    rows = {r["sku"]: r for r in e["rows"]}
    assert rows["Text Search Enterprise"]["usd_lista"] == 24.5 and rows["Text Search Enterprise"]["sobre_gratis"] == 200
    assert rows["Place Details Enterprise"]["usd_lista"] == 0.8 and e["usd_lista"] == 25.3
    assert pn.SKU_PRICE["places_text_atmos"][1] > pn.SKU_PRICE["places_text"][1], "resenas con fecha cuestan mas: apagado"
