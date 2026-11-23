#!/usr/bin/env bash
set -euo pipefail
cd /workspace
bash scripts/cluster.sh connect
k() { kubectl --context kind-rncp-bc3 "$@"; }
k -n bc3-test create secret generic grafana-password --from-file=admin_password=secrets/grafana_password --from-file=server.crt=secrets/grafana.crt --from-file=server.key=secrets/grafana.key --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic prometheus-tls --from-file=server.crt=secrets/prometheus.crt --from-file=server.key=secrets/prometheus.key --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/50-observability.json
k -n bc3-test rollout status deployment/prometheus --timeout=180s
k -n bc3-test rollout status deployment/grafana --timeout=180s
# Logs centralisés : Loki HTTPS et collecteur Alloy (lecture des logs par l'API Kubernetes).
k -n bc3-test create secret generic loki-tls --from-file=server.crt=secrets/loki.crt --from-file=server.key=secrets/loki.key --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/55-logging.json
k -n bc3-test rollout status deployment/loki --timeout=180s
k -n bc3-test rollout status deployment/alloy --timeout=180s
