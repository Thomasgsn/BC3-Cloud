"""Promotion locale atomique d’artefacts produits par notre pipeline, sans upload utilisateur."""

import argparse
import hashlib
import json
import os
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("version", nargs="?")
p.add_argument("--rollback", action="store_true")
p.add_argument("--root", default="/workspace/models")
a = p.parse_args()
root = Path(a.root)
active = root / "active.json"
old = json.loads(active.read_text()) if active.exists() else None
version = (old or {}).get("previous") if a.rollback else a.version
if not version or Path(version).name != version:
    raise SystemExit("Version invalide ou aucun précédent")
folder = root / version
m = json.loads((folder / "manifest.json").read_text())
sha = hashlib.sha256((folder / "model.joblib").read_bytes()).hexdigest()
if sha != m["model_sha256"]:
    raise SystemExit("REFUS : intégrité modèle")
if not m.get("trusted_local_pipeline") or m["validation_macro_f1"] < 0.75:
    raise SystemExit("REFUS : seuil de validation")
if old and not a.rollback and m["validation_macro_f1"] < old["validation_macro_f1"] - 0.02:
    raise SystemExit("REFUS : régression validation")
record = {k: m[k] for k in ["version", "model_sha256", "validation_macro_f1", "language"]}
record["previous"] = old["version"] if old else None
(root / "active.tmp").write_text(json.dumps(record, indent=2) + "\n")
os.replace(root / "active.tmp", active)
print(json.dumps({"event": "rollback" if a.rollback else "promotion", **record}))
