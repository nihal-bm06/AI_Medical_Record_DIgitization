# ============================================================
#  schema_builder.py  —  Reads reference.xlsx → JSON schema
#  Used by medical_extractor.py and validator.py
# ============================================================
import pandas as pd, re
from config import EXCEL_PATH


def _clean(name):
    name = str(name).strip().lower()
    name = re.sub(r"[^\w\s]", "", name)
    return name.replace(" ", "_")


def _infer_type(name):
    if "age" in name: return "int"
    if "sex" in name: return ["Male", "Female"]
    if any(x in name for x in ["tobacco","alcohol","pain","burning","bleeding"]): return [0,1]
    return "string"


def build_schema() -> dict:
    try:
        df = pd.read_excel(EXCEL_PATH)
        return {_clean(col): {"type": _infer_type(_clean(col)), "description": f"Extract {_clean(col)}"} for col in df.columns}
    except FileNotFoundError:
        print(f"[schema] {EXCEL_PATH} not found — using empty schema")
        return {}