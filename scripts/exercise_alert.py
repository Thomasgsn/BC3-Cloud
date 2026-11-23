"""Panne contrôlée API locale : alerte firing puis résolue, restauration finally."""

import json
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

K = ["kubectl", "--context", "kind-rncp-bc3", "-n", "bc3-test"]


def run(*args):
    return subprocess.check_output(K + list(args), text=True)


baseline = json.loads(run("get", "deployment", "api", "-o", "json"))["spec"]["replicas"]
pf = subprocess.Popen(
    K + ["port-forward", "service/prometheus", "19090:9090"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
context = ssl.create_default_context(cafile="secrets/ca.crt")
events = []
start = time.monotonic()


def alerts():
    with urllib.request.urlopen(
        "https://localhost:19090/api/v1/alerts", context=context, timeout=5
    ) as r:
        return json.load(r)["data"]["alerts"]


def await_state(firing, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        found = [
            a
            for a in alerts()
            if a["labels"]["alertname"] == "APIUnavailable" and a["state"] == "firing"
        ]
        if bool(found) == firing:
            return found
        time.sleep(3)
    raise TimeoutError("État alerte attendu non atteint")


try:
    for _ in range(20):
        try:
            alerts()
            break
        except (OSError, ValueError):
            time.sleep(1)
    await_state(False, 30)
    start = time.monotonic()
    run("scale", "deployment/api", "--replicas=0")
    fired = await_state(True, 100)
    events.append(
        {
            "event": "APIUnavailable_firing",
            "seconds_since_scale": time.monotonic() - start,
            "alerts": fired,
        }
    )
finally:
    run("scale", "deployment/api", "--replicas=" + str(max(1, baseline)))
    run("rollout", "status", "deployment/api", "--timeout=120s")
    try:
        await_state(False, 90)
        events.append(
            {
                "event": "APIUnavailable_resolved",
                "seconds_since_scale": time.monotonic() - start,
            }
        )
        Path("docs/evidence/k8s/alert-cycle.json").write_text(
            json.dumps(
                {
                    "events": events,
                    "tls_verified": True,
                    "notification_email": False,
                    "fault": "Own local API deployment scaled to zero, then restored",
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        pf.terminate()
        pf.wait(timeout=10)
assert any(e["event"] == "APIUnavailable_firing" for e in events)
print(json.dumps({"alert_cycle": "firing_then_resolved", "events": len(events)}))
