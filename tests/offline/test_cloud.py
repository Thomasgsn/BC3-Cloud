"""Contrats hors ligne, identités/digests fictifs explicitement réservés aux tests."""

import copy
import importlib.util
import json
import ssl
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cloud_renderer", ROOT / "scripts/render_cloud.py")
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


@pytest.fixture
def config():
    region = "eu-west-3"
    account = "123456789012"  # Identifiant de documentation ; aucun compte appelé.
    repos = {
        name: f"{account}.dkr.ecr.{region}.amazonaws.com/rncp-bc3/{name}"
        for name in ["api", "worker", "front"]
    }
    values = {
        "region": region,
        "cluster_name": "rncp-bc3",
        "database_host": f"bc3.fixture.{region}.rds.amazonaws.com",
        "bucket": "rncp-bc3-offline-fixture",
        "queue_url": f"https://sqs.{region}.amazonaws.com/{account}/jobs",
        "dlq_url": f"https://sqs.{region}.amazonaws.com/{account}/jobs-dead",
        "repositories": repos,
    }
    settings = {
        "hostname": "support.example.org",
        "images": {name: repo + "@sha256:" + "a" * 64 for name, repo in repos.items()},
    }
    return values, settings


def public_ca():
    bundle = Path(ssl.get_default_verify_paths().cafile).read_text()
    start = bundle.index("-----BEGIN CERTIFICATE-----")
    end = bundle.index("-----END CERTIFICATE-----", start) + len("-----END CERTIFICATE-----")
    return bundle[start:end]


def test_cloud_preparation_separates_identities_and_trust(config):
    values, settings = config
    manifest = cloud.render(values, settings, public_ca(), public_ca())
    items = manifest["items"]
    assert not any(x["kind"] in ["Secret", "PersistentVolumeClaim", "StatefulSet"] for x in items)
    deployments = {x["metadata"]["name"]: x for x in items if x["kind"] == "Deployment"}
    assert set(deployments) == {"api", "worker", "front", "ingress"}
    for name in ["api", "worker"]:
        pod = deployments[name]["spec"]["template"]["spec"]
        assert pod["serviceAccountName"] == name
        container = pod["containers"][0]
        env = {e["name"]: e.get("value") for e in container["env"]}
        assert env["BC3_STORAGE_MODE"] == "aws"
        assert env["DB_SSLROOTCERT"] == "/run/rds/rds-ca.crt"
        assert (
            not {"S3_ENDPOINT", "QUEUE_ENDPOINT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
            & env.keys()
        )
        assert all(
            v.get("secret", {}).get("secretName") != "cloud-bootstrap" for v in pod["volumes"]
        )
    job = next(x for x in items if x["kind"] == "Job")
    assert job["spec"]["template"]["spec"]["containers"][0]["command"] == [
        "python",
        "scripts/bootstrap_database.py",
    ]
    assert "cloud-bootstrap" in json.dumps(job)
    assert "bc3admin" not in json.dumps(deployments)
    ingress = next(x for x in items if x["kind"] == "Ingress")
    assert [r["host"] for r in ingress["spec"]["rules"]] == ["support.example.org"]
    assert ingress["spec"]["tls"][0]["secretName"] == "public-ingress-tls"
    lb = next(x for x in items if x["kind"] == "Service" and x["metadata"]["name"] == "ingress")
    assert lb["spec"]["loadBalancerClass"] == "service.k8s.aws/nlb"
    assert all("nodePort" not in p for p in lb["spec"]["ports"])


@pytest.mark.parametrize(
    "mutation",
    [
        "mutable_image",
        "external_image",
        "plain_queue",
        "wrong_region",
        "same_dlq",
        "wildcard_host",
        "credentials_field",
    ],
)
def test_unsafe_cloud_config_refused(config, mutation):
    values, settings = copy.deepcopy(config)
    if mutation == "mutable_image":
        settings["images"]["api"] = values["repositories"]["api"] + ":latest"
    elif mutation == "external_image":
        settings["images"]["api"] = "docker.io/unknown/api@sha256:" + "a" * 64
    elif mutation == "plain_queue":
        values["queue_url"] = values["queue_url"].replace("https:", "http:")
    elif mutation == "wrong_region":
        values["database_host"] = "bc3.fixture.us-east-1.rds.amazonaws.com"
    elif mutation == "same_dlq":
        values["dlq_url"] = values["queue_url"]
    elif mutation == "wildcard_host":
        settings["hostname"] = "*.example.org"
    else:
        settings["db_password"] = "fixture-rejected-not-a-real-password"
    with pytest.raises(ValueError):
        cloud.validate(values, settings)


def test_private_key_never_accepted_as_public_ca():
    with pytest.raises(ValueError):
        cloud.certificate("-----BEGIN " + "PRIVATE KEY-----\nfixture")
