# BC3 — Support bancaire cloud-native

Thomas Gassmann · RNCP40875, bloc 3 · travail individuel.

Application web de support client bancaire (tickets, pièces jointes privées, exports asynchrones), déployée sur Kubernetes, livrée par CI/CD, décrite en Terraform, supervisée, sécurisée et optimisée. Le fonctionnel est volontairement simple ; l’effort porte sur la chaîne d’exploitation.

**Point à valider** : le domaine applicatif doit être validé par l’enseignant.

## Documents du rendu

| Document | Contenu |
|---|---|
| [docs/rapport.md](docs/rapport.md) | Besoin, architecture, choix, résultats, limites, correspondance RNCP et ISO 27001 |
| [Rapport PDF](output/pdf/rapport-bc3-thomas-gassmann.pdf) | Rapport de 13 pages (format demandé : 10 à 15 pages) |
| [Support de soutenance](output/presentations/soutenance-bc3-thomas-gassmann.pptx) | 14 diapositives éditables |
| [docs/dictionnaire.md](docs/dictionnaire.md) | Termes techniques expliqués |
| `docs/evidence/` | Preuves : tests, charge, alertes, sauvegardes, scans, FinOps, environnements |

## Composants

| Rôle | Composant |
|---|---|
| Front-end | Vue/TypeScript servi par Nginx non-root |
| Back-end | API FastAPI sans état, sessions en base |
| Base relationnelle | PostgreSQL 17 |
| Stockage objet | SeaweedFS, API S3 |
| File de messages et worker | ElasticMQ (API SQS) derrière un relais TLS, worker d’export dédié |
| Orchestration | Kubernetes [kind](docs/dictionnaire.md#kind) à deux nœuds, Ingress Traefik |
| Supervision | Prometheus, Grafana, [Loki](docs/dictionnaire.md#loki) et Alloy |
| IaC | Terraform (AWS préparé, reconstruction locale) |

## Lancer en local (Compose)

Prérequis : Docker et Compose, Python 3, OpenSSL ; environ 12 Gio de RAM pour Docker ; ports 8453 à 8458 libres. Depuis `bc3/` :

```sh
bash scripts/up.sh
```

Cette commande crée les secrets locaux (jamais versionnés), entraîne le modèle d’intention s’il manque, construit les images et lance toute la pile. La base et le compte de démonstration sont initialisés par les services Compose `bootstrap` et `demo-user`.

- Interface : https://localhost:8454 (compte `thomas`, mot de passe dans `secrets/demo_password`).
- La CA du projet est `secrets/ca.crt` ; elle n’est pas ajoutée à la confiance du système.

## Déployer sur Kubernetes

```sh
bash scripts/ci/50-kubernetes.sh
bash scripts/ci/60-promote-prod.sh
```

- L’étape 50 crée le cluster kind `rncp-bc3`, charge les images, déploie dans le namespace `bc3-test`, installe Ingress, Prometheus, Grafana, Loki et Alloy, puis lance les tests du cluster, le contrôle des logs et une sauvegarde/restauration.
- L’étape 60 déploie les mêmes images dans `bc3-prod` avec des secrets distincts et vérifie l’isolation réseau et RBAC.
- Interface : https://localhost:8455.

Grafana et Prometheus en local :

```sh
docker compose run --rm kube-tools -lc 'python3 scripts/connect_ui.py'
docker compose --env-file .env -f infra/kubernetes/ui.compose.yml up -d grafana prometheus
```

Grafana : https://localhost:8456 (compte `thomas`, mot de passe dans `secrets/grafana_password`). Prometheus : https://localhost:8457.

## Tests et CI/CD

```sh
bash scripts/ci_local.sh
```

La chaîne locale enchaîne les mêmes scripts que les jobs GitHub Actions (`scripts/ci/`) :

| Étape | Contenu |
|---|---|
| `10-quality.sh` | Lint, format, audits pip et npm, données vérifiées |
| `20-model.sh` | Entraînement, registre de modèles, tests hors ligne |
| `30-build-scan.sh` | Builds multi-stage, scan Trivy bloquant |
| `40-compose.sh` | Pile Compose, tests d’intégration, navigateur |
| `50-kubernetes.sh` | Déploiement `bc3-test`, tests, logs, sauvegarde |
| `60-promote-prod.sh` | Promotion dans `bc3-prod` et contrôles d’isolation |
| `70-terraform.sh` | Terraform AWS : fmt, validate, tests simulés |

Le workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) publie aussi les images sur GHCR au push sur `main`. Il est vert sur GitHub depuis le 24 novembre ([run 45270784327](https://github.com/Thomasgsn/BC3-Cloud/actions/runs/45270784327)).

## Terraform

- `infra/terraform/aws` : VPC, EKS, RDS, S3, SQS et file d’échec, KMS, IAM, ECR. Validé et testé avec un provider simulé ; **aucun `apply`** (budget non autorisé).
- `infra/terraform/local` : reconstruction complète d’un cluster neuf, avec ses secrets et volumes :

```sh
docker compose run --rm kube-tools -lc 'terraform -chdir=infra/terraform/local init -backend=false && terraform -chdir=infra/terraform/local apply'
```

- `scripts/render_cloud.py` prépare les manifests de la cible AWS à partir des sorties Terraform ; il n’appelle aucun service AWS.

## Sauvegarde

```sh
docker compose run --rm admin-tools scripts/backup.py --verify-restore
```

Dump PostgreSQL chiffré, déposé dans le stockage objet, puis restauré dans une base neuve pour comparaison, sans toucher à la base active.

## Livrables générés

| Livrable | Générateur |
|---|---|
| Rapport PDF | `scripts/build_report.py` (ReportLab, pypdf, polices Arial du système) |
| Support PPTX | `scripts/build_deck.mjs` (bibliothèque de présentation du runtime Codex, chemins à adapter) |
| Archive locale | `python3 scripts/package_delivery.py` |

## Usage de l’IA

J’ai utilisé des assistants d’IA générative (Codex, puis Claude pour la relecture finale) pour la réécriture des textes, la recherche et le sourçage des références et la génération des documents. Les chiffres cités viennent des exécutions du projet et renvoient à `docs/evidence/`.

## Limites principales

- Aucun déploiement cloud réel : AWS est décrit et testé hors ligne seulement.
- Le déploiement continu cible le cluster kind éphémère du runner, pas un cluster persistant.
- Cluster local sur un seul hôte : pas de haute disponibilité physique.
- Avis de sécurité HIGH sans correctif à trier avant toute production.
