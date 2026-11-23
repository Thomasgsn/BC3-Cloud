"""Résolution DNS limitée au conteneur de test, aucune modification du système hôte."""

import ipaddress
import json
import subprocess
from pathlib import Path

info = json.loads(subprocess.check_output(["docker", "inspect", "rncp-bc3-control-plane"]))[0]
ip = str(ipaddress.ip_address(info["NetworkSettings"]["Networks"]["kind"]["IPAddress"]))
p = Path(".env")
lines = [s for s in p.read_text().splitlines() if not s.startswith("BC3_NODE_IP=")]
p.write_text("\n".join(lines + ["BC3_NODE_IP=" + ip]) + "\n")
Path("docs/evidence/k8s/browser").mkdir(parents=True, exist_ok=True)
print(
    json.dumps(
        {
            "event": "browser_local_dns_configured",
            "node_ip": ip,
            "host_dns_modified": False,
        }
    )
)
