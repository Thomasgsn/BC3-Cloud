"""Exécuter la chaîne complète et conserver son vrai code de sortie et journal local."""

import datetime
import json
import subprocess
import time
from pathlib import Path

r = Path(__file__).resolve().parents[1]
out = r / "docs/evidence/ci"
out.mkdir(parents=True, exist_ok=True)
start = time.monotonic()
at = datetime.datetime.now(datetime.UTC).isoformat()
with (out / "full-run.log").open("w") as log:
    result = subprocess.run(
        ["bash", "scripts/ci_local.sh"], cwd=r, stdout=log, stderr=subprocess.STDOUT, check=False
    )
record = {
    "started_at_utc": at,
    "exit_code": result.returncode,
    "elapsed_wall_seconds": time.monotonic() - start,
    "command": "bash scripts/ci_local.sh",
    "scope": "Actual full pipeline on local Docker/kind; no GitHub Actions remote execution, publication, email or AWS apply",
    "log": "full-run.log",
}
(out / "full-run.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
raise SystemExit(result.returncode)
