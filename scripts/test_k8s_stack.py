"""Rejouer les tests réels à l'intérieur de Kubernetes et extraire seulement les preuves."""

import json
import os
import subprocess
import uuid
from pathlib import Path

context = os.environ.get("BC3_KUBE_CONTEXT", "kind-rncp-bc3")
if context not in ["kind-rncp-bc3", "kind-rncp-bc3-repro-clean"]:
    raise ValueError("Cible non autorisée pour les tests BC3")
K = ["kubectl", "--context", context]
NS = "bc3-test"
pods = json.loads(
    subprocess.check_output(K + ["-n", NS, "get", "pods", "-l", "app=api", "-o", "json"])
)["items"]
desired = json.loads(
    subprocess.check_output(K + ["-n", NS, "get", "deployment", "api", "-o", "json"])
)["spec"]["template"]["spec"]["containers"][0]["image"]
pod = next(
    p["metadata"]["name"]
    for p in pods
    if not p["metadata"].get("deletionTimestamp")
    and p["spec"]["containers"][0]["image"] == desired
    and any(c.get("ready") for c in p["status"].get("containerStatuses", []))
)
temp = "/tmp/check-" + uuid.uuid4().hex[:10]
subprocess.run(K + ["-n", NS, "exec", pod, "--", "mkdir", "-p", temp], check=True)
subprocess.run(K + ["cp", "tests/unit", NS + "/" + pod + ":" + temp + "/unit"], check=True)
subprocess.run(
    K
    + [
        "cp",
        "tests/integration",
        NS + "/" + pod + ":" + temp + "/integration",
    ],
    check=True,
)
r = subprocess.run(
    K
    + [
        "-n",
        NS,
        "exec",
        pod,
        "--",
        "env",
        "BC3_TEST_ORIGIN=https://bc3.local:8455",
        "BC3_EVIDENCE_DIR=" + temp + "/evidence",
        "python",
        "-m",
        "pytest",
        "-q",
        "-o",
        "cache_dir=/tmp/pytest-cache",
        temp + "/unit",
        temp + "/integration",
    ],
    capture_output=True,
    check=False,
    text=True,
)
out = Path(os.environ.get("BC3_KUBE_EVIDENCE", "docs/evidence/k8s/integration"))
out.mkdir(exist_ok=True, parents=True)
(out / "pytest.json").write_text(
    json.dumps(
        {
            "command": "Real pytest inside a non-root Kubernetes API pod, actual SQL/S3/queue/worker",
            "exit_code": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr,
        },
        indent=2,
    )
    + "\n"
)
print(r.stdout)
print(r.stderr)
if r.returncode:
    raise SystemExit(r.returncode)
subprocess.run(K + ["cp", NS + "/" + pod + ":" + temp + "/evidence/.", str(out)], check=True)
