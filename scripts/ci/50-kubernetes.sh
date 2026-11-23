#!/usr/bin/env bash
# Étape déploiement : cluster kind dédié, namespace de test, tests, sauvegarde.
# La promotion vers bc3-prod est une étape distincte (60-promote-prod.sh).
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose build kube-tools
docker compose run --rm kube-tools -lc 'bash scripts/cluster.sh create && bash scripts/load_k8s_images.sh && bash scripts/deploy_k8s.sh && bash scripts/install_k8s_ingress.sh && bash scripts/install_observability.sh && python3 scripts/test_k8s_stack.py && python3 scripts/check_logging.py && python3 scripts/exercise_backup_k8s.py'
