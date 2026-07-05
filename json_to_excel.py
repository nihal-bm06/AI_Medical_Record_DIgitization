import json
import pandas as pd
import os

def json_to_excel(json_path="data/output_patients_full.json", output_xlsx="data/output_patients.xlsx"):
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    patients = data.get("patients", [])
    
    # 1. Prepare Main Fields Sheet
    main_rows = []
    for p in patients:
        row = p.get("fields", {}).copy()
        row["Patient_ID"] = p.get("Patient_ID", "Unknown")
        main_rows.append(row)
    
    df_main = pd.DataFrame(main_rows)
    # Ensure Patient_ID is the first column
    cols = ['Patient_ID'] + [c for c in df_main.columns if c != 'Patient_ID']
    df_main = df_main[cols]

    # 2. Prepare Summaries Sheet
    summary_rows = []
    for p in patients:
        summary_rows.append({
            "Patient_ID": p.get("Patient_ID"),
            "Patient_Summary": p.get("patient_summary")
        })
    df_summary = pd.DataFrame(summary_rows)

    # 3. Prepare Extra Findings Sheet
    extra_rows = []
    for p in patients:
        pid = p.get("Patient_ID")
        for finding in p.get("extra_findings", []):
            extra_rows.append({
                "Patient_ID": pid,
                "Category": finding.get("category"),
                "Title": finding.get("title"),
                "Detail": finding.get("detail"),
                "Evidence": finding.get("evidence"),
                "Source_Hint": finding.get("source_hint")
            })
    df_extras = pd.DataFrame(extra_rows)

    # 4. Prepare Evidence Map Sheet
    evidence_rows = []
    for p in patients:
        pid = p.get("Patient_ID")
        for ev in p.get("evidence_map", []):
            evidence_rows.append({
                "Patient_ID": pid,
                "Field": ev.get("field"),
                "Evidence": ev.get("evidence"),
                "Source_Hint": ev.get("source_hint")
            })
    df_evidence = pd.DataFrame(evidence_rows)

    # Write to Excel
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        df_main.to_excel(writer, sheet_name="main_39_fields", index=False)
        df_summary.to_excel(writer, sheet_name="patient_summaries", index=False)
        df_extras.to_excel(writer, sheet_name="extra_findings", index=False)
        df_evidence.to_excel(writer, sheet_name="evidence_map", index=False)

    print(f"✅ Successfully exported edited data to: {output_xlsx}")

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    json_to_excel()
