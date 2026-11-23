"""Rendu d'un environnement promu : même contenu applicatif, autre namespace, isolation réseau."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_env", ROOT / "scripts/render_env.py")
render_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_env)


def test_prod_render_changes_only_namespace_and_adds_isolation():
    rendered = render_env.render("bc3-prod")["items"]
    text = json.dumps(rendered)
    assert '"bc3-test"' not in text
    assert {o["metadata"]["namespace"] for o in rendered} == {"bc3-prod"}
    kinds = {o["kind"] for o in rendered}
    assert "Namespace" not in kinds and "ClusterRole" not in kinds
    policy = [o for o in rendered if o["kind"] == "NetworkPolicy"]
    assert policy and policy[0]["spec"]["ingress"] == [{"from": [{"podSelector": {}}]}]
    images = sorted(
        c["image"]
        for o in rendered
        if o["kind"] in {"Deployment", "StatefulSet"}
        for c in o["spec"]["template"]["spec"]["containers"]
    )
    assert "rncp-bc3-api:9" in images


@pytest.mark.parametrize("namespace", ["bc3-test", "default", "kube-system"])
def test_invalid_targets_are_refused(namespace):
    with pytest.raises(ValueError):
        render_env.render(namespace)
