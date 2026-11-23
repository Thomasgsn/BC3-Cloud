#!/usr/bin/env bash
# Préparation à relire avec budget/identité/registre. Pas appelé par la CI locale.
set -euo pipefail
if [ "${BC3_AUTHORIZE_PUBLICATION:-no}" != yes ]; then
  echo 'Publication distante non autorisée dans cette livraison locale.' >&2
  exit 2
fi
: "${BC3_ECR_API:?registre API approuvé requis}"
: "${BC3_ECR_FRONT:?registre front approuvé requis}"
: "${BC3_ECR_WORKER:?registre worker approuvé requis}"
: "${BC3_RELEASE_TAG:?tag immuable approuvé requis}"
# Les credentials ECR doivent provenir de la session IAM/OIDC autorisée, jamais du code.
docker tag rncp-bc3-api:9 "$BC3_ECR_API:$BC3_RELEASE_TAG"
docker tag rncp-bc3-front:4 "$BC3_ECR_FRONT:$BC3_RELEASE_TAG"
docker tag rncp-bc3-worker:6 "$BC3_ECR_WORKER:$BC3_RELEASE_TAG"
docker push "$BC3_ECR_API:$BC3_RELEASE_TAG"
docker push "$BC3_ECR_FRONT:$BC3_RELEASE_TAG"
docker push "$BC3_ECR_WORKER:$BC3_RELEASE_TAG"
