"""Boucle rouge/verte exécutée dans un vrai pod avec base et chiffrement réels."""

import json
import os
import subprocess
import uuid
from pathlib import Path

K = ["kubectl", "--context", "kind-rncp-bc3", "-n", "bc3-test"]
pods = json.loads(subprocess.check_output(K + ["get", "pods", "-l", "app=api", "-o", "json"]))[
    "items"
]
pod = next(
    p["metadata"]["name"]
    for p in pods
    if not p["metadata"].get("deletionTimestamp")
    and any(c.get("ready") for c in p["status"].get("containerStatuses", []))
)
target = "/tmp/test_read_cost_" + uuid.uuid4().hex[:8] + ".py"
subprocess.run(
    [
        "kubectl",
        "--context",
        "kind-rncp-bc3",
        "cp",
        "tests/integration/test_read_cost.py",
        "bc3-test/" + pod + ":" + target,
    ],
    check=True,
)
result = subprocess.run(
    K
    + [
        "exec",
        pod,
        "--",
        "python",
        "-m",
        "pytest",
        "-q",
        "-o",
        "cache_dir=/tmp/pytest-cache",
        target,
    ],
    text=True,
    capture_output=True,
    check=False,
)
report = {
    "exit_code": result.returncode,
    "stdout": result.stdout,
    "stderr": result.stderr,
    "scope": "Real SQL and encryption, instrumentation counts reads without replacing configuration or exposing values",
}
path = Path(os.getenv("BC3_PROBE_OUTPUT", "docs/evidence/diagnosis/read-cost-before.json"))
path.write_text(json.dumps(report, indent=2) + "\n")
print(result.stdout)
raise SystemExit(result.returncode)
