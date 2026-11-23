"""Backup/restauration réels via job administratif dédié, cible neuve conservée."""

import copy
import json
import os
import subprocess
import uuid
from pathlib import Path

K = ["kubectl", "--context", "kind-rncp-bc3", "-n", "bc3-test"]
r = Path(__file__).resolve().parents[1]
job = copy.deepcopy(json.loads((r / "infra/kubernetes/20-bootstrap.json").read_text())["items"][0])
name = "backup-check-" + uuid.uuid4().hex[:8]
job["metadata"]["name"] = name
job["spec"]["backoffLimit"] = 0
c = job["spec"]["template"]["spec"]["containers"][0]
c["image"] = "rncp-bc3-backup:5"
c["command"] = ["python", "/app/scripts/backup.py", "--verify-restore"]
c["env"].append({"name": "BC3_ROOT", "value": "/tmp"})
job["spec"]["template"]["metadata"]["labels"] = {"app": name}
subprocess.run(K + ["apply", "-f", "-"], input=json.dumps(job), text=True, check=True)
try:
    subprocess.run(
        K + ["wait", "--for=condition=complete", "job/" + name, "--timeout=180s"], check=True
    )
except subprocess.CalledProcessError:
    subprocess.run(K + ["logs", "job/" + name], check=False)
    raise
# Un pod terminé ne permet plus kubectl cp/exec ; le job imprime son résultat JSON.
payload = subprocess.check_output(K + ["logs", "job/" + name], text=True)
result = next(
    json.loads(line)
    for line in payload.splitlines()
    if line.startswith("{") and json.loads(line).get("event") == "encrypted_backup"
)
assert result["download_exact"] and result["restoration"]["encrypted_ticket_values_exact"]
assert len(result["restoration"]["table_counts"]) == 7
out = r / os.environ.get("BC3_BACKUP_EVIDENCE", "docs/evidence/k8s/backup-restore.json")
out.parent.mkdir(exist_ok=True, parents=True)
out.write_text(json.dumps(result, indent=2) + "\n")

print(
    json.dumps(
        {
            "backup_and_restore_verified": True,
            "proof": str(out.relative_to(r)),
            "active_database_overwritten": False,
            "job_retained": name,
        }
    )
)
