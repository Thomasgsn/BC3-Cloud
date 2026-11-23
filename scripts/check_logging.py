"""Vérifie la chaîne de logs réelle : Alloy → Loki (HTTPS) → Grafana, sans contenu métier exporté."""

import base64
import json
import socket
import ssl
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/workspace")
K = ["kubectl", "--context", "kind-rncp-bc3", "-n", "bc3-test"]


def forward(service, local, remote):
    process = subprocess.Popen(
        [*K, "port-forward", f"svc/{service}", f"{local}:{remote}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", local), timeout=1):
                return process
        except OSError:
            time.sleep(1)
    process.terminate()
    raise RuntimeError("Port-forward indisponible : " + service)


def get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    context = ssl.create_default_context(cafile=str(ROOT / "secrets/ca.crt"))
    context.check_hostname = True
    with urllib.request.urlopen(request, context=context, timeout=15) as response:
        return json.loads(response.read())


def main():
    report = {}
    loki = forward("loki", 13100, 3100)
    try:
        now = time.time_ns()
        found = {}
        for app in ["api", "worker", "front"]:
            query = urllib.parse.urlencode(
                {
                    "query": f'{{namespace="bc3-test", app="{app}"}}',
                    "start": now - 3600 * 10**9,
                    "end": now,
                    "limit": 5000,
                }
            )
            for _ in range(12):
                body = get(f"https://localhost:13100/loki/api/v1/query_range?{query}")
                lines = sum(len(s["values"]) for s in body["data"]["result"])
                if lines:
                    break
                time.sleep(5)
            found[app] = {
                "streams": len(body["data"]["result"]),
                "lines": lines,
                "labels": sorted({k for s in body["data"]["result"] for k in s["stream"]}),
            }
        report["loki_lines_last_hour"] = found
    finally:
        loki.terminate()
    grafana = forward("grafana", 13000, 3000)
    try:
        token = base64.b64encode(
            b"thomas:" + (ROOT / "secrets/grafana_password").read_text().strip().encode()
        ).decode()
        health = get(
            "https://localhost:13000/api/datasources/uid/bc3-loki/health",
            {"Authorization": "Basic " + token},
        )
        report["grafana_loki_datasource"] = {
            "status": health.get("status"),
            "message": health.get("message"),
        }
    finally:
        grafana.terminate()
    report["checks"] = {
        "api_logs_collected": found["api"]["lines"] > 0,
        "worker_logs_collected": found["worker"]["lines"] > 0,
        "grafana_reads_loki": report["grafana_loki_datasource"]["status"] == "OK",
    }
    out = ROOT / "docs/evidence/k8s/logging.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"event": "logging_checked", **report["checks"]}))
    if not all(report["checks"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
