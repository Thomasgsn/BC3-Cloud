#!/usr/bin/env bash
# Démarrage complet en une commande : secrets locaux, modèle si absent, puis toute la pile Compose.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init_local.py
if [ ! -s models/active.json ]; then
  docker compose build training
  docker compose run --rm training scripts/acquire_banking77.py
  docker compose run --rm training scripts/train_intent.py
fi
docker compose up -d --build --wait
echo "Interface : https://localhost:8454 (CA du projet : secrets/ca.crt, compte thomas)"
