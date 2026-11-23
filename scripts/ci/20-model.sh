#!/usr/bin/env bash
# Étape modèle : entraînement, garde-fous du registre et tests hors ligne.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose run --rm training scripts/train_intent.py
docker compose run --rm training scripts/test_model_registry.py
docker compose run --rm -e PYTHONPATH=/workspace/src training -m pytest -q -o cache_dir=/tmp/pytest-cache tests/offline
