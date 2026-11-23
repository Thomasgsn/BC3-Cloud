"""Promotions, régression refusée, intégrité refusée et rollback réellement exercés."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

r = Path("/workspace")
models = r / "models"
events = []


def promote(version=None, rollback=False, accepted=True):
    cmd = [
        sys.executable,
        str(r / "scripts/promote_model.py"),
        "--root",
        str(models),
    ] + (["--rollback"] if rollback else [version])
    p = subprocess.run(cmd, text=True, capture_output=True, check=False)
    assert (p.returncode == 0) == accepted, p.stdout + p.stderr
    serving = None
    if accepted:
        code = "import sys,json;sys.path.insert(0,'/workspace/src');from rncp_bc3.intent import suggest;print(json.dumps(suggest('My card has not arrived after two weeks')))"
        serving = json.loads(
            subprocess.check_output(
                [sys.executable, "-c", code],
                env=os.environ | {"BC3_MODEL_DIR": str(models)},
                text=True,
            )
        )
        assert (
            serving["model_version"] == json.loads((models / "active.json").read_text())["version"]
        )
        assert "card_arrival" in [item["category"] for item in serving["suggestions"]]
    events.append(
        {
            "version": version,
            "rollback": rollback,
            "accepted": p.returncode == 0,
            "served_model_version": serving["model_version"] if serving else None,
            "message": (p.stdout + p.stderr).strip(),
        }
    )


promote("banking77-c0-25")
promote("banking77-c1-0")
promote(rollback=True)
assert json.loads((models / "active.json").read_text())["version"] == "banking77-c0-25"
promote("banking77-c1-0")
for name, tamper in [
    ("negative-regression", False),
    ("negative-quality-floor", False),
    ("negative-integrity", True),
]:
    dest = models / name
    dest.mkdir(exist_ok=True)
    shutil.copyfile(models / "banking77-c1-0/model.joblib", dest / "model.joblib")
    manifest = json.loads((models / "banking77-c1-0/manifest.json").read_text())
    manifest["version"] = name
    if tamper:
        with (dest / "model.joblib").open("ab") as f:
            f.write(b"controlled-integrity-test")
    else:
        manifest["validation_macro_f1"] = 0.5 if name == "negative-quality-floor" else 0.85
    (dest / "manifest.json").write_text(json.dumps(manifest))
    promote(name, accepted=False)
(r / "docs/evidence/mlops/registry.json").write_text(
    json.dumps(
        {
            "events": events,
            "active": json.loads((models / "active.json").read_text()),
            "scope": "Local trusted build artifacts only; no uploaded untrusted pickle",
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"registry_checks_passed": len(events)}))
