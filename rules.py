'''
# ============================================================
#  rules.py  —  Post-processing rules for medical OCR data
#  Cleans up common patterns: age/sex combined, binary fields,
#  oral hygiene grading
# ============================================================

def apply_rules(row: dict) -> dict:
    row = _split_age_sex(row)
    row = _fix_binary_fields(row)
    row = _fix_oral_hygiene(row)
    return row


def _split_age_sex(row):
    if "age_sex" in row and row["age_sex"] and "/" in str(row["age_sex"]):
        age, sex = str(row["age_sex"]).split("/", 1)
        try:
            row["age"] = int(age.strip())
            row["sex"] = "Male" if sex.strip().upper() == "M" else "Female"
        except: pass
    return row


def _binary(val):
    if val is None: return None
    v = str(val).lower()
    if any(x in v for x in ["no","absent","negative"]): return 0
    if any(x in v for x in ["+","yes","present","positive"]): return 1
    return None


def _fix_binary_fields(row):
    binary_keywords = ["pain","tobacco","alcohol","burning","bleeding","swelling","ulcer"]
    for key in row:
        if any(kw in key for kw in binary_keywords):
            row[key] = _binary(row[key])
    return row


def _fix_oral_hygiene(row):
    if "oral_hygiene_status" not in row or not row["oral_hygiene_status"]:
        return row
    v = str(row["oral_hygiene_status"])
    row["oral_hygiene_status"] = "poor" if "+++" in v else ("fair" if "+" in v else "good")
    return row
'''
'''
# ============================================================
#  rules.py  —  Generalized post-processing for medical data
#  Works for ANY case sheet format — no hardcoded field names
# ============================================================

def apply_rules(row: dict) -> dict:
    """Apply all post-processing rules to a patient record."""
    row = _split_age_sex(row)
    row = _normalize_binary_fields(row)
    row = _normalize_oral_hygiene(row)
    row = _normalize_sex(row)
    row = _normalize_yes_no_fields(row)
    row = _clean_numeric_fields(row)
    return row


# ── Split combined age/sex like "52/M" or "45Y/F" ─────────
def _split_age_sex(row: dict) -> dict:
    for key in ["age_sex", "age/sex", "demographic"]:
        if key in row and row[key]:
            val = str(row[key])
            # Try "52/M" or "M/52" or "52Y/M"
            for sep in ["/", "-", " "]:
                parts = val.replace("Y","").replace("y","").split(sep)
                if len(parts) == 2:
                    a, s = parts[0].strip(), parts[1].strip()
                    try:
                        row["age"] = int(a)
                        row["sex"] = "Male" if s.upper() in ("M","MALE") else "Female"
                        break
                    except ValueError:
                        try:
                            row["age"] = int(s)
                            row["sex"] = "Male" if a.upper() in ("M","MALE") else "Female"
                            break
                        except: pass
    return row


# ── Normalize sex field regardless of abbreviation ─────────
def _normalize_sex(row: dict) -> dict:
    SEX_MAP = {
        "m": "Male", "male": "Male", "1": "Male",
        "f": "Female", "female": "Female", "2": "Female",
    }
    for key in list(row.keys()):
        if "sex" in key.lower() and row.get(key):
            v = str(row[key]).strip().lower()
            if v in SEX_MAP:
                row[key] = SEX_MAP[v]
    return row


# ── Binary fields: convert any positive indicator to 1, negative to 0
#    Works on ANY field dynamically — no hardcoded field list
def _normalize_binary_fields(row: dict) -> dict:
    BINARY_KEYWORDS = [
        "tobacco", "alcohol", "areca", "bleeding", "burning",
        "pain", "htn", "dm", "family_history", "lymph",
        "sponsored", "in_stock",
    ]
    POSITIVE = {"yes", "present", "positive", "+", "1", "true", "y"}
    NEGATIVE = {"no", "absent", "negative", "-", "0", "false", "n", "nil", "none"}

    for key in list(row.keys()):
        key_lower = key.lower()
        if any(kw in key_lower for kw in BINARY_KEYWORDS):
            val = row[key]
            if val is None:
                continue
            v = str(val).strip().lower()
            if v in POSITIVE:
                row[key] = 1
            elif v in NEGATIVE:
                row[key] = 0
            # else leave as-is (might be a detail string)
    return row


# ── Normalize Yes/No text fields ───────────────────────────
def _normalize_yes_no_fields(row: dict) -> dict:
    YES_NO_FIELDS = [
        "tobacco_use", "areca_nut_use", "alcohol_use",
        "bleeding_present", "burning_sensation",
        "htn", "dm",
    ]
    YES_VALS = {"yes", "y", "1", "true", "present", "positive", "+"}
    NO_VALS  = {"no", "n", "0", "false", "absent", "negative", "-", "nil"}

    for key in list(row.keys()):
        if key.lower() in YES_NO_FIELDS and row.get(key) is not None:
            v = str(row[key]).strip().lower()
            if v in YES_VALS:
                row[key] = "Yes"
            elif v in NO_VALS:
                row[key] = "No"
    return row


# ── Oral hygiene: grade from calculus/debris notation ──────
def _normalize_oral_hygiene(row: dict) -> dict:
    for key in list(row.keys()):
        if "oral_hygiene" in key.lower() or "hygiene" in key.lower():
            val = str(row.get(key, "") or "").strip()
            if not val or val.lower() in ("not documented", "none", ""):
                continue
            # Grade by notation
            if "+++" in val or "poor" in val.lower():
                row[key] = "Poor"
            elif "++" in val or "fair" in val.lower():
                row[key] = "Fair"
            elif "+" in val or "good" in val.lower():
                row[key] = "Fair"  # single + means some calculus → Fair
            elif any(x in val.lower() for x in ["no calculus", "clean", "adequate"]):
                row[key] = "Good"
            # else keep as-is (might be descriptive text)
    return row


# ── Clean numeric fields ────────────────────────────────────
def _clean_numeric_fields(row: dict) -> dict:
    NUMERIC_FIELDS = ["age", "price", "rating", "review_count",
                      "discount_pct", "original_price", "delivery_days"]
    for key in list(row.keys()):
        if key.lower() in NUMERIC_FIELDS and row.get(key) is not None:
            try:
                v = str(row[key]).replace(",","").replace("₹","").replace("%","").strip()
                row[key] = int(float(v))
            except (ValueError, TypeError):
                pass  # leave as-is if can't convert
    return row
'''

'''

import re
from typing import Any

from config import MISSING_VALUE

YES = "Yes"
NO = "No"
POSITIVE = "Positive"
NEGATIVE = "Negative"

BINARY_YES_PATTERNS = [
    r"\byes\b",
    r"\bpresent\b",
    r"\bpositive\b",
    r"\bdetected\b",
    r"\bseen\b",
    r"\bnoted\b",
    r"\bcomplains?\b",
    r"\bcomplaint of\b",
]

BINARY_NO_PATTERNS = [
    r"\bno\b",
    r"\babsent\b",
    r"\bnegative\b",
    r"\bdenies\b",
    r"\bnot present\b",
    r"\bnil\b",
]

KEYWORDS = {
    "Tobacco_Use": ["tobacco", "smoking", "smoker", "cigarette", "beedi", "bidi", "gutka", "gutkha", "pan masala", "khaini", "chewing tobacco"],
    "Areca_Nut_Use": ["areca", "betel nut", "supari", "pan", "gutka", "gutkha", "arecanut"],
    "Alcohol_Use": ["alcohol", "drinking", "liquor", "ethanol", "beer", "whisky", "wine", "rum"],
    "Bleeding_Present": ["bleeding"],
    "Burning_Sensation": ["burning sensation", "burning"],
    "Family_History": ["family history", "fh/o", "family h/o"],
    "Cervical_Lymphadenopathy": ["cervical lymphadenopathy", "lymph node", "lymphadenopathy", "submandibular node"],
}

AGE_SEX_PATTERNS = [
    r"\b(?P<age>\d{1,3})\s*/\s*(?P<sex>[MmFf])\b",
    r"\bage\s*[:=-]?\s*(?P<age>\d{1,3})\b.{0,20}?\bsex\s*[:=-]?\s*(?P<sex>male|female|m|f)\b",
    r"\b(?P<sex>male|female|m|f)\b.{0,20}?\b(?P<age>\d{1,3})\s*(?:years?|yrs?)\b",
    r"\b(?P<age>\d{1,3})\s*(?:years?|yrs?)\s*/?\s*(?P<sex>male|female|m|f)\b",
]

HOSPITAL_PATTERNS = [
    r"\b(?:hospital\s*no|hospital\s*number|hosp\s*no|uhid|uhid\s*no|ip\s*no|op\s*no|reg\s*no|registration\s*no)\s*[:#-]?\s*([A-Za-z0-9\-/]+)",
]

BP_PATTERN = re.compile(r"\b(?:bp|b\.p\.)\s*[:=-]?\s*(\d{2,3})\s*/\s*(\d{2,3})\b", re.I)

DM_DRUGS = ["metformin", "insulin", "glimepiride", "vildagliptin", "glycomet", "teneligliptin", "diabetes", "diabetic"]
HTN_DRUGS = ["amlodipine", "telmisartan", "losartan", "atenolol", "metoprolol", "nifedipine", "olmesartan", "hypertension", "hypertensive"]


def clean_text(text: str) -> str:
    text = text.replace("\x0c", "\n")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_first(patterns: list[str], text: str, flags: int = re.I | re.S) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match
    return None


def _norm_missing(val: Any) -> str:
    if val is None:
        return MISSING_VALUE
    s = str(val).strip()
    return s if s else MISSING_VALUE


def _norm_sex(val: str) -> str:
    v = str(val).strip().lower()
    if v in {"m", "male"}:
        return "Male"
    if v in {"f", "female"}:
        return "Female"
    return MISSING_VALUE


def _binary_from_snippet(snippet: str) -> str:
    s = snippet.lower()
    if any(re.search(p, s) for p in BINARY_NO_PATTERNS):
        return NO
    if any(re.search(p, s) for p in BINARY_YES_PATTERNS):
        return YES
    return MISSING_VALUE


def _lymph_from_snippet(snippet: str) -> str:
    s = snippet.lower()
    if any(re.search(p, s) for p in BINARY_NO_PATTERNS):
        return NEGATIVE
    if any(re.search(p, s) for p in BINARY_YES_PATTERNS):
        return POSITIVE
    return MISSING_VALUE


def _extract_age_sex(text: str) -> dict[str, str]:
    match = _find_first(AGE_SEX_PATTERNS, text)
    out = {}
    if match:
        age = match.groupdict().get("age")
        sex = match.groupdict().get("sex")
        if age:
            out["Age"] = age
        if sex:
            out["Sex"] = _norm_sex(sex)
    return out


def _extract_hospital_no(text: str) -> dict[str, str]:
    for pattern in HOSPITAL_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return {"Hospital_No": match.group(1).strip()}
    return {}


def _extract_bp_htn(text: str) -> str:
    for sys_bp, dia_bp in BP_PATTERN.findall(text):
        try:
            if int(sys_bp) >= 140 or int(dia_bp) >= 90:
                return YES
        except ValueError:
            pass
    low = text.lower()
    if any(drug in low for drug in HTN_DRUGS):
        return YES
    if re.search(r"\b(htn|hypertension|known hypertensive)\b", low):
        return YES
    if re.search(r"\b(no htn|non-hypertensive|hypertension absent)\b", low):
        return NO
    return MISSING_VALUE


def _extract_dm(text: str) -> str:
    low = text.lower()
    if any(drug in low for drug in DM_DRUGS):
        return YES
    if re.search(r"\b(dm|diabetes mellitus|diabetic|known diabetic)\b", low):
        return YES
    if re.search(r"\b(no dm|non-diabetic|diabetes absent)\b", low):
        return NO
    sugars = re.findall(r"\b(?:fbs|fasting blood sugar|blood sugar)\s*[:=-]?\s*(\d{2,3})\b", low)
    for s in sugars:
        try:
            if int(s) >= 126:
                return YES
        except ValueError:
            pass
    return MISSING_VALUE


def _extract_oral_hygiene(text: str) -> str:
    low = text.lower()
    patterns = [
        r"(?:oral hygiene|oh|ohs)\s*[:=-]?\s*(poor|fair|good)",
        r"(?:calculus|debris|plaque|stains?)\s*[:=-]?\s*(\+{1,3})",
    ]
    for p in patterns:
        m = re.search(p, low)
        if not m:
            continue
        val = m.group(1)
        if val in {"poor", "fair", "good"}:
            return val.capitalize()
        if val == "+++":
            return "Poor"
        if val in {"++", "+"}:
            return "Fair"
    if re.search(r"\bno calculus\b|\bno debris\b|\bgood oral hygiene\b", low):
        return "Good"
    return MISSING_VALUE


def _extract_keyword_binary(text: str, field: str) -> str:
    keywords = KEYWORDS.get(field, [])
    low = text.lower()
    for kw in keywords:
        for m in re.finditer(re.escape(kw), low):
            start = max(0, m.start() - 80)
            end = min(len(low), m.end() + 120)
            snippet = low[start:end]
            if field == "Cervical_Lymphadenopathy":
                val = _lymph_from_snippet(snippet)
            else:
                val = _binary_from_snippet(snippet)
            if val != MISSING_VALUE:
                return val
    return MISSING_VALUE


def _extract_family_history_details(text: str) -> str:
    m = re.search(r"\b(?:family history|fh/o|family h/o)\b\s*[:=-]?\s*([^\n.;]{3,120})", text, re.I)
    if not m:
        return MISSING_VALUE
    details = m.group(1).strip(" :-")
    return details if details else MISSING_VALUE


def _extract_habit_details(text: str, field: str) -> str:
    keywords = KEYWORDS.get(field, [])
    low = text.lower()
    for kw in keywords:
        m = re.search(rf"([^\n]{{0,40}}{re.escape(kw)}[^\n]{{0,60}})", low, re.I)
        if m:
            return m.group(1).strip().capitalize()
    return MISSING_VALUE


def extract_regex_fields(text: str) -> dict[str, str]:
    text = clean_text(text)
    out: dict[str, str] = {}

    out.update(_extract_age_sex(text))
    out.update(_extract_hospital_no(text))

    out["HTN"] = _extract_bp_htn(text)
    out["DM"] = _extract_dm(text)
    out["Oral_Hygiene_Status"] = _extract_oral_hygiene(text)

    for field in [
        "Tobacco_Use",
        "Areca_Nut_Use",
        "Alcohol_Use",
        "Bleeding_Present",
        "Burning_Sensation",
        "Family_History",
        "Cervical_Lymphadenopathy",
    ]:
        out[field] = _extract_keyword_binary(text, field)

    out["Family_History_Details"] = _extract_family_history_details(text)
    out["Tobacco_Use_Details"] = _extract_habit_details(text, "Tobacco_Use")
    out["Areca_Nut_Details"] = _extract_habit_details(text, "Areca_Nut_Use")
    out["Alcohol_Use_Details"] = _extract_habit_details(text, "Alcohol_Use")

    return {k: _norm_missing(v) for k, v in out.items() if _norm_missing(v) != MISSING_VALUE}


def normalize_value(col: str, val: Any) -> str:
    if isinstance(val, list):
        val = "; ".join(str(x).strip() for x in val if str(x).strip())

    s = _norm_missing(val)
    if s == MISSING_VALUE:
        return s

    if col == "Sex":
        return _norm_sex(s)

    if col == "Age":
        m = re.search(r"\d{1,3}", s)
        return m.group(0) if m else MISSING_VALUE

    if col in {
        "HTN",
        "DM",
        "Family_History",
        "Bleeding_Present",
        "Burning_Sensation",
        "Tobacco_Use",
        "Areca_Nut_Use",
        "Alcohol_Use",
    }:
        low = s.lower()
        if low in {"1", "y", "yes", "present", "positive", "true"}:
            return YES
        if low in {"0", "n", "no", "absent", "negative", "false"}:
            return NO

    if col == "Cervical_Lymphadenopathy":
        low = s.lower()
        if low in {"1", "y", "yes", "present", "positive", "true"}:
            return POSITIVE
        if low in {"0", "n", "no", "absent", "negative", "false"}:
            return NEGATIVE

    if col == "Oral_Hygiene_Status":
        low = s.lower()
        if "+++" in low or "poor" in low:
            return "Poor"
        if "++" in low or " +" in low or low == "+" or "fair" in low:
            return "Fair"
        if "good" in low:
            return "Good"

    return s.strip()


def apply_rules(row: dict[str, Any], full_text: str | None = None) -> dict[str, str]:
    fixed = {k: normalize_value(k, v) for k, v in row.items()}

    if full_text:
        regex_fill = extract_regex_fields(full_text)
        for key, val in regex_fill.items():
            if fixed.get(key, MISSING_VALUE) == MISSING_VALUE and val != MISSING_VALUE:
                fixed[key] = normalize_value(key, val)

    return fixed
'''
'''
# ============================================================
# rules.py (SAFE — NO DATA LOSS)
# ============================================================

def apply_rules(row):

    if "Sex" in row:
        v = str(row["Sex"]).lower()
        if "m" in v: row["Sex"] = "Male"
        elif "f" in v: row["Sex"] = "Female"

    if "Age" in row:
        try:
            row["Age"] = int(str(row["Age"]).replace("y","").strip())
        except:
            pass


    # Oral hygiene normalization
    if "Oral_Hygiene_Status" in row:
        v = str(row["Oral_Hygiene_Status"]).lower()
        if "+++" in v or "poor" in v:
            row["Oral_Hygiene_Status"] = "Poor"
        elif "++" in v or "fair" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "+" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "good" in v:
            row["Oral_Hygiene_Status"] = "Good"

    return row
'''
'''
# ============================================================
#  rules.py
#  SAFE POST-PROCESSING ONLY (no destructive yes/no conversion)
# ============================================================

import re

def apply_rules(row: dict) -> dict:
    row = normalize_sex(row)
    row = normalize_age(row)
    row = normalize_oral_hygiene(row)
    row = normalize_binary_fields(row)
    return row


def normalize_sex(row: dict) -> dict:
    if "Sex" in row:
        v = str(row["Sex"]).strip().lower()
        if v in ["m", "male"]:
            row["Sex"] = "Male"
        elif v in ["f", "female"]:
            row["Sex"] = "Female"
    return row


def normalize_age(row: dict) -> dict:
    if "Age" in row:
        try:
            v = str(row["Age"]).strip()
            v = re.sub(r"[^0-9]", "", v)
            if v:
                row["Age"] = int(v)
        except:
            pass
    return row


def normalize_oral_hygiene(row: dict) -> dict:
    if "Oral_Hygiene_Status" in row:
        v = str(row["Oral_Hygiene_Status"]).strip().lower()

        if not v or v == "not documented":
            return row

        if "+++" in v or "poor" in v:
            row["Oral_Hygiene_Status"] = "Poor"
        elif "++" in v or "fair" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "+" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "good" in v or "clean" in v or "no calculus" in v:
            row["Oral_Hygiene_Status"] = "Good"

    return row


def normalize_binary_fields(row: dict) -> dict:
    """
    ONLY normalize truly binary fields.
    Never touch detail / diagnosis / complaint text.
    """
    binary_fields = [
        "HTN", "DM",
        "Family_History",
        "Burning_Sensation",
        "Bleeding_Present",
        "Tobacco_Use",
        "Areca_Nut_Use",
        "Alcohol_Use",
    ]

    pos = {"yes", "y", "1", "true", "present", "positive"}
    neg = {"no", "n", "0", "false", "absent", "negative"}

    for field in binary_fields:
        if field in row:
            v = str(row[field]).strip().lower()

            if v in pos:
                row[field] = "Yes"
            elif v in neg:
                row[field] = "No"

    # Cervical lymph nodes use Positive/Negative
    if "Cervical_Lymphadenopathy" in row:
        v = str(row["Cervical_Lymphadenopathy"]).strip().lower()
        if v in pos:
            row["Cervical_Lymphadenopathy"] = "Positive"
        elif v in neg:
            row["Cervical_Lymphadenopathy"] = "Negative"

    return row
'''
'''
# ============================================================
# rules.py
# SAFE POST-PROCESSING ONLY
# ============================================================

import re

def apply_rules(row: dict) -> dict:
    row = normalize_sex(row)
    row = normalize_age(row)
    row = normalize_oral_hygiene(row)
    row = normalize_binary_fields(row)
    return row

def normalize_sex(row: dict) -> dict:
    if "Sex" in row:
        v = str(row["Sex"]).strip().lower()
        if v in ["m", "male"]:
            row["Sex"] = "Male"
        elif v in ["f", "female"]:
            row["Sex"] = "Female"
    return row

def normalize_age(row: dict) -> dict:
    if "Age" in row:
        try:
            v = str(row["Age"]).strip()
            v = re.sub(r"[^0-9]", "", v)
            if v:
                row["Age"] = int(v)
        except:
            pass
    return row

def normalize_oral_hygiene(row: dict) -> dict:
    if "Oral_Hygiene_Status" in row:
        v = str(row["Oral_Hygiene_Status"]).strip().lower()

        if not v or v == "not documented":
            return row

        if "+++" in v or "poor" in v:
            row["Oral_Hygiene_Status"] = "Poor"
        elif "++" in v or "fair" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "+" in v:
            row["Oral_Hygiene_Status"] = "Fair"
        elif "good" in v or "clean" in v or "no calculus" in v:
            row["Oral_Hygiene_Status"] = "Good"

    return row

def normalize_binary_fields(row: dict) -> dict:
    binary_fields = [
        "HTN", "DM",
        "Family_History",
        "Burning_Sensation",
        "Bleeding_Present",
        "Tobacco_Use",
        "Areca_Nut_Use",
        "Alcohol_Use",
    ]

    pos = {"yes", "y", "1", "true", "present", "positive"}
    neg = {"no", "n", "0", "false", "absent", "negative"}

    for field in binary_fields:
        if field in row:
            v = str(row[field]).strip().lower()
            if v in pos:
                row[field] = "Yes"
            elif v in neg:
                row[field] = "No"

    if "Cervical_Lymphadenopathy" in row:
        v = str(row["Cervical_Lymphadenopathy"]).strip().lower()
        if v in pos:
            row["Cervical_Lymphadenopathy"] = "Positive"
        elif v in neg:
            row["Cervical_Lymphadenopathy"] = "Negative"

    return row
'''

# ============================================================
#  rules.py  —  Post-processing rules for medical OCR data
#  Cleans up common patterns: age/sex combined, binary fields,
#  oral hygiene grading
# ============================================================

def apply_rules(row: dict) -> dict:
    row = _split_age_sex(row)
    row = _fix_binary_fields(row)
    row = _fix_oral_hygiene(row)
    return row


def _split_age_sex(row):
    if "age_sex" in row and row["age_sex"] and "/" in str(row["age_sex"]):
        age, sex = str(row["age_sex"]).split("/", 1)
        try:
            row["age"] = int(age.strip())
            row["sex"] = "Male" if sex.strip().upper() == "M" else "Female"
        except: pass
    return row


def _binary(val):
    if val is None: return None
    v = str(val).lower()
    if any(x in v for x in ["no","absent","negative"]): return 0
    if any(x in v for x in ["+","yes","present","positive"]): return 1
    return None


def _fix_binary_fields(row):
    binary_keywords = ["pain","tobacco","alcohol","burning","bleeding","swelling","ulcer"]
    for key in row:
        if any(kw in key for kw in binary_keywords):
            row[key] = _binary(row[key])
    return row


def _fix_oral_hygiene(row):
    if "oral_hygiene_status" not in row or not row["oral_hygiene_status"]:
        return row
    v = str(row["oral_hygiene_status"])
    row["oral_hygiene_status"] = "poor" if "+++" in v else ("fair" if "+" in v else "good")
    return row