"""Manifests Kubernetes standards, sans secrets ni accès à un cluster existant."""

import copy
import hashlib
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
OUT = R / "infra/kubernetes"
NS = "bc3-test"


def meta(name):
    return {"name": name, "namespace": NS, "labels": {"project": "rncp-bc3"}}


def obj(kind, name, spec, api="v1"):
    return {"apiVersion": api, "kind": kind, "metadata": meta(name), **spec}


def save(name, items):
    (OUT / name).write_text(
        json.dumps({"apiVersion": "v1", "kind": "List", "items": items}, indent=2) + "\n"
    )


def vol_secret(name, secret, items=None):
    d = {"secretName": secret, "defaultMode": 0o440}
    if items:
        d["items"] = [{"key": k, "path": v} for k, v in items.items()]
    return {"name": name, "secret": d}


def mount(name, path):
    return {"name": name, "mountPath": path, "readOnly": True}


def resources(cpu="50m", memory="128Mi", limit="512Mi"):
    return {
        "requests": {"cpu": cpu, "memory": memory},
        "limits": {"cpu": "2", "memory": limit},
    }


restricted = {
    "allowPrivilegeEscalation": False,
    "readOnlyRootFilesystem": True,
    "capabilities": {"drop": ["ALL"]},
}


def container(name, image, ports=None):
    d = {
        "name": name,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "resources": resources(),
        "securityContext": restricted,
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
    }
    if ports:
        d["ports"] = [{"containerPort": p} for p in ports]
    return d


def workload(name, containers, volumes=None, stateful=False, uid=10001, replicas=1):
    spec = {
        "enableServiceLinks": False,
        "serviceAccountName": "application",
        "automountServiceAccountToken": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": uid,
            "runAsGroup": uid,
            "fsGroup": uid,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": containers,
        "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "256Mi"}}] + (volumes or []),
        "terminationGracePeriodSeconds": 30,
    }
    d = {
        "replicas": replicas,
        "selector": {"matchLabels": {"app": name}},
        "template": {
            "metadata": {"labels": {"app": name, "project": "rncp-bc3"}},
            "spec": spec,
        },
    }
    if stateful:
        d["serviceName"] = name
    else:
        d["strategy"] = {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0},
        }
    return obj("StatefulSet" if stateful else "Deployment", name, {"spec": d}, "apps/v1")


def service(name, port, annotations=None):
    d = obj(
        "Service",
        name,
        {
            "spec": {
                "selector": {"app": name},
                "ports": [
                    {
                        "name": "https" if name != "db" else "postgres",
                        "port": port,
                        "targetPort": port,
                    }
                ],
            }
        },
    )
    if annotations:
        d["metadata"]["annotations"] = annotations
    return d


common = [obj("ServiceAccount", "application", {"automountServiceAccountToken": False})]
for ns in ["bc3-dev", "bc3-test", "bc3-prod"]:
    common.insert(
        0,
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": ns,
                "labels": {
                    "project": "rncp-bc3",
                    "pod-security.kubernetes.io/enforce": "restricted",
                    "pod-security.kubernetes.io/enforce-version": "v1.36",
                },
            },
        },
    )
for name in ["pg", "object"]:
    common.append(
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
for name, file in [
    ("queue-config", "infra/elasticmq.conf"),
    ("queue-tls-config", "infra/queue-tls/stunnel.conf"),
]:
    common.append(obj("ConfigMap", name, {"data": {Path(file).name: (R / file).read_text()}}))
save("00-foundation.json", common)
base = []
c = container("db", "rncp-bc3-db:1", [5432])
c["command"] = ["docker-entrypoint.sh"]
c["args"] = [
    "postgres",
    "-c",
    "ssl=on",
    "-c",
    "ssl_cert_file=/run/secrets/server.crt",
    "-c",
    "ssl_key_file=/run/secrets/server.key",
    "-c",
    "unix_socket_directories=/var/run/postgresql",
]
c["env"] = [
    {"name": k, "value": v}
    for k, v in {
        "POSTGRES_DB": "bc3",
        "POSTGRES_USER": "bc3",
        "POSTGRES_PASSWORD_FILE": "/run/secrets/db_password",
        "PGDATA": "/var/lib/postgresql/data/pgdata",
        "PGHOST": "/var/run/postgresql",
        "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256",
    }.items()
]
c["volumeMounts"] += [
    {"name": "data", "mountPath": "/var/lib/postgresql/data"},
    {"name": "pg-socket", "mountPath": "/var/run/postgresql"},
    mount("db-secret", "/run/secrets"),
]
c["readinessProbe"] = {
    "exec": {"command": ["pg_isready", "-h", "127.0.0.1", "-U", "bc3", "-d", "bc3"]},
    "periodSeconds": 5,
}
c["resources"] = resources("100m", "256Mi", "768Mi")
base += [
    workload(
        "db",
        [c],
        [
            {"name": "data", "persistentVolumeClaim": {"claimName": "pg"}},
            {"name": "pg-socket", "emptyDir": {}},
            vol_secret("db-secret", "db-secret"),
        ],
        True,
        70,
    ),
    service("db", 5432),
]
c = container(
    "s3",
    "chrislusf/seaweedfs:latest@sha256:4b42c212543a0acd4c0e675215ecdcaf62a186ef98def76c7e12701871222d15",
    [8343],
)
c["args"] = [
    "server",
    "-dir=/data",
    "-s3",
    "-s3.config=/run/secrets/s3.json",
    "-ip=127.0.0.1",
    "-ip.bind=127.0.0.1",
    "-s3.ip.bind=0.0.0.0",
    "-s3.port.https=8343",
    "-s3.cert.file=/run/secrets/s3.crt",
    "-s3.key.file=/run/secrets/s3.key",
    "-master.telemetry=false",
    "-s3.iam.selfServiceRequiresGrant=true",
    "-master.volumeSizeLimitMB=128",
]
c["volumeMounts"] += [
    {"name": "data", "mountPath": "/data"},
    mount("s3-secret", "/run/secrets"),
]
c["resources"] = resources("100m", "256Mi", "768Mi")
c["readinessProbe"] = {
    "tcpSocket": {"port": 8343},
    "periodSeconds": 5,
    "initialDelaySeconds": 5,
}
base += [
    workload(
        "s3",
        [c],
        [
            {"name": "data", "persistentVolumeClaim": {"claimName": "object"}},
            vol_secret("s3-secret", "s3-secret"),
        ],
        True,
    ),
    service("s3", 8343),
]
a = container(
    "broker",
    "softwaremill/elasticmq-native:latest@sha256:e4580ab9ad1bd5cd37b4ba04911bc5ccc8cd2d9ab4de56ece65acee71c24e05c",
)
a["volumeMounts"].append(
    {
        "name": "queue-config",
        "mountPath": "/opt/elasticmq.conf",
        "subPath": "elasticmq.conf",
        "readOnly": True,
    }
)
a["resources"] = resources("25m", "64Mi", "256Mi")
b = container("tls", "rncp-bc3-queue-tls:1", [9325])
b["volumeMounts"] += [
    mount("queue-secret", "/run/secrets"),
    {
        "name": "tls-config",
        "mountPath": "/etc/stunnel/stunnel.conf",
        "subPath": "stunnel.conf",
        "readOnly": True,
    },
]
b["resources"] = resources("10m", "16Mi", "64Mi")
b["readinessProbe"] = {"tcpSocket": {"port": 9325}, "periodSeconds": 5}
base += [
    workload(
        "queue",
        [a, b],
        [
            vol_secret("queue-secret", "queue-secret"),
            {"name": "queue-config", "configMap": {"name": "queue-config"}},
            {"name": "tls-config", "configMap": {"name": "queue-tls-config"}},
        ],
    ),
    service("queue", 9325),
]
save("10-storage.json", base)
env = {
    "DB_HOST": "db",
    "DB_USER": "bc3_app",
    "S3_ENDPOINT": "https://s3:8343",
    "QUEUE_ENDPOINT": "https://queue:9325",
    "BC3_ORIGINS": "https://bc3.local:8455,https://bc3.local:30443,https://localhost:8455,https://front:8443",
    "PYTHONPATH": "/app/src",
}
app = []


def probe(url):
    from urllib.parse import urlsplit

    return {
        "httpGet": {"path": urlsplit(url).path, "port": 8443, "scheme": "HTTPS"},
        "periodSeconds": 5,
        "timeoutSeconds": 4,
    }


c = container("api", "rncp-bc3-api:9", [8443])
c["env"] = [{"name": k, "value": v} for k, v in env.items()] + [
    {"name": "POD_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.podIP"}}}
]
c["volumeMounts"] += [mount("runtime", "/run/secrets"), mount("tls", "/run/tls")]
c["resources"] = resources("25m", "128Mi", "768Mi")
c["readinessProbe"] = probe("https://localhost:8443/health/ready")
c["livenessProbe"] = probe("https://localhost:8443/health/live")
c["livenessProbe"]["failureThreshold"] = 5
c["startupProbe"] = probe("https://localhost:8443/health/live")
c["startupProbe"]["failureThreshold"] = 40
app += [
    workload("api", [c], [vol_secret("runtime", "runtime"), vol_secret("tls", "api-tls")]),
    service(
        "api",
        8443,
        {
            "traefik.ingress.kubernetes.io/service.serversscheme": "https",
            "traefik.ingress.kubernetes.io/service.serverstransport": "api-tls@file",
        },
    ),
]
c = container("worker", "rncp-bc3-worker:6", [9091])
c["command"] = ["python", "-m", "rncp_bc3.worker"]
c["env"] = [{"name": k, "value": v} for k, v in env.items()]
c["volumeMounts"] += [mount("runtime", "/run/secrets"), mount("tls", "/run/tls")]
c["resources"] = resources("25m", "96Mi", "512Mi")
c["livenessProbe"] = {
    "httpGet": {"path": "/", "port": 9091, "scheme": "HTTPS"},
    "initialDelaySeconds": 10,
    "periodSeconds": 10,
}
app.append(
    workload(
        "worker",
        [c],
        [vol_secret("runtime", "runtime"), vol_secret("tls", "worker-tls")],
    )
)
c = container("front", "rncp-bc3-front:4", [8443])
c["volumeMounts"] += [mount("front-secrets", "/run/secrets")]
c["resources"] = resources("25m", "32Mi", "192Mi")
c["readinessProbe"] = {
    "httpGet": {"path": "/health", "port": 8443, "scheme": "HTTPS"},
    "periodSeconds": 5,
}
c["livenessProbe"] = copy.deepcopy(c["readinessProbe"])
app += [
    workload("front", [c], [vol_secret("front-secrets", "front-runtime")]),
    service(
        "front",
        8443,
        {
            "traefik.ingress.kubernetes.io/service.serversscheme": "https",
            "traefik.ingress.kubernetes.io/service.serverstransport": "front-tls@file",
        },
    ),
]
app += [
    obj(
        "HorizontalPodAutoscaler",
        "api",
        {
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "api",
                },
                "minReplicas": 1,
                "maxReplicas": 3,
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {"type": "Utilization", "averageUtilization": 60},
                        },
                    }
                ],
                "behavior": {"scaleDown": {"stabilizationWindowSeconds": 30}},
            }
        },
        "autoscaling/v2",
    ),
    obj(
        "PodDisruptionBudget",
        "api",
        {"spec": {"minAvailable": 1, "selector": {"matchLabels": {"app": "api"}}}},
        "policy/v1",
    ),
]
save("30-application.json", app)
job_container = container("bootstrap", "rncp-bc3-api:9")
job_container["command"] = [
    "sh",
    "-ec",
    "python scripts/bootstrap_database.py && python scripts/create_user.py --username thomas --role agent --password-file /run/secrets/demo_password",
]
job_container["env"] = [{"name": "DB_USER", "value": "bc3"}]
job_container["volumeMounts"] += [mount("bootstrap", "/run/secrets")]
job = obj(
    "Job",
    "database-bootstrap-v6",
    {
        "spec": {
            "backoffLimit": 3,
            "template": {
                "metadata": {"labels": {"app": "bootstrap"}},
                "spec": {
                    "restartPolicy": "Never",
                    "enableServiceLinks": False,
                    "serviceAccountName": "application",
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 10001,
                        "runAsGroup": 10001,
                        "fsGroup": 10001,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [job_container],
                    "volumes": [
                        {"name": "tmp", "emptyDir": {}},
                        vol_secret(
                            "bootstrap",
                            "bootstrap",
                            {
                                "config.json": "config.json",
                                "runtime-config.json": "runtime/config.json",
                                "ca.crt": "ca.crt",
                                "demo_password": "demo_password",
                            },
                        ),
                    ],
                },
            },
        }
    },
    "batch/v1",
)
save("20-bootstrap.json", [job])
print("Manifests standards générés, aucune valeur secrète incluse")
# Ingress : TLS entrant et vérification de la CA pour le saut vers le front.
traefik = []
traefik += [
    obj("ServiceAccount", "ingress-controller", {}),
    obj(
        "Role",
        "ingress-watch",
        {
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["services", "secrets", "endpoints"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["discovery.k8s.io"],
                    "resources": ["endpointslices"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingresses"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingresses/status"],
                    "verbs": ["update"],
                },
            ]
        },
        "rbac.authorization.k8s.io/v1",
    ),
    obj(
        "RoleBinding",
        "ingress-watch",
        {
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "ingress-watch",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "ingress-controller",
                    "namespace": NS,
                }
            ],
        },
        "rbac.authorization.k8s.io/v1",
    ),
]
traefik += [
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": "rncp-bc3-ingressclasses"},
        "rules": [
            {
                "apiGroups": ["networking.k8s.io"],
                "resources": ["ingressclasses"],
                "verbs": ["get", "list", "watch"],
            }
        ],
    },
    {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": "rncp-bc3-ingressclasses"},
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "rncp-bc3-ingressclasses",
        },
        "subjects": [{"kind": "ServiceAccount", "name": "ingress-controller", "namespace": NS}],
    },
]
traefik.append(
    obj(
        "ConfigMap",
        "traefik-dynamic",
        {
            "data": {
                "dynamic.yml": json.dumps(
                    {
                        "http": {
                            "serversTransports": {
                                "front-tls": {
                                    "serverName": "front",
                                    "rootCAs": ["/run/trust/ca.crt"],
                                },
                                "api-tls": {
                                    "serverName": "api",
                                    "rootCAs": ["/run/trust/ca.crt"],
                                },
                            }
                        }
                    }
                )
            }
        },
    )
)
c = container(
    "traefik",
    "traefik:v3.7.19@sha256:a6c0194dda77bcb804824580f36fa7edc56e315b1acfe933366c8b52844a78a4",
    [8443, 8082],
)
c["args"] = [
    "--entrypoints.websecure.address=:8443",
    "--entrypoints.health.address=:8082",
    "--ping=true",
    "--ping.entrypoint=health",
    "--providers.kubernetesingress=true",
    "--providers.kubernetesingress.namespaces=" + NS,
    "--providers.kubernetesingress.ingressclass=bc3",
    "--providers.file.filename=/etc/traefik/dynamic.yml",
    "--api.dashboard=false",
    "--global.checknewversion=false",
    "--global.sendanonymoususage=false",
    "--log.format=json",
    "--metrics.prometheus=true",
    "--metrics.prometheus.entrypoint=health",
]
c["volumeMounts"] += [mount("dynamic", "/etc/traefik"), mount("trust", "/run/trust")]
c["readinessProbe"] = {"httpGet": {"path": "/ping", "port": 8082}, "periodSeconds": 5}
c["livenessProbe"] = copy.deepcopy(c["readinessProbe"])
c["resources"] = resources("25m", "64Mi", "256Mi")
w = workload(
    "ingress",
    [c],
    [
        {"name": "dynamic", "configMap": {"name": "traefik-dynamic"}},
        {"name": "trust", "configMap": {"name": "trust"}},
    ],
    uid=65532,
)
w["spec"]["template"]["spec"]["serviceAccountName"] = "ingress-controller"
w["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
traefik.append(w)
traefik.append(
    obj(
        "Service",
        "ingress",
        {
            "spec": {
                "type": "NodePort",
                "selector": {"app": "ingress"},
                "ports": [
                    {
                        "name": "https",
                        "port": 443,
                        "targetPort": 8443,
                        "nodePort": 30443,
                    }
                ],
            }
        },
    )
)
traefik.append(
    {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "IngressClass",
        "metadata": {"name": "bc3"},
        "spec": {"controller": "traefik.io/ingress-controller"},
    }
)
traefik.append(
    obj(
        "Ingress",
        "support",
        {
            "spec": {
                "ingressClassName": "bc3",
                "tls": [{"hosts": ["bc3.local"], "secretName": "front-tls"}],
                "rules": [
                    {
                        "host": "bc3.local",
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": "front",
                                            "port": {"number": 8443},
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        },
        "networking.k8s.io/v1",
    )
)

for entry in traefik:
    if entry["kind"] == "Ingress":
        entry["spec"]["tls"][0]["hosts"].append("localhost")
        rule = copy.deepcopy(entry["spec"]["rules"][0])
        rule["host"] = "localhost"
        entry["spec"]["rules"].append(rule)

for entry in traefik:
    if entry["kind"] == "ClusterRole":
        entry["rules"].append(
            {
                "apiGroups": [""],
                "resources": ["nodes"],
                "verbs": ["get", "list", "watch"],
            }
        )
    if entry["kind"] == "Ingress":
        entry["metadata"]["annotations"] = {
            "traefik.ingress.kubernetes.io/router.entrypoints": "websecure",
            "traefik.ingress.kubernetes.io/router.tls": "true",
        }
save("40-ingress.json", traefik)

for entry in traefik:
    if entry["kind"] == "Ingress":
        for rule in entry["spec"]["rules"]:
            rule["http"]["paths"].insert(
                0,
                {
                    "path": "/health",
                    "pathType": "Prefix",
                    "backend": {"service": {"name": "api", "port": {"number": 8443}}},
                },
            )
save("40-ingress.json", traefik)

for entry in traefik:
    if entry["kind"] == "Deployment":
        entry["spec"]["template"]["metadata"]["annotations"] = {
            "checksum/config": hashlib.sha256(
                json.dumps(
                    [v for v in traefik if v["kind"] == "ConfigMap"], sort_keys=True
                ).encode()
            ).hexdigest()
        }
save("40-ingress.json", traefik)
