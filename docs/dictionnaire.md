# Dictionnaire BC3

Termes utiles pour comprendre et défendre le projet. Chaque entrée : définition, rôle ici, exemple si besoin.

## kind

« Kubernetes in Docker » : un cluster Kubernetes dont les nœuds sont des conteneurs Docker.
Ici : cluster local `rncp-bc3` à deux nœuds ; il remplace un cluster cloud pour la démonstration, mais tout tourne sur une seule machine.

## HPA

Horizontal Pod Autoscaler : ajoute ou retire des réplicas selon la charge.
Ici : l’API passe de 1 à 3 réplicas pendant l’essai de charge, puis revient à 1 au repos.

## Rolling update

Mise à jour progressive : les nouveaux pods démarrent avant l’arrêt des anciens.
Ici : `maxUnavailable=0`, la capacité ne baisse jamais pendant un déploiement.

## File d’échec

File où partent les messages qu’on n’arrive pas à traiter (en anglais : dead-letter queue, DLQ).
Ici : après trois tentatives d’export échouées, le message y est déplacé pour analyse au lieu de bloquer la file principale.

## Loki

Base de logs de Grafana, interrogeable par étiquettes (namespace, application, pod).
Ici : Grafana Alloy y envoie les logs des pods ; Grafana les affiche dans un panneau.

## SLI et SLO

Un SLI mesure la qualité de service (exemple : latence p95). Un SLO fixe l’objectif (exemple : p95 < 500 ms).
Ici : deux SLO, disponibilité ≥ 99 % et p95 < 500 ms, atteints sur la fenêtre de charge mesurée ; ce n’est pas un engagement mensuel (SLA).

## Ingress

Point d’entrée HTTP(S) d’un cluster Kubernetes, qui route vers les services internes.
Ici : Traefik en HTTPS sur https://localhost:8455.

## NetworkPolicy

Règle Kubernetes qui filtre le trafic réseau entre pods.
Ici : dans `bc3-prod`, seuls les pods du même namespace peuvent se connecter ; une connexion depuis `bc3-test` est bloquée.

## RBAC

Contrôle d’accès par rôles dans Kubernetes.
Ici : le compte de service de l’application ne peut pas lire les Secrets, ni ceux de son namespace, ni ceux de `bc3-prod`.

## Trivy

Scanner de vulnérabilités pour images de conteneurs.
Ici : la CI échoue si une vulnérabilité HIGH ou CRITICAL a un correctif disponible.

## GHCR

GitHub Container Registry : registre d’images lié au dépôt GitHub.
Ici : cible de publication des images par le workflow, au push sur `main` ; pas encore utilisée.

## AES-GCM

Algorithme de chiffrement qui vérifie aussi que les données n’ont pas été modifiées.
Ici : chiffre le contenu des tickets, les pièces jointes, les exports et les sauvegardes.

## Argon2id

Fonction de hachage des mots de passe, volontairement coûteuse pour freiner les attaques.
Ici : seules les empreintes des mots de passe sont stockées en base.

## CSRF

Attaque où un autre site fait envoyer une requête par le navigateur d’un utilisateur connecté.
Ici : bloquée par un jeton CSRF, le contrôle d’origine et un cookie `SameSite=Strict`.

## Terraform

Outil qui décrit une infrastructure dans des fichiers texte et la crée ou la modifie.
Ici : décrit la cible AWS (jamais appliquée) et pilote la reconstruction du cluster local.
