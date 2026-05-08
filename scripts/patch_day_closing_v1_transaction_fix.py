from pathlib import Path
import re

path = Path("app/api/v1/endpoints/day_closing_v1.py")
src = path.read_text(encoding="utf-8-sig")

# 1) Cada excepción capturada en fuentes opcionales debe limpiar transacción.
src = src.replace(
'''        except Exception as exc:
            warnings.append(f"{table_name}: {type(exc).__name__}: {exc}")''',
'''        except Exception as exc:
            await db.rollback()
            warnings.append(f"{table_name}: {type(exc).__name__}: {exc}")'''
)

src = src.replace(
'''    except Exception:
        return []''',
'''    except Exception:
        await db.rollback()
        return []'''
)

src = src.replace(
'''    except Exception as exc:
        warnings.append(f"employees: {type(exc).__name__}: {exc}")
        return [], warnings''',
'''    except Exception as exc:
        await db.rollback()
        warnings.append(f"employees: {type(exc).__name__}: {exc}")
        return [], warnings'''
)

# 2) Después de preview interno del save, limpiar transacción antes del INSERT.
src = src.replace(
'''    summary = await _preview_payload(db, company_id, date_value, start_time, end_time, timezone)
    summary["responsible"] = responsible''',
'''    summary = await _preview_payload(db, company_id, date_value, start_time, end_time, timezone)

    # El preview consulta fuentes opcionales. Si alguna falla y fue capturada,
    # PostgreSQL puede dejar la transacción en aborted. Limpiamos antes de guardar.
    await db.rollback()

    summary["responsible"] = responsible'''
)

# 3) Hacer ORDER BY de materiales seguro: solo columnas existentes.
old = '''            result = await db.execute(
                text(f"""
                    SELECT {", ".join(select_parts)}
                    FROM {table_name}
                    WHERE company_id::text = :company_id
                      AND ({time_filter})
                    ORDER BY COALESCE(status_updated_at, delivered_at, requested_at, created_at, updated_at) ASC NULLS LAST
                    LIMIT 3000
                """),
                {
                    "company_id": company_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )'''

new = '''            order_candidates = [
                col for col in [
                    "status_updated_at",
                    "delivered_at",
                    "requested_at",
                    "created_at",
                    "updated_at",
                ]
                if col in cols
            ]

            order_expr = "COALESCE(" + ", ".join(order_candidates) + ")" if order_candidates else "1"

            result = await db.execute(
                text(f"""
                    SELECT {", ".join(select_parts)}
                    FROM {table_name}
                    WHERE company_id::text = :company_id
                      AND ({time_filter})
                    ORDER BY {order_expr} ASC NULLS LAST
                    LIMIT 3000
                """),
                {
                    "company_id": company_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )'''

if old not in src:
    raise SystemExit("No encontré bloque ORDER BY de materiales esperado.")
src = src.replace(old, new)

path.write_text(src, encoding="utf-8")

print("DAY_CLOSING_V1_TX_FIX_OK")
