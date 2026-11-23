#!/usr/bin/env bash
# Prépare un runner neuf : secrets éphémères, données vérifiées et modèle entraîné (inclus dans l'image API).
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 scripts/init_local.py
docker compose build training
docker compose run --rm training scripts/acquire_banking77.py
docker compose run --rm training scripts/train_intent.py
# Promeut la version retenue par l'entraînement : sans active.json, l'API refuse de suggérer.
docker compose run --rm training scripts/promote_model.py "$(python3 -c 'import json; print(json.load(open("docs/evidence/mlops/evaluation.json"))["selected_version"])')"
