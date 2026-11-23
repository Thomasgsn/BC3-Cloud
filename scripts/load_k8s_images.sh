#!/usr/bin/env bash
set -euo pipefail
cd /workspace
bash scripts/cluster.sh connect
kubectl --context kind-rncp-bc3 wait --for=condition=Ready nodes --all --timeout=180s
kind load docker-image rncp-bc3-api:9 rncp-bc3-backup:5 rncp-bc3-worker:6 rncp-bc3-db:1 rncp-bc3-front:4 rncp-bc3-queue-tls:1 --name rncp-bc3
python3 scripts/encrypt_cluster_secrets.py
