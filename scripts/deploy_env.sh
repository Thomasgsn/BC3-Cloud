#!/usr/bin/env bash
# Promotion des mêmes images dans un namespace distinct, avec des secrets propres à cet environnement.
set -euo pipefail
cd /workspace
ns="${1:?namespace requis, ex. bc3-prod}"
bash scripts/cluster.sh connect
export KUBECONFIG=/workspace/secrets/kubeconfig
k() { kubectl --context kind-rncp-bc3 "$@"; }
# Secrets générés une fois pour cet environnement, jamais partagés avec bc3-test.
project="secrets/env/$ns"
mkdir -p "$project/scripts" && chmod 700 secrets/env "$project"
cp scripts/init_local.py "$project/scripts/init_local.py"
python3 "$project/scripts/init_local.py" > /dev/null
d="$project/secrets"
python3 scripts/render_env.py --namespace "$ns"
k get namespace "$ns" > /dev/null
s() { k -n "$ns" create secret generic "$@" --dry-run=client -o yaml | k apply -f -; }
s runtime --from-file=config.json="$d/runtime/config.json" --from-file=ca.crt="$d/ca.crt"
s api-tls --from-file=server.crt="$d/api.crt" --from-file=server.key="$d/api.key"
s db-secret --from-file=db_password="$d/db_password" --from-file=server.crt="$d/db.crt" --from-file=server.key="$d/db.key"
s s3-secret --from-file=s3.json="$d/s3.json" --from-file=s3.crt="$d/s3.crt" --from-file=s3.key="$d/s3.key"
s queue-secret --from-file=server.crt="$d/queue.crt" --from-file=server.key="$d/queue.key"
s worker-tls --from-file=server.crt="$d/worker.crt" --from-file=server.key="$d/worker.key"
s front-runtime --from-file=server.crt="$d/front.crt" --from-file=server.key="$d/front.key" --from-file=ca.crt="$d/ca.crt"
s bootstrap --from-file=config.json="$d/config.json" --from-file=runtime-config.json="$d/runtime/config.json" --from-file=ca.crt="$d/ca.crt" --from-file=demo_password="$d/demo_password"
k -n "$ns" create secret tls front-tls --cert="$d/front.crt" --key="$d/front.key" --dry-run=client -o yaml | k apply -f -
k -n "$ns" create configmap trust --from-file=ca.crt="$d/ca.crt" --dry-run=client -o yaml | k apply -f -
k apply -f "infra/kubernetes/env/$ns.json"
k -n "$ns" rollout status statefulset/db --timeout=240s
k -n "$ns" rollout status statefulset/s3 --timeout=240s
k -n "$ns" rollout status deployment/queue --timeout=240s
k -n "$ns" wait --for=condition=complete job/database-bootstrap-v6 --timeout=240s
for app in api worker front; do k -n "$ns" rollout status deployment/"$app" --timeout=240s; done
python3 scripts/check_env_isolation.py --namespace "$ns" --ca "$d/ca.crt"
