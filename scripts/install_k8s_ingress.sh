#!/usr/bin/env bash
set -euo pipefail
cd /workspace
bash scripts/cluster.sh connect
k() { kubectl --context kind-rncp-bc3 "$@"; }
k -n bc3-test create configmap trust --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/40-ingress.json
k apply -f infra/kubernetes/metrics-server-kind.yml
k -n bc3-test rollout status deployment/ingress --timeout=180s
k -n kube-system rollout status deployment/metrics-server --timeout=180s
k wait --for=condition=Available apiservice/v1beta1.metrics.k8s.io --timeout=180s
k get apiservice v1beta1.metrics.k8s.io
