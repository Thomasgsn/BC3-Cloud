"""Verrouiller les distributions effectivement installées, hashes des roues PyPI."""

import importlib.metadata as md
import json
import urllib.request
from pathlib import Path

root = Path("/workspace")
lines = ["# Versions observées, roues PyPI uniquement ; généré pour le runtime BC3."]
packages = {}
for d in sorted(
    md.distributions(path=["/workspace/tmp/quality"]),
    key=lambda d: d.metadata["Name"].lower(),
):
    name = d.metadata["Name"]
    version = d.version
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as r:
        info = json.load(r)
    hashes = sorted(
        {f["digests"]["sha256"] for f in info["urls"] if f["packagetype"] == "bdist_wheel"}
    )
    if not hashes:
        raise ValueError("Distribution sans roue : " + name)
    lines.append(f"{name}=={version} \\\n" + " \\\n".join("    --hash=sha256:" + h for h in hashes))
    packages[name] = version
(root / "exports").mkdir(exist_ok=True)
(root / "requirements.quality.lock").write_text("\n".join(lines) + "\n")
(root / "docs/evidence/k8s/quality-dependencies.json").write_text(
    json.dumps(
        {
            "source": "Installed runtime and PyPI release metadata",
            "versions": packages,
            "count": len(packages),
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"event": "dependencies_locked", "count": len(packages)}))
