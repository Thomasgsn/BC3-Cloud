"""Contrôles locaux de structure, syntaxe et absence de valeurs secrètes dans les livrables."""

import ast
import hashlib
import json
import re
from pathlib import Path

R = Path(__file__).resolve().parents[1]
required = [
    "README.md",
    "AGENTS.md",
    ".env.example",
    ".gitignore",
    "docs/rapport.md",
    "docs/checklist.md",
    "docs/dictionnaire.md",
]
errors = []
for name in required:
    if not (R / name).is_file():
        errors.append("Fichier absent : " + name)
files = []
for parent in ["src", "scripts", "tests", "infra", "frontend", "docs", ".github"]:
    for f in (R / parent).rglob("*"):
        if not f.is_file() or any(
            p in ["node_modules", ".terraform", "__pycache__", "dist"]
            for p in f.relative_to(R).parts
        ):
            continue
        if f.suffix in [
            ".py",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".tf",
            ".hcl",
            ".toml",
            ".ts",
            ".vue",
            ".css",
            ".sh",
            ".mjs",
            ".log",
            ".txt",
            ".lock",
        ] or f.name.endswith("Dockerfile"):
            files.append(f)
for f in (R / "src").rglob("*.py"):
    ast.parse(f.read_text(), str(f))
for f in (R / "scripts").glob("*.py"):
    ast.parse(f.read_text(), str(f))
secret_values = []
for path in [R / "secrets/config.json", R / "secrets/runtime/config.json"]:
    if path.exists():
        secret_values.extend(
            str(v)
            for v in json.loads(path.read_text()).values()
            if isinstance(v, str) and len(v) > 15
        )
for path in [R / "secrets/demo_password", R / "secrets/grafana_password"]:
    if path.exists():
        secret_values.append(path.read_text().strip())
for f in files:
    text = f.read_text(errors="replace")
    if any(value in text for value in secret_values):
        errors.append("Valeur secrète présente : " + str(f.relative_to(R)))
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        errors.append("Clé privée présente : " + str(f.relative_to(R)))
result = {
    "checked_text_files": len(files),
    "private_values_compared_not_printed": len(secret_values),
    "errors": errors,
    "sha_source_files": {
        str(f.relative_to(R)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in files
        if f.parts[-3:-1] != ("evidence", "security")
    },
}
p = R / "docs/evidence/delivery"
p.mkdir(parents=True, exist_ok=True)
(p / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: result[k]
            for k in ["checked_text_files", "private_values_compared_not_printed", "errors"]
        }
    )
)
assert not errors
