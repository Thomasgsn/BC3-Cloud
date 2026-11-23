"""Acquérir la source originale épinglée ; aucun réemploi de BC2."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path

r = Path(__file__).resolve().parents[1]
lock = json.loads((r / "infra/banking77.lock.json").read_text())
dest = r / "data/raw/banking77"
dest.mkdir(parents=True, exist_ok=True)
for name, info in lock["files"].items():
    path = dest / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]:
        continue
    relative = "LICENSE" if name == "LICENSE" else "banking_data/" + name
    url = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{lock['revision']}/{relative}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
        raise ValueError("Source incohérente : " + name)
    temp = path.with_suffix(path.suffix + ".partial")
    temp.write_bytes(data)
    os.replace(temp, path)
print(
    json.dumps(
        {
            "verified_original_files": len(lock["files"]),
            "revision": lock["revision"],
            "license": lock["license"],
        }
    )
)
