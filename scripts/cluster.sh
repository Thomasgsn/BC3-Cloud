#!/usr/bin/env bash
set -euo pipefail
cd /workspace
export KUBECONFIG=/workspace/secrets/kubeconfig
name=rncp-bc3
case "${1:-audit}" in
 audit)
  mkdir -p docs/evidence/k8s
  docker info --format '{"cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"os":"{{.OSType}}","architecture":"{{.Architecture}}"}' | tee docs/evidence/k8s/daemon-resources.json
  kind get clusters
  ;;
 create)
  if ! kind get clusters | grep -qx 'rncp-bc3'; then
   kind create cluster --name "$name" --image kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5 --config infra/kubernetes/kind.yml --wait 120s
  fi
  docker network connect kind "$HOSTNAME" 2>/dev/null || true
  kind export kubeconfig --name "$name" --internal --kubeconfig "$KUBECONFIG"
  chmod 600 "$KUBECONFIG"
  kubectl --context kind-rncp-bc3 get nodes -o wide
  ;;
 connect)
  docker network connect kind "$HOSTNAME" 2>/dev/null || true
  if [ ! -s "$KUBECONFIG" ]; then kind export kubeconfig --name "$name" --internal --kubeconfig "$KUBECONFIG"; fi
  [ "$(kubectl config current-context)" = kind-rncp-bc3 ] || exit 2
  ;;
 *) echo 'Sous-commande inconnue' >&2;exit 2;;
esac
