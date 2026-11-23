"""Prometheus/Grafana : données réelles, SLO de projet, logs Loki et alertes sans email."""

import hashlib
import json
import runpy
from pathlib import Path

r = Path(__file__).resolve().parents[1]
ns = runpy.run_path(str(r / "scripts/render_manifests.py"))
obj, save, container, workload, mount, resources = (
    ns[k] for k in ["obj", "save", "container", "workload", "mount", "resources"]
)
items = []
for name in ["prometheus", "grafana"]:
    items.append(
        obj(
            "PersistentVolumeClaim",
            name,
            {
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                }
            },
        )
    )
items += [
    obj("ServiceAccount", "monitor", {}),
    obj(
        "Role",
        "monitor-pods",
        {
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "watch"],
                }
            ]
        },
        "rbac.authorization.k8s.io/v1",
    ),
    obj(
        "RoleBinding",
        "monitor-pods",
        {
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "monitor-pods",
            },
            "subjects": [{"kind": "ServiceAccount", "name": "monitor", "namespace": "bc3-test"}],
        },
        "rbac.authorization.k8s.io/v1",
    ),
]
config = {
    "global": {"scrape_interval": "5s", "evaluation_interval": "5s"},
    "rule_files": ["/etc/prometheus/rules.yml"],
    "scrape_configs": [],
}
for app, port in [("api", 8443), ("worker", 9091)]:
    job = {
        "job_name": "bc3-" + app,
        "kubernetes_sd_configs": [{"role": "pod", "namespaces": {"names": ["bc3-test"]}}],
        "relabel_configs": [
            {
                "source_labels": ["__meta_kubernetes_pod_label_app"],
                "regex": app,
                "action": "keep",
            },
            {
                "source_labels": ["__meta_kubernetes_pod_container_port_number"],
                "regex": str(port),
                "action": "keep",
            },
            {"source_labels": ["__meta_kubernetes_pod_name"], "target_label": "pod"},
        ],
    }
    job.update(scheme="https", tls_config={"ca_file": "/run/trust/ca.crt", "server_name": app})
    config["scrape_configs"].append(job)
rules = {
    "groups": [
        {
            "name": "bc3-slo",
            "rules": [
                {
                    "alert": "APIUnavailable",
                    "expr": 'absent(up{job="bc3-api"}) or (sum(up{job="bc3-api"}) == 0)',
                    "for": "15s",
                    "labels": {"severity": "critical"},
                    "annotations": {"summary": "Aucune instance API ne répond au monitoring"},
                },
                {
                    "alert": "APIErrorBudget",
                    "expr": 'sum(rate(bc3_http_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(bc3_http_requests_total[1m])),0.001) > 0.01',
                    "for": "15s",
                    "labels": {"severity": "warning"},
                    "annotations": {
                        "summary": "Les réponses 5xx dépassent le budget de disponibilité de projet"
                    },
                },
                {
                    "alert": "ExportBacklog",
                    "expr": "bc3_worker_oldest_pending_seconds > 60",
                    "for": "15s",
                    "labels": {"severity": "warning"},
                    "annotations": {"summary": "Un export attend depuis plus d’une minute"},
                },
            ],
        }
    ]
}
items.append(
    obj(
        "ConfigMap",
        "prometheus",
        {
            "data": {
                "prometheus.yml": json.dumps(config),
                "rules.yml": json.dumps(rules),
                "web.yml": json.dumps(
                    {
                        "tls_server_config": {
                            "cert_file": "/run/server/server.crt",
                            "key_file": "/run/server/server.key",
                        }
                    }
                ),
            }
        },
    )
)
panels = []
queries = [
    (
        "Disponibilité logique sur 2 minutes",
        '1 - (sum(rate(bc3_http_requests_total{status=~"5.."}[2m])) / clamp_min(sum(rate(bc3_http_requests_total[2m])),0.001))',
    ),
    (
        "Latence API p95 (secondes)",
        "histogram_quantile(0.95,sum by(le)(rate(bc3_http_duration_seconds_bucket[2m])))",
    ),
    ("Requêtes par seconde", "sum(rate(bc3_http_requests_total[2m]))"),
    ("Âge maximal des exports (secondes)", "max(bc3_worker_oldest_pending_seconds)"),
    ("Jobs terminés ou repris", "sum by(result)(bc3_worker_jobs_total)"),
    (
        "CPU des processus applicatifs",
        "sum by(job)(rate(process_cpu_seconds_total[2m]))",
    ),
]
for i, (title, expr) in enumerate(queries):
    panels.append(
        {
            "id": i + 1,
            "type": "timeseries",
            "title": title,
            "datasource": {"type": "prometheus", "uid": "bc3-prometheus"},
            "targets": [{"expr": expr, "refId": "A"}],
            "gridPos": {"x": (i % 2) * 12, "y": (i // 2) * 8, "w": 12, "h": 8},
        }
    )
panels.append(
    {
        "id": len(panels) + 1,
        "type": "logs",
        "title": "Logs API et worker (Loki)",
        "datasource": {"type": "loki", "uid": "bc3-loki"},
        "targets": [{"expr": '{namespace="bc3-test", app=~"api|worker"}', "refId": "A"}],
        "gridPos": {"x": 0, "y": 24, "w": 24, "h": 10},
    }
)
dashboard = {
    "uid": "bc3-operations",
    "title": "BC3 · Exploitation et SLO",
    "schemaVersion": 39,
    "version": 1,
    "refresh": "5s",
    "time": {"from": "now-15m", "to": "now"},
    "tags": ["BC3", "local"],
    "panels": panels,
}
items.append(
    obj(
        "ConfigMap",
        "grafana-provisioning",
        {
            "data": {
                "datasource.yml": json.dumps(
                    {
                        "apiVersion": 1,
                        "datasources": [
                            {
                                "name": "BC3 Prometheus",
                                "uid": "bc3-prometheus",
                                "type": "prometheus",
                                "access": "proxy",
                                "url": "https://prometheus:9090",
                                "isDefault": True,
                                "jsonData": {"tlsAuthWithCACert": True},
                                "secureJsonData": {"tlsCACert": (r / "secrets/ca.crt").read_text()},
                            },
                            {
                                "name": "BC3 Loki",
                                "uid": "bc3-loki",
                                "type": "loki",
                                "access": "proxy",
                                "url": "https://loki:3100",
                                "jsonData": {"tlsAuthWithCACert": True, "serverName": "loki"},
                                "secureJsonData": {"tlsCACert": (r / "secrets/ca.crt").read_text()},
                            },
                        ],
                    }
                ),
                "dashboard-provider.yml": json.dumps(
                    {
                        "apiVersion": 1,
                        "providers": [
                            {
                                "name": "BC3",
                                "type": "file",
                                "disableDeletion": True,
                                "options": {"path": "/var/lib/grafana/dashboards"},
                            }
                        ],
                    }
                ),
                "operations.json": json.dumps(dashboard),
            }
        },
    )
)
c = container(
    "prometheus",
    "prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06",
    [9090],
)
c["args"] = [
    "--config.file=/etc/prometheus/prometheus.yml",
    "--web.config.file=/etc/prometheus/web.yml",
    "--storage.tsdb.path=/prometheus",
    "--storage.tsdb.retention.time=6h",
    "--storage.tsdb.retention.size=128MB",
]
c["resources"] = resources("50m", "128Mi", "512Mi")
c["volumeMounts"] += [
    mount("config", "/etc/prometheus"),
    mount("trust", "/run/trust"),
    mount("tls", "/run/server"),
    {"name": "data", "mountPath": "/prometheus"},
]
c["readinessProbe"] = {
    "httpGet": {"path": "/-/ready", "port": 9090, "scheme": "HTTPS"},
    "periodSeconds": 5,
}
w = workload(
    "prometheus",
    [c],
    [
        {"name": "config", "configMap": {"name": "prometheus"}},
        {"name": "trust", "configMap": {"name": "trust"}},
        {"name": "data", "persistentVolumeClaim": {"claimName": "prometheus"}},
        ns["vol_secret"]("tls", "prometheus-tls"),
    ],
    uid=65534,
)
w["spec"]["template"]["spec"]["serviceAccountName"] = "monitor"
w["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
items.append(w)
for name, port in [("prometheus", 9090), ("grafana", 3000)]:
    items.append(
        obj(
            "Service",
            name,
            {
                "spec": {
                    "selector": {"app": name},
                    "ports": [{"name": "http", "port": port, "targetPort": port}],
                }
            },
        )
    )
c = container(
    "grafana",
    "grafana/grafana:13.3.1@sha256:0615ec4fbd4072004b7d86b46ded63013a74b7d6eb1119273dd89e8fa25c13cf",
    [3000],
)
c["resources"] = resources("50m", "128Mi", "512Mi")
c["env"] = [
    {"name": k, "value": v}
    for k, v in {
        "GF_SECURITY_ADMIN_USER": "thomas",
        "GF_SECURITY_ADMIN_PASSWORD__FILE": "/run/grafana-secrets/admin_password",
        "GF_USERS_ALLOW_SIGN_UP": "false",
        "GF_ANALYTICS_REPORTING_ENABLED": "false",
        "GF_ANALYTICS_CHECK_FOR_UPDATES": "false",
        "GF_SMTP_ENABLED": "false",
        "GF_SERVER_PROTOCOL": "https",
        "GF_SERVER_CERT_FILE": "/run/grafana-secrets/server.crt",
        "GF_SERVER_CERT_KEY": "/run/grafana-secrets/server.key",
    }.items()
]
c["volumeMounts"] += [
    {"name": "data", "mountPath": "/var/lib/grafana"},
    mount("password", "/run/grafana-secrets"),
    {
        "name": "provisioning",
        "mountPath": "/etc/grafana/provisioning/datasources/bc3.yml",
        "subPath": "datasource.yml",
        "readOnly": True,
    },
    {
        "name": "provisioning",
        "mountPath": "/etc/grafana/provisioning/dashboards/bc3.yml",
        "subPath": "dashboard-provider.yml",
        "readOnly": True,
    },
    {
        "name": "provisioning",
        "mountPath": "/var/lib/grafana/dashboards/operations.json",
        "subPath": "operations.json",
        "readOnly": True,
    },
]
c["readinessProbe"] = {
    "httpGet": {"path": "/api/health", "port": 3000, "scheme": "HTTPS"},
    "periodSeconds": 5,
    "initialDelaySeconds": 10,
}
items.append(
    workload(
        "grafana",
        [c],
        [
            {"name": "data", "persistentVolumeClaim": {"claimName": "grafana"}},
            ns["vol_secret"]("password", "grafana-password"),
            {"name": "provisioning", "configMap": {"name": "grafana-provisioning"}},
        ],
        uid=472,
    )
)

for entry in items:
    if entry["kind"] == "Deployment":
        entry["spec"]["strategy"] = {"type": "Recreate"}
        entry["spec"]["template"]["metadata"]["annotations"] = {
            "checksum/config": hashlib.sha256(
                json.dumps([v for v in items if v["kind"] == "ConfigMap"], sort_keys=True).encode()
            ).hexdigest()
        }
save("50-observability.json", items)
(r / "docs/evidence/k8s/monitoring-design.json").write_text(
    json.dumps(
        {
            "project_slos": {"availability": 0.99, "p95_read_seconds": 0.5},
            "window": "Measured test window and rolling 2m dashboard, not a monthly SLA",
            "energy_measured": False,
            "email_enabled": False,
        },
        indent=2,
    )
    + "\n"
)
print("Configuration observabilité générée")
