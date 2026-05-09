from pathlib import Path

admin_path = Path("app/web/admin_v2.js")
client_path = Path("app/web/client.js")

def fix_text(src: str) -> str:
    replacements = {
        "modulos": "módulos",
        "Modulo": "Módulo",
        "modulo": "módulo",
        "Codigo": "Código",
        "codigo": "código",
        "Categoria": "Categoría",
        "categoria": "categoría",
        "Descripcion": "Descripción",
        "descripcion": "descripción",
        "Configuracion": "Configuración",
        "configuracion": "configuración",
        "conexion": "conexión",
        "validacion": "validación",
        "Documentacion": "Documentación",
        "Catalogo": "Catálogo",
        "rapidos": "rápidos",
        "Rapidos": "Rápidos",
        "rÃ¡pidos": "rápidos",
        "rÃ¡pidas": "rápidas",
        "MÃ³dulos": "Módulos",
        "mÃ³dulos": "módulos",
        "MÃ³dulo": "Módulo",
        "mÃ³dulo": "módulo",
        "Ãšltima actualizaciÃ³n": "Última actualización",
        "Ãºltima actualizaciÃ³n": "última actualización",
        "NÃ³mina": "Nómina",
        "Produccion": "Producción",
        "Operacion": "Operación",
        "Fidelizacion": "Fidelización",
        "Creacion": "Creación",
    }

    for bad, good in replacements.items():
        src = src.replace(bad, good)

    return src

for path in [admin_path, client_path]:
    if not path.exists():
        continue

    src = path.read_text(encoding="utf-8-sig")
    src = fix_text(src)

    path.write_text(src, encoding="utf-8")

print("MODULE_CATALOG_01_UI_TEXT_OK")
