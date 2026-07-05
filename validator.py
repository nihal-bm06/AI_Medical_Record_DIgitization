# ============================================================
#  validator.py  —  Validates extracted row against schema
#  Keeps only known fields, normalises empty/null values
# ============================================================
from schema_builder import build_schema

SCHEMA = build_schema()


def validate(row: dict) -> dict:
    clean = {}
    for key in SCHEMA:
        val = row.get(key)
        if val in ("", "null", "N/A", "n/a"): val = None
        clean[key] = val
    return clean