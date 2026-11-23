"""Initialisation additive : secrets locaux et certificats privés, jamais affichés."""

import base64
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dest = ROOT / "secrets"
dest.mkdir(exist_ok=True, mode=0o700)
os.chmod(dest, 0o700)


def write(name, value):
    p = dest / name
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(value)
    return p.read_text()


write("demo_password", secrets.token_urlsafe(24))
write("grafana_password", secrets.token_urlsafe(24))
password = write("db_password", secrets.token_urlsafe(32))
access = write("s3_access", secrets.token_hex(12))
key = write("s3_secret", secrets.token_urlsafe(32))
write(
    "config.json",
    json.dumps(
        {
            "db_password": password,
            "s3_access": access,
            "s3_secret": key,
            "encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        },
        indent=2,
    ),
)
write(
    "s3.json",
    json.dumps(
        {
            "identities": [
                {
                    "name": "bc3-service",
                    "credentials": [{"accessKey": access, "secretKey": key}],
                    "actions": ["Read", "Write", "List", "Tagging", "Admin"],
                }
            ]
        }
    ),
)
if not (dest / "ca.crt").exists():

    def run(args):
        subprocess.run(
            ["openssl", *args],
            cwd=dest,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    run(
        [
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-nodes",
            "-keyout",
            "ca.key",
            "-out",
            "ca.crt",
            "-days",
            "365",
            "-subj",
            "/CN=RNCP BC3 local CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
        ]
    )
    run(
        [
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            "server.key",
            "-out",
            "server.csr",
            "-subj",
            "/CN=bc3.local",
        ]
    )
    write(
        "server.ext",
        "subjectAltName=DNS:localhost,DNS:bc3.local,DNS:api,DNS:front,DNS:db,DNS:s3,DNS:queue,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n",
    )
    run(
        [
            "x509",
            "-req",
            "-in",
            "server.csr",
            "-CA",
            "ca.crt",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-out",
            "server.crt",
            "-days",
            "365",
            "-extfile",
            "server.ext",
        ]
    )
    for p in dest.iterdir():
        os.chmod(p, 0o600)
env = ROOT / ".env"
if not env.exists():
    env.write_text(f"LOCAL_UID={os.getuid()}\nLOCAL_GID={os.getgid()}\n")
print(
    json.dumps(
        {
            "event": "local_initialization_ready",
            "secrets_printed": False,
            "existing_files_preserved": True,
            "host_trust_store_modified": False,
        }
    )
)

# Le runtime ne reçoit ni clé de CA, ni mot de passe administratif PostgreSQL.

runtime = dest / "runtime"
runtime.mkdir(exist_ok=True, mode=0o700)
os.chmod(runtime, 0o700)
original = json.loads((dest / "config.json").read_text())
config = runtime / "config.json"
if not config.exists():
    original["db_password"] = secrets.token_urlsafe(32)
    config.write_text(json.dumps(original, indent=2))
    os.chmod(config, 0o600)
for name in ["server.key", "server.crt", "ca.crt"]:
    target = runtime / name
    if not target.exists():
        shutil.copyfile(dest / name, target)
        os.chmod(target, 0o600)
# Identités S3 séparées : l'application n'a pas les droits d'administration du service.
app = json.loads(config.read_text())
app_access = write("s3_app_access", secrets.token_hex(12))
app_secret = write("s3_app_secret", secrets.token_urlsafe(32))
identities = json.loads((dest / "s3.json").read_text())
if not any(i["name"] == "bc3-app" for i in identities["identities"]):
    identities["identities"].append(
        {
            "name": "bc3-app",
            "credentials": [{"accessKey": app_access, "secretKey": app_secret}],
            "actions": ["Read:bc3-private", "Write:bc3-private", "List:bc3-private"],
        }
    )
    (dest / "s3.json").write_text(json.dumps(identities))
app.update(s3_access=app_access, s3_secret=app_secret)
config.write_text(json.dumps(app, indent=2))
os.chmod(config, 0o600)
# Une clé de serveur par composant ; le runtime commun ne contient que config et CA.
for component, names in [
    ("api", "DNS:api,DNS:localhost,IP:127.0.0.1"),
    ("front", "DNS:front,DNS:localhost,DNS:bc3.local,IP:127.0.0.1"),
    ("db", "DNS:db,DNS:localhost"),
    ("s3", "DNS:s3,DNS:localhost"),
    ("queue", "DNS:queue,DNS:localhost"),
    ("worker", "DNS:worker,DNS:localhost"),
    ("grafana", "DNS:grafana,DNS:localhost,IP:127.0.0.1"),
    ("prometheus", "DNS:prometheus,DNS:localhost,IP:127.0.0.1"),
    ("loki", "DNS:loki,DNS:localhost"),
]:
    if not (dest / (component + ".crt")).exists():

        def run(args):
            subprocess.run(
                ["openssl", *args],
                cwd=dest,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        run(
            [
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                component + ".key",
                "-out",
                component + ".csr",
                "-subj",
                "/CN=" + component,
            ]
        )
        write(
            component + ".ext",
            "subjectAltName="
            + names
            + "\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n",
        )
        run(
            [
                "x509",
                "-req",
                "-in",
                component + ".csr",
                "-CA",
                "ca.crt",
                "-CAkey",
                "ca.key",
                "-CAcreateserial",
                "-out",
                component + ".crt",
                "-days",
                "365",
                "-extfile",
                component + ".ext",
            ]
        )
        os.chmod(dest / (component + ".key"), 0o600)
        os.chmod(dest / (component + ".crt"), 0o600)
for filename in ["server.key", "server.crt"]:
    if (runtime / filename).exists():
        os.replace(runtime / filename, dest / ("legacy-runtime-" + filename))
