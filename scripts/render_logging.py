"""Logs centralisés : Loki (HTTPS, rétention 72 h) et Grafana Alloy qui lit les logs des pods bc3-test.

Alloy passe par l'API Kubernetes (pods/log), sans montage de répertoire hôte.
"""

import hashlib
import json
import runpy
from pathlib import Path

r = Path(__file__).resolve().parents[1]
ns = runpy.run_path(str(r / "scripts/render_manifests.py"))
obj, save, container, workload, mount, resources = (
    ns[k] for k in ["obj", "save", "container", "workload", "mount", "resources"]
)
NS = "bc3-test"
LOKI_IMAGE = (
    "grafana/loki:3.5.5@sha256:31628519045e7f28692a7ae73b4a3fd293dccb425585ed5d16ceea3b5c9592e6"
)
ALLOY_IMAGE = (
    "grafana/alloy:v1.10.2@sha256:bcf27f18c4402869af112fb39e35e1db3804a404686f4caa20bdf77814219223"
)

loki_config = {
    "auth_enabled": False,
    "server": {
        "http_listen_port": 3100,
        "grpc_listen_port": 9095,
        "http_tls_config": {
            "cert_file": "/run/server/server.crt",
            "key_file": "/run/server/server.key",
        },
        "log_level": "warn",
    },
    "common": {
        "instance_addr": "127.0.0.1",
        "path_prefix": "/loki",
        "storage": {
            "filesystem": {"chunks_directory": "/loki/chunks", "rules_directory": "/loki/rules"}
        },
        "replication_factor": 1,
        "ring": {"kvstore": {"store": "inmemory"}},
    },
    "schema_config": {
        "configs": [
            {
                "from": "2024-01-01",
                "store": "tsdb",
                "object_store": "filesystem",
                "schema": "v13",
                "index": {"prefix": "index_", "period": "24h"},
            }
        ]
    },
    "limits_config": {"retention_period": "72h"},
    "compactor": {
        "working_directory": "/loki/compactor",
        "retention_enabled": True,
        "delete_request_store": "filesystem",
    },
    "analytics": {"reporting_enabled": False},
}
alloy_config = """
discovery.kubernetes "pods" {
  role = "pod"
  namespaces {
    names = ["bc3-test"]
  }
}
discovery.relabel "bc3" {
  targets = discovery.kubernetes.pods.targets
  rule {
    source_labels = ["__meta_kubernetes_namespace"]
    target_label  = "namespace"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_label_app"]
    target_label  = "app"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_name"]
    target_label  = "pod"
  }
  rule {
    source_labels = ["__meta_kubernetes_pod_container_name"]
    target_label  = "container"
  }
}
loki.source.kubernetes "pods" {
  targets    = discovery.relabel.bc3.output
  forward_to = [loki.write.local.receiver]
}
loki.write "local" {
  endpoint {
    url = "https://loki:3100/loki/api/v1/push"
    tls_config {
      ca_file     = "/run/trust/ca.crt"
      server_name = "loki"
    }
  }
}
"""

items = [
    obj(
        "PersistentVolumeClaim",
        "loki",
        {"spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "1Gi"}}}},
    ),
    obj("ServiceAccount", "logs", {}),
    obj(
        "Role",
        "logs-read-pods",
        {
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["pods", "pods/log"],
                    "verbs": ["get", "list", "watch"],
                }
            ]
        },
        "rbac.authorization.k8s.io/v1",
    ),
    obj(
        "RoleBinding",
        "logs-read-pods",
        {
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "logs-read-pods",
            },
            "subjects": [{"kind": "ServiceAccount", "name": "logs", "namespace": NS}],
        },
        "rbac.authorization.k8s.io/v1",
    ),
    obj("ConfigMap", "loki", {"data": {"loki.yml": json.dumps(loki_config)}}),
    obj("ConfigMap", "alloy", {"data": {"config.alloy": alloy_config.strip() + "\n"}}),
    obj(
        "Service",
        "loki",
        {
            "spec": {
                "selector": {"app": "loki"},
                "ports": [{"name": "https", "port": 3100, "targetPort": 3100}],
            }
        },
    ),
]

c = container("loki", LOKI_IMAGE, [3100])
c["args"] = ["-config.file=/etc/loki/loki.yml"]
c["resources"] = resources("50m", "128Mi", "512Mi")
c["volumeMounts"] += [
    mount("config", "/etc/loki"),
    mount("tls", "/run/server"),
    {"name": "data", "mountPath": "/loki"},
]
c["readinessProbe"] = {
    "httpGet": {"path": "/ready", "port": 3100, "scheme": "HTTPS"},
    "periodSeconds": 5,
    "initialDelaySeconds": 10,
}
items.append(
    workload(
        "loki",
        [c],
        [
            {"name": "config", "configMap": {"name": "loki"}},
            {"name": "data", "persistentVolumeClaim": {"claimName": "loki"}},
            ns["vol_secret"]("tls", "loki-tls"),
        ],
    )
)

c = container("alloy", ALLOY_IMAGE)
c["args"] = [
    "run",
    "/etc/alloy/config.alloy",
    "--storage.path=/tmp/alloy",
    "--server.http.listen-addr=127.0.0.1:12345",
    "--disable-reporting",
]
c["resources"] = resources("25m", "64Mi", "256Mi")
c["volumeMounts"] += [mount("config", "/etc/alloy"), mount("trust", "/run/trust")]
w = workload(
    "alloy",
    [c],
    [
        {"name": "config", "configMap": {"name": "alloy"}},
        {"name": "trust", "configMap": {"name": "trust"}},
    ],
)
w["spec"]["template"]["spec"]["serviceAccountName"] = "logs"
w["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
items.append(w)

for entry in items:
    if entry["kind"] == "Deployment":
        entry["spec"]["strategy"] = {"type": "Recreate"}
        entry["spec"]["template"]["metadata"]["annotations"] = {
            "checksum/config": hashlib.sha256(
                json.dumps([v for v in items if v["kind"] == "ConfigMap"], sort_keys=True).encode()
            ).hexdigest()
        }
save("55-logging.json", items)
print("Configuration de journalisation générée")
