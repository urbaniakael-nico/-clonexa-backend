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
                   "status": "encontrado"}
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


@pytest.mark.parametrize("btype,segment", [("restaurante", "carta"), ("comidas_rapidas", "carta"), ("cafe", "carta"),
                                           ("panaderia", "carta"), ("bar", "bar"), ("taller", "taller")])
def test_plantillas_utm_whatsapp_y_baja(btype, segment):
    mail = pe.render({**P, "business_type": btype}, followup=False, settings=ps.DEFAULT_SETTINGS, zone_slug="kennedy-central")
    assert mail["segment"] == segment and mail["to"] == "hola@laespiga.com.co"
    assert mail["subject"].startswith("Panadería La Espiga")
    demo = urlparse(mail["demo_url"])
    q = parse_qs(demo.query)
    assert q == {"utm_source": ["email"], "utm_medium": ["prospeccion"],
                 "utm_campaign": [f"kennedy-central-{pe.TYPE_SLUG[btype]}"], "utm_content": ["K7M2QD"]}
    assert demo.netloc == "www.clonexa.com.co"
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
