"""Rapport BC3 de 15 pages, construit à partir des preuves locales réellement produites."""

import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

R = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((R / path).read_text())


ci = load("docs/evidence/ci/full-run.json")
if ci["exit_code"] != 0:
    raise RuntimeError("La chaîne complète finale doit réellement réussir avant le rapport final")
ml = load("docs/evidence/mlops/evaluation.json")
protocol = load("docs/evidence/mlops/protocol.json")
charge = load("docs/evidence/k8s/load-result.json")
resilience = load("docs/evidence/k8s/resilience-load.json")
charge_130 = load("docs/evidence/k8s/load-result-1.3.0.json")
resilience_130 = load("docs/evidence/k8s/resilience-load-1.3.0.json")
cost = load("docs/evidence/finops/cost-scenario.json")
backup = load("docs/evidence/k8s/backup-restore.json")
backup_size = format(backup["bytes"], ",").replace(",", " ")
security = load("docs/evidence/security/ci-summary.json")
tests = load("docs/evidence/k8s/integration/pytest.json")
browser = load("docs/evidence/browser/checks.json")


def percent(x):
    return f"{100 * x:.2f}".replace(".", ",") + " %"


P = []


def page(title, paragraphs, rows=None, image=None, evidence="", screenshots=()):
    P.append(
        {
            "title": title,
            "paragraphs": paragraphs,
            "table": rows,
            "image": image,
            "evidence": evidence,
            "screenshots": screenshots,
        }
    )


followup = load("docs/evidence/followup/kubernetes/pytest.json")
snapshot = load("docs/evidence/followup/backup-snapshot-regression.json")
if followup["exit_code"] != 0 or not snapshot["write_absent_from_restored_snapshot"]:
    raise RuntimeError("Le rapport requiert les vraies preuves Kubernetes et snapshot 1.3.0")

page(
    "Contexte, objectif et usage de l’IA",
    [
        "L’objectif est de déployer puis d’exploiter une application web à trois niveaux sur Kubernetes, en mettant l’effort sur la chaîne qui l’entoure : conteneurs, orchestration, automatisation, supervision, sécurité et FinOps. Le fonctionnel reste volontairement réduit.",
        "Domaine retenu : le support client d’une banque. Un client ouvre un ticket et joint un justificatif PDF ou PNG ; un agent suit et fait évoluer le statut ; chacun peut demander un export CSV des tickets auxquels il a accès, produit en tâche de fond. Quatre entités (utilisateur, ticket, pièce jointe, export) suffisent à couvrir le téléversement vers le stockage objet et le traitement asynchrone exigés par le sujet. Le domaine doit encore être validé par l’enseignant.",
        "Pourquoi la banque : ce contexte justifie des exigences fortes de confidentialité (pièces privées, chiffrement applicatif, cloisonnement strict entre clients) et donne de la matière au volet sécurité sans alourdir le métier.",
        "Tout est exécuté localement : Docker Compose pour le développement, cluster Kubernetes kind pour l’exploitation. L’infrastructure AWS cible est décrite en Terraform et validée, mais pas appliquée, faute de budget autorisé. Le rapport sépare ce qui a été exécuté et mesuré de ce qui est seulement préparé.",
        "Usage de l’IA : j’ai utilisé des assistants d’IA générative (Codex, puis Claude pour la relecture finale) pour la réécriture des textes, la recherche et le sourçage des références (documentation des outils, catalogues de prix AWS, jeu de données) et la génération du rapport et du support. Les chiffres cités proviennent des exécutions du projet et renvoient chacun à un fichier de preuve.",
    ],
    evidence="docs/rapport.md ; docs/evidence/",
)
page(
    "Exigences et couverture de la grille",
    [
        "Le sujet impose front, back, base relationnelle, stockage objet, file de messages et worker, puis évalue sur 100 points la chaîne d’exploitation. Le tableau résume, axe par axe, ce qui est démontré et l’écart qui reste.",
        "J’ai ajouté une brique hors grille : une suggestion d’intention entraînée sur le jeu public BANKING77. Elle répond à la compétence C7.4 (MLOps) du référentiel, que le helpdesk seul ne couvre pas. Arbitrage assumé : un build plus long et un service de plus, en échange d’un cycle complet entraînement, évaluation, promotion et rollback.",
        "Les seuils chiffrés (p95 < 500 ms, disponibilité ≥ 99 %, seuil de promotion du modèle) sont des objectifs que je me suis fixés, pas des valeurs imposées. Les compétences C6.1 à C6.4 demandent en plus une certification de fournisseur cloud, distincte de ce projet.",
    ],
    rows=[
        ["Axe (points)", "Démontré", "Écart restant"],
        [
            "Conteneurisation (20)",
            "Images multi-stage non-root, Compose en une commande",
            "Images publiées sur GHCR par le workflow GitHub",
        ],
        [
            "Kubernetes (20)",
            "HPA 1→3, panne, rolling, rollback, PVC",
            "Objet S3-compatible local, pas cloud",
        ],
        [
            "CI/CD et IaC (20)",
            "Pipeline découpé, promotion test → prod, Terraform AWS validé",
            "Workflow vert sur GitHub ; pas d’apply AWS",
        ],
        [
            "Observabilité (10)",
            "Prometheus/Grafana, logs Loki, alerte testée, SLO mesurés",
            "Pas de traces distribuées (facultatives)",
        ],
        [
            "Sécurité (10)",
            "TLS, AES-GCM, moindre privilège, scans, prod isolée",
            "Avis HIGH sans correctif à trier",
        ],
        ["FinOps (10)", "Coût AWS chiffré, deux optimisations mesurées", "Aucune facture réelle"],
    ],
    evidence="docs/rapport.md",
)
page(
    "Architecture et choix techniques",
    [
        "Vue/TypeScript/Vite produit une interface statique servie par Nginx non-root, séparée de l’API. Traefik expose l’Ingress en HTTPS. FastAPI conserve l’état métier et les sessions en PostgreSQL : l’API est sans état et peut tourner en plusieurs réplicas sans affinité.",
        "PostgreSQL porte les transactions, les relations et le verrouillage des jobs. SeaweedFS fournit le stockage objet par l’API S3 ; ElasticMQ, derrière un sidecar TLS, fournit l’API SQS. Le worker est une image distincte : il lit un identifiant de job, récupère les tickets autorisés et écrit un CSV privé chiffré.",
        "Arbitrages. FastAPI plutôt que Django : une API légère avec validation stricte par Pydantic, sans ORM ni back-office inutiles ici. SQS plutôt que RabbitMQ : le même protocole qu’en cible AWS, donc aucun changement de client au passage au cloud. SeaweedFS et ElasticMQ plutôt qu’un vrai compte AWS : des briques locales gratuites qui parlent les protocoles S3 et SQS. Le prix : elles ne reproduisent ni la durabilité ni la disponibilité d’AWS.",
        "Compose sert au développement et aux tests rapides ; Kubernetes sert à démontrer l’exploitation (scaling, pannes, déploiements). Les deux profils exécutent la même suite de tests d’intégration.",
    ],
    rows=[
        ["Flux", "Transport et état"],
        ["Navigateur / Ingress / front / API", "HTTPS, origines et sessions contrôlées"],
        ["API / SQL", "TLS verify-full, relations et sessions"],
        ["API / objet", "HTTPS, clés UUID et AES-GCM"],
        ["API / file / worker", "SQS HTTPS, reprise depuis SQL"],
        ["Prometheus / Grafana", "HTTPS et datasource vérifiée"],
    ],
    evidence="docs/rapport.md (diagrammes Mermaid) ; compose.yml ; infra/kubernetes/",
)
page(
    "Modèle de données et contrôles d’accès",
    [
        "Quatre entités : utilisateur, ticket, pièce jointe et export, complétées par les tables techniques sessions, audit et schema_migrations. Chaque ticket porte une version : une modification fondée sur une version périmée renvoie 409. Un demandeur ne peut pas modifier les statuts réservés aux agents.",
        "Les mots de passe sont hachés en Argon2id ; les sessions opaques d’une heure sont stockées hachées. Le cookie __Host-bc3 est Secure, HttpOnly et SameSite=Strict ; un jeton CSRF et le contrôle d’origine protègent les mutations. La limitation des échecs de connexion freine les essais de mots de passe, au prix d’un verrouillage temporaire possible d’un identifiant connu.",
        "Titres et textes des tickets sont chiffrés en AES-GCM, avec un contexte lié au champ et à l’identifiant. Arbitrage : les identifiants, statuts et dates restent en clair pour permettre les requêtes et les index ; seul le contenu sensible est chiffré. Les clés restent hors base et hors archive.",
        "Le rôle SQL bc3_app ne peut créer ni base, ni rôle, ni schéma ; les identités S3 administrateur et application sont distinctes. L’API vérifie l’autorisation avant toute lecture d’objet ou de job et répond 404 en accès croisé. Depuis la version 1.3.0, la base est vérifiée avec sa propre CA et son nom d’hôte ; une CA inconnue ou absente est refusée.",
    ],
    rows=[
        ["Entité", "Garanties principales"],
        ["User / sessions", "Rôle, hash mot de passe, jeton haché et expiration"],
        ["Ticket", "FK propriétaire/agent, statut borné, version, contenu chiffré"],
        ["Attachment", "FK ticket, clé privée unique, type/taille/SHA"],
        ["Export", "État durable, lease, tentatives, clé et SHA"],
    ],
    evidence="src/rncp_bc3/db.py ; tests/integration/ ; evidence/followup/",
)
page(
    "Objets privés et traitement asynchrone",
    [
        "Le téléversement accepte PDF et PNG jusqu’à 5 Mio, avec contrôle de signature. Le nom de stockage est un UUID, jamais le nom fourni par l’utilisateur. Le téléchargement force une pièce jointe. Ce filtre ne remplace pas un antivirus. Si l’écriture SQL échoue, l’objet créé est retiré ; si un objet manque, l’API renvoie une erreur explicite.",
        "Une demande d’export est d’abord enregistrée en SQL, puis annoncée dans la file. Si la file est indisponible, le worker retrouve les jobs en attente et les réémet. FOR UPDATE SKIP LOCKED et un bail de 60 secondes empêchent deux workers de traiter le même job ; un message reçu deux fois ne produit pas de second export.",
        "Trois tentatives au plus, puis statut failed et passage en file d’échec (DLQ). Le CSV neutralise les cellules commençant par une formule et se limite à 5 000 lignes dans ce profil.",
        "Les tests d’intégration tournent contre les vrais services : cloisonnement entre comptes, téléchargement identique à l’octet près, contenu du CSV, doublon sans nouveau traitement, trois échecs S3 réels puis refus d’une quatrième exécution.",
    ],
    image="docs/evidence/browser/exports-desktop.png",
    evidence="evidence/k8s/integration/{stack-flow,deadletter,bounded-retries}.json ; README.md",
)
page(
    "Kubernetes et résilience mesurée",
    [
        "Cluster kind à deux nœuds, avec un kubeconfig dédié au projet. Les images sont chargées localement. Deployments, Services, Ingress, ConfigMaps, Secrets, PVC, requests/limits, HPA et PDB sont appliqués. Limite : les deux nœuds partagent le même hôte, ce n’est pas de la haute disponibilité physique.",
        "Stratégie de déploiement : rolling update avec maxUnavailable=0, pour ne jamais réduire la capacité pendant une mise à jour. Canary et blue/green, facultatifs dans le sujet, n’apportaient pas assez sur un cluster mono-hôte pour justifier leur complexité.",
        f"Campagne de charge sur la version 1.2.1 : {charge['requests']} requêtes, disponibilité {percent(charge['availability_fraction'])}, p95 {charge['latency_p95_seconds']:.3f} s, {charge['invalid_or_failed_responses']} échec. Le HPA monte à {resilience['max_hpa_current']} réplicas ; après suppression d’un pod, le service revient en {resilience['pod_recovery_seconds']:.2f} s, mesuré par scrutation toutes les dix secondes environ. Une configuration volontairement invalide est rejetée pendant que les anciens pods restent sains, puis rollback et rolling réussissent.",
        f"Campagne rejouée le 23 novembre sur la version 1.3.0 : {charge_130['requests']} requêtes, disponibilité {percent(charge_130['availability_fraction'])}, p95 {charge_130['latency_p95_seconds']:.3f} s, HPA à {resilience_130['max_hpa_current']} réplicas, reprise en {resilience_130['pod_recovery_seconds']:.2f} s, rollback de configuration réussi. La pile BC1 tournait sur la même machine : la latence est plus haute mais reste sous l’objectif de 500 ms.",
        "Un essai précédent donnait un p95 de 680 ms. Le profilage a montré 400 lectures de clé par réponse de 200 tickets. La version 1.2.1 lit la clé une fois par réponse, sans cache entre requêtes ; dix conversions passent de 0,422 à 0,052 s, avec un test de régression rouge puis vert.",
    ],
    evidence="evidence/k8s/load-result*.json ; resilience-load*.json ; diagnosis/",
)
page(
    "Supervision, alertes et sauvegardes",
    [
        "Prometheus collecte en HTTPS les métriques de l’API et du worker. Grafana provisionne un tableau de bord : disponibilité, p95, débit, âge des jobs, résultats d’export et CPU. Les métriques n’exposent ni texte de ticket ni identifiant de connexion. Les événements de sécurité (connexions, créations) vont dans une table d’audit SQL. Les logs JSON des pods sont centralisés dans Loki (HTTPS, rétention 72 h) par Grafana Alloy, qui les lit via l’API Kubernetes sans montage hôte ; un panneau Grafana les affiche et la source Loki est vérifiée.",
        "SLO retenus : disponibilité en lecture ≥ 99 % et p95 < 500 ms. Ils sont atteints sur la fenêtre de charge mesurée ; ce n’est pas une SLA mensuelle. L’inférence du modèle a sa propre mesure, car elle peut prendre plusieurs secondes à froid.",
        "L’alerte APIUnavailable a été déclenchée en arrêtant volontairement l’API : firing après 31,21 s, résolue 47,16 s après la remise en service. Un premier essai, lancé pendant un déploiement, avait expiré : l’essai est désormais isolé de toute autre mutation.",
        f"Sauvegarde : dump PostgreSQL chiffré puis déposé dans le stockage objet, restauré dans une base neuve sans toucher à la base active. Une restauration a révélé 19 exports actifs contre 18 restaurés : une écriture était arrivée après le dump. Le dump et les comptages de contrôle partagent désormais le même snapshot REPEATABLE READ ; dernier essai Kubernetes {backup_size} octets, {len(backup['restoration']['table_counts'])} tables comparées.",
        "La clé AES doit être sauvegardée à part, par un canal privé : l’archive de code seule ne permet pas de déchiffrer une ancienne base.",
    ],
    evidence="evidence/k8s/{monitoring-ready,alert-cycle,backup-restore}.json ; evidence/followup/",
)
page(
    "Automatisation et infrastructure déclarative",
    [
        "Le pipeline est découpé en jobs GitHub Actions qui appellent chacun un script de scripts/ci/, rejoués dans le même ordre par la chaîne locale : lint et audits ; modèle et tests hors ligne ; builds multi-stage et scan Trivy bloquant ; publication sur GHCR avec le SHA du commit ; intégration Compose avec ces images ; déploiement dans bc3-test puis promotion des mêmes images dans bc3-prod.",
        f"Dernière exécution complète : code de sortie {ci['exit_code']}. Le premier essai avait échoué après un backup pourtant réussi, car kubectl cp ne peut rien extraire d’un pod terminé ; le résultat est désormais lu dans les logs du job. En version 1.3.0, 32 tests passent sur Compose, 32 dans Kubernetes et 34 tests unitaires et hors ligne.",
        "Les pull requests exécutent lint, tests, build et scan ; la publication et le déploiement ne se font que sur push vers main, avec droits minimaux par job. actionlint ne relève aucune erreur et les étapes de déploiement et de promotion ont tourné localement sur un cluster recréé de zéro. Le 24 novembre, le workflow est passé au vert sur GitHub (run 45270784327) : images publiées sur GHCR, intégration Compose, déploiement bc3-test et promotion bc3-prod sur un cluster kind éphémère du runner. Les quatre runs précédents ont révélé des écarts macOS/Linux, corrigés : écriture du rapport Trivy, lecture des secrets par SeaweedFS, promotion du modèle, CA de Grafana.",
        "Terraform AWS décrit VPC, sous-réseaux privés, NAT, EKS avec nœuds chiffrés, RDS Multi-AZ chiffré par KMS, S3 privé et versionné, SQS avec DLQ, IAM/Pod Identity et ECR. init, validate et des tests avec provider simulé passent ; un générateur produit 27 manifestes cloud acceptés en dry-run par Kubernetes. Aucune ressource AWS n’a été créée.",
        "Arbitrage : la reconstruction locale passe par un terraform_data qui appelle le script de reconstruction (cluster, secrets et volumes neufs, 17 tests). Des providers kind et kubernetes ont été écartés : kubernetes_manifest doit joindre le cluster dès le plan, ce qui empêche une création depuis zéro en une passe, et le chargement des images comme le chiffrement d’etcd exigeraient des local-exec.",
    ],
    evidence="evidence/ci/full-run.* ; evidence/ci/github-run-45270784327.json ; evidence/reproduction/ ; infra/terraform/ ; .github/workflows/ci.yml",
)
page(
    "Captures : CI et charge",
    [
        "Captures réalisées le 24 novembre sur mon poste. En haut, le run n°9 du workflow sur le commit 18e21c6 : les cinq jobs réussissent en 12 min 43 s. En bas, l’essai de charge rejoué sur le cluster kind : le HPA demande 3 réplicas après 31 s, un pod API est supprimé, une configuration invalide est annulée par rollback, puis le redémarrage progressif se termine sous charge.",
    ],
    screenshots=(
        ("docs/evidence/screenshots/01-github-actions-run-9.png", "Run GitHub Actions n°9"),
        (
            "docs/evidence/screenshots/02-charge-hpa-rollback-1.png",
            "Essai de charge : HPA, suppression de pod et rollback",
        ),
    ),
    evidence="evidence/screenshots/ (manifest.json) ; evidence/k8s/",
)
page(
    "Captures : Grafana et Loki",
    [
        "Pendant le même essai, le tableau de bord Exploitation et SLO montre le débit monter à environ 20 requêtes par seconde et la latence p95 passer par un pic proche de 0,9 s avant de redescendre vers 0,1 s. Le panneau Loki affiche les redémarrages des pods API et la fin d’un export par le worker. Les règles d’alerte étaient chargées mais inactives à ce moment ; le cycle de l’alerte est prouvé séparément.",
    ],
    screenshots=(
        (
            "docs/evidence/screenshots/04-grafana-exploitation-slo.png",
            "Grafana : tableau de bord Exploitation et SLO",
        ),
        (
            "docs/evidence/screenshots/05-grafana-logs-loki.png",
            "Grafana : logs API et worker (Loki)",
        ),
    ),
    evidence="evidence/screenshots/ (manifest.json) ; evidence/k8s/alert-cycle.json",
)
page(
    "MLOps et limites du benchmark",
    [
        "Jeu BANKING77 original (Casanueva et al., 2020, licence CC BY 4.0), à révision Git figée et fichiers vérifiés par SHA : 10 003 lignes d’entraînement, 3 080 de test, 77 intentions en anglais.",
        f"Protocole : {protocol['removed_train_rows_matching_official_test']} phrases d’entraînement identiques au test sont retirées ; {protocol['fit_rows']} lignes d’apprentissage et {protocol['validation_rows']} de validation, sans groupe partagé. Modèle TF-IDF (uni- et bigrammes) puis LinearSVC ; C=0,25 et C=1 comparés sur le F1 macro de validation uniquement.",
        f"C=1 est figé avant le test officiel : accuracy {percent(ml['test_accuracy'])}, F1 macro {ml['test_macro_f1']:.4f}, top 3 {percent(ml['test_top3_accuracy'])}. Aucun réajustement sur le test.",
        "Promotion automatique seulement si le F1 de validation dépasse 0,75, s’il ne recule pas de plus de 0,02 face au modèle en place et si le SHA est exact. Deux promotions, un rollback servi par une vraie inférence de l’ancienne version, un refus pour régression et un refus pour intégrité ont été exercés.",
        "Arbitrage : un modèle linéaire simple, entraîné de façon reproductible (seed 42) dans la chaîne de build et léger à servir dans l’image API. L’interface présente la suggestion comme une aide, à confirmer par un agent ; elle ne prend aucune décision financière.",
    ],
    evidence="infra/banking77.lock.json ; evidence/mlops/ ; src/rncp_bc3/intent.py",
)
page(
    "FinOps et deux optimisations",
    [
        "Optimisation 1 : remplacer les sondes exec, qui lançaient Python à chaque vérification, par des sondes HTTPS natives. Moyenne de trois mesures au repos : CPU 0,40340 → 0,00659 cœur, mémoire 232 052 053 → 74 895 360 octets, réplicas 3 → 1. La sonde ne vérifie pas la CA, mais elle n’expose que la santé.",
        "Optimisation 2 : le worker utilisait l’image complète de l’API. Une image dédiée embarque 14 distributions au lieu de 45 : 759 494 790 → 275 993 084 octets, soit −63,66 %. Le même parcours d’export est retesté. Effet : moins d’octets à stocker et à transférer ; aucun gain monétaire n’est calculé.",
        f"Coût cible estimé sur AWS Paris, 730 h par mois : deux nœuds t3.medium, RDS Multi-AZ, un NAT, petits volumes. Total {float(cost['scenario_subtotal_usd']):.2f} USD par mois, {float(cost['scenario_with_margin_usd']):.2f} USD avec une marge de 30 %. Les prix unitaires viennent des catalogues publics AWS datés.",
        "Arbitrage : un seul NAT pour réduire le coût, au prix de la disponibilité inter-zones. Restent hors calcul : taxes, change, transferts sortants, Secrets Manager et dépassements. Énergie et CO2 ne sont pas mesurés.",
    ],
    evidence="evidence/finops/{native-probes,worker-image,cost-scenario}.json ; estimate_costs.py",
)
counts = [
    (
        x["image"],
        x["counts_by_package_finding"].get("CRITICAL", 0),
        x["counts_by_package_finding"].get("HIGH", 0),
        len(x["fixable_high_critical"]),
    )
    for x in security["images"]
]
page(
    "Sécurité et contrôles ISO 27001",
    [
        "Les mesures sont rattachées aux contrôles de l’Annexe A cités par le sujet : A.8.24 (chiffrement), A.5.15, A.8.2 et A.8.3 (accès), A.8.5 (authentification), A.5.17 et A.8.12 (secrets), A.8.15 et A.8.16 (journalisation, supervision), A.8.13 (sauvegarde), A.8.9 (configuration par le code). Il s’agit d’une correspondance pédagogique, pas d’une certification ISO.",
        "Secrets : mots de passe et clés restent hors du dépôt et de l’archive ; les Secrets Kubernetes sont chiffrés dans etcd (préfixe k8s:enc:aesgcm) et le compte applicatif ne peut pas les lire. Les images applicatives ne contiennent ni clé de CA, ni compte d’administration SQL, ni socket Docker.",
        "Chaîne d’images : Trivy à chaque livraison ; la CI bloque tout HIGH ou CRITICAL corrigeable. pip et le client PostgreSQL ont été retirés des images API et worker ; pg_dump vit dans une image de sauvegarde séparée. Le tableau donne la campagne 1.2.1 ; en 1.3.0, aucun avis corrigeable ne reste, mais 47 avis HIGH sans correctif subsistent par image API/worker et 106 dans l’image de sauvegarde, à trier avant toute production.",
        "A.8.31 : bc3-prod reçoit les mêmes images que bc3-test avec des secrets distincts. Une NetworkPolicy n’accepte que le trafic du même namespace : depuis bc3-test, l’API et la base de prod sont injoignables ; sans la règle, la connexion passe (contre-épreuve). Le compte applicatif de test ne peut pas lire les Secrets de prod. Limites : pas d’audit de code exhaustif, durées de conservation non approuvées.",
    ],
    rows=[["Image (campagne 1.2.1)", "Critiques", "Hautes / paquet", "Corrigibles H/C"]]
    + [[n, str(c), str(h), str(f)] for n, c, h, f in counts],
    evidence="evidence/security/ ; evidence/environments/ ; docs/rapport.md",
)
page(
    "Difficultés rencontrées et corrections",
    [
        "Chaque difficulté a été corrigée puis retestée ; les essais échoués sont conservés dans les preuves plutôt qu’effacés.",
    ],
    rows=[
        ["Difficulté", "Cause", "Correction"],
        [
            "PostgreSQL neuf sans base bc3",
            "Socket attendu absent, PGHOST vide",
            "Volume emptyDir sur /var/run/postgresql",
        ],
        [
            "SeaweedFS mal configuré",
            "Variable S3_PORT injectée par Kubernetes",
            "Service Links désactivés",
        ],
        ["Traefik ignore sa configuration", "Extension .json refusée", "Fichier .yml"],
        [
            "Scrape API en erreur 400",
            "IP du pod refusée par le filtre Host",
            "POD_IP injecté, sans joker",
        ],
        [
            "Certificats refusés par Python 3.14",
            "Extensions AKI et Key Usage absentes",
            "Extensions ajoutées, mêmes clés",
        ],
        ["p95 à 680 ms", "400 lectures de clé par réponse", "Une lecture par réponse : p95 74 ms"],
        [
            "Backup incohérent (19 contre 18)",
            "Écriture après le dump",
            "Snapshot REPEATABLE READ partagé",
        ],
        ["Chaîne CI en échec", "kubectl cp sur un pod terminé", "Résultat lu dans les logs du job"],
        [
            "Premiers runs GitHub en échec",
            "Droits de fichiers Linux ignorés par macOS",
            "Rapport Trivy écrit par le shell, secrets SeaweedFS copiés",
        ],
        [
            "API en 503 sur clone neuf",
            "Modèle entraîné mais jamais promu",
            "Promotion après l’entraînement",
        ],
        [
            "Grafana refuse Loki sur le runner",
            "CA locale figée dans le manifeste",
            "CA lue depuis un Secret",
        ],
    ],
    evidence="docs/rapport.md ; evidence/diagnosis/ ; evidence/ci/attempt1-full-run.* ; evidence/ci/github-run-45270784327.json",
)
page(
    "Bilan, réserves et sources",
    [
        "La démonstration suit ce parcours : connexion, ticket, pièce jointe, suggestion d’intention, export asynchrone, tableau de bord Grafana, puis preuves de scaling, de panne, de rollback, d’alerte et de restauration.",
        "Réserves : accord de l’enseignant sur le domaine ; apply AWS, qui demande un budget autorisé ; certification de fournisseur cloud pour C6.1 à C6.4 ; triage des avis HIGH sans correctif ; validation de la politique de conservation.",
        "Suites prioritaires : poser une règle d’approbation sur l’environnement production ; appliquer Terraform sur un compte AWS avec plafond de dépense.",
        "Sources : sujet et référentiel fournis ; dépôt BANKING77 à révision figée et sa licence ; documentation officielle des outils et catalogues de prix AWS cités dans docs/evidence/finops/. Rédaction et sourçage assistés par IA (Codex, Claude), comme indiqué en page 1.",
    ],
    evidence="README.md ; docs/rapport.md",
)
# Courbes de données natives ReportLab, pas d’illustration de résultat inventée.
from reportlab.graphics import renderSVG  # noqa: E402 - construction après lecture des preuves.
from reportlab.graphics.charts.lineplots import LinePlot  # noqa: E402
from reportlab.graphics.shapes import Drawing, String  # noqa: E402

chart = Drawing(503, 205)
plot = LinePlot()
plot.x = 40
plot.y = 35
plot.width = 440
plot.height = 150
samples = resilience["samples"]


def steps(key):
    result = []
    for i, v in enumerate(samples):
        if i:
            result.append((v["seconds"], samples[i - 1][key]))
        result.append((v["seconds"], v[key]))
    return result


plot.data = [steps("hpa_current"), steps("ready_api")]
plot.xValueAxis.valueMin = 0
plot.xValueAxis.valueMax = max(v["seconds"] for v in samples)
plot.yValueAxis.valueMin = 0
plot.yValueAxis.valueMax = 4
plot.yValueAxis.valueSteps = [0, 1, 2, 3, 4]
plot.lines[0].strokeColor = colors.HexColor("#126450")
plot.lines[0].strokeWidth = 2
plot.lines[1].strokeColor = colors.HexColor("#25465c")
plot.lines[1].strokeDashArray = [4, 3]
chart.add(plot)
chart.add(
    String(160, 6, "Temps depuis le début de la charge (s)", fontName="Helvetica", fontSize=9)
)
chart.add(
    String(
        40,
        194,
        "Réplicas : HPA (vert), API prêtes (bleu pointillé)",
        fontName="Helvetica",
        fontSize=9,
    )
)
renderSVG.drawToFile(chart, str(R / "docs/figures/hpa.svg"))
P[5]["image"] = "docs/figures/hpa.svg"
(R / "docs/report-content.json").write_text(json.dumps(P, ensure_ascii=False, indent=2) + "\n")
md = [
    "# Rapport technique BC3 - Thomas Gassmann",
    "\nVersion PDF de 15 pages. Rédaction et sourçage assistés par IA (Codex, Claude).",
]
for i, p in enumerate(P, 1):
    md += ["\n## " + str(i) + ". " + p["title"], "\n\n".join(p["paragraphs"])]
    if p["table"]:
        rows = p["table"]
        md += [
            "\n"
            + "\n".join(
                [
                    "| " + " | ".join(row) + " |"
                    for row in [rows[0], ["---"] * len(rows[0]), *rows[1:]]
                ]
            )
        ]
    md += ["\nPreuves : " + p["evidence"]]
# Le texte du PDF reste dans docs/report-content.json ; docs/rapport.md est rédigé séparément
# et n’est pas écrasé par ce script.
fonts = Path("/System/Library/Fonts/Supplemental")
pdfmetrics.registerFont(TTFont("BC3", str(fonts / "Arial.ttf")))
pdfmetrics.registerFont(TTFont("BC3-Bold", str(fonts / "Arial Bold.ttf")))
body = ParagraphStyle(
    "body",
    fontName="BC3",
    fontSize=10.3,
    leading=15,
    spaceAfter=11,
    textColor=colors.HexColor("#203746"),
    alignment=TA_LEFT,
)
heading = ParagraphStyle(
    "heading",
    parent=body,
    fontName="BC3-Bold",
    fontSize=24,
    leading=29,
    spaceAfter=22,
    textColor=colors.HexColor("#123443"),
)
small = ParagraphStyle(
    "small", parent=body, fontSize=8, leading=11, textColor=colors.HexColor("#4f6574")
)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=12, spaceAfter=0)


def para(s, style=body):
    return Paragraph(escape(s.replace("—", "-").replace("–", "-")), style)


story = []
for i, p in enumerate(P):
    story.append(para(p["title"], heading))
    for text in p["paragraphs"]:
        story.append(para(text))
    if p["table"]:
        rows = [[para(s, cell) for s in row] for row in p["table"]]
        width = 503 / len(rows[0])
        table = Table(rows, colWidths=[width] * len(rows[0]), hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0eee9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccd7de")),
                ]
            )
        )
        story += [table, Spacer(1, 12)]
    if p["image"] and p["image"].endswith(".svg"):
        story += [chart, Spacer(1, 10)]
    elif p["image"]:
        path = R / p["image"]
        w, h = ImageReader(str(path)).getSize()
        scale = min(503 / w, 240 / h)
        story += [Image(str(path), width=w * scale, height=h * scale), Spacer(1, 10)]
    for shot, caption in p["screenshots"]:
        w, h = ImageReader(str(R / shot)).getSize()
        scale = min(503 / w, 262 / h)
        story += [
            Image(str(R / shot), width=w * scale, height=h * scale),
            para(caption, small),
            Spacer(1, 6),
        ]
    story.append(para("Preuves : " + p["evidence"], small))
    if i < len(P) - 1:
        story.append(PageBreak())


def footer(canvas, doc):
    canvas.setFillColor(colors.HexColor("#4f6574"))
    canvas.setFont("BC3", 8)
    canvas.drawString(46, 27, "Thomas Gassmann - RNCP40875 / BC3")
    canvas.drawRightString(549, 27, str(doc.page) + " / " + str(len(P)))


out = Path(
    os.environ.get("BC3_REPORT_OUTPUT", str(R / "output/pdf/rapport-bc3-thomas-gassmann.pdf"))
)
doc = SimpleDocTemplate(
    str(out),
    pagesize=(595.28, 841.89),
    leftMargin=46,
    rightMargin=46,
    topMargin=48,
    bottomMargin=48,
    title="Rapport technique BC3 - Thomas Gassmann",
    author="Thomas Gassmann",
)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
reader = PdfReader(out)
assert len(reader.pages) == 15, len(reader.pages)
(R / "docs/evidence/delivery").mkdir(parents=True, exist_ok=True)
(R / "docs/evidence/delivery/pdf-text-check.json").write_text(
    json.dumps(
        {
            "pages": len(reader.pages),
            "nonempty_pages": all(len(p.extract_text()) > 200 for p in reader.pages),
            "visual_review": "Pending rendered inspection",
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps({"pdf": str(out), "pages": len(reader.pages)}))
