#!/usr/bin/env bash
# Prépare un runner neuf : secrets éphémères, données vérifiées et modèle entraîné (inclus dans l'image API).
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 scripts/init_local.py
docker compose build training
docker compose run --rm training scripts/acquire_banking77.py
docker compose run --rm training scripts/train_intent.py
