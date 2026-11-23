"""Mesures réelles avant/après : sondes natives HTTPS, sans changement du chemin métier."""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="docs/evidence/finops/native-probes.json")
args = parser.parse_args()
target = Path(args.output)
if target.exists():
    raise FileExistsError("Preuve existante préservée ; choisir --output pour un nouvel essai")
K = ["kubectl", "--context", "kind-rncp-bc3"]
root = Path("/workspace")
ns = "bc3-test"


def cpu(v):
    for suffix, factor in [("n", 1e-9), ("u", 1e-6), ("m", 1e-3)]:
        if v.endswith(suffix):
            return float(v[: -len(suffix)]) * factor
    return float(v)


def memory(v):
    for suffix, factor in [("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3)]:
        if v.endswith(suffix):
            return float(v[: -len(suffix)]) * factor
    return float(v)


def snapshot():
    data = json.loads(
        subprocess.check_output(
            K + ["get", "--raw", "/apis/metrics.k8s.io/v1beta1/namespaces/bc3-test/pods"]
        )
    )["items"]
    pods = [p for p in data if p["metadata"]["name"].startswith("api-")]
    return {
        "at_utc": datetime.now(UTC).isoformat(),
        "pods": len(pods),
        "cpu_cores": sum(cpu(c["usage"]["cpu"]) for p in pods for c in p["containers"]),
        "memory_bytes": sum(memory(c["usage"]["memory"]) for p in pods for c in p["containers"]),
        "windows": [p["window"] for p in pods],
    }


report = {
    "protocol": "Three Metrics Server samples 15 seconds apart before and after stable rollout/downscale; no ML training or image build during observation",
    "change": "Python exec health probes replaced by native kubelet HTTPS health probes, same paths/periods and business TLS verification unchanged",
    "security_boundary": "Kubelet HTTPS probes encrypt transport but do not verify serving certificate; business clients and dedicated TLS rejection tests still verify CA/hostname",
    "before": [],
    "after": [],
}
for _ in range(3):
    report["before"].append(snapshot())
    time.sleep(15)
file = root / "infra/kubernetes/30-application.json"
manifest = json.loads(file.read_text())
api = next(
    v for v in manifest["items"] if v["kind"] == "Deployment" and v["metadata"]["name"] == "api"
)
spec = api["spec"]["template"]["spec"]["containers"][0]
for field, path in [
    ("readinessProbe", "/health/ready"),
    ("livenessProbe", "/health/live"),
    ("startupProbe", "/health/live"),
]:
    spec[field].pop("exec", None)
    spec[field]["httpGet"] = {"path": path, "port": 8443, "scheme": "HTTPS"}
file.write_text(json.dumps(manifest, indent=2) + "\n")
subprocess.run(K + ["apply", "-f", str(file)], check=True)
subprocess.run(K + ["-n", ns, "rollout", "status", "deployment/api", "--timeout=180s"], check=True)
for _ in range(18):
    time.sleep(10)
    s = snapshot()
    print(
        json.dumps({"event": "waiting_metrics_after_probe_change", "sample": s}),
        flush=True,
    )
    if s["pods"] == 1 and s["cpu_cores"] < 0.05:
        break
for _ in range(3):
    report["after"].append(snapshot())
    time.sleep(15)
report["averages"] = {
    stage: {
        key: sum(v[key] for v in report[stage]) / len(report[stage])
        for key in ["pods", "cpu_cores", "memory_bytes"]
    }
    for stage in ["before", "after"]
}
report["energy_measured"] = False
report["cloud_bill_saved_measured"] = False
target.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report["averages"]))
