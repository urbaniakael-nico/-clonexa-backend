"""CSV del Board de gerencia (interruptor reports_board). Salen de reports_board.build: mismas
cifras que la pantalla y que Nomina. Sin dinero. El PDF esta en lider_pdf."""
from __future__ import annotations

import csv
import io
from typing import Any

from app.services.reports_board import GPS_LABEL, MARK_LABEL, NOTE_KINDS, _marks_of

BOM = "﻿"


def safe_cell(value: Any) -> str:
    """Texto libre en un CSV: que Excel no lo tome como formula."""
    s = str(value if value is not None else "")
    return f"'{s}" if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def op_label(o: dict) -> str:
    return f"{o['name']} ({o['abbr']})" if o.get("abbr") else o["name"]


def perimeter_text(mark: dict) -> str:
    if not mark.get("s"):
        return ""
    label = GPS_LABEL.get(mark["s"], "")
    return f"{label}: {mark['n']}" if mark.get("n") else label


# ------------------------------------------------------------------ CSV
def build_marks_csv(board: dict) -> str:
    """Una fila por marca: operacion, empleado, documento, fecha, hora local, tipo, lat, lng, perimetro, nota."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["operacion", "empleado", "documento", "fecha", "hora_local", "tipo", "latitud", "longitud", "perimetro", "nota"])
    for o in board["operations"]:
        for p in o["people"]:
            for d in sorted(p["days"], key=lambda x: x["date"]):
                for s in d["shifts"]:
                    closing = " | ".join(n["text"] for n in s["notes"] if n["kind"] in NOTE_KINDS)
                    for m in _marks_of(s):
                        w.writerow([op_label(o), safe_cell(p["name"]), safe_cell(p["document"]), m["d"], f"{m['t']} {m['a']}", MARK_LABEL[m["k"]],
                                    m.get("lat", ""), m.get("lng", ""), perimeter_text(m), safe_cell(closing) if m["k"] == "out" else ""])
    return BOM + buf.getvalue()


def build_notes_csv(board: dict) -> str:
    """Una fila por nota: operacion, empleado, fecha, hora, texto."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["operacion", "empleado", "fecha", "hora", "texto"])
    for o in board["operations"]:
        for n in o["notes"]:
            w.writerow([op_label(o), safe_cell(n["employee"]), n.get("d") or "", f"{n['t']} {n['a']}".strip(), safe_cell(n["text"])])
    return BOM + buf.getvalue()


def _latin(value: Any) -> str:
    """Las fuentes base del PDF no traen emojis: se quitan sin romper tildes."""
    return " ".join(str(value if value is not None else "").encode("cp1252", "ignore").decode("cp1252").split())
