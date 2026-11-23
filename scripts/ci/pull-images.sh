#!/usr/bin/env bash
# Récupère les images publiées pour ce commit et leur redonne les tags locaux attendus par Compose et kind.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${REGISTRY_PREFIX:?REGISTRY_PREFIX requis}" "${IMAGE_TAG:?IMAGE_TAG requis}"
grep -v '^#' scripts/ci/images.txt | while read -r spec; do
  name=${spec%%:*}
  docker pull "${REGISTRY_PREFIX}/rncp-bc3-${name}:${IMAGE_TAG}"
  docker tag "${REGISTRY_PREFIX}/rncp-bc3-${name}:${IMAGE_TAG}" "rncp-bc3-${spec}"
done
