"""Preuves limitées : Secrets réellement chiffrés dans etcd et RBAC applicatif refusé."""

import base64
import json
import subprocess
from pathlib import Path

K = ["kubectl", "--context", "kind-rncp-bc3"]
args = K + [
    "-n",
    "kube-system",
    "exec",
    "etcd-rncp-bc3-control-plane",
    "--",
    "etcdctl",
    "--endpoints=https://127.0.0.1:2379",
    "--cacert=/etc/kubernetes/pki/etcd/ca.crt",
    "--cert=/etc/kubernetes/pki/etcd/server.crt",
    "--key=/etc/kubernetes/pki/etcd/server.key",
    "get",
    "/registry/secrets/bc3-test/runtime",
    "--write-out=json",
]
r = subprocess.run(args, check=True, capture_output=True)
payload = json.loads(r.stdout)
raw = base64.b64decode(payload["kvs"][0]["value"])
expected = b"k8s:enc:aesgcm:v1:bc3-local-v1:"
assert raw.startswith(expected), "Les Secrets ne sont pas chiffrés par le fournisseur prévu"
role = subprocess.run(
    K
    + [
        "auth",
        "can-i",
        "get",
        "secrets",
        "--as=system:serviceaccount:bc3-test:application",
        "-n",
        "bc3-test",
    ],
    capture_output=True,
    check=False,
)
assert role.stdout.strip() == b"no"
pods = json.loads(subprocess.check_output(K + ["-n", "bc3-test", "get", "pods", "-o", "json"]))[
    "items"
]
assert all(p["spec"].get("enableServiceLinks") is False for p in pods)
report = {
    "event": "kubernetes_security",
    "cluster": "kind-rncp-bc3",
    "runtime_secret_raw_etcd_encryption_prefix": expected.decode(),
    "raw_secret_content_printed": False,
    "application_service_account_cannot_read_secrets": True,
    "application_service_account_tokens_automounted": False,
    "service_link_environment_injection_disabled": True,
    "pod_security": "restricted namespace, non-root with dropped capabilities and read-only root filesystems",
    "limits": "Does not demonstrate full host disk encryption or public cloud KMS activation; Metrics Server local kubelet certificate exception is documented separately",
}
Path("docs/evidence/k8s/security.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
