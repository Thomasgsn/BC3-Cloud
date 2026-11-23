#!/usr/bin/env bash
# Promotion : mêmes images que bc3-test, déployées dans bc3-prod avec secrets distincts,
# NetworkPolicy d'isolation et contrôles réels (santé, RBAC, trafic inter-namespace refusé).
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose build kube-tools
docker compose run --rm kube-tools -lc 'bash scripts/deploy_env.sh bc3-prod'
