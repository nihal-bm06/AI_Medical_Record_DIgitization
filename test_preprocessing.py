"""Quick dry-run to validate the preprocessing pipeline without making any API calls."""
import os
from ocr_to_excel import (
    extract_filename_metadata,
    strip_boilerplate,
    is_noise_page,
    score_page_quality,
    read_files,
    route_pages,
    cheap_prefill,
    controlled_truncate,
)

PATIENTS_DIR = "data/patients"

def test_patient(folder_name: str):
    folder_path = os.path.join(PATIENTS_DIR, folder_name)
    print("\n" + "=" * 60)
    print(f"Testing: {folder_name}")
    print("=" * 60)

    # 1. Read files with full preprocessing
    file_contents = read_files(folder_path)
    filenames = [fname for fname, _ in file_contents]
    
    print(f"  Files after preprocessing: {len(file_contents)}")
    
    # Show top 3 pages by quality (they come pre-sorted)
    for i, (fname, txt) in enumerate(file_contents[:3]):
        preview = txt[:80].replace("\n", " | ")
        print("  Top {i}: {fn} ({cl} chars) -> \"{pv}...\"".format(i=i+1, fn=fname, cl=len(txt), pv=preview))

    # 2. Test filename metadata extraction
    meta = extract_filename_metadata(filenames)
    print(f"\n  Filename metadata: {meta}")

    # 3. Test routing
    routed = route_pages(file_contents)
    print(f"  Routing: oral={len(routed['oral'])} | general={len(routed['general'])} | dropped={len(routed['dropped'])}")

    # 4. Build text and run cheap_prefill
    oral_text = "\n\n".join(f"=== {fn} ===\n{tx}" for fn, tx in routed["oral"])
    general_text = "\n\n".join(f"=== {fn} ===\n{tx}" for fn, tx in routed["general"])
    
    oral_text, _ = controlled_truncate(oral_text, 6600)
    general_text, _ = controlled_truncate(general_text, 3000)
    
    prefill = cheap_prefill(folder_name, oral_text, general_text, filename_meta=meta)
    
    # Show key fields from prefill
    key_fields = ["Hospital_No", "Age", "Sex", "HTN", "DM", "Tobacco_Use", 
                  "Areca_Nut_Use", "Alcohol_Use", "Family_History", "Oral_Hygiene_Status",
                  "Mouth_Opening_Status", "Cervical_Lymphadenopathy", "Bleeding_Present"]
    
    filled = sum(1 for v in prefill.values() if v != "Not documented")
    print("  Prefill results ({f}/{t} fields filled):".format(f=filled, t=len(prefill)))
    for field in key_fields:
        val = prefill.get(field, "Not documented")
        marker = "[Y]" if val != "Not documented" else "[N]"
        print("    {m} {f}: {v}".format(m=marker, f=field, v=val))

if __name__ == "__main__":
    for folder in sorted(os.listdir(PATIENTS_DIR)):
        if os.path.isdir(os.path.join(PATIENTS_DIR, folder)):
            test_patient(folder)
    
    print("\n" + "=" * 60)
    print("PREPROCESSING TEST COMPLETE — No API calls were made!")
    print("=" * 60)
