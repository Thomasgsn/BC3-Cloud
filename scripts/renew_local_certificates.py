"""Complète les extensions X.509 des feuilles, CA et clés existantes conservées."""

import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
d = root / "secrets"
renewed = []
for name in ["api", "front", "db", "s3", "queue", "worker", "grafana", "prometheus"]:
    cert = d / (name + ".crt")
    ext = d / (name + ".ext")
    text = ext.read_text()
    if "authorityKeyIdentifier" not in text:
        text += "basicConstraints=critical,CA:FALSE\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
        ext.write_text(text)
    inspect = subprocess.check_output(
        ["openssl", "x509", "-in", str(cert), "-text", "-noout"], text=True
    )
    if "Authority Key Identifier" in inspect:
        continue
    previous = d / (name + ".crt.previous")
    if not previous.exists():
        previous.write_bytes(cert.read_bytes())
        os.chmod(previous, 0o600)
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(d / (name + ".csr")),
            "-CA",
            str(d / "ca.crt"),
            "-CAkey",
            str(d / "ca.key"),
            "-CAcreateserial",
            "-out",
            str(cert),
            "-days",
            "365",
            "-extfile",
            str(ext),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.chmod(cert, 0o600)
    renewed.append(name)
print(
    json.dumps(
        {
            "renewed_leaf_certificates": renewed,
            "private_keys_preserved": True,
            "ca_preserved": True,
        }
    )
)
