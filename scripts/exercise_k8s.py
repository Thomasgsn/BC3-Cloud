"""Charge, HPA, suppression d’un pod de test, échec de config et rollback contrôlés."""

import copy
import json
import subprocess
import time
import uuid
from pathlib import Path

K = ["kubectl", "--context", "kind-rncp-bc3", "-n", "bc3-test"]
out = Path("docs/evidence/k8s")
out.mkdir(exist_ok=True)


def get(kind, name=None):
    return json.loads(
        subprocess.check_output(K + ["get", kind] + ([name] if name else []) + ["-o", "json"])
    )


def pods():
    return [
        p
        for p in get("pods")["items"]
        if p["metadata"]["labels"].get("app") == "api"
        and not p["metadata"].get("deletionTimestamp")
    ]


def ready(p):
    return any(c.get("ready") for c in p["status"].get("containerStatuses", []))


# Pilote de charge séparé : le worker optimisé ne dépend ni de HTTPX ni d’Argon2.
for _ in range(30):
    if (
        get("hpa", "api").get("status", {}).get("currentReplicas") == 1
        and sum(ready(p) for p in pods()) == 1
    ):
        break
    time.sleep(5)
else:
    raise RuntimeError("Le HPA ne revient pas au repos, charge non lancée")
worker = "load-driver-" + uuid.uuid4().hex[:8]
template = copy.deepcopy(get("deployment", "worker")["spec"]["template"])
container = template["spec"]["containers"][0]
container["image"] = get("deployment", "api")["spec"]["template"]["spec"]["containers"][0]["image"]
container["command"] = ["sh", "-c", "sleep 600"]
container.pop("livenessProbe", None)
container.pop("readinessProbe", None)
container["resources"] = {
    "requests": {"cpu": "100m", "memory": "128Mi"},
    "limits": {"cpu": "2", "memory": "512Mi"},
}
pod = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
        "name": worker,
        "namespace": "bc3-test",
        "labels": {"app": "load-driver", "project": "rncp-bc3"},
    },
    "spec": template["spec"],
}
pod["spec"]["restartPolicy"] = "Never"
subprocess.run(K + ["apply", "-f", "-"], input=json.dumps(pod), text=True, check=True)
subprocess.run(K + ["wait", "--for=condition=Ready", "pod/" + worker, "--timeout=120s"], check=True)
baseline = get("deployment", "api")
revision = baseline["metadata"]["annotations"]["deployment.kubernetes.io/revision"]
report = {
    "cluster": "kind-rncp-bc3",
    "baseline_revision": revision,
    "api_image": baseline["spec"]["template"]["spec"]["containers"][0]["image"],
    "load_driver_image": container["image"],
    "samples": [],
    "events": [],
}
subprocess.run(
    [
        "kubectl",
        "--context",
        "kind-rncp-bc3",
        "cp",
        "tests/integration/load_api.py",
        "bc3-test/" + worker + ":/tmp/load_api.py",
    ],
    check=True,
)
process = subprocess.Popen(K + ["exec", worker, "--", "python", "/tmp/load_api.py"])
deleted = False
injected = False
restored = False
rolled = False
deleted_at = None
candidate_at = None
start = time.monotonic()
try:
    while process.poll() is None:
        hpa = get("hpa", "api")
        current = pods()
        sample = {
            "seconds": time.monotonic() - start,
            "hpa_current": hpa.get("status", {}).get("currentReplicas"),
            "hpa_desired": hpa.get("status", {}).get("desiredReplicas"),
            "ready_api": sum(ready(p) for p in current),
        }
        report["samples"].append(sample)
        print(json.dumps({"event": "hpa_sample", **sample}), flush=True)
        if not deleted and sample["ready_api"] >= 2:
            victim = next(p for p in current if ready(p))
            subprocess.run(
                K + ["delete", "pod", victim["metadata"]["name"], "--wait=false"],
                check=True,
            )
            deleted_at = time.monotonic()
            deleted = True
            report["events"].append(
                {
                    "kind": "pod_deleted",
                    "pod_uid": victim["metadata"]["uid"],
                    "seconds": sample["seconds"],
                }
            )
        elif (
            deleted
            and not injected
            and sum(ready(p) for p in current) >= hpa.get("status", {}).get("desiredReplicas", 3)
            and time.monotonic() - deleted_at > 5
        ):
            report["pod_recovery_seconds"] = time.monotonic() - deleted_at
            subprocess.run(
                K
                + [
                    "set",
                    "env",
                    "deployment/api",
                    "BC3_SECRET_DIR=/run/invalid-controlled-test",
                ],
                check=True,
            )
            candidate_at = time.monotonic()
            injected = True
            report["events"].append(
                {"kind": "invalid_configuration_deployed", "seconds": sample["seconds"]}
            )
        elif injected and not restored and time.monotonic() - candidate_at >= 15:
            report["healthy_replicas_during_rejected_candidate"] = sum(ready(p) for p in current)
            subprocess.run(
                K + ["rollout", "undo", "deployment/api", "--to-revision=" + revision],
                check=True,
            )
            subprocess.run(
                K + ["rollout", "status", "deployment/api", "--timeout=120s"],
                check=True,
            )
            restored = True
            report["events"].append(
                {"kind": "configuration_rollback", "seconds": time.monotonic() - start}
            )
        elif restored and not rolled:
            subprocess.run(K + ["rollout", "restart", "deployment/api"], check=True)
            subprocess.run(
                K + ["rollout", "status", "deployment/api", "--timeout=120s"],
                check=True,
            )
            rolled = True
            report["events"].append(
                {
                    "kind": "successful_rolling_restart",
                    "seconds": time.monotonic() - start,
                }
            )
        time.sleep(10)
    code = process.wait()
    assert code == 0, code
    subprocess.run(
        [
            "kubectl",
            "--context",
            "kind-rncp-bc3",
            "cp",
            "bc3-test/" + worker + ":/tmp/load-result.json",
            str(out / "load-result.json"),
        ],
        check=True,
    )
    report.update(
        {
            "pod_fault_exercised": deleted,
            "bad_configuration_rolled_back": restored,
            "rolling_restart_completed": rolled,
            "max_hpa_current": max(s["hpa_current"] or 0 for s in report["samples"]),
            "qualification": "Configuration rollback is real; earlier image v1→v2 upgrade separately executed. No binary rollback is falsely claimed.",
        }
    )
    (out / "resilience-load.json").write_text(json.dumps(report, indent=2) + "\n")
    assert deleted and restored and rolled and report["max_hpa_current"] >= 2
finally:
    subprocess.run(K + ["delete", "pod", worker, "--wait=false"], check=False)
    if injected and not restored:
        subprocess.run(
            K + ["rollout", "undo", "deployment/api", "--to-revision=" + revision],
            check=False,
        )
