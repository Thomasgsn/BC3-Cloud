"""Rend les manifests applicatifs pour un autre namespace (promotion), avec isolation réseau.

Les objets namespacés de 00 à 30 sont repris à l'identique, seul le namespace change.
Ingress et observabilité restent dans bc3-test ; prod est joint par port-forward.
Une NetworkPolicy refuse tout trafic entrant venant d'un autre namespace.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["00-foundation.json", "10-storage.json", "20-bootstrap.json", "30-application.json"]
SOURCE_NS = "bc3-test"


def items(path):
    data = json.loads(path.read_text())
    return data.get("items", data if isinstance(data, list) else [data])


def isolation(namespace):
    """Trafic entrant autorisé seulement depuis le même namespace."""
    meta = {"namespace": namespace, "labels": {"project": "rncp-bc3"}}
    return [
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "same-namespace-only", **meta},
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress"],
                "ingress": [{"from": [{"podSelector": {}}]}],
            },
        }
    ]


def render(namespace):
    if namespace == SOURCE_NS or not namespace.startswith("bc3-"):
        raise ValueError("Namespace cible invalide")
    out = []
    for name in SOURCES:
        for obj in items(ROOT / "infra/kubernetes" / name):
            if obj["metadata"].get("namespace") != SOURCE_NS:
                continue  # Namespaces et objets de cluster déjà créés par la fondation.
            text = json.dumps(obj).replace(f'"{SOURCE_NS}"', f'"{namespace}"')
            out.append(json.loads(text))
    out += isolation(namespace)
    return {"apiVersion": "v1", "kind": "List", "items": out}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    target = ROOT / "infra/kubernetes/env" / f"{args.namespace}.json"
    target.parent.mkdir(exist_ok=True)
    rendered = render(args.namespace)
    target.write_text(json.dumps(rendered, indent=2) + "\n")
    print(
        json.dumps(
            {
                "event": "env_rendered",
                "namespace": args.namespace,
                "objects": len(rendered["items"]),
            }
        )
    )
