# ============================================================
#  utils.py  —  Cache helpers (MD5 hash + JSON file)
# ============================================================
import hashlib, json, os
from config import CACHE_FILE


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f: return json.load(f)
        except: pass
    return {}


def save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f: json.dump(cache, f, indent=2)


def get_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()