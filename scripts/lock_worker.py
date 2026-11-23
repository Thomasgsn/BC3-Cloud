"""Sous-ensemble de dépendances du worker, versions/hashes conservés du verrou complet."""

import importlib.metadata as md
import json
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

roots = {
    "psycopg": {"binary"},
    "boto3": set(),
    "cryptography": set(),
    "prometheus-client": set(),
}
pending = list(roots.items())
seen = {}
while pending:
    name, extras = pending.pop()
    name = canonicalize_name(name)
    previous = seen.get(name)
    if previous is not None and extras <= previous:
        continue
    seen[name] = extras | (previous or set())
    env = default_environment()
    for raw in md.requires(name) or []:
        req = Requirement(raw)
        if req.marker and not any(
            req.marker.evaluate(env | {"extra": extra}) for extra in [""] + list(seen[name])
        ):
            continue
        pending.append((req.name, set(req.extras)))
blocks = {}
current = None
for line in Path("/workspace/requirements.lock").read_text().splitlines():
    if line and not line.startswith((" ", "#")) and "==" in line:
        current = canonicalize_name(line.split("==")[0])
        blocks[current] = [line]
    elif current and line.startswith(" "):
        blocks[current].append(line)
result = [
    "# Worker uniquement : fermeture des dépendances, mêmes versions et hashes que requirements.lock."
]
for name in sorted(seen):
    result.extend(blocks[name])
Path("/workspace/requirements.worker.lock").write_text("\n".join(result) + "\n")
Path("/workspace/docs/evidence/finops/worker-dependencies.json").write_text(
    json.dumps(
        {
            "roots": {k: sorted(v) for k, v in roots.items()},
            "distributions": sorted(seen),
            "count": len(seen),
            "full_runtime_count": len(blocks),
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"worker_distributions": len(seen), "full_runtime_distributions": len(blocks)}))
