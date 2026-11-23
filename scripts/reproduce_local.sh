#!/usr/bin/env bash
# Reconstruction isolée réelle ; aucune suppression de cluster ni de volume.
set -euo pipefail
cd /workspace
name=rncp-bc3-repro-clean
ctx=kind-rncp-bc3-repro-clean
export KUBECONFIG=/workspace/secrets/repro-clean-kubeconfig
mkdir -p tmp/repro-clean-project/scripts docs/evidence/reproduction
cp scripts/init_local.py tmp/repro-clean-project/scripts/init_local.py
python3 tmp/repro-clean-project/scripts/init_local.py > docs/evidence/reproduction/secrets-initialization.json
d=tmp/repro-clean-project/secrets
if ! kind get clusters | grep -qx "$name"; then
cat > tmp/repro-kind.yml <<'YAML'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: "127.0.0.1"
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30443
    hostPort: 8458
    listenAddress: "127.0.0.1"
YAML
kind create cluster --name "$name" --image kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5 --config tmp/repro-kind.yml --wait 150s
fi
docker network connect kind "$HOSTNAME" 2>/dev/null || true
kind export kubeconfig --name "$name" --internal --kubeconfig "$KUBECONFIG"
chmod 600 "$KUBECONFIG"
k() { kubectl --context "$ctx" "$@"; }
k wait --for=condition=Ready nodes --all --timeout=180s
kind load docker-image rncp-bc3-api:9 rncp-bc3-worker:6 rncp-bc3-db:1 rncp-bc3-front:4 rncp-bc3-queue-tls:1 --name "$name"
BC3_KIND_CLUSTER="$name" python3 scripts/encrypt_cluster_secrets.py
k apply -f infra/kubernetes/00-foundation.json
s() { k -n bc3-test create secret generic "$@" --dry-run=client -o yaml | k apply -f -; }
s runtime --from-file=config.json="$d/runtime/config.json" --from-file=ca.crt="$d/ca.crt"
s api-tls --from-file=server.crt="$d/api.crt" --from-file=server.key="$d/api.key"
s db-secret --from-file=db_password="$d/db_password" --from-file=server.crt="$d/db.crt" --from-file=server.key="$d/db.key"
s s3-secret --from-file=s3.json="$d/s3.json" --from-file=s3.crt="$d/s3.crt" --from-file=s3.key="$d/s3.key"
s queue-secret --from-file=server.crt="$d/queue.crt" --from-file=server.key="$d/queue.key"
s worker-tls --from-file=server.crt="$d/worker.crt" --from-file=server.key="$d/worker.key"
s front-runtime --from-file=server.crt="$d/front.crt" --from-file=server.key="$d/front.key" --from-file=ca.crt="$d/ca.crt"
s bootstrap --from-file=config.json="$d/config.json" --from-file=runtime-config.json="$d/runtime/config.json" --from-file=ca.crt="$d/ca.crt" --from-file=demo_password="$d/demo_password"
k -n bc3-test create secret tls front-tls --cert="$d/front.crt" --key="$d/front.key" --dry-run=client -o yaml | k apply -f -
k -n bc3-test create configmap trust --from-file=ca.crt="$d/ca.crt" --dry-run=client -o yaml | k apply -f -
k apply -f infra/kubernetes/10-storage.json
k -n bc3-test rollout status statefulset/db --timeout=180s
k -n bc3-test rollout status statefulset/s3 --timeout=180s
k -n bc3-test rollout status deployment/queue --timeout=180s
k apply -f infra/kubernetes/20-bootstrap.json
k -n bc3-test wait --for=condition=complete job/database-bootstrap-v6 --timeout=180s
k apply -f infra/kubernetes/30-application.json
k apply -f infra/kubernetes/40-ingress.json
for app in api worker front ingress; do k -n bc3-test rollout status deployment/"$app" --timeout=180s; done
# Les tests originaux sont réutilisés, seule la cible et le chemin de preuve sont adaptés.
BC3_KUBE_CONTEXT="$ctx" BC3_KUBE_EVIDENCE=docs/evidence/reproduction/integration python3 scripts/test_k8s_stack.py
k get nodes -o json > docs/evidence/reproduction/nodes.json
k -n bc3-test get pvc -o json > docs/evidence/reproduction/pvc.json
ip=$(docker inspect -f '{{.NetworkSettings.Networks.kind.IPAddress}}' "${name}-control-plane")
curl --fail --silent --show-error --cacert "$d/ca.crt" --resolve "localhost:30443:$ip" https://localhost:30443/health/ready > docs/evidence/reproduction/health.json
