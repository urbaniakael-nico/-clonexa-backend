"""Sin letras dañadas ("SesiÃ³n", "Ã¢â‚¬â€") en los textos que ve la gente.

Solo se permiten las lineas que trabajan con el daño a proposito: la
normalizacion de company_users (.replace("Ã¡", "a") ...) y la busqueda de
modulos con nombre dañado guardado en la base (LIKE '%creaciÃ³n%mini%').
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"
BAD = re.compile("Ã[\u0080-¿‘-„€™ŒœŠšŸŽžƒˆ˜]|Â[ -¿]|â€")
ALLOWED = re.compile(r'\.replace\("Ã|LIKE \'%creaciÃ')


def test_no_broken_letters_in_app_texts():
    found = []
    for path in sorted(ROOT.rglob("*")):
        if path.suffix not in {".py", ".js", ".html", ".css", ".json"} or not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BAD.search(line) and not ALLOWED.search(line):
                found.append(f"{path.relative_to(ROOT.parent)}:{number}: {line.strip()[:100]}")
    assert not found, "Letras dañadas:\n" + "\n".join(found)
