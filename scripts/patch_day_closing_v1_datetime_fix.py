from pathlib import Path
import re

path = Path("app/api/v1/endpoints/day_closing_v1.py")
src = path.read_text(encoding="utf-8-sig")

# 1) _range_utc debe devolver datetime reales, no strings.
old = '''def _range_utc(date_value: str, start_time: str, end_time: str, tz_name: str) -> tuple[str, str]:
    try:
        tz = ZoneInfo(tz_name or "America/Bogota")
    except Exception:
        raise HTTPException(status_code=422, detail="Zona horaria inválida.")

    start_local = datetime.fromisoformat(f"{date_value}T{start_time}:00").replace(tzinfo=tz)
    end_local = datetime.fromisoformat(f"{date_value}T{end_time}:00").replace(tzinfo=tz)

    if end_local <= start_local:
        raise HTTPException(status_code=422, detail="La hora fin debe ser mayor a la hora inicio.")

    return (
        start_local.astimezone(ZoneInfo("UTC")).isoformat(),
        end_local.astimezone(ZoneInfo("UTC")).isoformat(),
    )'''

new = '''def _range_utc(date_value: str, start_time: str, end_time: str, tz_name: str) -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(tz_name or "America/Bogota")
    except Exception:
        raise HTTPException(status_code=422, detail="Zona horaria inválida.")

    start_local = datetime.fromisoformat(f"{date_value}T{start_time}:00").replace(tzinfo=tz)
    end_local = datetime.fromisoformat(f"{date_value}T{end_time}:00").replace(tzinfo=tz)

    if end_local <= start_local:
        raise HTTPException(status_code=422, detail="La hora fin debe ser mayor a la hora inicio.")

    return (
        start_local.astimezone(ZoneInfo("UTC")),
        end_local.astimezone(ZoneInfo("UTC")),
    )'''

if old not in src:
    raise SystemExit("No encontré bloque _range_utc esperado.")
src = src.replace(old, new)

# 2) El response debe serializar range_utc como texto, pero las queries deben usar datetime.
old = '''        "range_utc": {
            "start": start_utc,
            "end": end_utc,
        },'''

new = '''        "range_utc": {
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
        },'''

if old not in src:
    raise SystemExit("No encontré bloque range_utc esperado.")
src = src.replace(old, new)

path.write_text(src, encoding="utf-8")

print("DAY_CLOSING_V1_DATETIME_FIX_OK")
