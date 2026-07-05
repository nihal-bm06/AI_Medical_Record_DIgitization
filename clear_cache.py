# Run this whenever you want to clear stale LLM prompt cache:
#   python clear_cache.py
import os, json

path = "data/prompt_cache.json"
if os.path.exists(path):
    # Only delete entries with empty records — keep good cached results
    with open(path) as f:
        cache = json.load(f)
    before = len(cache)
    cache = {k:v for k,v in cache.items()
             if not (isinstance(json.loads(v).get("records"), list)
                     and len(json.loads(v)["records"]) == 0)}
    with open(path, "w") as f:
        json.dump(cache, f)
    print(f"Removed {before - len(cache)} stale entries. {len(cache)} remain.")
else:
    print("No prompt cache found.")