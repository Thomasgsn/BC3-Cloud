# Checklist BC3

Statuts : **À faire**, **En cours**, **Fait** (coché seulement avec une preuve). Ordre = priorité.

## 1. À faire personnellement (Thomas)

| # | Action | Pourquoi | Comment | Preuve à garder | Statut |
|---|---|---|---|---|---|
| 1 | Obtenir l’accord de l’enseignant sur le domaine (support bancaire) | Le sujet exige la validation du domaine | Envoyer une description courte : tickets, pièces jointes, exports asynchrones, 4 entités | Réponse écrite | À faire |
| 2 | Pousser le dépôt sur GitHub et faire passer le workflow au vert | Le sujet demande un pipeline sur push et des images publiées ; l’axe CI/CD vaut 20 points | Commiter (vérifier que `secrets/`, `.env`, `*.tfstate`, `tmp/` ne sont pas suivis), pousser sur `main`, suivre l’onglet Actions | URL du dépôt, lien du run vert, paquets GHCR visibles | À faire |
| 3 | Ajouter une règle d’approbation sur l’environnement GitHub `production` | Montre une promotion contrôlée vers la prod | Settings → Environments → production → Required reviewers | Capture de la règle | À faire |
| 4 | Vérifier les modalités : certification cloud C6.1–C6.4 | Le référentiel associe ces compétences à une certification de fournisseur cloud | Demander à l’école quelle certification est attendue, s’inscrire, passer l’examen | Attestation | À faire |
| 5 | Relire rapport, support et déclaration d’usage de l’IA | Contenu assisté par IA à défendre seul ; vérifier le règlement de l’école | Lire `docs/rapport.md`, le PDF et le PPTX ; vérifier les arbitrages | Version relue | À faire |
| 6 | Répéter la démonstration et l’oral | Évaluation orale | Scaling, panne, rollback, alerte, restauration, logs, isolation prod | Notes de répétition | À faire |
| 7 | Remettre le rendu | Évaluation | Lien du dépôt et rapport sur la plateforme de l’école | Accusé de dépôt | À faire |

## 2. À autoriser ou fournir pour qu’un agent continue

| # | Action | Pourquoi | Comment | Statut |
|---|---|---|---|---|
| 8 | Autoriser le commit et le push par l’agent, ou les faire vous-même | Les consignes actuelles les interdisent | Le dire explicitement et donner l’URL du dépôt distant | À faire |
| 9 | Décider d’un déploiement AWS réel ou demander si le local suffit | Un `terraform apply` coûte de l’argent (environ 251 USD par mois en continu, bien moins pour quelques heures) | Demander à l’école ; si oui, fournir un compte avec plafond de budget et des identifiants hors chat | À faire |
| 10 | Trier les avis HIGH sans correctif (47 API/worker, 106 sauvegarde) | Accepter un risque est une décision humaine | Lire `docs/evidence/security/followup-*.json`, décider | À faire |
| 11 | Approuver les durées de conservation proposées | Une purge de données ne doit pas être décidée par l’agent | Valider ou modifier les durées proposées | À faire |

## 3. Reste technique (automatisable)

| # | Action | Pourquoi | Statut |
|---|---|---|---|
| 12 | Corriger le workflow si le premier run GitHub échoue | Il n’a jamais tourné sur un runner GitHub | Bloqué par l’action 2 |
| 13 | Rejouer une campagne de charge sur la version 1.3.0 | Les mesures de charge datent de la version 1.2.1 | À faire |
| 14 | Appliquer Terraform AWS et rejouer les tests sur EKS | Stockage objet cloud et cluster managé non démontrés | Bloqué par l’action 9 |

## 4. Améliorations facultatives

- Traces distribuées (OpenTelemetry).
- Déploiement canary ou blue/green.
- Terraform local avec providers `kind` et `kubernetes` (arbitrage expliqué dans le rapport).

## Déjà fait (preuves)

- [x] Pile Compose en une commande (`scripts/up.sh`) et 32 tests Compose — `docs/evidence/followup/compose-up-20261123.log`, `docs/evidence/followup/compose/`
- [x] Déploiement Kubernetes, HPA, panne, rollback — `docs/evidence/k8s/resilience-load.json`
- [x] Promotion `bc3-prod` et isolation réseau vérifiée — `docs/evidence/environments/bc3-prod.json`
- [x] Logs centralisés dans Loki — `docs/evidence/k8s/logging.json`
- [x] Alerte déclenchée puis résolue — `docs/evidence/k8s/alert-cycle.json`
- [x] Sauvegarde et restauration — `docs/evidence/k8s/backup-restore.json`
- [x] Deux optimisations FinOps mesurées — `docs/evidence/finops/`
- [x] Rapport PDF (13 pages) et support (14 diapositives) — `output/`
