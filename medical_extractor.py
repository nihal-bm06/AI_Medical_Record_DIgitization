# ============================================================
#  medical_extractor.py  —  OCR text → structured clinical data
#  Reads .txt files from data/ocr/ and maps fields using
#  the schema defined in data/reference.xlsx
# ============================================================
import json
from llm_client import call_llm
from schema_builder import build_schema

SCHEMA = build_schema()


def extract_medical(text: str) -> dict | None:
    return call_llm(f"""
You are a clinical data extraction system.
Extract ALL fields from the schema below from the clinical text.

Rules:
- "52/M" → age=52, sex=Male
- "+" or "present" → 1  |  "no" or "absent" → 0
- Convert clinical shorthand (e.g. HTN=hypertension, DM=diabetes)
- Return null only if truly missing — do NOT guess
- Return ONLY valid JSON, no markdown, no explanation

Schema:
{json.dumps(SCHEMA, indent=2)}

Clinical text:
{text}
""")