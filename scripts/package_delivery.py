"""Archive autonome BC3 : manifeste SHA et contrôle d’absence de secret, sans Git/push."""

import datetime
import hashlib
import json
import zipfile
from pathlib import Path

R = Path(__file__).resolve().parents[1]
out = R / f"output/bc3-rendu-{datetime.datetime.now(datetime.UTC):%Y%m%d}.zip"
if out.exists():
    raise SystemExit(f"{out.name} existe déjà : archive non écrasée")
excluded = {
    "secrets",
    "data",
    "models",
    "exports",
    "tmp",
    "node_modules",
    ".git",
    ".terraform",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
}
allowed_roots = {"src", "tests", "scripts", "infra", "frontend", "docs", ".github", "output"}
files = []
for path in R.rglob("*"):
    if not path.is_file() or path.is_symlink():
        continue
    relative = path.relative_to(R)
    if str(relative) == "docs/evidence/delivery/archive.json":
        continue
    if any(part in excluded for part in relative.parts):
        continue
    if relative.parts[0] == "output" and path.suffix not in [".pdf", ".pptx"]:
        continue
    if len(relative.parts) > 1 and relative.parts[0] not in allowed_roots:
        continue
    if path.name.startswith(".env") and path.name != ".env.example":
        continue
    if (
        path.suffix in [".key", ".pem", ".tfstate", ".tfplan", ".tfvars", ".pyc"]
        or ".tfstate." in path.name
    ):
        continue
    if path.name == ".DS_Store":
        continue
    files.append(path)
assert (R / "output/pdf/rapport-bc3-thomas-gassmann.pdf") in files
assert (R / "output/presentations/soutenance-bc3-thomas-gassmann.pptx") in files
secret_values = []
for conf in [R / "secrets/config.json", R / "secrets/runtime/config.json"]:
    secret_values.extend(
        str(v).encode()
        for v in json.loads(conf.read_text()).values()
        if isinstance(v, str) and len(v) > 15
    )
for conf in [R / "secrets/demo_password", R / "secrets/grafana_password"]:
    secret_values.append(conf.read_bytes().strip())
manifest = {}
for path in files:
    content = path.read_bytes()
    assert not any(value in content for value in secret_values), str(path.relative_to(R))
    manifest[str(path.relative_to(R))] = hashlib.sha256(content).hexdigest()
    if path.suffix == ".pptx":
        with zipfile.ZipFile(path) as deck:
            for name in deck.namelist():
                assert not any(v in deck.read(name) for v in secret_values), name
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(files):
        archive.write(path, "bc3/" + str(path.relative_to(R)))
    archive.writestr("bc3/MANIFEST.sha256.json", json.dumps(manifest, indent=2) + "\n")
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
    loaded = json.loads(archive.read("bc3/MANIFEST.sha256.json"))
    for name, sha in loaded.items():
        assert hashlib.sha256(archive.read("bc3/" + name)).hexdigest() == sha, name
result = {
    "archive": out.name,
    "files": len(files),
    "entries": len(files) + 1,
    "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    "crc_verified": True,
    "all_entry_sha_verified": True,
    "known_private_values_checked_not_printed": len(secret_values),
    "excluded": "Secrets, raw data, model weights, volumes, runtime state, Git and caches",
    "restoration_of_old_encrypted_database": "Requires separately preserved private keys; archive deliberately cannot decrypt it",
}
(R / "docs/evidence/delivery/archive.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
