#!/usr/bin/env bash
# Étape images : builds multi-stage puis scan Trivy ; échec si HIGH/CRITICAL corrigeable.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose build api worker db queue-tls front browser
docker compose build admin-tools
docker compose -f infra/security.compose.yml build scanner
for spec in 'api:9' 'worker:6' 'front:4'; do
  service=${spec%%:*}
  # Rapport écrit par le shell de l'hôte : sans capacités, le scanner ne peut pas écrire dans un dossier
  # du runner Linux qui ne lui appartient pas (Docker Desktop masque ce cas sur macOS).
  docker compose -f infra/security.compose.yml run --rm -T scanner image --timeout 15m --scanners vuln --image-src docker --format json "rncp-bc3-${spec}" > "docs/evidence/security/ci-${service}.json"
done
python3 scripts/check_image_reports.py docs/evidence/security/ci-api.json docs/evidence/security/ci-worker.json docs/evidence/security/ci-front.json --output docs/evidence/security/ci-summary.json
