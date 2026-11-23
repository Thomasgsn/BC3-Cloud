"""Préparer l'application AWS hors ligne ; aucune commande AWS/Kubernetes exécutée."""

import argparse
import copy
import json
import re
import ssl
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
NS = "bc3-test"


def output_values(outputs):
    return {name: item["value"] for name, item in outputs.items()}


def validate(values, settings):
    required = {
        "region",
        "cluster_name",
        "database_host",
        "bucket",
        "queue_url",
        "dlq_url",
        "repositories",
    }
    if not required <= values.keys() or set(settings) != {"hostname", "images"}:
        raise ValueError("Sorties Terraform ou configuration incomplètes/inconnues")
    region = values["region"]
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", region):
        raise ValueError("Région invalide")
    hostname = settings["hostname"]
    if (
        len(hostname) > 253
        or len(hostname.split(".")) < 2
        or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in hostname.split(".")
        )
    ):
        raise ValueError("FQDN public explicite requis, sans port ni joker")
    if not re.fullmatch(
        r"[a-zA-Z0-9.-]+\." + re.escape(region) + r"\.rds\.amazonaws\.com", values["database_host"]
    ):
        raise ValueError("Endpoint RDS incohérent")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", values["bucket"]):
        raise ValueError("Nom de bucket invalide")
    accounts = set()
    for field in ["queue_url", "dlq_url"]:
        url = urlsplit(values[field])
        if (
            url.scheme != "https"
            or url.netloc != f"sqs.{region}.amazonaws.com"
            or url.query
            or url.fragment
        ):
            raise ValueError("Endpoint SQS HTTPS régional requis")
        if not re.fullmatch(r"/\d{12}/[A-Za-z0-9_-]+", url.path):
            raise ValueError("Chemin SQS invalide")
        accounts.add(url.path.split("/")[1])
    if values["queue_url"] == values["dlq_url"] or len(accounts) != 1:
        raise ValueError("File et DLQ distinctes dans le même compte requises")
    if set(settings["images"]) != {"api", "worker", "front"}:
        raise ValueError("Trois images requises")
    account = accounts.pop()
    for name, image in settings["images"].items():
        repo = values["repositories"][name]
        if not re.fullmatch(
            re.escape(account + f".dkr.ecr.{region}.amazonaws.com/") + r"[a-z0-9/_-]+", repo
        ):
            raise ValueError("Dépôt ECR régional du même compte requis")
        if not re.fullmatch(re.escape(repo) + r"@sha256:[0-9a-f]{64}", image):
            raise ValueError("Image ECR immuable par digest requise")


def certificate(text):
    # CA publiques uniquement ; les clés privées ne doivent jamais entrer dans le rendu.
    if "PRIVATE KEY" in text or "-----BEGIN CERTIFICATE-----" not in text:
        raise ValueError("Fichier de certificats publics requis")
    ssl.create_default_context(cadata=text)
    return text


def render(values, settings, backend_ca, rds_ca):
    validate(values, settings)
    items = []

    def resource(kind, name, **fields):
        return {
            "apiVersion": "v1",
            "kind": kind,
            "metadata": {"name": name, "namespace": NS},
            **fields,
        }

    foundation = json.loads((ROOT / "infra/kubernetes/00-foundation.json").read_text())
    items += [copy.deepcopy(x) for x in foundation["items"] if x["kind"] == "Namespace"]
    items += [
        resource("ServiceAccount", name, automountServiceAccountToken=False)
        for name in ["api", "worker", "front", "application"]
    ]
    items += [
        resource("ConfigMap", "trust", data={"ca.crt": certificate(backend_ca)}),
        resource("ConfigMap", "rds-trust", data={"rds-ca.crt": certificate(rds_ca)}),
    ]
    app = json.loads((ROOT / "infra/kubernetes/30-application.json").read_text())
    for item in app["items"]:
        item = copy.deepcopy(item)
        if item["kind"] == "Deployment":
            name = item["metadata"]["name"]
            spec = item["spec"]["template"]["spec"]
            spec["serviceAccountName"] = name
            container = spec["containers"][0]
            container["image"] = settings["images"][name]
            container["imagePullPolicy"] = "Always"
            for volume in spec["volumes"]:
                if volume.get("secret", {}).get("secretName") == "runtime":
                    volume["secret"]["secretName"] = "cloud-runtime"
            if name in ["api", "worker"]:
                env = {
                    "DB_HOST": values["database_host"],
                    "DB_NAME": "bc3",
                    "DB_USER": "bc3_app",
                    "DB_SSLROOTCERT": "/run/rds/rds-ca.crt",
                    "BC3_STORAGE_MODE": "aws",
                    "AWS_REGION": values["region"],
                    "S3_BUCKET": values["bucket"],
                    "QUEUE_URL": values["queue_url"],
                    "DLQ_URL": values["dlq_url"],
                    "BC3_PUBLIC_HOST": settings["hostname"],
                    "BC3_ORIGINS": "https://" + settings["hostname"],
                    "PYTHONPATH": "/app/src",
                    "AWS_EC2_METADATA_DISABLED": "true",
                }
                container["env"] = [{"name": k, "value": v} for k, v in env.items()]
                container["env"].append(
                    {"name": "POD_IP", "valueFrom": {"fieldRef": {"fieldPath": "status.podIP"}}}
                )
                container["volumeMounts"].append(
                    {"name": "rds-trust", "mountPath": "/run/rds", "readOnly": True}
                )
                spec["volumes"].append({"name": "rds-trust", "configMap": {"name": "rds-trust"}})
        items.append(item)
    ingress = json.loads((ROOT / "infra/kubernetes/40-ingress.json").read_text())
    for item in ingress["items"]:
        item = copy.deepcopy(item)
        if item["kind"] == "Service":
            item["spec"]["type"] = "LoadBalancer"
            item["spec"]["loadBalancerClass"] = "service.k8s.aws/nlb"
            item["spec"]["ports"][0].pop("nodePort", None)
            item["metadata"]["annotations"] = {
                "service.beta.kubernetes.io/aws-load-balancer-scheme": "internet-facing",
                "service.beta.kubernetes.io/aws-load-balancer-nlb-target-type": "ip",
                "service.beta.kubernetes.io/aws-load-balancer-healthcheck-protocol": "TCP",
            }
        elif item["kind"] == "Ingress":
            item["spec"]["rules"] = item["spec"]["rules"][:1]
            item["spec"]["rules"][0]["host"] = settings["hostname"]
            item["spec"]["tls"] = [
                {"hosts": [settings["hostname"]], "secretName": "public-ingress-tls"}
            ]
        items.append(item)
    # Bootstrap distinct : le rôle SQL administratif n'est jamais monté dans API/worker.
    api = next(x for x in items if x["kind"] == "Deployment" and x["metadata"]["name"] == "api")
    template = copy.deepcopy(api["spec"]["template"])
    template["metadata"]["labels"]["app"] = "cloud-bootstrap"
    spec = template["spec"]
    spec["restartPolicy"] = "Never"
    container = spec["containers"][0]
    container["name"] = "bootstrap"
    container["command"] = ["python", "scripts/bootstrap_database.py"]
    for key in ["ports", "startupProbe", "readinessProbe", "livenessProbe"]:
        container.pop(key, None)
    for env in container["env"]:
        if env["name"] == "DB_USER":
            env["value"] = "bc3admin"
    spec["volumes"] = [v for v in spec["volumes"] if v["name"] != "tls"]
    for volume in spec["volumes"]:
        if volume["name"] == "runtime":
            volume["secret"]["secretName"] = "cloud-bootstrap"
            volume["secret"]["items"] = [
                {"key": k, "path": p}
                for k, p in {
                    "config.json": "config.json",
                    "runtime-config.json": "runtime/config.json",
                    "ca.crt": "ca.crt",
                }.items()
            ]
    container["volumeMounts"] = [v for v in container["volumeMounts"] if v["name"] != "tls"]
    items.append(
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": "cloud-database-bootstrap", "namespace": NS},
            "spec": {"backoffLimit": 1, "activeDeadlineSeconds": 180, "template": template},
        }
    )
    return {"apiVersion": "v1", "kind": "List", "items": items}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terraform-outputs", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--backend-ca", type=Path, required=True)
    parser.add_argument("--rds-ca", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = render(
        output_values(json.loads(args.terraform_outputs.read_text())),
        json.loads(args.settings.read_text()),
        args.backend_ca.read_text(),
        args.rds_ca.read_text(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "event": "cloud_manifest_prepared_offline",
                "resources": len(result["items"]),
                "applied": False,
            }
        )
    )


if __name__ == "__main__":
    main()
