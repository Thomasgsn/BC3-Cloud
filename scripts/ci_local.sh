#!/usr/bin/env bash
# Chaîne locale autonome : mêmes étapes que le workflow GitHub Actions, sans publication ni cloud.
set -euo pipefail
cd "$(dirname "$0")/.."
for stage in 10-quality 20-model 30-build-scan 40-compose 50-kubernetes 60-promote-prod 70-terraform; do
  echo "{\"event\":\"ci_stage_started\",\"stage\":\"$stage\"}"
  bash "scripts/ci/$stage.sh"
done
