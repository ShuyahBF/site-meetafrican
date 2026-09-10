# Portage VIDAL vers Sawali Smart Systems — à faire

## Contexte

Le module VIDAL (sécurisation de prescription, posologie, admin médecins,
suivi des logs) a été prototypé et validé visuellement dans **ce dépôt**
(`ShuyahBF/site-meetafrican`), sous la route cachée `/secure`, faute de
crédits Emergent.sh disponibles pour prévisualiser directement sur
l'environnement cible. Ce n'est **pas** l'emplacement final : c'est un
banc d'essai.

**La destination réelle est le portail Sawali Smart Systems**, sur la
branche `Site-SawaliSmartSystems` du job Emergent `sawali-portal`
(stack FastAPI + React + MongoDB Atlas, base `vidal`).

## À faire plus tard

Porter les fonctionnalités validées ici vers `Site-SawaliSmartSystems`,
**via prompt + patch git envoyé au job Emergent `sawali-portal`** — même
méthode déjà utilisée pour les autres correctifs Sawali (patch généré,
join en un seul `git am`, déploiement direct sans re-vérification quand
déjà validé côté utilisateur). Ce n'est pas un copier-coller direct : le
code React/CSS de ce dépôt (`frontend/src/secure/`) sert de référence
visuelle et fonctionnelle, mais l'intégration réelle demande une vraie
intégration backend (auth, dossiers patients, vrais appels API VIDAL,
collections MongoDB `vidal.*` documentées dans le code) — absente ici où
tout est simulé côté client.

## Pull requests de référence (dépôt `site-meetafrican`)

| PR | Contenu |
|----|---------|
| [#2](https://github.com/ShuyahBF/site-meetafrican/pull/2) | Route cachée `/secure` avec sidebar (Sécurisation / Posologie / Admin médecins) |
| [#3](https://github.com/ShuyahBF/site-meetafrican/pull/3) | Sidebar responsive sur mobile (barre horizontale) |
| [#4](https://github.com/ShuyahBF/site-meetafrican/pull/4) | Sidebar en tiroir rétractable sur mobile (bouton ☰) |
| [#5](https://github.com/ShuyahBF/site-meetafrican/pull/5) | Fond opaque Posologie + en-tête Sécurisation compact au défilement |
| [#6](https://github.com/ShuyahBF/site-meetafrican/pull/6) | Thème clair (défaut) / sombre pilotable depuis la sidebar, notes VIDAL repliables réservées à l'admin, boutons d'action égaux/repliables |
| [#7](https://github.com/ShuyahBF/site-meetafrican/pull/7) | Journal des appels API VIDAL (page "Suivi des logs" dédiée, filtre par période, impression), bloc persistance MongoDB réservé à l'admin |

## Points à ne pas perdre au portage

- **Adresse MAC non capturable** depuis un navigateur (documenté dans le
  journal des logs) — ne pas tenter de la fabriquer côté Sawali non plus.
- Convention **texte saisi en bleu** (`--input-text` / `--accent`), distincte
  de la couleur des libellés.
- Thème clair par défaut, sombre en bascule explicite (ne pas dépendre de
  `prefers-color-scheme` seul).
- Notes techniques VIDAL et bloc persistance MongoDB : réservés à l'admin,
  masqués par défaut.
- Schémas VIDAL réels (voir le manuel d'intégration confidentiel déjà
  analysé) : `patient`, `prescription-lines`, `alert-types`,
  `posology-request` — les noms de champs et types d'énumération utilisés
  dans ce prototype sont vérifiés ligne à ligne contre le manuel, pas
  inventés.
- **Ordonnances PDF — deux versions distinctes, pas une seule** :
  - Celle imprimée/téléchargée par le médecin porte le **nom du patient en
    clair** (nécessaire à la pharmacie) et n'est jamais envoyée où que ce
    soit depuis le navigateur du médecin.
  - Celle archivée côté serveur (`ordonnance_pdf_ref`, stockée dans
    **Cloudflare R2**, bucket **dédié VIDAL** — séparé du bucket
    `meetafrican-documents` déjà utilisé sur cette infra) doit être une
    régénération avec **identité anonymisée** (ID patient ou nom masqué,
    même convention que l'historique) : c'est cette version que verrait un
    tiers scannant le QR de vérification, jamais le nom complet.

## État réel de l'infrastructure MongoDB Atlas (vérifié le 10/09/2026)

Le cluster `Cluster0` (celui déjà utilisé par `site_meetafrican`, `albarka`,
`bfmobility`) est **le cluster réel de production/dev partagé** — pas une
maquette. La base `vidal` y existe déjà et a été complétée à cette date :
les 6 collections documentées ci-dessus (`medecins`, `api_calls`,
`patients`, `patient_access_requests`, `patient_treatments`,
`securisation`) sont toutes créées (vides, sans données factices — seule
`securisation` préexistait, déjà vide). Le bucket Cloudflare R2 dédié
VIDAL, lui, **reste à créer** — aucun accès Cloudflare disponible depuis
cette session pour le faire.

## Bucket R2 dédié VIDAL — en attente (mise à jour 10/09/2026)

Des identifiants R2 étaient bien présents dans l'environnement de cette
session, mais **vérifiés inutilisables pour ce besoin** : le token
(`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_ACCOUNT_ID`/`R2_BUCKET`)
est scopé sur un unique bucket existant, `aizenta-inventaires-clients`,
qui contient déjà de vraies données d'un projet tiers sans rapport
(« Aizenta », inventaires/rapports classés par client — ex.
`AMY/inventaires/...`, `PHL/inventaires/...`). `ListBuckets` et
`CreateBucket` renvoient tous deux `AccessDenied` avec ce token : il ne
permet ni de voir d'autres buckets, ni d'en créer un nouveau. Stocker des
ordonnances (même anonymisées) dans ce bucket mélangerait des données
santé avec celles d'un client tiers — écarté.

**Décision de l'utilisateur (10/09/2026)** : il va créer lui-même un
nouveau bucket Cloudflare dédié à VIDAL et fournira les identifiants
correspondants plus tard. **Ne pas utiliser le token `aizenta-*` déjà
présent dans l'environnement pour le stockage des ordonnances**, même si
de nouveaux identifiants R2 apparaissent dans l'environnement sans
précision explicite de l'utilisateur — vérifier le nom du bucket et son
contenu avant d'y écrire quoi que ce soit.

## Bucket R2 dédié VIDAL — provisionné et vérifié (10/09/2026)

L'utilisateur a créé le bucket et fourni de nouvelles variables
d'environnement dédiées, préfixées `R2_VIDAL_` (distinctes des `R2_*`
génériques ci-dessus, qui restent celles d'Aizenta) :
`R2_VIDAL_ACCESS_KEY_ID`, `R2_VIDAL_SECRET_ACCESS_KEY`,
`R2_VIDAL_ACCOUNT_ID`, `R2_VIDAL_BUCKET` (= `vidal`), et
`R2_VIDAL_JETON` (le jeton API Cloudflare natif généré en même temps que
les clés S3 — non utilisé pour l'accès S3-compatible, potentiellement
utile pour des opérations via l'API Cloudflare directe si besoin plus
tard).

**Piège rencontré et corrigé** : `R2_VIDAL_ACCOUNT_ID` contenait 34
caractères au lieu des 32 attendus pour un Account ID Cloudflare
(hexadécimal) — 2 caractères de trop, confirmé par l'utilisateur comme
une erreur de copier-coller, corrigés en tronquant les 2 derniers
caractères. À vérifier si cette variable d'environnement est un jour
corrigée à la source (le contournement en tronquant ne doit pas devenir
permanent dans du code réel).

**Vérifié avec succès** (accès S3-compatible via `boto3`, `region_name="auto"`,
endpoint `https://{account_id}.r2.cloudflarestorage.com`) :
- `head_bucket('vidal')` → accès confirmé, bucket vide (0 objet).
- `put_object` / `get_object` / `delete_object` → lecture/écriture/suppression
  toutes fonctionnelles (testées avec un objet jetable, supprimé après coup).
- `list_buckets` et `create_bucket` → `AccessDenied` (token scopé sur ce seul
  bucket, sans droit de lister ou créer d'autres buckets) — cohérent avec
  un bucket dédié VIDAL et rien d'autre.

**Le bucket R2 dédié VIDAL est donc prêt à l'usage** pour le stockage des
ordonnances anonymisées décrit plus haut, dès que le portage vers
`Site-SawaliSmartSystems` implémente réellement l'upload/téléchargement
(absent de ce prototype, qui reste 100 % simulé côté client).
