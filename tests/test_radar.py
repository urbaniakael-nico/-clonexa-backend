"""NEXUS · Radar: reglas puras (puntaje, huella, repetidas, textos de Telegram)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.services import radar as rd


def test_puntaje_impacto_vs_esfuerzo_vs_costo():
    assert rd.score("alto", "bajo", "bajo") == 100 and rd.score("bajo", "alto", "alto") == 0
    assert rd.score("alto", "medio", "medio") > rd.score("medio", "medio", "medio") > rd.score("bajo", "medio", "medio")
    assert rd.score("medio", "bajo", "medio") > rd.score("medio", "alto", "medio"), "menos esfuerzo sube"
    hoy = date(2026, 11, 13)
    assert rd.score("medio", "medio", "medio", date(2026, 11, 25), hoy) == rd.score("medio", "medio", "medio") + 5, "convocatoria que cierra pronto"
    assert rd.score("medio", "medio", "medio", date(2027, 3, 1), hoy) == rd.score("medio", "medio", "medio")


def test_huella_y_titulos_parecidos():
    assert rd.fingerprint("Convocatoria iNNpulsa para software") == rd.fingerprint("software, convocatoria de iNNpulsa para")
    assert rd.similar("Convocatoria iNNpulsa 2026 para startups de software", "iNNpulsa abre convocatoria para startups de software")
    assert not rd.similar("WhatsApp agrega catálogo en la API", "DIAN cambia la nómina electrónica")
    recent = [{"titulo": "Fondo Emprender abre convocatoria nacional", "huella": rd.fingerprint("Fondo Emprender abre convocatoria nacional"),
               "fuentes": [{"url": "https://www.fondoemprender.com/convocatoria-108"}]}]
    assert rd.is_repeated({"titulo": "Fondo Emprender abre convocatoria nacional 108", "fuentes": []}, recent)
    assert rd.is_repeated({"titulo": "Otra cosa distinta", "fuentes": [{"url": "https://fondoemprender.com/convocatoria-108/"}]}, recent), "misma fuente"
    assert not rd.is_repeated({"titulo": "Telegram lanza pagos con estrellas", "fuentes": [{"url": "https://telegram.org/blog/x"}]}, recent)


def test_mensaje_de_idea_con_fuente_y_tres_botones():
    i = {"id": 7, "titulo": "Convocatoria <MinTIC>", "resumen": "Apoyo a software", "por_que": "Financia el 3D", "impacto": "alto",
         "esfuerzo": "medio", "costo": "bajo", "costo_estimado": "US$0", "puntaje": 80, "estado": "nueva", "fecha_limite": "2026-12-01",
         "fuentes": [{"url": "https://www.mintic.gov.co/x", "titulo": "MinTIC", "fecha": "2026-11-10"}]}
    m = rd.idea_message(i)
    assert "&lt;MinTIC&gt;" in m and "https://www.mintic.gov.co/x" in m and "2026-11-10" in m and "Cierra: 2026-12-01" in m
    assert "Impacto alto · Esfuerzo medio · Costo bajo" in m
    b = rd.idea_buttons(i)
    assert b == {"interesa": "rx:me_interesa:7", "backlog": "rx:backlog:7", "descartar": "rx:descartada:7"}
    assert all(len(v.encode()) <= 64 for v in b.values())
    assert "Sin ideas aún" in rd.list_message([], "x")
    for cmd in ("/radar", "/ideas", "/backlog", "/ayuda"):
        assert cmd in rd.HELP


def test_proximo_informe_lunes_8():
    thu = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)
    assert rd.next_monday_8(thu).isoformat().startswith("2026-11-16T08:00:00-05:00")
    mon_before = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)   # 7:00 Bogota
    assert rd.next_monday_8(mon_before).day == 16
    mon_after = datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc)
    assert rd.next_monday_8(mon_after).day == 23
