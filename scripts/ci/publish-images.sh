#!/usr/bin/env bash
# Publication sur un registre : réservée à la CI (push sur main), jamais lancée par la chaîne locale.
# Requiert REGISTRY_PREFIX (ex. ghcr.io/proprietaire), IMAGE_TAG (SHA Git) et une session docker login active.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${REGISTRY_PREFIX:?REGISTRY_PREFIX requis}" "${IMAGE_TAG:?IMAGE_TAG requis}"
[ "${CI:-}" = true ] || { echo 'Publication refusée hors CI.' >&2; exit 2; }
grep -v '^#' scripts/ci/images.txt | while read -r spec; do
  name=${spec%%:*}
  for tag in "$IMAGE_TAG" "${spec#*:}"; do
    docker tag "rncp-bc3-${spec}" "${REGISTRY_PREFIX}/rncp-bc3-${name}:${tag}"
    docker push "${REGISTRY_PREFIX}/rncp-bc3-${name}:${tag}"
  done
done
