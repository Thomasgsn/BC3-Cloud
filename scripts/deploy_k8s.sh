#!/usr/bin/env bash
set -euo pipefail
cd /workspace
bash scripts/cluster.sh connect
export KUBECONFIG=/workspace/secrets/kubeconfig
k() { kubectl --context kind-rncp-bc3 "$@"; }
k apply -f infra/kubernetes/00-foundation.json
# Les valeurs restent dans des fichiers privés, jamais dans un manifeste versionné.
k -n bc3-test create secret generic runtime --from-file=config.json=secrets/runtime/config.json --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic api-tls --from-file=server.crt=secrets/api.crt --from-file=server.key=secrets/api.key --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic db-secret --from-file=db_password=secrets/db_password --from-file=server.crt=secrets/db.crt --from-file=server.key=secrets/db.key --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic s3-secret --from-file=s3.json=secrets/s3.json --from-file=s3.crt=secrets/s3.crt --from-file=s3.key=secrets/s3.key --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic queue-secret --from-file=server.crt=secrets/queue.crt --from-file=server.key=secrets/queue.key --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic front-runtime --from-file=server.crt=secrets/front.crt --from-file=server.key=secrets/front.key --from-file=ca.crt=secrets/ca.crt --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret tls front-tls --cert=secrets/front.crt --key=secrets/front.key --dry-run=client -o yaml | k apply -f -
k -n bc3-test create secret generic bootstrap --from-file=config.json=secrets/config.json --from-file=runtime-config.json=secrets/runtime/config.json --from-file=ca.crt=secrets/ca.crt --from-file=demo_password=secrets/demo_password --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/10-storage.json
k -n bc3-test rollout status statefulset/db --timeout=180s
k -n bc3-test rollout status statefulset/s3 --timeout=180s
k -n bc3-test rollout status deployment/queue --timeout=180s
k apply -f infra/kubernetes/20-bootstrap.json
k -n bc3-test wait --for=condition=complete job/database-bootstrap-v6 --timeout=180s
k -n bc3-test create secret generic worker-tls --from-file=server.crt=secrets/worker.crt --from-file=server.key=secrets/worker.key --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/30-application.json
k -n bc3-test rollout status deployment/api --timeout=180s
k -n bc3-test rollout status deployment/front --timeout=180s
k -n bc3-test rollout status deployment/worker --timeout=180s
k -n bc3-test get pods,pvc,svc,hpa
