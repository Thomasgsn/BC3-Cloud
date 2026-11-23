#!/usr/bin/env bash
set -euo pipefail
cd /workspace
bash scripts/cluster.sh connect
k() { kubectl --context kind-rncp-bc3 -n bc3-test "$@"; }
k create configmap trust --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k create secret generic runtime --from-file=config.json=secrets/runtime/config.json --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k create secret generic front-runtime --from-file=server.crt=secrets/front.crt --from-file=server.key=secrets/front.key --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k create secret generic bootstrap --from-file=config.json=secrets/config.json --from-file=runtime-config.json=secrets/runtime/config.json --from-file=ca.crt=secrets/ca.crt --from-file=demo_password=secrets/demo_password --dry-run=client -o yaml | k apply -f -
k rollout restart deployment/api deployment/worker deployment/front deployment/ingress
bash scripts/install_observability.sh
k rollout restart deployment/prometheus
k rollout status deployment/prometheus --timeout=120s
k rollout status deployment/api --timeout=120s
python3 scripts/exercise_alert.py
