"""Résumé du scan image : aucun signal masqué, barrière aux correctifs critiques disponibles."""

import argparse
import collections
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("reports", nargs="+")
p.add_argument("--output", default="docs/evidence/security/summary.json")
a = p.parse_args()
summary = []
blocked = []
for name in a.reports:
    report = json.loads(Path(name).read_text())
    vulnerabilities = [v for r in report.get("Results", []) for v in r.get("Vulnerabilities", [])]
    fixable = [
        {
            "id": v["VulnerabilityID"],
            "package": v["PkgName"],
            "severity": v["Severity"],
            "installed": v["InstalledVersion"],
            "fixed": v.get("FixedVersion"),
        }
        for v in vulnerabilities
        if v.get("FixedVersion") and v["Severity"] in ["HIGH", "CRITICAL"]
    ]
    entry = {
        "report": name,
        "image": report.get("ArtifactName"),
        "created_at": report.get("CreatedAt"),
        "scanner": report.get("Trivy", {}),
        "counts_by_package_finding": dict(
            collections.Counter(v["Severity"] for v in vulnerabilities)
        ),
        "unique_cve_count": len({v["VulnerabilityID"] for v in vulnerabilities}),
        "fixable_high_critical": fixable,
        "production_release_approved": False,
    }
    summary.append(entry)
    blocked.extend(fixable)
Path(a.output).write_text(
    json.dumps(
        {
            "images": summary,
            "scope": "Automated package scan, not source exploitation validation; no severity ignored",
            "known_unfixed_findings_require_human_triage": "No blanket acceptance or production approval supplied",
            "fixable_high_critical_count": len(blocked),
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"scanned_images": len(summary), "fixable_high_critical": len(blocked)}))
raise SystemExit(1 if blocked else 0)
