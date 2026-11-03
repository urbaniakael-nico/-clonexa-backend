"""Reparte tests/test_*.py en N grupos parejos para el CI (job "python-resto").

Uso: python scripts/ci_shard.py <grupo 1..N> <N>  -> imprime los archivos del grupo.
Peso de cada archivo = numero de pruebas (def test_) + extra si levanta Postgres
embebido (pgserver), que es lo que mas tarda. Reparto LPT (el mas pesado primero al
grupo mas liviano): determinista, sin dependencias.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PG_EXTRA = 25


def weight(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    tests = len(re.findall(r"^\s*(?:async\s+)?def test_", text, re.M))
    return max(1, tests) + (PG_EXTRA if "pgserver" in text else 0)


def shards(total: int, root: Path = Path("tests")) -> list[list[str]]:
    files = sorted(root.glob("test_*.py"))
    groups: list[tuple[int, list[str]]] = [(0, []) for _ in range(total)]
    for f in sorted(files, key=lambda p: (-weight(p), p.name)):
        i = min(range(total), key=lambda k: (groups[k][0], k))
        w, items = groups[i]
        groups[i] = (w + weight(f), items + [f.as_posix()])
    return [sorted(items) for _, items in groups]


if __name__ == "__main__":
    index, total = int(sys.argv[1]), int(sys.argv[2])
    print(" ".join(shards(total)[index - 1]))
