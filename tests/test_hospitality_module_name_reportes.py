"""El módulo "hospitality" se muestra como "Reportes" en todas las empresas.

Solo cambia el nombre visible: el código del módulo, sus rutas, permisos y
los datos guardados siguen siendo "hospitality".
"""
from __future__ import annotations

from pathlib import Path

from app.api.v1.endpoints import module_catalog_v1

CLIENT = Path("app/web/client.js").read_text(encoding="utf-8")
ADMIN = Path("app/web/admin_v2.js").read_text(encoding="utf-8")


def test_hospitality_module_is_named_reportes_in_the_company_panel():
    assert '    hospitality: ["Reportes", "analisis de cierres", "HSP"],' in CLIENT
    assert '<div class="client-eyebrow">Modulo Reportes</div>' in CLIENT
    assert '<h1 class="client-title">Reportes</h1>' in CLIENT
    assert 'hospitality: ["Hospitality", "analisis de cierres"' not in CLIENT
    # el código del módulo no cambia (navegación, permisos, rutas)
    assert 'renderClientNav("hospitality")' in CLIENT
    assert 'data-client-module="hospitality">Abrir Reportes</button>' in CLIENT


def test_hospitality_module_is_named_reportes_in_admin_v2_catalog():
    entry = module_catalog_v1.__dict__
    catalog = next(v for v in entry.values() if isinstance(v, dict) and "hospitality" in v and isinstance(v["hospitality"], dict) and "name" in v["hospitality"])
    assert catalog["hospitality"]["name"] == "Reportes"
    # la categoría que agrupa Pedidos, Mesas, etc. sigue igual
    assert catalog["hospitality"]["category"] == "hospitality"
    assert catalog["hospitality"]["category_label"] == "Hospitality"
    assert '    hospitality: ["Reportes", "Motor para bares' in ADMIN


def test_hospitality_module_rename_touches_no_data():
    # ninguna migración renombra el módulo en la base de datos
    for path in Path("migrations/versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "Reportes" not in text, path.name


def test_hospitality_pdf_footers_say_clonexa_reportes():
    """048J: the PDFs (dashboard and reorder) match the module's new name."""
    import re

    from app.api.v1.endpoints import hospitality

    source = Path("app/api/v1/endpoints/hospitality.py").read_text(encoding="utf-8")
    assert "CLONEXA Hospitality" not in source
    assert "Hospitality dashboard PDF" not in source
    assert '"Documento operativo generado por CLONEXA Reportes"' in source
    assert 'c.drawString(margin, 18, "CLONEXA / Reportes dashboard PDF")' in source

    payload = {
        "company": {"name": "Empresa", "timezone": "America/Bogota"}, "period": "daily", "period_label": "Diario",
        "range_label": "Hoy", "generated_at": "2026-09-24T12:00:00+00:00", "periods": [],
        "totals": {"total": 0, "orders": 0, "cash": 0, "transfer": 0, "card": 0, "other": 0, "tables": {}},
        "closures": [], "cards": [], "top_products": [], "top_tables": [], "top_songs": [],
    }
    pdf = hospitality.build_hospitality_dashboard_pdf(payload)
    assert pdf[:4] == b"%PDF"
    title = re.search(rb"/Title \(([^)]*)\)", pdf)
    assert title and b"Reportes" in title.group(1)
