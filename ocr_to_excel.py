'''
# ============================================================
#  ocr_to_excel.py
#
#  FOLDER STRUCTURE:
#  data/
#    patients/
#      patient_001/        <- folder name = patient ID
#        visit_1.txt       <- any number of .txt files
#        visit_2.txt
#        dental_2023.txt
#        ... (no limit)
#      patient_002/
#        ...
#
#  HOW TO RUN:
#    python ocr_to_excel.py
#
#  OUTPUT:
#    data/output_patients.csv
#    data/output_patients.xlsx
# ============================================================
import os, json
import argparse
import pandas as pd
from llm_client import call_llm


COLUMNS = [
    "Patient_ID", "Hospital_No", "ICD_Code", "Age", "Sex",
    "HTN", "DM", "Family_History", "Family_History_Details",
    "Chief_Complaint", "Mouth_Opening_Status", "Mouth_Opening_Details",
    "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Burning_Sensation", "Pain_Details",
    "Bleeding_Present", "Bleeding_Details", "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details", "Clinical_Diagnosis",
    "Final_Provisional_Dx", "Differential_Diagnosis", "TNM_Stage",
    "Histological_Subgroup", "Investigations", "Biopsy_Details",
    "Treatment_Plan", "Tobacco_Use", "Tobacco_Use_Details",
    "Areca_Nut_Use", "Areca_Nut_Details", "Alcohol_Use",
    "Alcohol_Use_Details", "Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

EXTRACTION_RULES = """
EXTRACTION RULES — apply these medical standards:

- Patient_ID: use the folder name as patient identifier

- Hospital_No: look for hospital number, registration number, MRD number

- HTN (Hypertension):
  Medical rule: systolic BP > 140 OR diastolic BP > 90 = Yes
  Also Yes if: antihypertensive medication prescribed, or "HTN"/"hypertension" explicitly stated
  No: only if ALL BP readings clearly below 140/90 with no medication
  Not documented: if no BP readings or mentions found

- DM (Diabetes Mellitus):
  Medical rule: fasting glucose > 126 mg/dL or RBS > 200 mg/dL = Yes
  Also Yes if: on insulin/metformin/diabetic medication, or "DM"/"diabetes" explicitly stated
  Not documented: if not mentioned

- Chief_Complaint: the patient's PRIMARY oral/dental complaint
  NOT a referral reason like "referred for oral prophylaxis"
  Look for: swelling, pain, ulcer, growth, difficulty opening mouth, bleeding
  Priority: oral surgery file > dental OPD > any oral symptom mention

- Mouth_Opening_Status: Normal / Restricted / Not documented
  Look for: "mouth opening", "trismus", finger breadth measurements

- Oral_Hygiene_Status:
  Calculus +++ OR Debris +++ = Poor
  Calculus ++ OR Debris ++ = Fair
  Calculus + OR Debris + = Fair
  No calculus/debris = Good
  Explicitly stated = use that value

- Tobacco_Use / Areca_Nut_Use / Alcohol_Use:
  Search EVERYWHERE in ALL files for these keywords:
  Tobacco: "tobacco", "smoking", "cigarette", "beedi", "bidi", "chewing", "gutka", "pan masala", "khaini"
  Areca: "areca", "betel", "pan", "supari", "gutkha"
  Alcohol: "alcohol", "drinking", "ethanol", "liquor"
  If ANY mention found → Yes with details
  If explicitly denied → No
  If not mentioned anywhere → Not documented

- Oral_Hygiene_Status:
  Search ALL files for: "calculus", "debris", "plaque", "stains", "hygiene"
  Calculus +++ or Debris +++ → Poor
  Calculus ++ or Debris ++ → Fair  
  Calculus + or Debris + → Fair
  "Good oral hygiene" or no calculus/debris mentioned → Good
  Explicitly stated value → use that
  If not mentioned anywhere → Not documented

- Treatment_Plan: combine ALL treatments from ALL files
  Include: dental treatments (scaling, extraction), surgical plans, medications for oral conditions
  Exclude: psychiatric medications unless directly relevant to oral condition

- Investigations: list ALL investigations ordered across all files with results if available

- TNM_Stage, Histological_Subgroup, Biopsy_Details:
  Only present in cancer/suspicious lesion cases
  Leave as "Not documented" if not a cancer case

- For ALL fields: if genuinely not found in any file → "Not documented"
- Return ONLY valid JSON — no markdown, no explanation
"""


def read_files(folder_path: str) -> list[tuple[str, str]]:
    """Read all .txt files, return list of (filename, content)."""
    files = sorted([f for f in os.listdir(folder_path) if f.endswith(".txt")])
    result = []
    for fname in files:
        with open(os.path.join(folder_path, fname), encoding="utf-8") as f:
            result.append((fname, f.read().strip()))
    return result


def chunk_files(file_contents: list[tuple[str, str]], max_chars: int = 10000) -> list[str]:
    """
    Group files into chunks that fit within max_chars.
    This handles patients with many files.
    """
    chunks = []
    current_chunk = []
    current_len = 0

    for fname, content in file_contents:
        entry = f"=== {fname} ===\n{content}"
        entry_len = len(entry)

        # If single file is too big, truncate it
        if entry_len > max_chars:
            entry = entry[:max_chars] + "\n[...truncated]"
            entry_len = max_chars

        if current_len + entry_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [entry]
            current_len = entry_len
        else:
            current_chunk.append(entry)
            current_len += entry_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def extract_from_chunk(chunk_text: str, patient_id: str,
                        existing: dict, chunk_num: int, total: int) -> dict:
    """
    Extract fields from one chunk of files.
    Pass existing results so LLM can fill gaps without overwriting good data.
    """
    # Tell LLM what's already filled so it doesn't overwrite with "Not documented"
    already_filled = {k: v for k, v in existing.items()
                      if v and v != "Not documented"}
    filled_str = json.dumps(already_filled, indent=2) if already_filled else "None yet"

    result = call_llm(f"""
You are a strict medical data extraction system. Extract ONLY what is EXPLICITLY written in the text.

CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER invent, guess, or assume any value.
2. ONLY extract text that is LITERALLY present in the case sheets below.
3. If a field is not clearly stated anywhere in the text → return "Not documented".
4. Do NOT infer diagnoses — only extract what is written as a diagnosis.
5. Do NOT calculate values — only extract what is explicitly shown.
6. Keep extracted values SHORT and EXACT — copy the actual words used in the notes.

Patient ID: {patient_id}
Chunk {chunk_num} of {total}

Already extracted (do NOT overwrite these with worse values):
{filled_str}

Extract these fields FROM THE TEXT BELOW. For each field:
- If clearly stated → extract the exact value
- If not found → "Not documented"

FIELDS:
- Patient_ID: patient folder/ID name
- Hospital_No: hospital registration number
- ICD_Code: ICD code if written
- Age: patient age as integer only
- Sex: Male or Female only
- HTN: Yes if BP > 140/90 or hypertension mentioned, No if normal BP, else Not documented
- DM: Yes if diabetes/metformin/insulin mentioned, No if explicitly denied, else Not documented
- Family_History: Positive/Negative/Not documented
- Family_History_Details: exact text about family history
- Chief_Complaint: patient's main oral/dental complaint in their own words
- Mouth_Opening_Status: Normal or Restricted or Not documented
- Mouth_Opening_Details: exact measurement or description if written
- Soft_Tissue_Exam: exact findings written in soft tissue examination
- Specific_Findings: exact clinical findings written by doctor
- Lesion_Type: exact type written e.g. Ulcerative, Leukoplakia, Nodular
- Lesion_Color: exact color written
- Lesion_Site: exact anatomical site written
- Burning_Sensation: Yes/No/Not documented — only if explicitly stated
- Pain_Details: exact pain description written
- Bleeding_Present: Yes/No/Not documented — only if explicitly stated
- Bleeding_Details: exact bleeding description written
- Cervical_Lymphadenopathy: Positive/Negative/Not documented — only if examined
- Cervical_Lymphadenopathy_Details: exact lymph node findings written
- Clinical_Diagnosis: exact diagnosis written by doctor
- Final_Provisional_Dx: exact final/provisional diagnosis written
- Differential_Diagnosis: exact differential diagnosis written
- TNM_Stage: exact TNM staging written e.g. T2N0M0
- Histological_Subgroup: exact histological finding written
- Investigations: exact investigations ordered as written
- Biopsy_Details: exact biopsy result written
- Treatment_Plan: exact treatment written — include ALL treatments across all departments
- Tobacco_Use: Yes/No/Not documented — only from explicit statement or habit section
- Tobacco_Use_Details: exact tobacco habit description written
- Areca_Nut_Use: Yes/No/Not documented
- Areca_Nut_Details: exact areca/pan habit written
- Alcohol_Use: Yes/No/Not documented
- Alcohol_Use_Details: exact alcohol habit written
- Oral_Hygiene_Status: Poor if Calculus+++ or Debris+++, Fair if ++, Good if +/none, else Not documented
- Trauma_Irritation_History: exact trauma history written

Return ONLY valid JSON with exactly these 39 keys. No explanation. No markdown.

CASE SHEET TEXT:
{chunk_text}
""")
    return result or {}


def merge_results(base: dict, update: dict) -> dict:
    """
    Merge two extraction results.
    Only update a field if the new value is better (not 'Not documented').
    """
    merged = dict(base)
    for key in COLUMNS:
        new_val = update.get(key, "")
        old_val = merged.get(key, "Not documented")

        # Update if new value is substantive and old is empty/not documented
        if (new_val and
            str(new_val).strip().lower() not in ("not documented", "none", "", "nan") and
            str(old_val).strip().lower() in ("not documented", "none", "", "nan")):
            merged[key] = new_val

        # Also update if new value is longer/more detailed
        elif (new_val and
              str(new_val).strip().lower() not in ("not documented", "none", "", "nan") and
              len(str(new_val)) > len(str(old_val))):
            merged[key] = new_val

    return merged


def targeted_search(all_text: str, patient_id: str, missing_fields: list) -> dict:
    """
    Second pass: search specifically for fields that are still missing.
    Sends the full combined text with focus only on missing fields.
    """
    if not missing_fields:
        return {}

    fields_str = "\n".join(f"- {f}" for f in missing_fields)

    result = call_llm(f"""
You are a strict medical data extraction system.
Search the text below for ONLY these specific fields: {fields_str}

STRICT RULES:
- Only extract what is EXPLICITLY written in the text.
- NEVER guess, infer or hallucinate a value.
- If the field is not clearly stated → "Not documented"

Search terms per field:
- Tobacco_Use: look for tobacco, smoking, cigarette, beedi, chewing, gutka, pan masala, khaini
- Areca_Nut_Use: look for areca, betel nut, pan, supari, gutkha
- Alcohol_Use: look for alcohol, drinking, liquor, ethanol
- Oral_Hygiene_Status: look for calculus, debris, plaque, stains (+++= Poor, ++=Fair, +=Fair)
- Family_History: look for family history, hereditary, cancer in family
- Burning_Sensation: look for burning sensation explicitly stated
- Bleeding_Present: look for bleeding explicitly stated
- Cervical_Lymphadenopathy: look for lymph node, neck node, cervical node findings

Return ONLY a JSON object with the requested fields.
Use "Not documented" for anything not clearly found.
No explanation. No markdown. No extra keys.

TEXT TO SEARCH:
{all_text[:15000]}
""")
    return result or {}


def extract_patient(folder_path: str, patient_id: str) -> dict:
    """Full extraction pipeline for one patient with any number of files."""

    # Read all files
    file_contents = read_files(folder_path)
    if not file_contents:
        print(f"  [ocr] No .txt files found")
        return {}

    print(f"  [ocr] {len(file_contents)} files → chunking...")

    # Split into chunks
    chunks = chunk_files(file_contents, max_chars=10000)
    print(f"  [ocr] {len(chunks)} chunk(s) to process")

    # Initialize result
    result = {col: "Not documented" for col in COLUMNS}
    result["Patient_ID"] = patient_id

    # Build full combined text for second pass
    full_text = "\n\n".join(
        f"=== {fname} ===\n{txt}"
        for fname, txt in file_contents
    )

    # Process each chunk, merging results progressively
    for i, chunk in enumerate(chunks):
        print(f"  [ocr] Chunk {i+1}/{len(chunks)}...")
        update = None
        for attempt in range(3):
            update = extract_from_chunk(chunk, patient_id, result, i+1, len(chunks))
            if update:
                break
            print(f"  [ocr] Chunk {i+1} attempt {attempt+1} failed, retrying...")
            import time; time.sleep(3)
        if update:
            result = merge_results(result, update)
        else:
            print(f"  [ocr] Chunk {i+1} failed after 3 attempts — skipping")

    # Second pass: targeted search for still-missing critical fields
    critical = ["Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
                "Oral_Hygiene_Status", "Family_History", "Burning_Sensation",
                "Bleeding_Present", "Cervical_Lymphadenopathy"]
    still_missing = [f for f in critical
                     if result.get(f, "Not documented") == "Not documented"]

    if still_missing:
        print(f"  [ocr] Second pass for: {still_missing}")
        update2 = targeted_search(full_text, patient_id, still_missing)
        if update2:
            result = merge_results(result, update2)

    return result


def run(patients_dir: str, output_csv: str, output_xlsx: str):
    """Process all patient folders."""

    subfolders = sorted([
        d for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d))
    ])

    if not subfolders:
        print(f"\n❌ No patient folders found in: {patients_dir}")
        print("\nExpected structure:")
        print(f"  {patients_dir}/")
        print(f"    patient_001/     <- any folder name, used as Patient_ID")
        print(f"      file1.txt      <- any number of .txt files")
        print(f"      file2.txt")
        print(f"    patient_002/")
        print(f"      ...")
        return

    print(f"\n[ocr] Found {len(subfolders)} patient folder(s)")

    # Load existing results to allow resuming interrupted runs
    existing_results = {}
    if os.path.exists(output_csv):
        try:
            existing_df = pd.read_csv(output_csv)
            for _, row in existing_df.iterrows():
                pid = str(row.get("Patient_ID", ""))
                filled = sum(1 for v in row.values
                             if str(v).strip().lower() not in
                             ("not documented","nan","none",""))
                existing_results[pid] = (row.to_dict(), filled)
            print(f"[ocr] Loaded {len(existing_results)} existing patient(s) from previous run")
        except:
            pass

    all_rows = list(r for r, _ in existing_results.values())

    for i, folder_name in enumerate(subfolders):
        folder_path = os.path.join(patients_dir, folder_name)
        print(f"\n{'='*55}")
        print(f"[ocr] Patient {i+1}/{len(subfolders)}: {folder_name}")

        # Check if already processed with good coverage (>25 fields filled)
        if folder_name in existing_results:
            _, filled_count = existing_results[folder_name]
            if filled_count >= 25:
                print(f"  [ocr] Already processed ({filled_count}/39 fields) — skipping")
                continue
            else:
                print(f"  [ocr] Previously incomplete ({filled_count}/39 fields) — reprocessing")
                # Remove old result so it gets replaced
                all_rows = [r for r in all_rows
                            if str(r.get("Patient_ID","")) != folder_name]

        row = extract_patient(folder_path, folder_name)
        if not row:
            print(f"  [ocr] Skipping — no data extracted")
            continue

        # Ensure all columns present, convert lists to strings, normalize values
        clean = {}
        for col in COLUMNS:
            val = row.get(col, "Not documented")
            if isinstance(val, list):
                val = "; ".join(str(v) for v in val)
            val = str(val).strip()

            # Normalize common abbreviations
            if col == "Sex":
                val = {"M": "Male", "F": "Female", "m": "Male", "f": "Female",
                       "MALE": "Male", "FEMALE": "Female"}.get(val, val)
                if val not in ("Male", "Female", "Not documented"):
                    val = "Male" if "m" in val.lower() else "Female"
            if col in ("HTN", "DM", "Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
                       "Bleeding_Present", "Burning_Sensation", "Family_History"):
                val = {"Y": "Yes", "N": "No", "y": "Yes", "n": "No",
                       "1": "Yes", "0": "No", "Positive": "Yes", "Negative": "No",
                       "Present": "Yes", "Absent": "No"}.get(val, val)
            if col == "Cervical_Lymphadenopathy":
                val = {"Y": "Positive", "N": "Negative", "Yes": "Positive",
                       "No": "Negative", "1": "Positive", "0": "Negative"}.get(val, val)

            clean[col] = "Not documented" if val in ("", "nan", "None", "[]", "Not documented") else val

        all_rows.append(clean)

        # Show summary
        filled = [k for k, v in clean.items() if v != "Not documented"]
        print(f"  [ocr] {len(filled)}/{len(COLUMNS)} fields filled")
        print(f"  [ocr] HTN={clean['HTN']} | DM={clean['DM']} | Tobacco={clean['Tobacco_Use']} | Oral_Hygiene={clean['Oral_Hygiene_Status']}")
        print(f"  [ocr] Diagnosis: {clean['Clinical_Diagnosis'][:70]}")

        # Save progress after every patient
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        print(f"  [ocr] Progress saved → {output_csv}")

    if all_rows:
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        df.to_excel(output_xlsx, index=False)

        print(f"\n{'='*55}")
        print(f"✅ DONE")
        print(f"   Patients   : {len(all_rows)}")
        print(f"   Columns    : {len(COLUMNS)}")
        print(f"   CSV        : {output_csv}")
        print(f"   Excel      : {output_xlsx}")
        print(f"\nPreview:")
        print(df[["Patient_ID","Age","Sex","Tobacco_Use",
                   "HTN","Oral_Hygiene_Status","Clinical_Diagnosis"]].to_string())
    else:
        print("\n❌ No patients processed.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--folder",  default="data/patients")
    p.add_argument("--output",  default="data/output_patients.csv")
    p.add_argument("--excel",   default="data/output_patients.xlsx")
    args = p.parse_args()
    os.makedirs("data", exist_ok=True)
    run(args.folder, args.output, args.excel)
'''
'''
# ============================================================
#  ocr_to_excel.py  —  Multi-department OCR → ML-ready Excel
#
#  Works for ANY patient regardless of:
#  - Number of case sheets (5 or 500)
#  - Department (dental, oral surgery, psychiatry, eye, etc.)
#  - Format (structured forms or free-text notes)
#
#  FOLDER STRUCTURE:
#  data/patients/
#    PATIENT_001/       ← folder name = Patient_ID
#      1.txt
#      2.txt
#      ... (any number)
#    PATIENT_002/
#      ...
#
#  RUN:
#    python ocr_to_excel.py
#
#  OUTPUT:
#    data/output_patients.csv
#    data/output_patients.xlsx
# ============================================================
import os, json, time, argparse
import pandas as pd
from llm_client import call_llm

# ── 39 target columns ─────────────────────────────────────
COLUMNS = [
    "Patient_ID", "Hospital_No", "ICD_Code", "Age", "Sex",
    "HTN", "DM", "Family_History", "Family_History_Details",
    "Chief_Complaint", "Mouth_Opening_Status", "Mouth_Opening_Details",
    "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Burning_Sensation", "Pain_Details",
    "Bleeding_Present", "Bleeding_Details", "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details", "Clinical_Diagnosis",
    "Final_Provisional_Dx", "Differential_Diagnosis", "TNM_Stage",
    "Histological_Subgroup", "Investigations", "Biopsy_Details",
    "Treatment_Plan", "Tobacco_Use", "Tobacco_Use_Details",
    "Areca_Nut_Use", "Areca_Nut_Details", "Alcohol_Use",
    "Alcohol_Use_Details", "Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

# Critical fields to verify in second pass
CRITICAL = [
    "Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
    "Oral_Hygiene_Status", "HTN", "DM",
    "Burning_Sensation", "Bleeding_Present", "Cervical_Lymphadenopathy",
    "Family_History",
]

CHUNK_SIZE = 20000  # ~20k chars — balance between speed and completeness


# ── EXTRACTION PROMPT ─────────────────────────────────────
EXTRACT_PROMPT = """You are a strict medical data extraction system for oral cancer research.
Read the hospital case sheets below and extract the requested fields.

STRICT RULES:
1. Only extract text that is EXPLICITLY written — never guess or invent.
2. If a field is not found anywhere → use exactly "Not documented"
3. Do not diagnose from symptoms — only copy written diagnoses.
4. Copy the doctor's exact words, keep values concise.

ALLOWED INFERENCES (these 3 only):
- HTN: if any BP reading is systolic>140 or diastolic>90 → "Yes"
       if antihypertensive drug mentioned (amlodipine, telmisartan, atenolol etc.) → "Yes"
- DM: if diabetes/metformin/insulin/glipizide mentioned → "Yes"
      if random blood sugar > 200 or fasting > 126 mentioned → "Yes"
- Oral_Hygiene_Status: Calculus+++ or Debris+++ → "Poor"
                       Calculus++ or Debris++ → "Fair"
                       Calculus+ or Debris+ → "Fair"
                       No calculus/debris mentioned → "Good"

FIELD RULES:
- Chief_Complaint: patient's main ORAL/DENTAL complaint only
  e.g. "swelling for 2 weeks", "ulcer on tongue", "difficulty opening mouth"
  NOT referral reasons like "referred for scaling" or "for oral prophylaxis"
- Sex: return ONLY "Male" or "Female"
- Age: return ONLY the integer e.g. 52
- Tobacco search: tobacco, smoking, cigarette, beedi, bidi, gutka, pan masala, khaini, chewing
- Areca search: areca, betel nut, pan, supari, gutkha, mawa
- Alcohol search: alcohol, drinking, liquor, spirits, beer, wine
- Treatment_Plan: combine ALL treatments from ALL departments in this chunk

Already extracted from earlier chunks (do NOT overwrite with "Not documented"):
{already_filled}

Patient: {patient_id} | Chunk {chunk_num}/{total_chunks}

Return ONLY valid JSON with EXACTLY these keys (no extra keys, no markdown):
{col_list}

CASE SHEETS:
{text}
"""

# ── SECOND PASS PROMPT ────────────────────────────────────
SECOND_PASS_PROMPT = """You are a strict medical data extractor.
Search the full patient text below for ONLY these missing fields: {fields}

RULES:
- Extract ONLY what is explicitly written.
- NEVER guess or invent a value.
- Allowed inferences:
  * HTN: BP>140/90 or antihypertensive drugs → "Yes"
  * DM: diabetes/metformin/insulin → "Yes"
  * Oral_Hygiene: Calculus+++→"Poor", ++→"Fair", +→"Fair"
- If not found: "Not documented"

Search terms by field:
- Tobacco_Use: tobacco, smoking, cigarette, beedi, bidi, gutka, pan masala, khaini, chewing
- Areca_Nut_Use: areca, betel nut, pan, supari, gutkha
- Alcohol_Use: alcohol, drinking, liquor, ethanol, spirits
- Oral_Hygiene_Status: calculus, debris, plaque, stains, oral hygiene
- HTN: blood pressure, BP, mmHg, hypertension, antihypertensive
- DM: diabetes, metformin, insulin, blood sugar, RBS, HbA1c
- Burning_Sensation: burning sensation, burning in mouth
- Bleeding_Present: bleeding, haemorrhage, blood from
- Cervical_Lymphadenopathy: lymph node, neck node, cervical node, LN

Return ONLY JSON with the requested field names as keys.
"Not documented" for anything not found. No markdown. No explanation.

FULL TEXT:
{text}
"""


# ── HELPERS ───────────────────────────────────────────────
def _is_empty(val) -> bool:
    return str(val).strip().lower() in (
        "not documented", "none", "", "nan", "[]", "n/a", "na", "null"
    )

def _normalize(col: str, val) -> str:
    """Normalize values to standard forms regardless of how LLM returns them."""
    if isinstance(val, list):
        val = "; ".join(str(v) for v in val)
    v = str(val).strip()

    if col == "Sex":
        mapping = {
            "M": "Male", "F": "Female", "m": "Male", "f": "Female",
            "MALE": "Male", "FEMALE": "Female", "male": "Male", "female": "Female",
            "1": "Male", "2": "Female"
        }
        v = mapping.get(v, v)
        # Fuzzy match
        if v not in ("Male", "Female", "Not documented"):
            v = "Male" if "male" in v.lower() else ("Female" if "female" in v.lower() else v)

    if col in ("HTN", "DM", "Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
               "Bleeding_Present", "Burning_Sensation"):
        mapping = {
            "Y": "Yes", "N": "No", "y": "Yes", "n": "No",
            "1": "Yes", "0": "No", "TRUE": "Yes", "FALSE": "No",
            "true": "Yes", "false": "No",
            "Present": "Yes", "Absent": "No",
            "Positive": "Yes", "Negative": "No",
            "+": "Yes", "-": "No",
        }
        v = mapping.get(v, v)

    if col == "Cervical_Lymphadenopathy":
        mapping = {
            "Yes": "Positive", "No": "Negative",
            "Y": "Positive", "N": "Negative",
            "1": "Positive", "0": "Negative",
            "yes": "Positive", "no": "Negative",
            "Present": "Positive", "Absent": "Negative",
        }
        v = mapping.get(v, v)

    if col == "Family_History":
        mapping = {
            "Yes": "Positive", "No": "Negative",
            "Y": "Positive", "N": "Negative",
            "yes": "Positive", "no": "Negative",
        }
        v = mapping.get(v, v)

    return "Not documented" if _is_empty(v) else v


def merge(base: dict, update: dict) -> dict:
    """Merge extraction results — never overwrite good values with empty."""
    merged = dict(base)
    for key in COLUMNS:
        new = str(update.get(key, "")).strip()
        old = str(merged.get(key, "Not documented")).strip()
        if _is_empty(new):
            continue
        if _is_empty(old):
            merged[key] = new
        elif len(new) > len(old) + 5:  # prefer more detailed value
            merged[key] = new
    return merged


# ── FILE READING ──────────────────────────────────────────
def read_files(folder_path: str) -> list[tuple[str, str]]:
    files = sorted([f for f in os.listdir(folder_path) if f.endswith(".txt")])
    result = []
    for fname in files:
        path = os.path.join(folder_path, fname)
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(path, encoding=enc) as f:
                    result.append((fname, f.read().strip()))
                break
            except UnicodeDecodeError:
                continue
    return result


# ── CHUNKING ──────────────────────────────────────────────
def chunk_files(file_contents: list[tuple[str, str]],
                max_chars: int = CHUNK_SIZE) -> list[str]:
    chunks, current, current_len = [], [], 0
    for fname, content in file_contents:
        entry = f"=== {fname} ===\n{content}"
        if len(entry) > max_chars:
            entry = entry[:max_chars] + "\n[...truncated]"
        if current_len + len(entry) > max_chars and current:
            chunks.append("\n\n".join(current))
            current, current_len = [entry], len(entry)
        else:
            current.append(entry)
            current_len += len(entry)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


# ── EXTRACTION ────────────────────────────────────────────
def extract_chunk(text: str, patient_id: str,
                  existing: dict, chunk_num: int, total: int) -> dict:
    already = {k: v for k, v in existing.items() if not _is_empty(v)}
    filled_str = json.dumps(already, indent=2) if already else "None yet"

    prompt = EXTRACT_PROMPT.format(
        already_filled = filled_str,
        patient_id     = patient_id,
        chunk_num      = chunk_num,
        total_chunks   = total,
        col_list       = ", ".join(COLUMNS),
        text           = text
    )
    return call_llm(prompt) or {}


def second_pass(all_text: str, missing_fields: list) -> dict:
    if not missing_fields:
        return {}
    prompt = SECOND_PASS_PROMPT.format(
        fields = ", ".join(missing_fields),
        text   = all_text[:20000]
    )
    result = call_llm(prompt) or {}
    time.sleep(2)
    return result


# ── MAIN PATIENT PIPELINE ─────────────────────────────────
def extract_patient(folder_path: str, patient_id: str) -> dict:
    file_contents = read_files(folder_path)
    if not file_contents:
        print("  [ocr] No .txt files found")
        return {}

    n_files = len(file_contents)
    print(f"  [ocr] {n_files} file(s) → chunking...")

    chunks = chunk_files(file_contents)
    print(f"  [ocr] {len(chunks)} chunk(s) → {len(chunks)} API call(s)")

    # Initialize all fields as Not documented
    result = {col: "Not documented" for col in COLUMNS}
    result["Patient_ID"] = patient_id

    # Full combined text for second pass
    full_text = "\n\n".join(f"=== {fn} ===\n{txt}" for fn, txt in file_contents)

    # ── Process each chunk ────────────────────────────────
    for i, chunk in enumerate(chunks):
        print(f"  [ocr] Chunk {i+1}/{len(chunks)}...")

        update = None
        for attempt in range(3):
            update = extract_chunk(chunk, patient_id, result, i+1, len(chunks))
            if update:
                break
            wait = 5 * (attempt + 1)
            print(f"  [ocr] Attempt {attempt+1} failed — retrying in {wait}s…")
            time.sleep(wait)

        if update:
            result = merge(result, update)
        else:
            print(f"  [ocr] Chunk {i+1} failed — skipping")

        # Small pause between chunks to avoid hammering rate limit
        if i < len(chunks) - 1:
            time.sleep(3)

    # ── Second pass: targeted search for missing critical fields ──
    missing_critical = [f for f in CRITICAL if _is_empty(result.get(f, ""))]
    if missing_critical:
        print(f"  [ocr] Second pass for {len(missing_critical)} missing fields: {missing_critical}")
        update2 = second_pass(full_text, missing_critical)
        if update2:
            result = merge(result, update2)
    else:
        print("  [ocr] All critical fields found — skipping second pass")

    # ── Normalize all values ──────────────────────────────
    for col in COLUMNS:
        result[col] = _normalize(col, result.get(col, "Not documented"))

    return result


# ── BATCH RUNNER ──────────────────────────────────────────
def run(patients_dir: str, output_csv: str, output_xlsx: str):
    subfolders = sorted([
        d for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d))
    ])

    if not subfolders:
        print(f"\n No patient folders found in: {patients_dir}")
        print(f"\nExpected:")
        print(f"  {patients_dir}/")
        print(f"    PATIENT_001/   <- any folder name")
        print(f"      1.txt")
        print(f"      2.txt")
        return

    print(f"\n[ocr] Found {len(subfolders)} patient folder(s)")

    # Resume support — load existing results
    existing = {}
    if os.path.exists(output_csv):
        try:
            existing_df = pd.read_csv(output_csv)
            for _, row in existing_df.iterrows():
                pid = str(row.get("Patient_ID", ""))
                filled = sum(1 for v in row.values if not _is_empty(str(v)))
                existing[pid] = (row.to_dict(), filled)
            print(f"[ocr] Resuming: {len(existing)} patient(s) from previous run")
        except:
            pass

    all_rows = [r for r, _ in existing.values()]

    for i, folder_name in enumerate(subfolders):
        folder_path = os.path.join(patients_dir, folder_name)
        print(f"\n{'='*55}")
        print(f"[ocr] Patient {i+1}/{len(subfolders)}: {folder_name}")

        # Skip if already well processed
        if folder_name in existing:
            _, filled_count = existing[folder_name]
            if filled_count >= 25:
                print(f"  [ocr] Already complete ({filled_count}/39) — skipping")
                continue
            else:
                print(f"  [ocr] Incomplete ({filled_count}/39) — reprocessing")
                all_rows = [r for r in all_rows
                            if str(r.get("Patient_ID", "")) != folder_name]

        row = extract_patient(folder_path, folder_name)
        if not row:
            print("  [ocr] No data — skipping")
            continue

        all_rows.append(row)

        # Summary
        filled = [k for k, v in row.items() if not _is_empty(v)]
        print(f"  [ocr] {len(filled)}/{len(COLUMNS)} fields filled")
        print(f"  [ocr] HTN={row['HTN']} | DM={row['DM']} | "
              f"Tobacco={row['Tobacco_Use']} | Hygiene={row['Oral_Hygiene_Status']}")
        diag = row.get('Clinical_Diagnosis', 'Not documented')
        print(f"  [ocr] Diagnosis: {diag[:70]}")

        # Save after every patient — safe against crashes
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        print(f"  [ocr] Saved → {output_csv}")

        # Pause between patients
        if i < len(subfolders) - 1:
            time.sleep(4)

    if all_rows:
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        df.to_excel(output_xlsx, index=False)
        print(f"\n{'='*55}")
        print(f"DONE — {len(all_rows)} patients | {len(COLUMNS)} columns")
        print(f"CSV  : {output_csv}")
        print(f"Excel: {output_xlsx}")
        preview_cols = ["Patient_ID","Age","Sex","HTN","DM",
                        "Tobacco_Use","Oral_Hygiene_Status","Clinical_Diagnosis"]
        print(f"\nPreview:")
        print(df[preview_cols].to_string())
    else:
        print("\nNo patients processed.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--folder", default="data/patients")
    p.add_argument("--output", default="data/output_patients.csv")
    p.add_argument("--excel",  default="data/output_patients.xlsx")
    args = p.parse_args()
    os.makedirs("data", exist_ok=True)
    run(args.folder, args.output, args.excel)
'''


'''
import argparse
import hashlib
import json
import os
import time
from typing import Iterable

import pandas as pd

from config import (
    CHUNK_SIZE,
    MISSING_VALUE,
    MIN_FILLED_FIELDS_TO_SKIP,
    OUTPUT_CSV,
    OUTPUT_XLSX,
    PATIENTS_DIR,
    PATIENT_COOLDOWN_SECONDS,
)
from llm_client import call_llm_json
from rules import apply_rules, clean_text, extract_regex_fields, normalize_value

COLUMNS = [
    "Patient_ID", "Hospital_No", "ICD_Code", "Age", "Sex",
    "HTN", "DM", "Family_History", "Family_History_Details",
    "Chief_Complaint", "Mouth_Opening_Status", "Mouth_Opening_Details",
    "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Burning_Sensation", "Pain_Details",
    "Bleeding_Present", "Bleeding_Details", "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details", "Clinical_Diagnosis",
    "Final_Provisional_Dx", "Differential_Diagnosis", "TNM_Stage",
    "Histological_Subgroup", "Investigations", "Biopsy_Details",
    "Treatment_Plan", "Tobacco_Use", "Tobacco_Use_Details",
    "Areca_Nut_Use", "Areca_Nut_Details", "Alcohol_Use",
    "Alcohol_Use_Details", "Oral_Hygiene_Status",
    "Trauma_Irritation_History",
]

ALWAYS_LLM_FIELDS = {
    "Chief_Complaint", "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Clinical_Diagnosis", "Final_Provisional_Dx",
    "Differential_Diagnosis", "Treatment_Plan", "Investigations", "Biopsy_Details",
    "Histological_Subgroup", "TNM_Stage", "Mouth_Opening_Status",
    "Mouth_Opening_Details", "Pain_Details", "Bleeding_Details",
    "Cervical_Lymphadenopathy_Details", "Trauma_Irritation_History", "ICD_Code",
}

FIELD_KEYWORDS = {
    "Hospital_No": ["hospital no", "uhid", "reg no", "op no", "ip no"],
    "Age": ["age", "yrs", "/m", "/f"],
    "Sex": ["sex", "male", "female", "/m", "/f"],
    "HTN": ["htn", "hypertension", "bp", "amlodipine", "telmisartan"],
    "DM": ["dm", "diabetes", "metformin", "insulin", "blood sugar"],
    "Family_History": ["family history", "fh/o"],
    "Family_History_Details": ["family history", "fh/o"],
    "Chief_Complaint": ["chief complaint", "complaint", "c/o", "complains of"],
    "Mouth_Opening_Status": ["mouth opening", "trismus"],
    "Mouth_Opening_Details": ["mouth opening", "trismus", "mm"],
    "Soft_Tissue_Exam": ["soft tissue", "intraoral", "extraoral"],
    "Specific_Findings": ["finding", "findings", "noted", "seen"],
    "Lesion_Type": ["ulcer", "growth", "patch", "plaque", "lesion"],
    "Lesion_Color": ["red", "white", "erythematous", "blanch", "color"],
    "Lesion_Site": ["buccal", "tongue", "palate", "vestibule", "site"],
    "Burning_Sensation": ["burning"],
    "Pain_Details": ["pain", "tenderness", "painful"],
    "Bleeding_Present": ["bleeding"],
    "Bleeding_Details": ["bleeding"],
    "Cervical_Lymphadenopathy": ["lymph", "lymphadenopathy", "node"],
    "Cervical_Lymphadenopathy_Details": ["lymph", "lymphadenopathy", "node"],
    "Clinical_Diagnosis": ["clinical diagnosis", "diagnosis", "provisional diagnosis"],
    "Final_Provisional_Dx": ["final diagnosis", "provisional diagnosis", "final provisional"],
    "Differential_Diagnosis": ["differential diagnosis", "ddx"],
    "TNM_Stage": ["tnm", "stage", "t1", "t2", "n1", "m0"],
    "Histological_Subgroup": ["histology", "histopathology", "subgroup", "grade"],
    "Investigations": ["investigation", "opg", "ct", "mri", "blood"],
    "Biopsy_Details": ["biopsy", "hpe", "histopathology"],
    "Treatment_Plan": ["treatment", "plan", "advised", "surgery", "medication"],
    "Tobacco_Use": ["tobacco", "smoking", "beedi", "bidi", "gutka", "pan masala"],
    "Tobacco_Use_Details": ["tobacco", "smoking", "beedi", "bidi", "gutka", "pan masala"],
    "Areca_Nut_Use": ["areca", "betel nut", "supari", "pan"],
    "Areca_Nut_Details": ["areca", "betel nut", "supari", "pan"],
    "Alcohol_Use": ["alcohol", "drinking", "liquor"],
    "Alcohol_Use_Details": ["alcohol", "drinking", "liquor"],
    "Oral_Hygiene_Status": ["oral hygiene", "calculus", "debris", "plaque", "stains"],
    "Trauma_Irritation_History": ["trauma", "irritation", "sharp tooth", "friction"],
}


def _is_empty(val: object) -> bool:
    return str(val).strip().lower() in {"", "none", "nan", "not documented", "n/a", "na", "[]"}


def read_files(folder_path: str) -> list[tuple[str, str]]:
    files = sorted(f for f in os.listdir(folder_path) if f.lower().endswith(".txt"))
    out: list[tuple[str, str]] = []
    seen_hashes: set[str] = set()

    for fname in files:
        path = os.path.join(folder_path, fname)
        text = None
        for enc in ("utf-8", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    text = clean_text(f.read())
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            continue

        if not text:
            continue

        digest = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        out.append((fname, text))

    return out


def chunk_files(file_contents: list[tuple[str, str]], max_chars: int = CHUNK_SIZE) -> list[str]:
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for fname, content in file_contents:
        entry = f"=== FILE: {fname} ===\n{content}"
        if len(entry) > max_chars:
            entry = entry[:max_chars] + "\n[TRUNCATED]"

        if current_parts and current_len + len(entry) > max_chars:
            chunks.append("\n\n".join(current_parts))
            current_parts = [entry]
            current_len = len(entry)
        else:
            current_parts.append(entry)
            current_len += len(entry)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


def merge_results(base: dict[str, str], update: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key in COLUMNS:
        old_val = normalize_value(key, merged.get(key, MISSING_VALUE))
        new_val = normalize_value(key, update.get(key, MISSING_VALUE))

        if _is_empty(new_val):
            continue
        if _is_empty(old_val):
            merged[key] = new_val
            continue

        if key.endswith("_Details") or key in {
            "Chief_Complaint", "Specific_Findings", "Clinical_Diagnosis",
            "Final_Provisional_Dx", "Differential_Diagnosis", "Treatment_Plan",
            "Investigations", "Biopsy_Details", "Lesion_Site", "Lesion_Type",
            "Lesion_Color", "Soft_Tissue_Exam",
        }:
            if len(str(new_val)) > len(str(old_val)):
                merged[key] = new_val

    return merged


def get_missing_fields(row: dict[str, str]) -> list[str]:
    return [col for col in COLUMNS if col != "Patient_ID" and _is_empty(row.get(col, MISSING_VALUE))]


def build_extraction_prompt(
    patient_id: str,
    chunk_text: str,
    chunk_num: int,
    total_chunks: int,
    missing_fields: list[str],
    known_fields: dict[str, str],
) -> str:
    return f"""
You are a strict medical case-sheet extraction system.

Task:
Extract ONLY these missing fields for this patient from the OCR text.
Do NOT return any other keys.

Patient_ID: {patient_id}
Chunk: {chunk_num}/{total_chunks}

Rules:
1. NEVER guess, infer, or hallucinate.
2. Use only text explicitly present in the OCR text.
3. Exception: you MAY mark HTN='Yes' if BP >= 140/90 or antihypertensive drug is written.
4. Exception: you MAY mark DM='Yes' if diabetes/insulin/metformin/high sugar is written.
5. If a field is absent, return exactly '{MISSING_VALUE}'.
6. Keep wording short and faithful to the case sheet.
7. Sex must be only 'Male' or 'Female'.
8. Age must be only the number.
9. Binary fields should be 'Yes'/'No'.
10. Cervical_Lymphadenopathy should be 'Positive'/'Negative'.
11. Oral_Hygiene_Status should be 'Good'/'Fair'/'Poor' if written or derivable from calculus/debris/plaque grading.

Missing fields to extract:
{json.dumps(missing_fields, ensure_ascii=False, indent=2)}

Already known fields (do not repeat or overwrite in your reasoning; these are already filled):
{json.dumps(known_fields, ensure_ascii=False, indent=2)}

Return EXACTLY one JSON object using only the missing field names above.
No markdown. No explanation.

OCR TEXT:
{chunk_text}
""".strip()


def collect_snippets_for_fields(text: str, fields: Iterable[str]) -> str:
    lines = text.splitlines()
    low_lines = [line.lower() for line in lines]
    snippets: list[str] = []
    added = set()

    for field in fields:
        keywords = FIELD_KEYWORDS.get(field, [field.lower().replace("_", " ")])
        for i, low_line in enumerate(low_lines):
            if any(kw in low_line for kw in keywords):
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                snippet = "\n".join(lines[start:end]).strip()
                if snippet and snippet not in added:
                    added.add(snippet)
                    snippets.append(snippet)

    if not snippets:
        return text[:4000]

    combined = "\n\n---\n\n".join(snippets)
    max_chars = max(5000, min(len(combined), 14000))
    return combined[:max_chars]


def second_pass(patient_id: str, full_text: str, row: dict[str, str]) -> dict[str, str]:
    missing_fields = get_missing_fields(row)
    if not missing_fields:
        return {}

    snippet_text = collect_snippets_for_fields(full_text, missing_fields)
    prompt = build_extraction_prompt(
        patient_id=patient_id,
        chunk_text=snippet_text,
        chunk_num=1,
        total_chunks=1,
        missing_fields=missing_fields,
        known_fields={k: v for k, v in row.items() if not _is_empty(v)},
    )
    return call_llm_json(prompt, expected_keys=missing_fields) or {}


def extract_patient(folder_path: str, patient_id: str) -> dict[str, str]:
    file_contents = read_files(folder_path)
    if not file_contents:
        print("  [ocr] no txt files found")
        return {}

    full_text = "\n\n".join(f"=== FILE: {name} ===\n{text}" for name, text in file_contents)
    result = {col: MISSING_VALUE for col in COLUMNS}
    result["Patient_ID"] = patient_id

    regex_fill = extract_regex_fields(full_text)
    result = merge_results(result, regex_fill)

    chunks = chunk_files(file_contents)
    print(f"  [ocr] {len(file_contents)} file(s), {len(chunks)} chunk(s)")

    for idx, chunk_text in enumerate(chunks, start=1):
        missing_fields = get_missing_fields(result)
        if not missing_fields:
            print("  [ocr] all fields filled before finishing all chunks")
            break

        chunk_regex = extract_regex_fields(chunk_text)
        result = merge_results(result, chunk_regex)
        missing_fields = get_missing_fields(result)
        if not missing_fields:
            break

        prompt = build_extraction_prompt(
            patient_id=patient_id,
            chunk_text=chunk_text,
            chunk_num=idx,
            total_chunks=len(chunks),
            missing_fields=missing_fields,
            known_fields={k: v for k, v in result.items() if not _is_empty(v)},
        )
        update = call_llm_json(prompt, expected_keys=missing_fields) or {}
        result = merge_results(result, update)

    still_missing = get_missing_fields(result)
    if still_missing:
        print(f"  [ocr] second pass for {len(still_missing)} field(s)")
        result = merge_results(result, second_pass(patient_id, full_text, result))

    result = apply_rules(result, full_text)
    result["Patient_ID"] = patient_id
    return {col: normalize_value(col, result.get(col, MISSING_VALUE)) for col in COLUMNS}


def count_filled_fields(row: dict[str, str]) -> int:
    return sum(1 for k, v in row.items() if k != "Patient_ID" and not _is_empty(v))


def load_existing_results(output_csv: str) -> dict[str, dict[str, str]]:
    if not os.path.exists(output_csv):
        return {}

    try:
        df = pd.read_csv(output_csv)
    except Exception:
        return {}

    out: dict[str, dict[str, str]] = {}
    for _, r in df.iterrows():
        row = {col: str(r.get(col, MISSING_VALUE)) for col in COLUMNS}
        pid = row.get("Patient_ID", "").strip()
        if pid:
            out[pid] = row
    return out


def run(patients_dir: str, output_csv: str, output_xlsx: str) -> None:
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)

    patient_folders = sorted(
        d for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d))
    )
    if not patient_folders:
        print(f"No patient folders found in {patients_dir}")
        return

    existing = load_existing_results(output_csv)
    all_rows = [row for _, row in sorted(existing.items())]
    existing_ids = {row["Patient_ID"] for row in all_rows if row.get("Patient_ID")}

    print(f"[ocr] found {len(patient_folders)} patient folder(s)")
    if existing:
        print(f"[ocr] existing output found for {len(existing)} patient(s)")

    for idx, patient_id in enumerate(patient_folders, start=1):
        folder_path = os.path.join(patients_dir, patient_id)
        print("\n" + "=" * 60)
        print(f"[ocr] patient {idx}/{len(patient_folders)}: {patient_id}")

        prev = existing.get(patient_id)
        if prev and count_filled_fields(prev) >= MIN_FILLED_FIELDS_TO_SKIP:
            print(f"  [ocr] already good enough ({count_filled_fields(prev)} filled) -> skipping")
            continue

        if patient_id in existing_ids:
            all_rows = [r for r in all_rows if r.get("Patient_ID") != patient_id]

        row = extract_patient(folder_path, patient_id)
        if not row:
            print("  [ocr] no data extracted")
            continue

        all_rows.append(row)
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        print(f"  [ocr] saved progress -> {output_csv}")
        print(
            "  [ocr] summary | "
            f"Age={row['Age']} Sex={row['Sex']} Tobacco={row['Tobacco_Use']} "
            f"HTN={row['HTN']} DM={row['DM']} Dx={row['Clinical_Diagnosis'][:60]}"
        )

        if idx < len(patient_folders):
            time.sleep(PATIENT_COOLDOWN_SECONDS)

    if not all_rows:
        print("No patients processed.")
        return

    final_df = pd.DataFrame(all_rows, columns=COLUMNS).sort_values(by="Patient_ID")
    final_df.to_csv(output_csv, index=False)
    final_df.to_excel(output_xlsx, index=False)

    print("\n" + "=" * 60)
    print("DONE")
    print(f"Patients: {len(final_df)}")
    print(f"CSV:     {output_csv}")
    print(f"Excel:   {output_xlsx}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default=PATIENTS_DIR)
    parser.add_argument("--output", default=OUTPUT_CSV)
    parser.add_argument("--excel", default=OUTPUT_XLSX)
    args = parser.parse_args()
    run(args.folder, args.output, args.excel)
'''
'''
# ============================================================
#  ocr_to_excel.py
#
#  FOLDER STRUCTURE:
#  data/
#    patients/
#      patient_001/        <- folder name = patient ID
#        visit_1.txt       <- any number of .txt files
#        visit_2.txt
#        dental_2023.txt
#        ... (no limit)
#      patient_002/
#        ...
#
#  HOW TO RUN:
#    python ocr_to_excel.py
#
#  OUTPUT:
#    data/output_patients.csv
#    data/output_patients.xlsx
# ============================================================
import os, json
import argparse
import pandas as pd
from llm_client import call_llm


COLUMNS = [
    "Patient_ID", "Hospital_No", "ICD_Code", "Age", "Sex",
    "HTN", "DM", "Family_History", "Family_History_Details",
    "Chief_Complaint", "Mouth_Opening_Status", "Mouth_Opening_Details",
    "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Burning_Sensation", "Pain_Details",
    "Bleeding_Present", "Bleeding_Details", "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details", "Clinical_Diagnosis",
    "Final_Provisional_Dx", "Differential_Diagnosis", "TNM_Stage",
    "Histological_Subgroup", "Investigations", "Biopsy_Details",
    "Treatment_Plan", "Tobacco_Use", "Tobacco_Use_Details",
    "Areca_Nut_Use", "Areca_Nut_Details", "Alcohol_Use",
    "Alcohol_Use_Details", "Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

EXTRACTION_RULES = """
EXTRACTION RULES — apply these medical standards:

- Patient_ID: use the folder name as patient identifier

- Hospital_No: look for hospital number, registration number, MRD number

- HTN (Hypertension):
  Medical rule: systolic BP > 140 OR diastolic BP > 90 = Yes
  Also Yes if: antihypertensive medication prescribed, or "HTN"/"hypertension" explicitly stated
  No: only if ALL BP readings clearly below 140/90 with no medication
  Not documented: if no BP readings or mentions found

- DM (Diabetes Mellitus):
  Medical rule: fasting glucose > 126 mg/dL or RBS > 200 mg/dL = Yes
  Also Yes if: on insulin/metformin/diabetic medication, or "DM"/"diabetes" explicitly stated
  Not documented: if not mentioned

- Chief_Complaint: the patient's PRIMARY oral/dental complaint
  NOT a referral reason like "referred for oral prophylaxis"
  Look for: swelling, pain, ulcer, growth, difficulty opening mouth, bleeding
  Priority: oral surgery file > dental OPD > any oral symptom mention

- Mouth_Opening_Status: Normal / Restricted / Not documented
  Look for: "mouth opening", "trismus", finger breadth measurements

- Oral_Hygiene_Status:
  Calculus +++ OR Debris +++ = Poor
  Calculus ++ OR Debris ++ = Fair
  Calculus + OR Debris + = Fair
  No calculus/debris = Good
  Explicitly stated = use that value

- Tobacco_Use / Areca_Nut_Use / Alcohol_Use:
  Search EVERYWHERE in ALL files for these keywords:
  Tobacco: "tobacco", "smoking", "cigarette", "beedi", "bidi", "chewing", "gutka", "pan masala", "khaini"
  Areca: "areca", "betel", "pan", "supari", "gutkha"
  Alcohol: "alcohol", "drinking", "ethanol", "liquor"
  If ANY mention found → Yes with details
  If explicitly denied → No
  If not mentioned anywhere → Not documented

- Oral_Hygiene_Status:
  Search ALL files for: "calculus", "debris", "plaque", "stains", "hygiene"
  Calculus +++ or Debris +++ → Poor
  Calculus ++ or Debris ++ → Fair  
  Calculus + or Debris + → Fair
  "Good oral hygiene" or no calculus/debris mentioned → Good
  Explicitly stated value → use that
  If not mentioned anywhere → Not documented

- Treatment_Plan: combine ALL treatments from ALL files
  Include: dental treatments (scaling, extraction), surgical plans, medications for oral conditions
  Exclude: psychiatric medications unless directly relevant to oral condition

- Investigations: list ALL investigations ordered across all files with results if available

- TNM_Stage, Histological_Subgroup, Biopsy_Details:
  Only present in cancer/suspicious lesion cases
  Leave as "Not documented" if not a cancer case

- For ALL fields: if genuinely not found in any file → "Not documented"
- Return ONLY valid JSON — no markdown, no explanation
"""


def read_files(folder_path: str) -> list[tuple[str, str]]:
    """Read all .txt files, return list of (filename, content)."""
    files = sorted([f for f in os.listdir(folder_path) if f.endswith(".txt")])
    result = []
    for fname in files:
        with open(os.path.join(folder_path, fname), encoding="utf-8") as f:
            result.append((fname, f.read().strip()))
    return result


def chunk_files(file_contents: list[tuple[str, str]], max_chars: int = 10000) -> list[str]:
    """
    Group files into chunks that fit within max_chars.
    This handles patients with many files.
    """
    chunks = []
    current_chunk = []
    current_len = 0

    for fname, content in file_contents:
        entry = f"=== {fname} ===\n{content}"
        entry_len = len(entry)

        # If single file is too big, truncate it
        if entry_len > max_chars:
            entry = entry[:max_chars] + "\n[...truncated]"
            entry_len = max_chars

        if current_len + entry_len > max_chars and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [entry]
            current_len = entry_len
        else:
            current_chunk.append(entry)
            current_len += entry_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def extract_from_chunk(chunk_text: str, patient_id: str,
                        existing: dict, chunk_num: int, total: int) -> dict:
    """
    Extract fields from one chunk of files.
    Pass existing results so LLM can fill gaps without overwriting good data.
    """
    # Tell LLM what's already filled so it doesn't overwrite with "Not documented"
    already_filled = {k: v for k, v in existing.items()
                      if v and v != "Not documented"}
    filled_str = json.dumps(already_filled, indent=2) if already_filled else "None yet"

    result = call_llm(f"""
You are a medical data extraction specialist for oral cancer research.

Patient ID: {patient_id}
Processing chunk {chunk_num} of {total} (patient may have many case sheets split across chunks)

Fields already extracted from previous chunks:
{filled_str}

From the files below, extract ANY fields not yet filled or improve existing ones.
Only update a field if you find BETTER/MORE COMPLETE information than what's already there.
Never replace a filled value with "Not documented".

Target fields (39 total):
{json.dumps(COLUMNS, indent=2)}

{EXTRACTION_RULES}

Return ONLY a JSON object with all 39 fields.
For fields you cannot improve, return the existing value.
For truly missing fields, return "Not documented".

CASE SHEET FILES (chunk {chunk_num}/{total}):
{chunk_text}
""")
    return result or {}


def merge_results(base: dict, update: dict) -> dict:
    """
    Merge two extraction results.
    Only update a field if the new value is better (not 'Not documented').
    """
    merged = dict(base)
    for key in COLUMNS:
        new_val = update.get(key, "")
        old_val = merged.get(key, "Not documented")

        # Update if new value is substantive and old is empty/not documented
        if (new_val and
            str(new_val).strip().lower() not in ("not documented", "none", "", "nan") and
            str(old_val).strip().lower() in ("not documented", "none", "", "nan")):
            merged[key] = new_val

        # Also update if new value is longer/more detailed
        elif (new_val and
              str(new_val).strip().lower() not in ("not documented", "none", "", "nan") and
              len(str(new_val)) > len(str(old_val))):
            merged[key] = new_val

    return merged


def targeted_search(all_text: str, patient_id: str, missing_fields: list) -> dict:
    """
    Second pass: search specifically for fields that are still missing.
    Sends the full combined text with focus only on missing fields.
    """
    if not missing_fields:
        return {}

    fields_str = "\n".join(f"- {f}" for f in missing_fields)

    result = call_llm(f"""
You are searching medical case sheets for specific missing information.
Patient: {patient_id}

ONLY extract these specific fields that were not found in previous processing:
{fields_str}

Critical search terms to look for:
- Tobacco_Use: tobacco, smoking, cigarette, beedi, bidi, chewing, gutka, pan masala, khaini, snuff
- Areca_Nut_Use: areca, betel nut, pan, supari, gutkha, mawa
- Alcohol_Use: alcohol, drinking, ethanol, liquor, beer, wine, spirits
- Oral_Hygiene_Status: calculus, debris, plaque, stains, oral hygiene, scaling
- Family_History: family history, cancer in family, hereditary
- Burning_Sensation: burning, burning sensation
- Bleeding_Present: bleeding, haemorrhage, hemorrhage
- Cervical_Lymphadenopathy: lymph node, cervical, neck node, LN

Return ONLY JSON with the missing fields.
If truly not found anywhere: "Not documented"

FULL TEXT:
{all_text[:15000]}
""")
    return result or {}


def extract_patient(folder_path: str, patient_id: str) -> dict:
    """Full extraction pipeline for one patient with any number of files."""

    # Read all files
    file_contents = read_files(folder_path)
    if not file_contents:
        print(f"  [ocr] No .txt files found")
        return {}

    print(f"  [ocr] {len(file_contents)} files → chunking...")

    # Split into chunks
    chunks = chunk_files(file_contents, max_chars=10000)
    print(f"  [ocr] {len(chunks)} chunk(s) to process")

    # Initialize result
    result = {col: "Not documented" for col in COLUMNS}
    result["Patient_ID"] = patient_id

    # Build full combined text for second pass
    full_text = "\n\n".join(
        f"=== {fname} ===\n{txt}"
        for fname, txt in file_contents
    )

    # Process each chunk, merging results progressively
    for i, chunk in enumerate(chunks):
        print(f"  [ocr] Chunk {i+1}/{len(chunks)}...")
        update = None
        for attempt in range(3):
            update = extract_from_chunk(chunk, patient_id, result, i+1, len(chunks))
            if update:
                break
            print(f"  [ocr] Chunk {i+1} attempt {attempt+1} failed, retrying...")
            import time; time.sleep(3)
        if update:
            result = merge_results(result, update)
        else:
            print(f"  [ocr] Chunk {i+1} failed after 3 attempts — skipping")

    # Second pass: targeted search for still-missing critical fields
    critical = ["Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
                "Oral_Hygiene_Status", "Family_History", "Burning_Sensation",
                "Bleeding_Present", "Cervical_Lymphadenopathy"]
    still_missing = [f for f in critical
                     if result.get(f, "Not documented") == "Not documented"]

    if still_missing:
        print(f"  [ocr] Second pass for: {still_missing}")
        update2 = targeted_search(full_text, patient_id, still_missing)
        if update2:
            result = merge_results(result, update2)

    return result


def run(patients_dir: str, output_csv: str, output_xlsx: str):
    """Process all patient folders."""

    subfolders = sorted([
        d for d in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, d))
    ])

    if not subfolders:
        print(f"\n❌ No patient folders found in: {patients_dir}")
        print("\nExpected structure:")
        print(f"  {patients_dir}/")
        print(f"    patient_001/     <- any folder name, used as Patient_ID")
        print(f"      file1.txt      <- any number of .txt files")
        print(f"      file2.txt")
        print(f"    patient_002/")
        print(f"      ...")
        return

    print(f"\n[ocr] Found {len(subfolders)} patient folder(s)")
    all_rows = []

    for i, folder_name in enumerate(subfolders):
        folder_path = os.path.join(patients_dir, folder_name)
        print(f"\n{'='*55}")
        print(f"[ocr] Patient {i+1}/{len(subfolders)}: {folder_name}")

        row = extract_patient(folder_path, folder_name)
        if not row:
            print(f"  [ocr] Skipping — no data extracted")
            continue

        # Ensure all columns present, convert lists to strings, normalize values
        clean = {}
        for col in COLUMNS:
            val = row.get(col, "Not documented")
            if isinstance(val, list):
                val = "; ".join(str(v) for v in val)
            val = str(val).strip()

            # Normalize common abbreviations
            if col == "Sex":
                val = {"M": "Male", "F": "Female", "m": "Male", "f": "Female",
                       "MALE": "Male", "FEMALE": "Female"}.get(val, val)
                if val not in ("Male", "Female", "Not documented"):
                    val = "Male" if "m" in val.lower() else "Female"
            if col in ("HTN", "DM", "Tobacco_Use", "Areca_Nut_Use", "Alcohol_Use",
                       "Bleeding_Present", "Burning_Sensation", "Family_History"):
                val = {"Y": "Yes", "N": "No", "y": "Yes", "n": "No",
                       "1": "Yes", "0": "No", "Positive": "Yes", "Negative": "No",
                       "Present": "Yes", "Absent": "No"}.get(val, val)
            if col == "Cervical_Lymphadenopathy":
                val = {"Y": "Positive", "N": "Negative", "Yes": "Positive",
                       "No": "Negative", "1": "Positive", "0": "Negative"}.get(val, val)

            clean[col] = "Not documented" if val in ("", "nan", "None", "[]", "Not documented") else val

        all_rows.append(clean)

        # Show summary
        filled = [k for k, v in clean.items() if v != "Not documented"]
        print(f"  [ocr] {len(filled)}/{len(COLUMNS)} fields filled")
        print(f"  [ocr] HTN={clean['HTN']} | DM={clean['DM']} | Tobacco={clean['Tobacco_Use']} | Oral_Hygiene={clean['Oral_Hygiene_Status']}")
        print(f"  [ocr] Diagnosis: {clean['Clinical_Diagnosis'][:70]}")

        # Save progress after every patient
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        print(f"  [ocr] Progress saved → {output_csv}")

    if all_rows:
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(output_csv, index=False)
        df.to_excel(output_xlsx, index=False)

        print(f"\n{'='*55}")
        print(f"✅ DONE")
        print(f"   Patients   : {len(all_rows)}")
        print(f"   Columns    : {len(COLUMNS)}")
        print(f"   CSV        : {output_csv}")
        print(f"   Excel      : {output_xlsx}")
        print(f"\nPreview:")
        print(df[["Patient_ID","Age","Sex","Tobacco_Use",
                   "HTN","Oral_Hygiene_Status","Clinical_Diagnosis"]].to_string())
    else:
        print("\n❌ No patients processed.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--folder",  default="data/patients")
    p.add_argument("--output",  default="data/output_patients.csv")
    p.add_argument("--excel",   default="data/output_patients.xlsx")
    args = p.parse_args()
    os.makedirs("data", exist_ok=True)
    run(args.folder, args.output, args.excel)
'''
'''
# ============================================================
#  ocr_to_excel.py (FINAL — ACCURACY + CLEAN JSON)
# ============================================================

import os, json, re, time, argparse
import pandas as pd
from llm_client import call_llm
from rules import apply_rules

# ─────────────────────────────────────────────────────────────
COLUMNS = [
    "Patient_ID","Hospital_No","ICD_Code","Age","Sex",
    "HTN","DM","Family_History","Family_History_Details",
    "Chief_Complaint","Mouth_Opening_Status","Mouth_Opening_Details",
    "Soft_Tissue_Exam","Specific_Findings","Lesion_Type",
    "Lesion_Color","Lesion_Site","Burning_Sensation","Pain_Details",
    "Bleeding_Present","Bleeding_Details","Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details","Clinical_Diagnosis",
    "Final_Provisional_Dx","Differential_Diagnosis","TNM_Stage",
    "Histological_Subgroup","Investigations","Biopsy_Details",
    "Treatment_Plan","Tobacco_Use","Tobacco_Use_Details",
    "Areca_Nut_Use","Areca_Nut_Details","Alcohol_Use",
    "Alcohol_Use_Details","Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

CHUNK_SIZE = 25000  # safe token control

# ─────────────────────────────────────────────────────────────
# CLEAN OCR TEXT
# ─────────────────────────────────────────────────────────────
def clean_text(text):
    text = text.replace("\r", "\n")
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────
# SAFE JSON PARSER
# ─────────────────────────────────────────────────────────────
def safe_json_parse(text):

    # ✅ CASE 1: already dict → return directly
    if isinstance(text, dict):
        return text

    # ✅ CASE 2: empty
    if not text:
        return {}

    # ✅ CASE 3: normal JSON string
    if isinstance(text, str):
        try:
            return json.loads(text)
        except:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass

    return {}

# ─────────────────────────────────────────────────────────────
# FILE READING
# ─────────────────────────────────────────────────────────────
def read_files(folder):
    files = sorted(f for f in os.listdir(folder) if f.endswith(".txt"))
    data = []
    for f in files:
        with open(os.path.join(folder, f), encoding="utf-8", errors="ignore") as file:
            txt = clean_text(file.read())
            if len(txt) > 20:
                data.append((f, txt))
    return data


# ─────────────────────────────────────────────────────────────
# CHUNKING
# ─────────────────────────────────────────────────────────────
def chunk_files(files):
    chunks, curr, size = [], [], 0
    for fname, txt in files:
        entry = f"=== {fname} ===\n{txt}"

        if size + len(entry) > CHUNK_SIZE and curr:
            chunks.append("\n\n".join(curr))
            curr, size = [], 0

        curr.append(entry)
        size += len(entry)

    if curr:
        chunks.append("\n\n".join(curr))

    return chunks


# ─────────────────────────────────────────────────────────────
# LLM EXTRACTION
# ─────────────────────────────────────────────────────────────
def extract_chunk(text, pid, existing, i, total):

    prompt = f"""
You are a medical data extraction system.

STRICT RULES:
- Output ONLY valid JSON
- NO explanation
- NO markdown
- NO extra text
- If you fail, output is useless

Extract ALL fields with FULL DETAILS (not just Yes/No).

Example:
Chief_Complaint: "Pain and ulcer in buccal mucosa for 3 months"

FIELDS:
{json.dumps(COLUMNS)}

Patient: {pid}
Chunk {i}/{total}

TEXT:
{text}
"""

    raw = call_llm(prompt)
    result = safe_json_parse(raw)

    time.sleep(3)
    return result


# ─────────────────────────────────────────────────────────────
def merge(a, b):
    res = dict(a)
    for k in COLUMNS:
        nv = str(b.get(k, "")).strip()
        ov = str(res.get(k, "Not documented")).strip()

        if nv and nv.lower() != "not documented":
            if ov.lower() == "not documented" or len(nv) > len(ov)*1.2:
                res[k] = nv
    return res


# ─────────────────────────────────────────────────────────────
def second_pass(full_text, missing):

    prompt = f"""
Extract ONLY these fields from text:
{missing}

STRICT:
- JSON only
- no explanation

TEXT:
{full_text[:30000]}
"""

    raw = call_llm(prompt)
    result = safe_json_parse(raw)

    time.sleep(3)
    return result


# ─────────────────────────────────────────────────────────────
def extract_patient(folder, pid):

    files = read_files(folder)
    chunks = chunk_files(files)

    result = {c: "Not documented" for c in COLUMNS}
    result["Patient_ID"] = pid

    full_text = "\n\n".join(t for _, t in files)

    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}/{len(chunks)}")

        for attempt in range(3):
            out = extract_chunk(chunk, pid, result, i+1, len(chunks))
            if out:
                result = merge(result, out)
                break
            time.sleep(5*(attempt+1))

    missing = [k for k,v in result.items() if v == "Not documented"]

    if missing:
        out2 = second_pass(full_text, missing[:8])
        result = merge(result, out2)

    return result


# ─────────────────────────────────────────────────────────────
def run(folder, out_csv, out_xlsx):

    patients = [d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder,d))]
    all_rows = []

    for i, p in enumerate(patients):
        print(f"\nPatient {i+1}/{len(patients)}: {p}")

        row = extract_patient(os.path.join(folder, p), p)

        row = apply_rules(row)

        all_rows.append(row)

        df = pd.DataFrame(all_rows)
        df.to_csv(out_csv, index=False)

        print(f"  Saved → {out_csv}")

        time.sleep(5)

    df = pd.DataFrame(all_rows)
    df.to_excel(out_xlsx, index=False)

    print("\n✅ DONE")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/patients")
    parser.add_argument("--output", default="data/output.csv")
    parser.add_argument("--excel", default="data/output.xlsx")
    args = parser.parse_args()

    run(args.folder, args.output, args.excel)
'''
'''
#use this below code for good output now

# ============================================================
#  ocr_to_excel.py
#  GROUPED EXTRACTION MODE (higher accuracy for OCR case sheets)
#
#  HOW TO RUN:
#    python ocr_to_excel.py
#
#  EXPECTED FOLDER STRUCTURE:
#    data/
#      patients/
#        patient_1/
#          1.txt
#          2.txt
#          ...
#        patient_2/
#          ...
#
#  OUTPUT:
#    data/output.csv
#    data/output.xlsx
# ============================================================

import os
import json
import re
import time
import argparse
import pandas as pd

from llm_client import call_llm
from rules import apply_rules

# ------------------------------------------------------------
# ALL OUTPUT COLUMNS
# ------------------------------------------------------------
COLUMNS = [
    "Patient_ID","Hospital_No","ICD_Code","Age","Sex",
    "HTN","DM","Family_History","Family_History_Details",
    "Chief_Complaint","Mouth_Opening_Status","Mouth_Opening_Details",
    "Soft_Tissue_Exam","Specific_Findings","Lesion_Type",
    "Lesion_Color","Lesion_Site","Burning_Sensation","Pain_Details",
    "Bleeding_Present","Bleeding_Details","Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details","Clinical_Diagnosis",
    "Final_Provisional_Dx","Differential_Diagnosis","TNM_Stage",
    "Histological_Subgroup","Investigations","Biopsy_Details",
    "Treatment_Plan","Tobacco_Use","Tobacco_Use_Details",
    "Areca_Nut_Use","Areca_Nut_Details","Alcohol_Use",
    "Alcohol_Use_Details","Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

# ------------------------------------------------------------
# FIELD GROUPS (THE MAIN ACCURACY UPGRADE)
# ------------------------------------------------------------
FIELD_GROUPS = {
    "demographics": [
        "Hospital_No", "ICD_Code", "Age", "Sex"
    ],
    "history_habits": [
        "HTN", "DM",
        "Family_History", "Family_History_Details",
        "Tobacco_Use", "Tobacco_Use_Details",
        "Areca_Nut_Use", "Areca_Nut_Details",
        "Alcohol_Use", "Alcohol_Use_Details"
    ],
    "symptoms": [
        "Chief_Complaint", "Burning_Sensation", "Pain_Details",
        "Bleeding_Present", "Bleeding_Details",
        "Trauma_Irritation_History"
    ],
    "clinical_exam": [
        "Mouth_Opening_Status", "Mouth_Opening_Details",
        "Soft_Tissue_Exam", "Specific_Findings",
        "Lesion_Type", "Lesion_Color", "Lesion_Site",
        "Cervical_Lymphadenopathy", "Cervical_Lymphadenopathy_Details",
        "Oral_Hygiene_Status"
    ],
    "diagnosis_oncology": [
        "Clinical_Diagnosis", "Final_Provisional_Dx",
        "Differential_Diagnosis", "TNM_Stage",
        "Histological_Subgroup", "Biopsy_Details"
    ],
    "investigation_treatment": [
        "Investigations", "Treatment_Plan"
    ]
}

# Safe chunk size for free models (character-based approximation)
CHUNK_SIZE = 18000

# ------------------------------------------------------------
# OCR CLEANING (IMPORTANT FOR TOKENS + GARBAGE REDUCTION)
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""

    # Normalize newlines
    text = text.replace("\r", "\n")

    # Remove weird nulls / OCR junk control chars
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)

    # Collapse repeated spaces/tabs
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n\s*\n+", "\n", text)

    # Remove lines that are only punctuation / garbage
    cleaned_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Keep lines that contain letters/numbers
        if re.search(r"[A-Za-z0-9]", line):
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    return text.strip()


# ------------------------------------------------------------
# SAFE JSON PARSER
# Handles:
#   - dict returned directly
#   - JSON string
#   - text with extra explanation around JSON
# ------------------------------------------------------------
def safe_json_parse(x):
    if isinstance(x, dict):
        return x

    if not x:
        return {}

    if isinstance(x, str):
        try:
            return json.loads(x)
        except:
            match = re.search(r"\{.*\}", x, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass

    return {}


# ------------------------------------------------------------
# FILE READING
# ------------------------------------------------------------
def read_files(folder: str):
    files = sorted([f for f in os.listdir(folder) if f.endswith(".txt")])
    data = []

    for f in files:
        path = os.path.join(folder, f)
        try:
            with open(path, encoding="utf-8", errors="ignore") as file:
                txt = clean_text(file.read())
                if len(txt) > 20:
                    data.append((f, txt))
        except Exception as e:
            print(f"  [read] Failed to read {f}: {e}")

    return data


# ------------------------------------------------------------
# COMBINE ALL FILES FOR A PATIENT
# ------------------------------------------------------------
def combine_patient_text(files):
    parts = []
    for fname, txt in files:
        parts.append(f"=== {fname} ===\n{txt}")
    return "\n\n".join(parts)


# ------------------------------------------------------------
# OPTIONAL CHUNKING (only if very large patient text)
# We keep this because some patients may have huge OCR dumps.
# ------------------------------------------------------------
def chunk_text(full_text: str, max_chars: int = CHUNK_SIZE):
    if len(full_text) <= max_chars:
        return [full_text]

    lines = full_text.split("\n")
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


# ------------------------------------------------------------
# BOOST IMPORTANT LINES
# Pulls clinically relevant lines to the top of the prompt
# so the model notices them early.
# ------------------------------------------------------------
def boost_text(text: str) -> str:
    keywords = [
        "pain","ulcer","swelling","burning","bleeding","lesion","growth",
        "diagnosis","carcinoma","biopsy","histopathology","tnm","stage",
        "tobacco","smoking","gutka","pan","supari","areca","alcohol",
        "htn","hypertension","dm","diabetes","metformin","insulin",
        "mouth opening","trismus","lymph node","cervical",
        "calculus","debris","oral hygiene"
    ]

    important = []
    seen = set()

    for line in text.split("\n"):
        low = line.lower()
        if any(k in low for k in keywords):
            if line not in seen:
                important.append(line)
                seen.add(line)

    # Put important lines first, then full text
    if important:
        boosted = "\n".join(important[:250]) + "\n\n" + text
        return boosted

    return text


# ------------------------------------------------------------
# STRICT FIELD-SPECIFIC PROMPT
# ------------------------------------------------------------
def build_group_prompt(group_name: str, fields: list, text: str, patient_id: str):
    fields_csv = ", ".join(fields)

    return f"""
Extract structured medical data from OCR case sheets.

TASK:
Fill ONLY these fields:
{fields_csv}

STRICT RULES:
- Output ONLY valid JSON
- No explanation, no markdown
- Search the ENTIRE text carefully before saying "Not documented"
- If exact wording is not available, extract the closest medically relevant phrase
- Keep details concise but informative
- Do NOT invent values
- For binary-like fields (HTN, DM, Tobacco_Use, Alcohol_Use, etc.):
  return "Yes", "No", or "Not documented" only IF that field itself is binary
- For detail fields, return the actual phrase/details

PATIENT:
{patient_id}

TEXT:
{text}
""".strip()


# ------------------------------------------------------------
# SINGLE GROUP EXTRACTION ON ONE TEXT CHUNK
# ------------------------------------------------------------
def extract_group_once(group_name: str, fields: list, text: str, patient_id: str):
    prompt = build_group_prompt(group_name, fields, text, patient_id)

    raw = call_llm(prompt)
    result = safe_json_parse(raw)

    # Anti-rate-limit delay
    time.sleep(5)

    # Keep only expected fields
    cleaned = {}
    for f in fields:
        val = result.get(f, "Not documented")
        if val is None or str(val).strip() == "":
            val = "Not documented"
        cleaned[f] = val

    return cleaned


# ------------------------------------------------------------
# GROUP EXTRACTION OVER FULL PATIENT TEXT (with chunk fallback)
# ------------------------------------------------------------
def extract_group(group_name: str, fields: list, full_text: str, patient_id: str):
    """
    Strategy:
    1. Try once on the whole patient text (best context)
    2. If text too large, split into chunks and merge best answers
    """
    full_text = boost_text(full_text)

    if len(full_text) <= CHUNK_SIZE:
        print(f"  [{group_name}] 1 pass")
        return extract_group_once(group_name, fields, full_text, patient_id)

    # If too large, chunk
    print(f"  [{group_name}] large text → chunked")
    chunks = chunk_text(full_text, CHUNK_SIZE)

    merged = {f: "Not documented" for f in fields}

    for i, ch in enumerate(chunks, start=1):
        print(f"    [{group_name}] chunk {i}/{len(chunks)}")
        for attempt in range(2):  # keep retries low to reduce rate limits
            out = extract_group_once(group_name, fields, ch, patient_id)
            if out:
                merged = merge_dicts(merged, out, fields)
                break
            time.sleep(8 * (attempt + 1))

    return merged


# ------------------------------------------------------------
# MERGE HELPERS
# ------------------------------------------------------------
def is_missing(v):
    return str(v).strip().lower() in ("", "not documented", "none", "nan", "null")

def merge_dicts(base: dict, update: dict, keys=None):
    if keys is None:
        keys = set(base.keys()) | set(update.keys())

    out = dict(base)

    for k in keys:
        old = str(out.get(k, "Not documented")).strip()
        new = str(update.get(k, "Not documented")).strip()

        if is_missing(new):
            continue

        # If old missing, take new
        if is_missing(old):
            out[k] = new
            continue

        # Prefer more detailed / longer text
        if len(new) > len(old) * 1.1:
            out[k] = new

    return out


# ------------------------------------------------------------
# FIELD-WISE FALLBACKS (RULE / REGEX BASED)
# This helps fill fields the model often misses.
# ------------------------------------------------------------
def field_fallback(result: dict, full_text: str) -> dict:
    t = full_text.lower()

    def set_if_missing(field, value):
        if is_missing(result.get(field, "Not documented")) and value:
            result[field] = value

    # --- Demographics ---
    # Age / Sex patterns like 52/M, 45/F, 52 years male
    m = re.search(r"\b(\d{1,3})\s*/\s*([mfMF])\b", full_text)
    if m:
        set_if_missing("Age", m.group(1))
        set_if_missing("Sex", "Male" if m.group(2).lower() == "m" else "Female")

    if is_missing(result.get("Age", "")):
        m = re.search(r"\bAge[:\s\-]*([0-9]{1,3})\b", full_text, re.I)
        if m:
            set_if_missing("Age", m.group(1))

    if is_missing(result.get("Sex", "")):
        if re.search(r"\bmale\b", t):
            set_if_missing("Sex", "Male")
        elif re.search(r"\bfemale\b", t):
            set_if_missing("Sex", "Female")

    if is_missing(result.get("Hospital_No", "")):
        m = re.search(r"(?:med\.?\s*reg\.?\s*no|mrd\s*no|hospital\s*no|reg(?:istration)?\s*no)[:\s\-]*([A-Za-z0-9\/\-]+)", full_text, re.I)
        if m:
            set_if_missing("Hospital_No", m.group(1))

    # --- Habits / History ---
    if is_missing(result.get("Tobacco_Use", "")):
        if any(x in t for x in ["tobacco","smoking","smoker","cigarette","beedi","bidi","gutka","pan masala","khaini","chewing tobacco"]):
            set_if_missing("Tobacco_Use", "Yes")

    if is_missing(result.get("Tobacco_Use_Details", "")):
        m = re.search(r"((?:tobacco|smoking|cigarette|beedi|bidi|gutka|pan masala|khaini)[^\n\.]{0,120})", full_text, re.I)
        if m:
            set_if_missing("Tobacco_Use_Details", m.group(1).strip())

    if is_missing(result.get("Areca_Nut_Use", "")):
        if any(x in t for x in ["areca","betel nut","supari","pan","gutkha","mawa"]):
            set_if_missing("Areca_Nut_Use", "Yes")

    if is_missing(result.get("Areca_Nut_Details", "")):
        m = re.search(r"((?:areca|betel nut|supari|pan|gutkha|mawa)[^\n\.]{0,120})", full_text, re.I)
        if m:
            set_if_missing("Areca_Nut_Details", m.group(1).strip())

    if is_missing(result.get("Alcohol_Use", "")):
        if any(x in t for x in ["alcohol","drinking","liquor","beer","wine","whisky","ethanol"]):
            set_if_missing("Alcohol_Use", "Yes")

    if is_missing(result.get("Alcohol_Use_Details", "")):
        m = re.search(r"((?:alcohol|drinking|liquor|beer|wine|whisky|ethanol)[^\n\.]{0,120})", full_text, re.I)
        if m:
            set_if_missing("Alcohol_Use_Details", m.group(1).strip())

    if is_missing(result.get("HTN", "")):
        if any(x in t for x in ["hypertension","htn","amlodipine","telmisartan","losartan","atenolol"]):
            set_if_missing("HTN", "Yes")
        else:
            bp_matches = re.findall(r"\b([12]?\d{2})\s*/\s*([5-9]\d|1\d{2})\b", full_text)
            for s, d in bp_matches:
                try:
                    if int(s) > 140 or int(d) > 90:
                        set_if_missing("HTN", "Yes")
                        break
                except:
                    pass

    if is_missing(result.get("DM", "")):
        if any(x in t for x in ["diabetes","dm","metformin","insulin","glimepiride"]):
            set_if_missing("DM", "Yes")
        else:
            sugar = re.findall(r"\b(?:rbs|fbs|blood sugar|glucose)[:\s\-]*([0-9]{2,3})\b", full_text, re.I)
            for val in sugar:
                try:
                    if int(val) > 126:
                        set_if_missing("DM", "Yes")
                        break
                except:
                    pass

    # --- Symptoms / Complaint ---
    if is_missing(result.get("Chief_Complaint", "")):
        m = re.search(r"((?:pain|ulcer|swelling|growth|burning|difficulty opening mouth|trismus)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Chief_Complaint", m.group(1).strip())

    if is_missing(result.get("Burning_Sensation", "")):
        if "burning" in t or "burning sensation" in t:
            set_if_missing("Burning_Sensation", "Yes")

    if is_missing(result.get("Pain_Details", "")):
        m = re.search(r"((?:pain|painful)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Pain_Details", m.group(1).strip())

    if is_missing(result.get("Bleeding_Present", "")):
        if "bleeding" in t or "haemorrhage" in t or "hemorrhage" in t:
            set_if_missing("Bleeding_Present", "Yes")

    if is_missing(result.get("Bleeding_Details", "")):
        m = re.search(r"((?:bleeding|haemorrhage|hemorrhage)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Bleeding_Details", m.group(1).strip())

    if is_missing(result.get("Trauma_Irritation_History", "")):
        m = re.search(r"((?:trauma|irritation|sharp tooth|frictional)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Trauma_Irritation_History", m.group(1).strip())

    # --- Clinical exam ---
    if is_missing(result.get("Mouth_Opening_Status", "")):
        if any(x in t for x in ["restricted mouth opening","trismus","reduced mouth opening"]):
            set_if_missing("Mouth_Opening_Status", "Restricted")
        elif "mouth opening normal" in t:
            set_if_missing("Mouth_Opening_Status", "Normal")

    if is_missing(result.get("Mouth_Opening_Details", "")):
        m = re.search(r"((?:mouth opening|trismus|finger breadth)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Mouth_Opening_Details", m.group(1).strip())

    if is_missing(result.get("Oral_Hygiene_Status", "")):
        if "+++" in t and ("calculus" in t or "debris" in t):
            set_if_missing("Oral_Hygiene_Status", "Poor")
        elif "++" in t and ("calculus" in t or "debris" in t):
            set_if_missing("Oral_Hygiene_Status", "Fair")
        elif "good oral hygiene" in t:
            set_if_missing("Oral_Hygiene_Status", "Good")

    if is_missing(result.get("Cervical_Lymphadenopathy", "")):
        if any(x in t for x in ["cervical lymph node","cervical lymphadenopathy","neck node","lymph node palpable"]):
            set_if_missing("Cervical_Lymphadenopathy", "Positive")

    if is_missing(result.get("Cervical_Lymphadenopathy_Details", "")):
        m = re.search(r"((?:lymph node|cervical)[^\n]{0,150})", full_text, re.I)
        if m:
            set_if_missing("Cervical_Lymphadenopathy_Details", m.group(1).strip())

    if is_missing(result.get("Lesion_Type", "")):
        m = re.search(r"\b(ulcer|growth|mass|lesion|patch|plaque|ulceroproliferative growth)\b", full_text, re.I)
        if m:
            set_if_missing("Lesion_Type", m.group(1))

    if is_missing(result.get("Lesion_Color", "")):
        m = re.search(r"\b(white|red|erythematous|mixed red and white|ulcerated)\b", full_text, re.I)
        if m:
            set_if_missing("Lesion_Color", m.group(1))

    if is_missing(result.get("Lesion_Site", "")):
        m = re.search(r"\b(buccal mucosa|tongue|alveolus|gingiva|palate|retromolar trigone|floor of mouth|lip)\b", full_text, re.I)
        if m:
            set_if_missing("Lesion_Site", m.group(1))

    # --- Diagnosis / oncology ---
    if is_missing(result.get("Clinical_Diagnosis", "")):
        m = re.search(r"((?:clinical diagnosis|diagnosis)[:\s\-]*[^\n]{1,150})", full_text, re.I)
        if m:
            set_if_missing("Clinical_Diagnosis", m.group(1).strip())
        else:
            m = re.search(r"((?:carcinoma|scc|squamous cell carcinoma|malignancy|oral submucous fibrosis|osmf)[^\n]{0,150})", full_text, re.I)
            if m:
                set_if_missing("Clinical_Diagnosis", m.group(1).strip())

    if is_missing(result.get("Final_Provisional_Dx", "")):
        m = re.search(r"((?:provisional diagnosis|final diagnosis)[:\s\-]*[^\n]{1,150})", full_text, re.I)
        if m:
            set_if_missing("Final_Provisional_Dx", m.group(1).strip())

    if is_missing(result.get("Differential_Diagnosis", "")):
        m = re.search(r"((?:differential diagnosis)[:\s\-]*[^\n]{1,150})", full_text, re.I)
        if m:
            set_if_missing("Differential_Diagnosis", m.group(1).strip())

    if is_missing(result.get("TNM_Stage", "")):
        m = re.search(r"\b(T[0-4][a-cA-C]?\s*N[0-3][a-cA-C]?\s*M[0-1][a-cA-C]?)\b", full_text)
        if m:
            set_if_missing("TNM_Stage", m.group(1))

    if is_missing(result.get("Histological_Subgroup", "")):
        m = re.search(r"((?:well differentiated|moderately differentiated|poorly differentiated)[^\n]{0,100})", full_text, re.I)
        if m:
            set_if_missing("Histological_Subgroup", m.group(1).strip())

    if is_missing(result.get("Biopsy_Details", "")):
        m = re.search(r"((?:biopsy|histopathology|hpe)[^\n]{0,180})", full_text, re.I)
        if m:
            set_if_missing("Biopsy_Details", m.group(1).strip())

    # --- Investigations / treatment ---
    if is_missing(result.get("Investigations", "")):
        m = re.search(r"((?:cbc|blood test|biopsy|x-ray|ct|mri|opg|investigation)[^\n]{0,180})", full_text, re.I)
        if m:
            set_if_missing("Investigations", m.group(1).strip())

    if is_missing(result.get("Treatment_Plan", "")):
        m = re.search(r"((?:treatment plan|plan|advised|scaling|extraction|surgery|radiotherapy|chemotherapy)[^\n]{0,200})", full_text, re.I)
        if m:
            set_if_missing("Treatment_Plan", m.group(1).strip())

    return result


# ------------------------------------------------------------
# ENSURE NO EMPTY STRINGS
# ------------------------------------------------------------
def enforce_not_empty(result: dict) -> dict:
    for k in COLUMNS:
        if k not in result or str(result[k]).strip() == "":
            result[k] = "Not documented"
    return result


# ------------------------------------------------------------
# EXTRACT ONE PATIENT
# ------------------------------------------------------------
def extract_patient(folder: str, patient_id: str):
    files = read_files(folder)

    if not files:
        print("  [ocr] no usable .txt files")
        return {}

    print(f"  [ocr] {len(files)} files read")

    full_text = combine_patient_text(files)

    result = {c: "Not documented" for c in COLUMNS}
    result["Patient_ID"] = patient_id

    # 1) Run grouped extraction
    for group_name, fields in FIELD_GROUPS.items():
        try:
            out = extract_group(group_name, fields, full_text, patient_id)
            result = merge_dicts(result, out, fields)
        except Exception as e:
            print(f"  [{group_name}] failed: {e}")

        # Short pause between groups to reduce rate-limit risk
        time.sleep(4)

    # 2) Fallback regex/rule-based fill
    result = field_fallback(result, full_text)

    # 3) Final cleanup
    result = enforce_not_empty(result)

    return result


# ------------------------------------------------------------
# MAIN RUN
# ------------------------------------------------------------
def run(folder: str, out_csv: str, out_xlsx: str):
    if not os.path.exists(folder):
        print(f"❌ Folder not found: {folder}")
        return

    patients = sorted([
        d for d in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, d))
    ])

    if not patients:
        print("❌ No patient folders found.")
        return

    all_rows = []

    print(f"[ocr] Found {len(patients)} patient folder(s)")

    for i, p in enumerate(patients, start=1):
        print(f"\nPatient {i}/{len(patients)}: {p}")

        row = extract_patient(os.path.join(folder, p), p)
        if not row:
            print("  [ocr] skipped")
            continue

        row = apply_rules(row)
        all_rows.append(row)

        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(out_csv, index=False)
        print(f"  Saved → {out_csv}")

        # Delay between patients
        time.sleep(6)

    if all_rows:
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(out_csv, index=False)
        df.to_excel(out_xlsx, index=False)

        print("\n✅ DONE")
        print(f"CSV   : {out_csv}")
        print(f"Excel : {out_xlsx}")
        print("\nPreview:")
        preview_cols = ["Patient_ID","Age","Sex","Tobacco_Use","HTN","DM","Clinical_Diagnosis"]
        print(df[preview_cols].to_string(index=False))
    else:
        print("❌ No data extracted.")


# ------------------------------------------------------------
# ENTRY
# ------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/patients")
    parser.add_argument("--output", default="data/output.csv")
    parser.add_argument("--excel", default="data/output.xlsx")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)
    run(args.folder, args.output, args.excel)
'''

'''
# ============================================================
# ocr_to_excel.py
# HYBRID MODE = fewer API calls + decent accuracy
# ============================================================

import os
import json
import re
import time
import argparse
import pandas as pd

from llm_client import call_llm
from rules import apply_rules

# ------------------------------------------------------------
# ALL OUTPUT COLUMNS
# ------------------------------------------------------------
COLUMNS = [
    "Patient_ID","Hospital_No","ICD_Code","Age","Sex",
    "HTN","DM","Family_History","Family_History_Details",
    "Chief_Complaint","Mouth_Opening_Status","Mouth_Opening_Details",
    "Soft_Tissue_Exam","Specific_Findings","Lesion_Type",
    "Lesion_Color","Lesion_Site","Burning_Sensation","Pain_Details",
    "Bleeding_Present","Bleeding_Details","Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details","Clinical_Diagnosis",
    "Final_Provisional_Dx","Differential_Diagnosis","TNM_Stage",
    "Histological_Subgroup","Investigations","Biopsy_Details",
    "Treatment_Plan","Tobacco_Use","Tobacco_Use_Details",
    "Areca_Nut_Use","Areca_Nut_Details","Alcohol_Use",
    "Alcohol_Use_Details","Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]

# These are the fields we’ll ask the LLM for only if still missing
HARD_FIELDS = [
    "Family_History","Family_History_Details",
    "Soft_Tissue_Exam","Specific_Findings",
    "Lesion_Type","Lesion_Color","Lesion_Site",
    "Final_Provisional_Dx","Differential_Diagnosis",
    "TNM_Stage","Histological_Subgroup",
    "Investigations","Biopsy_Details","Treatment_Plan",
    "Trauma_Irritation_History","Pain_Details"
]

# ------------------------------------------------------------
# CLEAN OCR TEXT
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    cleaned_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.search(r"[A-Za-z0-9]", line):
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()

# ------------------------------------------------------------
# SAFE JSON PARSER
# ------------------------------------------------------------
def safe_json_parse(x):
    if isinstance(x, dict):
        return x

    if not x:
        return {}

    if isinstance(x, str):
        try:
            return json.loads(x)
        except:
            match = re.search(r"\{.*\}", x, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass

    return {}

# ------------------------------------------------------------
# READ TXT FILES
# ------------------------------------------------------------
def read_files(folder: str):
    data = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".txt"):
            path = os.path.join(folder, f)
            try:
                with open(path, encoding="utf-8", errors="ignore") as file:
                    txt = clean_text(file.read())
                    if len(txt) > 20:
                        data.append((f, txt))
            except Exception as e:
                print(f"  [read] failed {f}: {e}")
    return data

# ------------------------------------------------------------
# COMBINE PATIENT TEXT
# ------------------------------------------------------------
def combine_files(files):
    parts = []
    for fname, txt in files:
        parts.append(f"=== {fname} ===\n{txt}")
    return "\n\n".join(parts)

# ------------------------------------------------------------
# MISSING CHECK
# ------------------------------------------------------------
def is_missing(v):
    return str(v).strip().lower() in ("", "not documented", "none", "nan", "null")

# ------------------------------------------------------------
# MERGE RESULTS
# ------------------------------------------------------------
def merge_dicts(base: dict, update: dict):
    out = dict(base)
    for k, v in update.items():
        if k not in COLUMNS:
            continue
        new = str(v).strip()
        old = str(out.get(k, "Not documented")).strip()

        if is_missing(new):
            continue

        if is_missing(old):
            out[k] = new
        else:
            # Prefer longer / more detailed values
            if len(new) > len(old) * 1.1:
                out[k] = new
    return out

# ------------------------------------------------------------
# RULE-BASED EXTRACTION (fills many fields without LLM)
# ------------------------------------------------------------
def rule_extract(text: str) -> dict:
    res = {}
    t = text.lower()

    def setf(k, v):
        if k not in res and v:
            res[k] = v

    # --- Age / Sex ---
    m = re.search(r"\b(\d{1,3})\s*/\s*([mfMF])\b", text)
    if m:
        setf("Age", m.group(1))
        setf("Sex", "Male" if m.group(2).lower() == "m" else "Female")

    if "Age" not in res:
        m = re.search(r"\bage[:\s\-]*([0-9]{1,3})\b", text, re.I)
        if m:
            setf("Age", m.group(1))

    if "Sex" not in res:
        if re.search(r"\bmale\b", t):
            setf("Sex", "Male")
        elif re.search(r"\bfemale\b", t):
            setf("Sex", "Female")

    # --- Hospital No ---
    m = re.search(r"(?:med\.?\s*reg\.?\s*no|mrd\s*no|hospital\s*no|reg(?:istration)?\s*no)[:\s\-]*([A-Za-z0-9\/\-]+)", text, re.I)
    if m:
        setf("Hospital_No", m.group(1))

    # --- HTN / DM ---
    if any(x in t for x in ["hypertension","htn","amlodipine","telmisartan","losartan","atenolol"]):
        setf("HTN", "Yes")

    if any(x in t for x in ["diabetes","dm","metformin","insulin","glimepiride"]):
        setf("DM", "Yes")

    # --- Tobacco ---
    if any(x in t for x in ["tobacco","smoking","smoker","cigarette","beedi","bidi","gutka","pan masala","khaini","chewing tobacco"]):
        setf("Tobacco_Use", "Yes")
        m = re.search(r"((?:tobacco|smoking|cigarette|beedi|bidi|gutka|pan masala|khaini)[^\n\.]{0,120})", text, re.I)
        if m:
            setf("Tobacco_Use_Details", m.group(1).strip())

    # --- Areca ---
    if any(x in t for x in ["areca","betel nut","supari","pan","gutkha","mawa"]):
        setf("Areca_Nut_Use", "Yes")
        m = re.search(r"((?:areca|betel nut|supari|pan|gutkha|mawa)[^\n\.]{0,120})", text, re.I)
        if m:
            setf("Areca_Nut_Details", m.group(1).strip())

    # --- Alcohol ---
    if any(x in t for x in ["alcohol","drinking","liquor","beer","wine","whisky","ethanol"]):
        setf("Alcohol_Use", "Yes")
        m = re.search(r"((?:alcohol|drinking|liquor|beer|wine|whisky|ethanol)[^\n\.]{0,120})", text, re.I)
        if m:
            setf("Alcohol_Use_Details", m.group(1).strip())

    # --- Chief complaint ---
    m = re.search(r"((?:pain|ulcer|swelling|growth|burning|difficulty opening mouth|trismus)[^\n]{0,150})", text, re.I)
    if m:
        setf("Chief_Complaint", m.group(1).strip())

    # --- Burning / bleeding ---
    if "burning" in t or "burning sensation" in t:
        setf("Burning_Sensation", "Yes")

    if "bleeding" in t or "haemorrhage" in t or "hemorrhage" in t:
        setf("Bleeding_Present", "Yes")
        m = re.search(r"((?:bleeding|haemorrhage|hemorrhage)[^\n]{0,150})", text, re.I)
        if m:
            setf("Bleeding_Details", m.group(1).strip())

    # --- Mouth opening ---
    if any(x in t for x in ["restricted mouth opening","trismus","reduced mouth opening"]):
        setf("Mouth_Opening_Status", "Restricted")
    elif "mouth opening normal" in t:
        setf("Mouth_Opening_Status", "Normal")

    m = re.search(r"((?:mouth opening|trismus|finger breadth)[^\n]{0,150})", text, re.I)
    if m:
        setf("Mouth_Opening_Details", m.group(1).strip())

    # --- Oral hygiene ---
    if "+++" in t and ("calculus" in t or "debris" in t):
        setf("Oral_Hygiene_Status", "Poor")
    elif "++" in t and ("calculus" in t or "debris" in t):
        setf("Oral_Hygiene_Status", "Fair")
    elif "good oral hygiene" in t:
        setf("Oral_Hygiene_Status", "Good")

    # --- Cervical nodes ---
    if any(x in t for x in ["cervical lymph node","cervical lymphadenopathy","neck node","lymph node palpable"]):
        setf("Cervical_Lymphadenopathy", "Positive")
        m = re.search(r"((?:lymph node|cervical)[^\n]{0,150})", text, re.I)
        if m:
            setf("Cervical_Lymphadenopathy_Details", m.group(1).strip())

    # --- Lesion site/type/color ---
    m = re.search(r"\b(ulcer|growth|mass|lesion|patch|plaque|ulceroproliferative growth)\b", text, re.I)
    if m:
        setf("Lesion_Type", m.group(1))

    m = re.search(r"\b(white|red|erythematous|mixed red and white|ulcerated)\b", text, re.I)
    if m:
        setf("Lesion_Color", m.group(1))

    m = re.search(r"\b(buccal mucosa|tongue|alveolus|gingiva|palate|retromolar trigone|floor of mouth|lip)\b", text, re.I)
    if m:
        setf("Lesion_Site", m.group(1))

    # --- Diagnosis ---
    m = re.search(r"((?:clinical diagnosis|diagnosis)[:\s\-]*[^\n]{1,150})", text, re.I)
    if m:
        setf("Clinical_Diagnosis", m.group(1).strip())
    else:
        m = re.search(r"((?:carcinoma|scc|squamous cell carcinoma|malignancy|oral submucous fibrosis|osmf)[^\n]{0,150})", text, re.I)
        if m:
            setf("Clinical_Diagnosis", m.group(1).strip())

    # --- TNM ---
    m = re.search(r"\b(T[0-4][a-cA-C]?\s*N[0-3][a-cA-C]?\s*M[0-1][a-cA-C]?)\b", text)
    if m:
        setf("TNM_Stage", m.group(1))

    # --- Histology / biopsy ---
    m = re.search(r"((?:well differentiated|moderately differentiated|poorly differentiated)[^\n]{0,100})", text, re.I)
    if m:
        setf("Histological_Subgroup", m.group(1).strip())

    m = re.search(r"((?:biopsy|histopathology|hpe)[^\n]{0,180})", text, re.I)
    if m:
        setf("Biopsy_Details", m.group(1).strip())

    # --- Investigations / treatment ---
    m = re.search(r"((?:cbc|blood test|biopsy|x-ray|ct|mri|opg|investigation)[^\n]{0,180})", text, re.I)
    if m:
        setf("Investigations", m.group(1).strip())

    m = re.search(r"((?:treatment plan|plan|advised|scaling|extraction|surgery|radiotherapy|chemotherapy)[^\n]{0,200})", text, re.I)
    if m:
        setf("Treatment_Plan", m.group(1).strip())

    return res

# ------------------------------------------------------------
# BOOST IMPORTANT LINES FOR LLM
# ------------------------------------------------------------
def boost_text(text: str) -> str:
    keywords = [
        "pain","ulcer","swelling","burning","bleeding","lesion","growth",
        "diagnosis","carcinoma","biopsy","histopathology","tnm","stage",
        "tobacco","smoking","gutka","pan","supari","areca","alcohol",
        "htn","hypertension","dm","diabetes","metformin","insulin",
        "mouth opening","trismus","lymph node","cervical",
        "calculus","debris","oral hygiene"
    ]

    important = []
    seen = set()

    for line in text.split("\n"):
        low = line.lower()
        if any(k in low for k in keywords):
            if line not in seen:
                important.append(line)
                seen.add(line)

    if important:
        return "\n".join(important[:250]) + "\n\n" + text

    return text

# ------------------------------------------------------------
# LLM EXTRACTION FOR ONLY HARD / MISSING FIELDS
# ------------------------------------------------------------
def llm_extract(text: str, missing_fields: list) -> dict:
    if not missing_fields:
        return {}

    text = boost_text(text)

    prompt = f"""
Extract medical data into JSON.

FIELDS:
{", ".join(missing_fields)}

RULES:
- Output ONLY valid JSON
- No explanation, no markdown
- Search the full text carefully
- Return "Not documented" only if truly absent
- Keep details concise but informative
- Do NOT invent values

TEXT:
{text[:14000]}
""".strip()

    raw = call_llm(prompt)
    result = safe_json_parse(raw)

    # Anti-rate-limit delay
    time.sleep(6)

    # Keep only expected fields
    cleaned = {}
    for f in missing_fields:
        val = result.get(f, "Not documented")
        if val is None or str(val).strip() == "":
            val = "Not documented"
        cleaned[f] = val

    return cleaned

# ------------------------------------------------------------
# ENSURE ALL FIELDS EXIST
# ------------------------------------------------------------
def finalize_result(result: dict) -> dict:
    for c in COLUMNS:
        if c not in result or str(result[c]).strip() == "":
            result[c] = "Not documented"
    return result

# ------------------------------------------------------------
# EXTRACT ONE PATIENT
# ------------------------------------------------------------
def extract_patient(folder: str, patient_id: str) -> dict:
    files = read_files(folder)

    if not files:
        print("  [ocr] no usable .txt files found")
        return {}

    print(f"  [ocr] {len(files)} files found")

    full_text = combine_files(files)

    # Start with empty template
    result = {c: "Not documented" for c in COLUMNS}
    result["Patient_ID"] = patient_id

    # 1) Rule-based fill
    rule_data = rule_extract(full_text)
    result = merge_dicts(result, rule_data)

    # 2) Only ask LLM for still-missing hard fields
    missing = [f for f in HARD_FIELDS if is_missing(result.get(f, "Not documented"))]

    if missing:
        print(f"  [ocr] LLM extracting {len(missing)} hard field(s)...")
        llm_data = llm_extract(full_text, missing)
        result = merge_dicts(result, llm_data)
    else:
        print("  [ocr] No hard fields left for LLM")

    result = finalize_result(result)
    return result

# ------------------------------------------------------------
# MAIN RUN
# ------------------------------------------------------------
def run(folder: str, out_csv: str, out_xlsx: str):
    print(">>> run() entered")
    print(">>> folder =", folder)

    if not os.path.exists(folder):
        print(f"❌ Folder not found: {folder}")
        return

    patients = sorted([
        d for d in os.listdir(folder)
        if os.path.isdir(os.path.join(folder, d))
    ])

    if not patients:
        print("❌ No patient folders found.")
        return

    print(f"[ocr] Found {len(patients)} patient folder(s)")

    all_rows = []

    for i, p in enumerate(patients, start=1):
        print(f"\nPatient {i}/{len(patients)}: {p}")

        row = extract_patient(os.path.join(folder, p), p)
        if not row:
            print("  [ocr] skipped")
            continue

        row = apply_rules(row)
        all_rows.append(row)

        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(out_csv, index=False)
        print(f"  Saved → {out_csv}")

        # Delay between patients
        time.sleep(5)

    if all_rows:
        df = pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(out_csv, index=False)
        df.to_excel(out_xlsx, index=False)

        print("\n✅ DONE")
        print(f"CSV   : {out_csv}")
        print(f"Excel : {out_xlsx}")

        preview_cols = [
            "Patient_ID","Age","Sex","Tobacco_Use","HTN","DM","Clinical_Diagnosis"
        ]
        print("\nPreview:")
        print(df[preview_cols].to_string(index=False))
    else:
        print("❌ No data extracted.")

# ------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------
print(">>> script started")

if __name__ == "__main__":
    print(">>> entering __main__")

    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/patients")
    parser.add_argument("--output", default="data/output.csv")
    parser.add_argument("--excel", default="data/output.xlsx")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)
    run(args.folder, args.output, args.excel)
'''

'''
import os, json, re, time, argparse
import pandas as pd
from llm_client import call_llm
from config import OCR_FOLDER, OUTPUT_FILE

COLUMNS = [
    "sl no.","Hospital No.","ICD Code","Age","Sex",
    "Tobacco Use","Tobacco Type","Areca Nut Use","Alcohol Use",
    "Oral Hygiene Status","Trauma / Irritation History",
    "Burning Sensation","Lesion Color","Lesion Type",
    "Localised / Multiple Site","Pain Present",
    "Bleeding Present","Cervical Lymphadenopathy"
]

# ------------------------------------------------------------
def clean_text(text):
    text = text.replace("\r","\n")
    text = re.sub(r"\n\s*\n+","\n",text)
    text = re.sub(r"[ \t]+"," ",text)
    text = "\n".join([line for line in text.split("\n") if len(line.strip()) > 3])
    return text.strip()

# ------------------------------------------------------------
def safe_json(x):
    if isinstance(x, dict):
        return x
    if not x:
        return {}
    try:
        return json.loads(x)
    except:
        m = re.search(r"\{.*\}", str(x), re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                pass
    return {}

# ------------------------------------------------------------
def read_files(folder):
    data=[]
    for f in sorted(os.listdir(folder)):
        if f.endswith(".txt"):
            with open(os.path.join(folder,f),encoding="utf-8",errors="ignore") as file:
                txt=clean_text(file.read())
                if len(txt)>20:
                    data.append((f,txt))
    return data

# ------------------------------------------------------------
def combine(files):
    return "\n\n".join([f"{name}\n{text}" for name,text in files])

# ------------------------------------------------------------
def build_prompt(text):

    return f"""
You are extracting structured medical data.

Follow EXACTLY this format.

Example:

Input:
"45 year old male, tobacco chewing, white patch on buccal mucosa, no pain, no bleeding"

Output:
{{
"Hospital No.": "NA",
"ICD Code": "NA",
"Age": 45,
"Sex": "M",
"Tobacco Use": "R",
"Tobacco Type": "C",
"Areca Nut Use": "U",
"Alcohol Use": "U",
"Oral Hygiene Status": "U",
"Trauma / Irritation History": "U",
"Burning Sensation": "A",
"Lesion Color": "W",
"Lesion Type": "Patch",
"Localised / Multiple Site": "L",
"Pain Present": "A",
"Bleeding Present": "A",
"Cervical Lymphadenopathy": "A"
}}

Now extract from this patient:

TEXT:
{text[:10000]}

STRICT RULES:
- Output ONLY JSON
- Use ONLY allowed codes
- If unsure → NA
- DO NOT guess
- Prefer NA over wrong value

CODES:
Sex: M/F/O
Tobacco Use: R/U
Tobacco Type: SE/C/B/NA
Areca Nut Use: R/U
Alcohol Use: R/U
Oral Hygiene Status: R/U
Trauma: R/U
Burning: P/A
Lesion Color: W/R/W/R/B/NA
Lesion Type: U/F/U/P/Patch/Papule/Swelling/NA
Site: L/M/NA
Pain: P/A
Bleeding: P/A
Nodes: P/A
"""

# ------------------------------------------------------------
def validate(result):

    allowed = {
        "Sex": {"M","F","O"},
        "Tobacco Use": {"R","U"},
        "Tobacco Type": {"SE","C","B","NA"},
        "Areca Nut Use": {"R","U"},
        "Alcohol Use": {"R","U"},
        "Oral Hygiene Status": {"R","U"},
        "Trauma / Irritation History": {"R","U"},
        "Burning Sensation": {"P","A"},
        "Lesion Color": {"W","R","W/R","B","NA"},
        "Lesion Type": {"U/F","U/P","Patch","Papule","Swelling","NA"},
        "Localised / Multiple Site": {"L","M","NA"},
        "Pain Present": {"P","A"},
        "Bleeding Present": {"P","A"},
        "Cervical Lymphadenopathy": {"P","A"},
    }

    # Age validation
    try:
        age=int(result.get("Age","NA"))
        if not (1<=age<=120):
            result["Age"]="NA"
    except:
        result["Age"]="NA"

    # ICD validation
    if not re.fullmatch(r"[A-TV-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?", str(result.get("ICD Code",""))):
        result["ICD Code"]="NA"

    # Hospital no validation
    if not re.search(r"[0-9]", str(result.get("Hospital No.",""))):
        result["Hospital No."]="NA"

    # enforce coded values
    for k,v in allowed.items():
        if result.get(k) not in v:
            if k in ["Lesion Color","Lesion Type","Localised / Multiple Site","Tobacco Type"]:
                result[k]="NA"
            elif k=="Sex":
                result[k]="O"
            elif k in ["Burning Sensation","Pain Present","Bleeding Present","Cervical Lymphadenopathy"]:
                result[k]="A"
            else:
                result[k]="U"

    return result

# ------------------------------------------------------------
def extract_patient(folder,pid,idx):

    files = read_files(folder)
    if not files:
        return {}

    print(f"  [ocr] {len(files)} files")

    text = combine(files)

    # ---------- PASS 1 ----------
    raw = call_llm(build_prompt(text))
    data = safe_json(raw)

    # ---------- PASS 2 (fix missing critical fields) ----------
    missing_fields = [
        k for k,v in data.items()
        if str(v).strip() in ["", "NA"]
    ]

    if missing_fields:
        print(f"  [ocr] second pass fixing {len(missing_fields)} fields")

        fix_prompt = f"""
Fix ONLY these fields:
{missing_fields}

Return JSON only.

TEXT:
{text[:8000]}
"""
        raw2 = call_llm(fix_prompt)
        data2 = safe_json(raw2)

        for k in missing_fields:
            if k in data2 and data2[k] not in ["", "NA"]:
                data[k] = data2[k]

    # ---------- FINAL ----------
    result = {c:"NA" for c in COLUMNS}
    result["sl no."] = idx

    for k in data:
        if k in result:
            result[k] = data[k]

    return validate(result)
# ------------------------------------------------------------
def run(folder,out_csv,out_xlsx):

    if not os.path.exists(folder):
        print(f"❌ Folder not found: {folder}")
        return

    patients=[d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder,d))]
    patients=sorted(patients)

    all_rows=[]

    for i,p in enumerate(patients):
        print(f"\nPatient {i+1}/{len(patients)}: {p}")

        row=extract_patient(os.path.join(folder,p),p,i+1)
        if not row:
            continue

        all_rows.append(row)

        pd.DataFrame(all_rows).to_csv(out_csv,index=False)
        print(f"  Saved → {out_csv}")

        time.sleep(5)

    if all_rows:
        df=pd.DataFrame(all_rows, columns=COLUMNS)
        df.to_csv(out_csv,index=False)
        df.to_excel(out_xlsx,index=False)

        print("\n✅ DONE")
        print(f"CSV   : {out_csv}")
        print(f"Excel : {out_xlsx}")
        print("\nPreview:")
        print(df.head().to_string(index=False))
    else:
        print("❌ No rows extracted.")

# ------------------------------------------------------------
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--folder",default=OCR_FOLDER)
    parser.add_argument("--output",default=OUTPUT_FILE)
    parser.add_argument("--excel",default="data/output_coded.xlsx")
    args=parser.parse_args()

    os.makedirs("data",exist_ok=True)
    run(args.folder,args.output,args.excel)
'''
'''
# ============================================================
#  ocr_to_excel.py (HYBRID VERSION - ACCURACY MODE)
# ============================================================

import os
import re
import json
import pandas as pd
from llm_client import call_llm


# ----------------------------
# COLUMNS
# ----------------------------
COLUMNS = [
    "Patient_ID", "Hospital_No", "ICD_Code", "Age", "Sex",
    "HTN", "DM", "Family_History", "Family_History_Details",
    "Chief_Complaint", "Mouth_Opening_Status", "Mouth_Opening_Details",
    "Soft_Tissue_Exam", "Specific_Findings", "Lesion_Type",
    "Lesion_Color", "Lesion_Site", "Burning_Sensation", "Pain_Details",
    "Bleeding_Present", "Bleeding_Details", "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details", "Clinical_Diagnosis",
    "Final_Provisional_Dx", "Differential_Diagnosis", "TNM_Stage",
    "Histological_Subgroup", "Investigations", "Biopsy_Details",
    "Treatment_Plan", "Tobacco_Use", "Tobacco_Use_Details",
    "Areca_Nut_Use", "Areca_Nut_Details", "Alcohol_Use",
    "Alcohol_Use_Details", "Oral_Hygiene_Status",
    "Trauma_Irritation_History"
]


# ----------------------------
# BASIC CLEANING
# ----------------------------
def clean_text(text):
    lines = []
    for l in text.splitlines():
        l = l.strip()
        if not l:
            continue
        if len(l) < 3:
            continue
        if re.fullmatch(r"\d+", l):
            continue
        lines.append(l)
    return "\n".join(lines)


def read_patient(folder):
    texts = []
    for f in sorted(os.listdir(folder)):
        if f.endswith(".txt"):
            with open(os.path.join(folder, f), encoding="utf-8", errors="ignore") as file:
                txt = clean_text(file.read())
                texts.append(txt)
    return "\n\n".join(texts)


# ----------------------------
# RULE BASED EXTRACTION
# ----------------------------
def extract_rules(text, pid):
    t = text.lower()
    r = {c: "Not documented" for c in COLUMNS}
    r["Patient_ID"] = pid

    # Age + Sex
    m = re.search(r"\b(\d{1,3})\s*[/ ]\s*(m|f|male|female)\b", t)
    if m:
        r["Age"] = m.group(1)
        r["Sex"] = "Male" if m.group(2)[0] == "m" else "Female"

    # Age fallback
    m = re.search(r"age[: ]*(\d{1,3})", t)
    if m:
        r["Age"] = m.group(1)

    # Sex fallback
    if "male" in t:
        r["Sex"] = "Male"
    elif "female" in t:
        r["Sex"] = "Female"

    # Hospital no
    m = re.search(r"(uhid|mrd|hospital no)[^\d]*(\d+)", t)
    if m:
        r["Hospital_No"] = m.group(2)

    # HTN / DM
    if "htn" in t or "hypertension" in t:
        r["HTN"] = "Yes"
    if "dm" in t or "diabetes" in t:
        r["DM"] = "Yes"

    # Tobacco
    if any(x in t for x in ["tobacco", "smoking", "gutka", "pan"]):
        r["Tobacco_Use"] = "Yes"

    # Bleeding
    if "bleeding" in t:
        r["Bleeding_Present"] = "Yes"

    # Burning
    if "burning" in t:
        r["Burning_Sensation"] = "Yes"

    # Oral hygiene
    if "poor" in t:
        r["Oral_Hygiene_Status"] = "Poor"
    elif "fair" in t:
        r["Oral_Hygiene_Status"] = "Fair"
    elif "good" in t:
        r["Oral_Hygiene_Status"] = "Good"

    return r


# ----------------------------
# LLM EXTRACTION (SHORT OUTPUT)
# ----------------------------
def extract_llm(text, pid):
    prompt = f"""
Extract ONLY short clinical values (1-2 lines max per field).

Fields:
Chief_Complaint, Lesion_Type, Lesion_Site, Lesion_Color,
Clinical_Diagnosis, Treatment_Plan, Biopsy_Details

Rules:
- Keep answers SHORT
- No paragraphs
- No explanations
- Only direct extraction

TEXT:
{text[:12000]}
"""
    return call_llm(prompt)


# ----------------------------
# MERGE
# ----------------------------
def merge(a, b):
    for k in b:
        if b[k] and b[k] != "Not documented":
            a[k] = b[k]
    return a


# ----------------------------
# VALIDATION
# ----------------------------
def validate(r):
    # Age sanity
    if r["Age"].isdigit():
        if not (1 <= int(r["Age"]) <= 120):
            r["Age"] = "Not documented"

    # Sex fix
    if r["Sex"] not in ["Male", "Female"]:
        r["Sex"] = "Not documented"

    return r


# ----------------------------
# MAIN
# ----------------------------
def process_patient(folder, pid):
    text = read_patient(folder)

    r = extract_rules(text, pid)

    llm = extract_llm(text, pid)
    r = merge(r, llm)

    r = validate(r)

    return r


def run(base):
    rows = []

    for p in sorted(os.listdir(base)):
        folder = os.path.join(base, p)
        if not os.path.isdir(folder):
            continue

        print(f"[ocr] {p}")
        row = process_patient(folder, p)
        rows.append(row)

    df = pd.DataFrame(rows, columns=COLUMNS)
    df.to_excel("output.xlsx", index=False)
    df.to_csv("output.csv", index=False)

    print("\nDONE ✅")


if __name__ == "__main__":
    run("data/patients")
'''


import argparse
import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from llm_client import call_llm


COLUMNS = [
    "Patient_ID",
    "Hospital_No",
    "ICD_Code",
    "Age",
    "Sex",
    "HTN",
    "DM",
    "Family_History",
    "Family_History_Details",
    "Chief_Complaint",
    "Mouth_Opening_Status",
    "Mouth_Opening_Details",
    "Soft_Tissue_Exam",
    "Specific_Findings",
    "Lesion_Type",
    "Lesion_Color",
    "Lesion_Site",
    "Burning_Sensation",
    "Pain_Details",
    "Bleeding_Present",
    "Bleeding_Details",
    "Cervical_Lymphadenopathy",
    "Cervical_Lymphadenopathy_Details",
    "Clinical_Diagnosis",
    "Final_Provisional_Dx",
    "Differential_Diagnosis",
    "TNM_Stage",
    "Histological_Subgroup",
    "Investigations",
    "Biopsy_Details",
    "Treatment_Plan",
    "Tobacco_Use",
    "Tobacco_Use_Details",
    "Areca_Nut_Use",
    "Areca_Nut_Details",
    "Alcohol_Use",
    "Alcohol_Use_Details",
    "Oral_Hygiene_Status",
    "Trauma_Irritation_History",
]

YES_NO_FIELDS = {
    "HTN",
    "DM",
    "Family_History",
    "Burning_Sensation",
    "Bleeding_Present",
    "Tobacco_Use",
    "Areca_Nut_Use",
    "Alcohol_Use",
}

MISSING_VALUES = {
    "",
    "not documented",
    "none",
    "nan",
    "[]",
    "{}",
    "null",
    "not mentioned",
}

ORAL_PAGE_TERMS = [
    "oral", "buccal", "mucosa", "tongue", "palate", "gingiva", "gingivobuccal",
    "gingivo buccal", "submandibular", "mouth opening", "trismus", "lesion", "ulcer",
    "growth", "vestibule", "faucial", "retromolar", "soft palate", "hard palate",
    "neck node", "lymph node", "palpable node", "calculus", "debris", "oral hygiene",
    "burning sensation", "clinical diagnosis", "provisional diagnosis", "differential diagnosis",
    "biopsy", "histopath", "fnac", "carcinoma", "osmf", "ocsmf", "leukoplakia",
    "erythroplakia", "periodontology", "prosthodontics", "oral surgery",
]

GENERAL_PAGE_TERMS = [
    "hospital no", "registration no", "mrd no", "uhid", "op no", "age", "sex",
    "history", "medical history", "past history", "family history", "htn", "hypertension",
    "dm", "diabetes", "diabetic", "insulin", "metformin", "thyroid", "thyronorm",
    "tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini",
    "pan masala", "areca", "betel", "supari", "alcohol", "drinking",
]

IRRELEVANT_PAGE_TERMS = [
    "ophthalmology", "visual acuity", "fundus", "refraction", "psychiatry", "sertraline",
    "venlafaxine", "schizo", "2d echo", "cabg", "angioplasty", "stemi", "ecg", "melena",
    "hematemesis", "dialysis", "nephrology", "orthopedics",
]

FIELD_KEYWORDS = {
    "Hospital_No": ["hospital no", "registration no", "mrd no", "uhid", "op no"],
    "ICD_Code": ["icd", "icd code", "icdo", "c06", "c02", "d00"],
    "Age": ["age", "years", "yrs", "year old", "/m", "/f"],
    "Sex": ["male", "female", "/m", "/f", "sex"],
    "HTN": ["htn", "hypertension", "antihypertensive"],
    "DM": ["dm", "diabetes", "diabetic", "metformin", "insulin"],
    "Family_History": ["family history", "maternal", "paternal", "mother", "father", "brother", "sister"],
    "Family_History_Details": ["family history", "runs in family", "mother", "father", "brother", "sister"],
    "Chief_Complaint": ["chief complaint", "complaint", "c/o", "presents with"],
    "Mouth_Opening_Status": ["mouth opening", "trismus", "restricted", "reduced", "normal"],
    "Mouth_Opening_Details": ["mouth opening", "interincisal", "trismus", "restricted"],
    "Soft_Tissue_Exam": ["soft tissue", "mucosa", "vestibule", "gingiva", "palate", "tongue"],
    "Specific_Findings": ["finding", "induration", "ulcer", "growth", "tenderness", "surface", "margin"],
    "Lesion_Type": ["ulcer", "growth", "patch", "plaque", "swelling", "lesion", "mass"],
    "Lesion_Color": ["red", "white", "mixed", "erythematous", "pale", "blanched"],
    "Lesion_Site": ["buccal", "tongue", "palate", "vestibule", "retromolar", "gingiva", "commissure"],
    "Burning_Sensation": ["burning sensation", "burning"],
    "Pain_Details": ["pain", "painful", "tenderness", "odynophagia"],
    "Bleeding_Present": ["bleeding", "bleeds", "bleeding on probing"],
    "Bleeding_Details": ["bleeding", "bleeding on probing", "spontaneous bleed"],
    "Cervical_Lymphadenopathy": ["lymph node", "neck node", "submandibular node", "palpable node"],
    "Cervical_Lymphadenopathy_Details": ["lymph node", "neck node", "submandibular node", "level ii", "level iii"],
    "Clinical_Diagnosis": ["clinical diagnosis", "diagnosis", "impression"],
    "Final_Provisional_Dx": ["provisional diagnosis", "final diagnosis", "working diagnosis"],
    "Differential_Diagnosis": ["differential diagnosis", "differentials"],
    "TNM_Stage": ["tnm", "t1", "t2", "t3", "n0", "n1", "stage"],
    "Histological_Subgroup": ["well differentiated", "moderately differentiated", "poorly differentiated", "histology"],
    "Investigations": ["investigation", "ct", "mri", "pet", "biopsy", "fnac", "blood", "histopath"],
    "Biopsy_Details": ["biopsy", "histopath", "fnac", "hpe", "incisional biopsy"],
    "Treatment_Plan": ["treatment plan", "plan", "advised", "surgery", "radiotherapy", "chemotherapy"],
    "Tobacco_Use": ["tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini", "pan masala"],
    "Tobacco_Use_Details": ["tobacco", "smoking", "cigarette", "beedi", "bidi", "gutka", "gutkha", "khaini", "pan masala"],
    "Areca_Nut_Use": ["areca", "betel", "supari"],
    "Areca_Nut_Details": ["areca", "betel", "supari"],
    "Alcohol_Use": ["alcohol", "beer", "wine", "liquor", "drinking"],
    "Alcohol_Use_Details": ["alcohol", "beer", "wine", "liquor", "drinking"],
    "Oral_Hygiene_Status": ["oral hygiene", "calculus", "debris", "plaque", "stains"],
    "Trauma_Irritation_History": ["sharp tooth", "trauma", "irritation", "frictional", "cheek bite", "tooth irritation"],
}

GLOBAL_MEDICAL_TERMS = sorted({term for terms in FIELD_KEYWORDS.values() for term in terms})

EXTRACTION_RULES = """
You are extracting oral-case-sheet data from OCR text.

Core rules:
- Return ONLY valid JSON.
- You are analyzing exactly one patient.
- Use exact field names for the 39 fixed fields.
- Use "Not documented" when evidence is absent or too weak.
- Never invent values.
- Prefer oral/maxillofacial/pathology evidence for lesion-related fields.
- Prefer general history/demographic evidence for age, sex, comorbidities, and habits.
- If two snippets conflict, prefer the more specific snippet with clearer wording.
- Use the provided evidence packets first, then the routed text.
- Keep extra important findings in extra_findings even if they do not fit neatly into the 39 fixed fields.
- Keep evidence_map concise and field-linked.

Normalization rules:
- Sex -> Male / Female / Not documented.
- HTN, DM, Family_History, Burning_Sensation, Bleeding_Present, Tobacco_Use, Areca_Nut_Use, Alcohol_Use -> Yes / No / Not documented.
- Mouth_Opening_Status -> Normal / Restricted / Not documented.
- Oral_Hygiene_Status -> Good / Fair / Poor / Not documented.
- Cervical_Lymphadenopathy -> Positive / Negative / Not documented.
- Family history must come from explicit family-history text, not generic past history.
- Bleeding_Present refers to oral complaint context, not unrelated GI bleeding.
""".strip()


EXTRA_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "title": {"type": "string"},
        "detail": {"type": "string"},
        "evidence": {"type": "string"},
        "source_hint": {"type": "string"},
    },
    "required": ["category", "title", "detail", "evidence", "source_hint"],
}

EVIDENCE_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string"},
        "evidence": {"type": "string"},
        "source_hint": {"type": "string"},
    },
    "required": ["field", "evidence", "source_hint"],
}

SINGLE_PATIENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "Patient_ID": {"type": "string"},
        "fields": {
            "type": "object",
            "properties": {col: {"type": "string"} for col in COLUMNS},
            "required": COLUMNS,
        },
        "patient_summary": {"type": "string"},
        "extra_findings": {
            "type": "array",
            "items": EXTRA_FINDING_SCHEMA,
        },
        "evidence_map": {
            "type": "array",
            "items": EVIDENCE_ITEM_SCHEMA,
        },
    },
    "required": ["Patient_ID", "fields", "patient_summary", "extra_findings", "evidence_map"],
}


def is_missing(value: Any) -> bool:
    return str(value).strip().lower() in MISSING_VALUES


def normalize_spaces(text: str) -> str:
    text = text.replace("\x0c", "\n")
    lines: List[str] = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def dedupe_lines(text: str) -> str:
    seen = set()
    out: List[str] = []
    for line in text.splitlines():
        key = line.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(line.strip())
    return "\n".join(out)


def read_files(folder_path: str) -> List[Tuple[str, str]]:
    files = sorted(f for f in os.listdir(folder_path) if f.endswith(".txt"))
    result: List[Tuple[str, str]] = []
    for fname in files:
        path = os.path.join(folder_path, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            txt = dedupe_lines(normalize_spaces(f.read()))
            result.append((fname, txt))
    return result


def count_matches(low: str, terms: Sequence[str]) -> int:
    return sum(1 for term in terms if term in low)


def route_pages(file_contents: List[Tuple[str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    oral_pages: List[Tuple[str, str]] = []
    general_pages: List[Tuple[str, str]] = []
    dropped_pages: List[Tuple[str, str]] = []
    scored_rows: List[Tuple[str, str, int, int, int]] = []

    for fname, txt in file_contents:
        low = txt.lower()
        oral_score = count_matches(low, ORAL_PAGE_TERMS)
        general_score = count_matches(low, GENERAL_PAGE_TERMS)
        irrelevant_score = count_matches(low, IRRELEVANT_PAGE_TERMS)
        scored_rows.append((fname, txt, oral_score, general_score, irrelevant_score))

        if oral_score >= 2:
            oral_pages.append((fname, txt))
            if general_score >= 1:
                general_pages.append((fname, txt))
            continue

        if general_score >= 2 and irrelevant_score <= 1:
            general_pages.append((fname, txt))
            continue

        if irrelevant_score >= 2 and oral_score == 0 and general_score == 0:
            dropped_pages.append((fname, txt))
            continue

        if oral_score >= 1:
            oral_pages.append((fname, txt))
        elif general_score >= 1:
            general_pages.append((fname, txt))
        else:
            dropped_pages.append((fname, txt))

    if not oral_pages and scored_rows:
        ranked = sorted(scored_rows, key=lambda x: (x[2], x[3], -x[4], len(x[1])), reverse=True)
        oral_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[:min(3, len(ranked))]]

    if not general_pages and scored_rows:
        ranked = sorted(scored_rows, key=lambda x: (x[3], x[2], -x[4], len(x[1])), reverse=True)
        general_pages = [(fname, txt) for fname, txt, _, _, _ in ranked[:min(3, len(ranked))]]

    return {"oral": oral_pages, "general": general_pages, "dropped": dropped_pages}


def controlled_truncate(text: str, max_chars: int) -> Tuple[str, bool]:
    text = text.strip()
    if len(text) <= max_chars:
        return text, False

    head = int(max_chars * 0.70)
    tail = max_chars - head
    clipped = text[:head] + "\n\n...[TRUNCATED MIDDLE FOR TOKEN CONTROL]...\n\n" + text[-tail:]
    return clipped, True


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def split_into_snippets(file_contents: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    snippets: List[Dict[str, Any]] = []
    seen = set()

    for fname, txt in file_contents:
        for raw_line in txt.splitlines():
            line = raw_line.strip(" -•:\t")
            if len(line) < 6:
                continue

            chunks = re.split(r"(?<=[.;])\s+|\s{2,}", line)
            for chunk in chunks:
                chunk = chunk.strip(" -•:\t")
                if len(chunk) < 6:
                    continue

                key = chunk.lower()
                if key in seen:
                    continue
                seen.add(key)

                tokens = set(tokenize(chunk))
                snippets.append(
                    {
                        "text": chunk,
                        "source": fname,
                        "tokens": tokens,
                        "low": key,
                    }
                )
    return snippets


def lexical_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ta = a["tokens"]
    tb = b["tokens"]
    if not ta or not tb:
        return 0.0

    inter = len(ta & tb)
    if inter == 0:
        return 0.0

    union = len(ta | tb)
    shared_med = sum(1 for term in GLOBAL_MEDICAL_TERMS if term in a["low"] and term in b["low"])
    same_source_bonus = 0.08 if a["source"] == b["source"] else 0.0
    return (inter / union) + 0.06 * shared_med + same_source_bonus


def cluster_label(items: List[Dict[str, Any]]) -> str:
    bag: Dict[str, int] = defaultdict(int)
    for item in items[:4]:
        for term in GLOBAL_MEDICAL_TERMS:
            if term in item["low"]:
                bag[term] += 1

    if not bag:
        return "general evidence"

    return ", ".join([term for term, _ in sorted(bag.items(), key=lambda kv: (-kv[1], kv[0]))[:3]])


def build_clusters(snippets: List[Dict[str, Any]], max_clusters: int = 16) -> List[Dict[str, Any]]:
    if not snippets:
        return []

    clusters: List[Dict[str, Any]] = []
    ranked_snippets = sorted(
        snippets,
        key=lambda s: (sum(1 for term in GLOBAL_MEDICAL_TERMS if term in s["low"]), len(s["text"])),
        reverse=True,
    )

    for snip in ranked_snippets:
        best_idx: Optional[int] = None
        best_score = 0.0

        for idx, cluster in enumerate(clusters):
            score = lexical_similarity(snip, cluster["centroid"])
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx is not None and best_score >= 0.24:
            clusters[best_idx]["items"].append(snip)
            if len(snip["tokens"]) > len(clusters[best_idx]["centroid"]["tokens"]):
                clusters[best_idx]["centroid"] = snip
        elif len(clusters) < max_clusters:
            clusters.append({"centroid": snip, "items": [snip]})
        else:
            smallest = min(range(len(clusters)), key=lambda i: len(clusters[i]["items"]))
            clusters[smallest]["items"].append(snip)

    packed: List[Dict[str, Any]] = []
    for cluster in clusters:
        items = cluster["items"]
        items_sorted = sorted(items, key=lambda x: len(x["text"]), reverse=True)
        packed.append(
            {
                "label": cluster_label(items_sorted),
                "summary": " | ".join(item["text"] for item in items_sorted[:3]),
                "source_hint": ", ".join(sorted({item["source"] for item in items_sorted[:3]})),
                "items": items_sorted,
            }
        )

    packed.sort(key=lambda c: len(c["items"]), reverse=True)
    return packed


def rank_snippets_for_field(
    field: str,
    snippets: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    max_items: int = 4,
) -> List[Dict[str, Any]]:
    keywords = FIELD_KEYWORDS.get(field, [])
    scored: List[Tuple[float, Dict[str, Any]]] = []

    for snip in snippets:
        low = snip["low"]
        direct_hits = sum(2 for kw in keywords if kw in low)
        med_hits = sum(1 for term in GLOBAL_MEDICAL_TERMS if term in low)
        numeric_bonus = 1 if re.search(r"\b\d+(?:mm|cm|x\d|/m|/f|yrs|year)\b", low) else 0
        negative_context_penalty = 2 if any(term in low for term in IRRELEVANT_PAGE_TERMS) else 0
        score = direct_hits + 0.25 * med_hits + 0.8 * numeric_bonus - negative_context_penalty
        if score > 0:
            scored.append((score, snip))

    scored.sort(key=lambda x: (x[0], len(x[1]["text"])), reverse=True)
    picked = [snip for _, snip in scored[:max_items]]

    if clusters:
        boosted: List[Dict[str, Any]] = []
        for cluster in clusters:
            cluster_text = (cluster["label"] + " " + cluster["summary"]).lower()
            cluster_score = sum(1 for kw in keywords if kw in cluster_text)
            if cluster_score >= 2:
                boosted.extend(cluster["items"][:2])

        for item in boosted:
            if item not in picked:
                picked.append(item)
            if len(picked) >= max_items:
                break

    return picked[:max_items]


def extract_age_sex(text: str) -> Tuple[str, str]:
    m = re.search(r"\b(\d{1,3})\s*[/,\- ]\s*(male|female|m|f)\b", text, re.I)
    if m:
        age = int(m.group(1))
        sex = m.group(2).strip().lower()
        return (
            str(age) if 1 <= age <= 120 else "Not documented",
            "Male" if sex in ("m", "male") else "Female",
        )

    age = "Not documented"
    sex = "Not documented"

    m_age = re.search(r"\bage[:\s\-]*(\d{1,3})\b", text, re.I)
    if m_age:
        n = int(m_age.group(1))
        if 1 <= n <= 120:
            age = str(n)

    m_sex = re.search(r"\bsex[:\s\-]*(male|female|m|f)\b", text, re.I)
    if m_sex:
        s = m_sex.group(1).strip().lower()
        sex = "Male" if s in ("m", "male") else "Female"

    return age, sex


def detect_binary(low: str, positive_patterns: Sequence[str], negative_patterns: Sequence[str]) -> str:
    for pat in negative_patterns:
        if re.search(pat, low):
            return "No"
    for pat in positive_patterns:
        if re.search(pat, low):
            return "Yes"
    return "Not documented"


def cheap_prefill(patient_id: str, oral_text: str, general_text: str) -> Dict[str, str]:
    row = {col: "Not documented" for col in COLUMNS}
    row["Patient_ID"] = patient_id

    combined = (general_text + "\n\n" + oral_text).strip()
    oral_low = oral_text.lower()
    general_low = general_text.lower()

    m = re.search(r"(?:hospital\s*no|registration\s*no|mrd\s*no|uhid|op\s*no)[:\s\-]*([a-z0-9/\-]{3,30})", combined, re.I)
    if m:
        row["Hospital_No"] = m.group(1).strip()

    m_icd = re.search(r"\b([CD]\d{2}(?:\.\d+)?)\b", combined, re.I)
    if m_icd:
        row["ICD_Code"] = m_icd.group(1).upper()

    age, sex = extract_age_sex(combined)
    row["Age"] = age
    row["Sex"] = sex

    row["HTN"] = detect_binary(
        general_low,
        [r"\bhtn\b", r"\bhypertension\b", r"\bantihypertensive\b"],
        [r"\bno\b.{0,20}\b(htn|hypertension)\b"],
    )

    row["DM"] = detect_binary(
        general_low,
        [r"\bdm\b", r"\bdiabetes\b", r"\bdiabetic\b", r"\bmetformin\b", r"\binsulin\b"],
        [r"\bno\b.{0,20}\b(dm|diabetes|diabetic)\b"],
    )

    row["Tobacco_Use"] = detect_binary(
        general_low,
        [r"\btobacco\b", r"\bsmoking\b", r"\bcigarette\b", r"\bbeedi\b", r"\bbidi\b", r"\bgutka\b", r"\bgutkha\b", r"\bkhaini\b", r"\bpan masala\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,30}\b(tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)\b"],
    )

    row["Areca_Nut_Use"] = detect_binary(
        general_low,
        [r"\bareca\b", r"\bbetel\b", r"\bsupari\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\b(areca|betel|supari)\b"],
    )

    row["Alcohol_Use"] = detect_binary(
        general_low,
        [r"\balcohol\b", r"\bliquor\b", r"\bbeer\b", r"\bwine\b", r"\bdrinking\b"],
        [r"\b(no\s+h/o|no\s+history\s+of|denies?)\b.{0,25}\balcohol\b"],
    )

    if re.search(r"family history\s*[:\-]\s*(yes|present|positive)", general_low):
        row["Family_History"] = "Yes"
    elif re.search(r"family history\s*[:\-]\s*(no|nil|absent|negative)", general_low):
        row["Family_History"] = "No"

    m_fh = re.search(r"family history[:\s\-]*([^\n]{1,140})", general_text, re.I)
    if m_fh:
        fh = m_fh.group(1).strip(" .,:;-")
        if fh and fh.lower() not in {"yes", "no", "nil", "absent", "negative", "positive", "present"}:
            row["Family_History_Details"] = fh

    m_cc = re.search(r"(?:chief complaint|complaint|c/o|presents with)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_cc:
        row["Chief_Complaint"] = m_cc.group(1).strip(" .,:;-")

    if row["Tobacco_Use"] == "Yes":
        m = re.search(r"((?:tobacco|smoking|cigarette|beedi|bidi|gutka|gutkha|khaini|pan masala)[^\n]{0,120})", general_text, re.I)
        if m:
            row["Tobacco_Use_Details"] = m.group(1).strip(" .,:;-")

    if row["Areca_Nut_Use"] == "Yes":
        m = re.search(r"((?:areca|betel|supari)[^\n]{0,120})", general_text, re.I)
        if m:
            row["Areca_Nut_Details"] = m.group(1).strip(" .,:;-")

    if row["Alcohol_Use"] == "Yes":
        m = re.search(r"(alcohol[^\n]{0,120}|drinking[^\n]{0,120})", general_text, re.I)
        if m:
            row["Alcohol_Use_Details"] = m.group(1).strip(" .,:;-")

    if re.search(r"\bburning sensation\b", oral_low):
        row["Burning_Sensation"] = "Yes"

    m_pain = re.search(r"(pain[^\n]{0,100}|painful[^\n]{0,100}|tenderness[^\n]{0,100}|odynophagia[^\n]{0,100})", oral_text, re.I)
    if m_pain:
        row["Pain_Details"] = m_pain.group(1).strip(" .,:;-")

    if re.search(r"\b(restricted|reduced)\b.{0,25}\bmouth opening\b|\btrismus\b", oral_low):
        row["Mouth_Opening_Status"] = "Restricted"
    elif re.search(r"\bmouth opening\b.{0,15}\bnormal\b", oral_low):
        row["Mouth_Opening_Status"] = "Normal"

    m_mo = re.search(r"(mouth opening[^\n]{0,100}|interincisal[^\n]{0,100}|trismus[^\n]{0,100})", oral_text, re.I)
    if m_mo:
        row["Mouth_Opening_Details"] = m_mo.group(1).strip(" .,:;-")

    if re.search(r"oral hygiene status\s*[:\-]\s*poor", oral_low) or "calculus +++" in oral_low or "debris +++" in oral_low:
        row["Oral_Hygiene_Status"] = "Poor"
    elif re.search(r"oral hygiene status\s*[:\-]\s*fair", oral_low) or "calculus ++" in oral_low or "debris ++" in oral_low or "calculus +" in oral_low or "debris +" in oral_low:
        row["Oral_Hygiene_Status"] = "Fair"
    elif re.search(r"oral hygiene status\s*[:\-]\s*good", oral_low):
        row["Oral_Hygiene_Status"] = "Good"

    if re.search(r"\bno palpable neck node\b|\bno neck node\b|\bnodes? not palpable\b", oral_low):
        row["Cervical_Lymphadenopathy"] = "Negative"
        row["Cervical_Lymphadenopathy_Details"] = "No palpable neck node"
    elif re.search(r"\blymph node\b|\bsubmandibular node\b|\bneck node\b", oral_low):
        row["Cervical_Lymphadenopathy"] = "Positive"
        m_ln = re.search(r"(lymph node[^\n]{0,100}|submandibular node[^\n]{0,100}|neck node[^\n]{0,100})", oral_text, re.I)
        if m_ln:
            row["Cervical_Lymphadenopathy_Details"] = m_ln.group(1).strip(" .,:;-")

    if re.search(r"no\s+h/o\s+bleeding|no\s+history\s+of\s+bleeding", oral_low):
        row["Bleeding_Present"] = "No"
        row["Bleeding_Details"] = "No H/o bleeding"
    elif re.search(r"\bbleeding\b", oral_low):
        row["Bleeding_Present"] = "Yes"
        m_bleed = re.search(r"(bleeding[^\n]{0,100})", oral_text, re.I)
        if m_bleed:
            row["Bleeding_Details"] = m_bleed.group(1).strip(" .,:;-")

    m_dx = re.search(r"(?:clinical diagnosis|diagnosis|impression)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_dx:
        row["Clinical_Diagnosis"] = m_dx.group(1).strip(" .,:;-")

    m_pdx = re.search(r"(?:provisional diagnosis|final diagnosis|working diagnosis)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_pdx:
        row["Final_Provisional_Dx"] = m_pdx.group(1).strip(" .,:;-")

    m_ddx = re.search(r"(?:differential diagnosis|differentials?)[:\s\-]*([^\n]{3,180})", oral_text, re.I)
    if m_ddx:
        row["Differential_Diagnosis"] = m_ddx.group(1).strip(" .,:;-")

    m_tnm = re.search(r"\b(T[0-4X][A-Z]?(?:\s*)N[0-3X][A-Z]?(?:\s*)M[0-1X])\b", combined, re.I)
    if m_tnm:
        row["TNM_Stage"] = re.sub(r"\s+", "", m_tnm.group(1).upper())

    m_hist = re.search(r"(well differentiated|moderately differentiated|poorly differentiated)", combined, re.I)
    if m_hist:
        row["Histological_Subgroup"] = m_hist.group(1).strip().title()

    m_biopsy = re.search(r"(?:biopsy|histopath|hpe|fnac|incisional biopsy)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_biopsy:
        row["Biopsy_Details"] = m_biopsy.group(1).strip(" .,:;-")

    m_inv = re.search(r"(?:investigation|investigations)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_inv:
        row["Investigations"] = m_inv.group(1).strip(" .,:;-")

    m_plan = re.search(r"(?:treatment plan|plan|advised)[:\s\-]*([^\n]{3,180})", combined, re.I)
    if m_plan:
        row["Treatment_Plan"] = m_plan.group(1).strip(" .,:;-")

    lesion_types = ["ulcer", "growth", "patch", "plaque", "swelling", "mass", "lesion"]
    for token in lesion_types:
        if re.search(rf"\b{re.escape(token)}\b", oral_low):
            row["Lesion_Type"] = token.title()
            break

    color_map = {
        "erythematous": "Red",
        "red": "Red",
        "white": "White",
        "mixed": "Mixed",
        "pale": "Pale",
        "blanched": "Pale",
    }
    for token, norm in color_map.items():
        if re.search(rf"\b{re.escape(token)}\b", oral_low):
            row["Lesion_Color"] = norm
            break

    site_tokens = ["buccal mucosa", "tongue", "palate", "retromolar", "gingiva", "vestibule", "commissure", "faucial pillar"]
    for site in site_tokens:
        if site in oral_low:
            row["Lesion_Site"] = site.title()
            break

    m_soft = re.search(r"(?:soft tissue|mucosa|buccal mucosa|tongue|palate|gingiva)[^\n]{0,180}", oral_text, re.I)
    if m_soft:
        row["Soft_Tissue_Exam"] = m_soft.group(0).strip(" .,:;-")

    m_find = re.search(r"(?:induration|ulcer|growth|tenderness|surface|margin)[^\n]{0,180}", oral_text, re.I)
    if m_find:
        row["Specific_Findings"] = m_find.group(0).strip(" .,:;-")

    m_trauma = re.search(r"(sharp tooth[^\n]{0,120}|trauma[^\n]{0,120}|irritation[^\n]{0,120}|frictional[^\n]{0,120}|cheek bite[^\n]{0,120}|tooth irritation[^\n]{0,120})", combined, re.I)
    if m_trauma:
        row["Trauma_Irritation_History"] = m_trauma.group(1).strip(" .,:;-")

    return row


def normalize_yes_no(value: str) -> str:
    v = str(value).strip().lower()
    if v in {"yes", "y", "1", "true", "present", "positive"}:
        return "Yes"
    if v in {"no", "n", "0", "false", "absent", "negative"}:
        return "No"
    return value


def clean_output_row(row: Dict[str, Any]) -> Dict[str, str]:
    clean: Dict[str, str] = {}

    for col in COLUMNS:
        val = row.get(col, "Not documented")
        if isinstance(val, list):
            val = "; ".join(str(v) for v in val)

        val = str(val).strip()

        if col == "Sex":
            lut = {"M": "Male", "F": "Female", "m": "Male", "f": "Female", "male": "Male", "female": "Female"}
            val = lut.get(val, lut.get(val.lower(), val))
            if val not in ("Male", "Female", "Not documented"):
                val = "Not documented"

        if col in YES_NO_FIELDS:
            val = normalize_yes_no(val)

        if col == "Cervical_Lymphadenopathy":
            low = val.lower()
            if low in {"yes", "positive", "present", "1"}:
                val = "Positive"
            elif low in {"no", "negative", "absent", "0"}:
                val = "Negative"

        if col == "Mouth_Opening_Status":
            low = val.lower()
            if "restrict" in low or "reduced" in low or "trismus" in low:
                val = "Restricted"
            elif "normal" in low:
                val = "Normal"
            elif val != "Not documented":
                val = "Not documented"

        if col == "Oral_Hygiene_Status":
            low = val.lower()
            if "poor" in low:
                val = "Poor"
            elif "fair" in low:
                val = "Fair"
            elif "good" in low:
                val = "Good"
            elif val != "Not documented":
                val = "Not documented"

        clean[col] = "Not documented" if val in {"", "None", "nan", "[]", "{}"} else val

    return clean


def post_validate_row(row: Dict[str, str]) -> Dict[str, str]:
    row = dict(row)

    age_txt = str(row.get("Age", "")).strip()
    if age_txt.isdigit():
        age = int(age_txt)
        if not (1 <= age <= 120):
            row["Age"] = "Not documented"
    elif age_txt != "Not documented":
        row["Age"] = "Not documented"

    icd = str(row.get("ICD_Code", "")).strip().upper()
    if icd not in {"", "NOT DOCUMENTED"}:
        m = re.match(r"^[CD]\d{2}(?:\.\d+)?$", icd)
        row["ICD_Code"] = icd if m else "Not documented"

    node_details = str(row.get("Cervical_Lymphadenopathy_Details", "")).lower()
    if any(x in node_details for x in ["no palpable", "no neck node", "absent", "not palpable"]):
        row["Cervical_Lymphadenopathy"] = "Negative"

    bleeding_details = str(row.get("Bleeding_Details", "")).lower()
    if any(x in bleeding_details for x in ["no h/o bleeding", "no history of bleeding", "bleeding absent", "no bleeding"]):
        row["Bleeding_Present"] = "No"

    fam_details = str(row.get("Family_History_Details", "")).strip().lower()
    if row.get("Family_History") == "Yes" and fam_details in {"", "not documented", "nrmh", "+ nrmh.", "+nrmh."}:
        row["Family_History"] = "Not documented"
        row["Family_History_Details"] = "Not documented"

    findings = (str(row.get("Specific_Findings", "")) + " " + str(row.get("Soft_Tissue_Exam", ""))).lower()
    oral = str(row.get("Oral_Hygiene_Status", "")).lower()
    if "calculus +++" in findings or "poor oral hygiene" in findings or "debris +++" in findings:
        row["Oral_Hygiene_Status"] = "Poor"
    elif oral not in {"good", "fair", "poor", "not documented"}:
        row["Oral_Hygiene_Status"] = "Not documented"

    for status_field, detail_field in [
        ("Tobacco_Use", "Tobacco_Use_Details"),
        ("Areca_Nut_Use", "Areca_Nut_Details"),
        ("Alcohol_Use", "Alcohol_Use_Details"),
    ]:
        details = str(row.get(detail_field, "")).lower()
        if row.get(status_field) == "Not documented":
            if any(x in details for x in ["no ", "denies", "absent", "negative"]):
                row[status_field] = "No"
            elif details not in {"", "not documented"}:
                row[status_field] = "Yes"

    return row


def merge_results(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)

    always_replace_if_present = {
        "Clinical_Diagnosis",
        "Final_Provisional_Dx",
        "Differential_Diagnosis",
        "Investigations",
        "Biopsy_Details",
        "Treatment_Plan",
        "Specific_Findings",
        "Soft_Tissue_Exam",
        "Chief_Complaint",
        "Histological_Subgroup",
        "TNM_Stage",
        "ICD_Code",
    }

    for key in COLUMNS:
        old_val = merged.get(key, "Not documented")
        new_val = update.get(key, "Not documented")

        if is_missing(new_val):
            continue

        if is_missing(old_val):
            merged[key] = new_val
            continue

        if key in {"Mouth_Opening_Status", "Oral_Hygiene_Status", "Cervical_Lymphadenopathy"}:
            merged[key] = new_val
            continue

        if key in always_replace_if_present:
            merged[key] = new_val
            continue

        if len(str(new_val).strip()) > len(str(old_val).strip()):
            merged[key] = new_val

    return merged


def format_snippet(item: Dict[str, Any]) -> str:
    return "[{src}] {txt}".format(src=item["source"], txt=item["text"])


def build_patient_payload(folder_path: str, patient_id: str, max_patient_chars: int) -> Optional[Dict[str, Any]]:
    file_contents = read_files(folder_path)
    if not file_contents:
        print("  [ocr] No .txt files found")
        return None

    print("  [ocr] {n} file(s) loaded".format(n=len(file_contents)))

    routed = route_pages(file_contents)
    oral_pages = routed["oral"]
    general_pages = routed["general"]
    dropped_pages = routed["dropped"]
    print("  [ocr] oral={o} | general={g} | dropped={d}".format(o=len(oral_pages), g=len(general_pages), d=len(dropped_pages)))

    oral_text_raw = "\n\n".join("=== {fname} ===\n{txt}".format(fname=fname, txt=txt) for fname, txt in oral_pages).strip()
    general_text_raw = "\n\n".join("=== {fname} ===\n{txt}".format(fname=fname, txt=txt) for fname, txt in general_pages).strip()

    if not oral_text_raw and not general_text_raw:
        print("  [ocr] No useful text survived routing")
        return None

    oral_budget = max(4500, int(max_patient_chars * 0.55))
    general_budget = max(2200, int(max_patient_chars * 0.25))
    cluster_budget = max(1400, max_patient_chars - oral_budget - general_budget)

    oral_snippets = split_into_snippets(oral_pages)
    general_snippets = split_into_snippets(general_pages)
    all_snippets = oral_snippets + [s for s in general_snippets if s not in oral_snippets]
    clusters = build_clusters(all_snippets)

    field_packets: Dict[str, List[str]] = {}
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        ranked = rank_snippets_for_field(field, all_snippets, clusters, max_items=4)
        if ranked:
            field_packets[field] = [format_snippet(item) for item in ranked]

    cluster_text = "\n".join(
        "- {label} :: {summary} :: {src}".format(
            label=cluster["label"],
            summary=cluster["summary"],
            src=cluster["source_hint"],
        )
        for cluster in clusters[:10]
    )
    cluster_text, _ = controlled_truncate(cluster_text, cluster_budget)

    oral_text, oral_truncated = controlled_truncate(oral_text_raw, oral_budget)
    general_text, general_truncated = controlled_truncate(general_text_raw, general_budget)

    prefill = cheap_prefill(patient_id, oral_text, general_text)

    packet_lines: List[str] = []
    for field in COLUMNS:
        if field == "Patient_ID":
            continue
        evidences = field_packets.get(field)
        if evidences:
            packet_lines.append("{field}:".format(field=field))
            packet_lines.extend("  - {item}".format(item=item) for item in evidences)

    field_evidence_text = "\n".join(packet_lines)

    return {
        "patient_id": patient_id,
        "prefill": prefill,
        "oral_text": oral_text,
        "general_text": general_text,
        "cluster_text": cluster_text,
        "field_evidence_text": field_evidence_text,
        "truncated": oral_truncated or general_truncated,
    }


def make_patient_prompt(payload: Dict[str, Any]) -> str:
    pid = payload["patient_id"]
    schema_hint = {col: "Not documented" for col in COLUMNS}

    return f"""
You are a medical data extraction specialist for oral case sheets.

You are analyzing EXACTLY ONE patient.
Never invent facts.
Never use one field to hallucinate another.
Prefer explicit evidence.
If evidence is weak or missing, write "Not documented".

Rules:
{EXTRACTION_RULES}

Output contract:
- Return exactly one valid JSON object.
- No markdown.
- No explanation.
- JSON only.
- Patient_ID must be exactly "{pid}".
- The "fields" object must contain all 39 fixed fields exactly once.
- patient_summary should be short and clinically useful.
- extra_findings should include useful findings that do not fit neatly into the 39 columns.
- evidence_map should contain concise field-linked evidence.

Example fields skeleton:
{json.dumps(schema_hint, ensure_ascii=False)}

PATIENT_BLOCK_START
Patient_ID: {pid}

CURRENT_PREFILL_JSON:
{json.dumps(payload["prefill"], ensure_ascii=False)}

SALIENT_SIMILARITY_CLUSTERS:
{payload["cluster_text"] if payload["cluster_text"] else "Not documented"}

FIELD_EVIDENCE_PACKETS:
{payload["field_evidence_text"] if payload["field_evidence_text"] else "Not documented"}

ORAL_TEXT:
{payload["oral_text"] if payload["oral_text"] else "Not documented"}

GENERAL_TEXT:
{payload["general_text"] if payload["general_text"] else "Not documented"}

PATIENT_BLOCK_END
""".strip()


def normalize_model_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for col in COLUMNS:
        normalized[col] = fields.get(col, "Not documented")
    return normalized


def validate_single_patient_response(response: Any, expected_patient_id: str) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {}

    pid = str(response.get("Patient_ID", "")).strip()
    fields = response.get("fields")

    if pid != expected_patient_id:
        return {}

    if not isinstance(fields, dict):
        return {}

    return {
        "fields": normalize_model_fields(fields),
        "patient_summary": str(response.get("patient_summary", "")).strip() or "Not documented",
        "extra_findings": response.get("extra_findings", []) if isinstance(response.get("extra_findings"), list) else [],
        "evidence_map": response.get("evidence_map", []) if isinstance(response.get("evidence_map"), list) else [],
    }


def flatten_extra_findings(patient_id: str, findings: Sequence[Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "Patient_ID": patient_id,
                "Category": str(item.get("category", "")).strip() or "Other",
                "Title": str(item.get("title", "")).strip() or "Untitled",
                "Detail": str(item.get("detail", "")).strip() or "Not documented",
                "Evidence": str(item.get("evidence", "")).strip() or "Not documented",
                "Source_Hint": str(item.get("source_hint", "")).strip() or "Not documented",
            }
        )
    return rows


def flatten_evidence_map(patient_id: str, evidence_items: Sequence[Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        if field and field not in COLUMNS:
            continue
        rows.append(
            {
                "Patient_ID": patient_id,
                "Field": field or "Unknown",
                "Evidence": str(item.get("evidence", "")).strip() or "Not documented",
                "Source_Hint": str(item.get("source_hint", "")).strip() or "Not documented",
            }
        )
    return rows


def call_patient_model(payload: Dict[str, Any], model: str) -> Tuple[Any, Dict[str, Any]]:
    pid = payload["patient_id"]
    prompt = make_patient_prompt(payload)

    print(f"  [ocr] Sending 1 Gemini call for {pid}")

    try:
        response = call_llm(
            prompt,
            response_schema=SINGLE_PATIENT_RESPONSE_SCHEMA,
            model=model,
            temperature=0.0,
            use_cache=True,
        )
    except Exception as e:
        print(f"  [ocr] LLM call failed for {pid}: {e}")
        return None, {}

    parsed = validate_single_patient_response(response, pid)
    if not parsed:
        print(f"  [ocr] Invalid/empty structured response for {pid}")
        return response, {}

    return response, parsed


def run(
    patients_dir: str,
    output_csv: str,
    output_xlsx: str,
    output_json: str,
    max_patient_chars: int,
    model: str,
) -> None:
    subfolders = sorted(d for d in os.listdir(patients_dir) if os.path.isdir(os.path.join(patients_dir, d)))
    if not subfolders:
        print("\n❌ No patient folders found in: {path}".format(path=patients_dir))
        return

    print("\n[ocr] Found {n} patient folder(s)".format(n=len(subfolders)))

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(output_xlsx) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)

    rows_by_patient: Dict[str, Dict[str, str]] = {}
    extra_rows: List[Dict[str, str]] = []
    evidence_rows: List[Dict[str, str]] = []
    summary_rows: List[Dict[str, str]] = []
    raw_json_rows: List[Dict[str, Any]] = []

    prepared_payloads: List[Dict[str, Any]] = []

    for i, folder_name in enumerate(subfolders, start=1):
        folder_path = os.path.join(patients_dir, folder_name)

        print("\n" + "=" * 60)
        print("[ocr] Preparing patient {i}/{n}: {name}".format(i=i, n=len(subfolders), name=folder_name))

        payload = build_patient_payload(folder_path, folder_name, max_patient_chars=max_patient_chars)
        if payload is None:
            print("  [ocr] Skipping — no valid payload")
            continue

        if payload["truncated"]:
            print("  [ocr] Text was truncated locally for token control")

        prepared_payloads.append(payload)
        rows_by_patient[folder_name] = post_validate_row(clean_output_row(payload["prefill"]))

    if not prepared_payloads:
        print("\n❌ No valid patient payloads prepared.")
        return

    for idx, payload in enumerate(prepared_payloads, start=1):
        pid = payload["patient_id"]

        print("\n" + "-" * 60)
        print("[ocr] LLM patient {i}/{n}: {pid}".format(i=idx, n=len(prepared_payloads), pid=pid))

        raw_response, parsed = call_patient_model(payload, model=model)

        raw_json_rows.append(
            {
                "Patient_ID": pid,
                "raw_response": raw_response,
            }
        )

        if parsed:
            merged = merge_results(rows_by_patient[pid], parsed.get("fields", {}))
            rows_by_patient[pid] = post_validate_row(clean_output_row(merged))

            for row in flatten_extra_findings(pid, parsed.get("extra_findings", [])):
                extra_rows.append(row)

            for row in flatten_evidence_map(pid, parsed.get("evidence_map", [])):
                evidence_rows.append(row)

            summary_rows.append(
                {
                    "Patient_ID": pid,
                    "Patient_Summary": str(parsed.get("patient_summary", "Not documented")) or "Not documented",
                }
            )
        else:
            summary_rows.append(
                {
                    "Patient_ID": pid,
                    "Patient_Summary": "Not documented",
                }
            )

        filled = sum(1 for v in rows_by_patient[pid].values() if v != "Not documented")
        print("  [ocr] {pid}: {filled}/{total} fixed fields filled".format(pid=pid, filled=filled, total=len(COLUMNS)))
        print("  [ocr] Diagnosis: {txt}".format(txt=rows_by_patient[pid]["Clinical_Diagnosis"][:120]))

    df = pd.DataFrame([rows_by_patient[pid] for pid in sorted(rows_by_patient)], columns=COLUMNS)
    df.to_csv(output_csv, index=False)

    extras_df = pd.DataFrame(extra_rows, columns=["Patient_ID", "Category", "Title", "Detail", "Evidence", "Source_Hint"])
    evidence_df = pd.DataFrame(evidence_rows, columns=["Patient_ID", "Field", "Evidence", "Source_Hint"])
    summary_df = pd.DataFrame(summary_rows, columns=["Patient_ID", "Patient_Summary"])

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="main_39_fields", index=False)
        summary_df.to_excel(writer, sheet_name="patient_summaries", index=False)
        extras_df.to_excel(writer, sheet_name="extra_findings", index=False)
        evidence_df.to_excel(writer, sheet_name="evidence_map", index=False)

    json_payload = {
        "patients": raw_json_rows,
        "final_rows": df.to_dict(orient="records"),
        "patient_summaries": summary_rows,
    }

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ DONE")
    print("   Patients   : {n}".format(n=len(df)))
    print("   Fixed cols : {n}".format(n=len(COLUMNS)))
    print("   CSV        : {p}".format(p=output_csv))
    print("   Excel      : {p}".format(p=output_xlsx))
    print("   JSON       : {p}".format(p=output_json))

    print("\nPreview:")
    preview_cols = [
        "Patient_ID",
        "Age",
        "Sex",
        "HTN",
        "DM",
        "Tobacco_Use",
        "Oral_Hygiene_Status",
        "Clinical_Diagnosis",
        "Final_Provisional_Dx",
    ]
    print(df[preview_cols].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", default="data/patients")
    parser.add_argument("--output", default="data/output_patients.csv")
    parser.add_argument("--excel", default="data/output_patients.xlsx")
    parser.add_argument("--json", default="data/output_patients_full.json")
    parser.add_argument(
        "--max-patient-chars",
        type=int,
        default=14000,
        help="Approx chars kept per patient after routing and evidence packing",
    )
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)

    run(
        patients_dir=args.folder,
        output_csv=args.output,
        output_xlsx=args.excel,
        output_json=args.json,
        max_patient_chars=args.max_patient_chars,
        model=args.model,
    )