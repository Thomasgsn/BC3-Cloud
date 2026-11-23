"""Configurer le chiffrement des Secrets du seul cluster kind BC3, avant déploiement."""

import base64
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

root = Path("/workspace")
cluster = os.getenv("BC3_KIND_CLUSTER", "rncp-bc3")
node = cluster + "-control-plane"
context = "kind-" + cluster
file = root / ("secrets/" + cluster + "-encryption-config.json")
legacy = root / "secrets/encryption-config.json"
if cluster == "rncp-bc3" and legacy.exists() and not file.exists():
    file.write_bytes(legacy.read_bytes())
    file.chmod(0o600)
if not file.exists():
    file.write_text(
        json.dumps(
            {
                "apiVersion": "apiserver.config.k8s.io/v1",
                "kind": "EncryptionConfiguration",
                "resources": [
                    {
                        "resources": ["secrets"],
                        "providers": [
                            {
                                "aesgcm": {
                                    "keys": [
                                        {
                                            "name": "bc3-local-v1",
                                            "secret": base64.b64encode(
                                                secrets.token_bytes(32)
                                            ).decode(),
                                        }
                                    ]
                                }
                            },
                            {"identity": {}},
                        ],
                    }
                ],
            }
        )
    )
    file.chmod(0o600)
subprocess.run(
    ["docker", "cp", str(file), node + ":/etc/kubernetes/pki/encryption-config.json"],
    check=True,
    capture_output=True,
)
p = "/etc/kubernetes/manifests/kube-apiserver.yaml"
original = subprocess.check_output(["docker", "exec", node, "cat", p]).decode()
flag = "--encryption-provider-config=/etc/kubernetes/pki/encryption-config.json"
if flag not in original:
    (root / ("secrets/" + cluster + "-kube-apiserver-original.yml")).write_text(original)
    changed = original.replace(
        "    - kube-apiserver\n", "    - kube-apiserver\n    - " + flag + "\n"
    )
    if changed == original:
        raise ValueError("Format du manifeste apiserver inattendu, pas de modification")
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            node,
            "sh",
            "-c",
            "cat > /etc/kubernetes/manifests/kube-apiserver.yaml",
        ],
        input=changed.encode(),
        check=True,
    )
for _ in range(45):
    r = subprocess.run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            "kube-system",
            "get",
            "pod",
            "kube-apiserver-" + node,
            "-o",
            "json",
        ],
        capture_output=True,
        check=False,
    )
    if r.returncode == 0:
        pod = json.loads(r.stdout)
        ready = any(v.get("ready") for v in pod.get("status", {}).get("containerStatuses", []))
        if flag in pod["spec"]["containers"][0]["command"] and ready:
            break
    time.sleep(2)
else:
    raise RuntimeError("API Kubernetes non prête après configuration du chiffrement")
print(
    json.dumps(
        {
            "event": "etcd_encryption_configured",
            "cluster": context,
            "provider": "AES-GCM",
            "key_printed": False,
            "other_clusters_modified": False,
            "raw_etcd_proof": "To verify after runtime Secret creation",
        }
    )
)
