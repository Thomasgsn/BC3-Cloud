#!/usr/bin/env bash
# Étape qualité : données vérifiées, lint, format et audits de dépendances.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p docs/evidence/ci
python3 scripts/init_local.py
docker compose build training quality
docker compose run --rm training scripts/acquire_banking77.py
docker compose run --rm training scripts/audit_intent_data.py
docker compose run --rm quality -m ruff check --no-cache --config pyproject.toml src scripts tests
docker compose run --rm quality -m ruff format --no-cache --check --config pyproject.toml src scripts tests
docker compose run --rm quality -m pip_audit --disable-pip --no-deps --cache-dir /tmp/audit-cache -r requirements.lock -f json -o docs/evidence/ci/dependencies.json
docker compose run --rm frontend-tools 'npm audit --audit-level=high --json > /evidence/npm-audit.json'
