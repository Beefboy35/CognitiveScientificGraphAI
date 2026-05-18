import os
import json
from typing import List, Callable, Dict

def write_jsonl_atomic(path: str, items: List[Dict], validate: Callable[[Dict], None]) -> None:
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in items:
            validate(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
