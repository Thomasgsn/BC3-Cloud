#!/usr/bin/env bash
# Étape IaC : Terraform AWS formaté, validé et testé avec provider simulé (aucun apply).
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose build kube-tools
docker compose run --rm kube-tools -lc 'terraform -chdir=infra/terraform/aws init -backend=false -input=false && terraform -chdir=infra/terraform/aws fmt -check && terraform -chdir=infra/terraform/aws validate && terraform -chdir=infra/terraform/aws test'
