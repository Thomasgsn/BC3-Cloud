"""Vérifie un environnement promu : santé TLS, secrets distincts, RBAC et isolation réseau réelle."""

import argparse
import hashlib
import json
import socket
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path("/workspace")
K = ["kubectl", "--context", "kind-rncp-bc3"]
PROBE = (
    "import socket,sys\n"
    "s=socket.socket();s.settimeout(5)\n"
    "try:\n s.connect((sys.argv[1],int(sys.argv[2])));print('open')\n"
    "except OSError as e:print('blocked:'+type(e).__name__)\n"
)


def run(*args):
    return subprocess.run([*K, *args], capture_output=True, text=True, timeout=120, check=False)


def probe(namespace, host, port):
    """Connexion TCP depuis un pod API réel du namespace source, sans outil ajouté à l'image."""
    result = run(
        "-n", namespace, "exec", "deploy/api", "--", "python", "-c", PROBE, host, str(port)
    )
    return result.stdout.strip() or "error:" + result.stderr.strip()[-200:]


def health(namespace, ca):
    forward = subprocess.Popen(
        [*K, "-n", namespace, "port-forward", "svc/api", "18443:8443"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        context = ssl.create_default_context(cafile=ca)
        for _ in range(30):
            try:
                with socket.create_connection(("127.0.0.1", 18443), timeout=1):
                    break
            except OSError:
                time.sleep(1)
        request = urllib.request.Request("https://localhost:18443/health/ready")
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            return {"status": response.status, "body": json.loads(response.read())}
    finally:
        forward.terminate()
        forward.wait(10)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--ca", required=True)
    args = parser.parse_args()
    ns = args.namespace
    report = {
        "namespace": ns,
        "health_with_environment_ca": health(ns, ROOT / args.ca),
        "environment_ca_differs_from_test": digest(ROOT / args.ca)
        != digest(ROOT / "secrets/ca.crt"),
        "same_namespace_api_to_db": probe(ns, "db", 5432),
        "test_namespace_to_own_api": probe("bc3-test", "api", 8443),
        "test_namespace_to_this_api": probe("bc3-test", f"api.{ns}.svc.cluster.local", 8443),
        "test_namespace_to_this_db": probe("bc3-test", f"db.{ns}.svc.cluster.local", 5432),
        "rbac_test_app_can_read_these_secrets": run(
            "auth",
            "can-i",
            "get",
            "secrets",
            "-n",
            ns,
            "--as",
            "system:serviceaccount:bc3-test:application",
        ).stdout.strip(),
        "rbac_own_app_can_read_secrets": run(
            "auth",
            "can-i",
            "get",
            "secrets",
            "-n",
            ns,
            "--as",
            f"system:serviceaccount:{ns}:application",
        ).stdout.strip(),
        "images": sorted(
            {
                c["image"]
                for p in json.loads(run("-n", ns, "get", "pods", "-o", "json").stdout)["items"]
                for c in p["spec"]["containers"]
            }
        ),
    }
    checks = {
        "healthy": report["health_with_environment_ca"]["status"] == 200,
        "distinct_secrets": report["environment_ca_differs_from_test"],
        "same_namespace_allowed": report["same_namespace_api_to_db"] == "open",
        "test_baseline_open": report["test_namespace_to_own_api"] == "open",
        "cross_namespace_blocked": report["test_namespace_to_this_api"].startswith("blocked")
        and report["test_namespace_to_this_db"].startswith("blocked"),
        "rbac_denied": report["rbac_test_app_can_read_these_secrets"] == "no"
        and report["rbac_own_app_can_read_secrets"] == "no",
    }
    report["checks"] = checks
    out = ROOT / "docs/evidence/environments"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{ns}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"event": "environment_checked", "namespace": ns, "checks": checks}))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
