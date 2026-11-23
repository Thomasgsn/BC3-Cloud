#!/usr/bin/env bash
# Démarrage complet en une commande : secrets locaux, modèle si absent, puis toute la pile Compose.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init_local.py
if [ ! -s models/active.json ]; then
  docker compose build training
  docker compose run --rm training scripts/acquire_banking77.py
  docker compose run --rm training scripts/train_intent.py
  # Promeut la version retenue par l'entraînement : sans active.json, l'API refuse de suggérer.
  docker compose run --rm training scripts/promote_model.py "$(python3 -c 'import json; print(json.load(open("docs/evidence/mlops/evaluation.json"))["selected_version"])')"
fi
docker compose up -d --build --wait
echo "Interface : https://localhost:8454 (CA du projet : secrets/ca.crt, compte thomas)"
