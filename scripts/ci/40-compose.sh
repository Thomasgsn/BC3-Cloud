#!/usr/bin/env bash
# Étape intégration : pile Compose complète, tests réels et navigateur.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose build browser
docker compose up -d --wait db s3 queue queue-tls
docker compose run --rm admin-tools scripts/bootstrap_database.py
docker compose run --rm admin-tools -m pytest -q -o cache_dir=/tmp/pytest-cache tests/admin
docker compose up -d --wait api worker front
docker compose run --rm tools scripts/create_user.py --username thomas --role agent --password-file /run/test-secrets/demo_password
docker compose run --rm tools -m pytest -q -o cache_dir=/tmp/pytest-cache tests/unit tests/integration
docker compose run --rm browser
