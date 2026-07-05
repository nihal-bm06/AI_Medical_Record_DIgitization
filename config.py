# ============================================================
#  config.py  
# ============================================================
GEMINI_API_KEY = your_gemini_api_key_here 

# ── File paths (don't change these)
OCR_FOLDER  = "data/ocr"            # put your .txt OCR files here
OUTPUT_FILE = "data/output.csv"     # final ML-ready CSV
CACHE_FILE  = "data/cache.json"     # data-level cache
EXCEL_PATH  = "data/reference.xlsx" # column schema for medical mode

# ── Scraper settings
MAX_RETRIES     = 5    # self-healing retry attempts
REQUEST_TIMEOUT = 30   # seconds per page load
