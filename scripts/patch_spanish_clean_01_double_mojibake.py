from pathlib import Path

files = [
    Path("app/web/admin_v2.js"),
    Path("app/web/client.js"),
]

replacements = {
    "MÃƒÂ³dulos": "Módulos",
    "mÃƒÂ³dulos": "módulos",
    "MÃƒÂ³dulo": "Módulo",
    "mÃƒÂ³dulo": "módulo",
    "rÃƒÂ¡pidos": "rápidos",
    "rÃƒÂ¡pidas": "rápidas",
    "ÃƒÂšltima actualizaciÃƒÂ³n": "Última actualización",
    "ÃƒÂºltima actualizaciÃƒÂ³n": "última actualización",
    "NÃƒÂ³mina": "Nómina",
    "ProducciÃƒÂ³n": "Producción",
    "OperaciÃƒÂ³n": "Operación",
    "FidelizaciÃƒÂ³n": "Fidelización",
    "CreaciÃƒÂ³n": "Creación",
    "ConfiguraciÃƒÂ³n": "Configuración",
    "conexiÃƒÂ³n": "conexión",
    "validaciÃƒÂ³n": "validación",
    "DescripciÃƒÂ³n": "Descripción",
    "CategorÃƒÂ­a": "Categoría",
    "CÃƒÂ³digo": "Código",
}

changed = []

for path in files:
    src = path.read_text(encoding="utf-8-sig")
    before = src

    for bad, good in replacements.items():
        src = src.replace(bad, good)

    if src != before:
        path.write_text(src, encoding="utf-8")
        changed.append(str(path))

print("SPANISH_CLEAN_01_CHANGED:", changed)
