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
