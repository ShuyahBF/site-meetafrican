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
| [#14](https://github.com/ShuyahBF/site-meetafrican/pull/14) | Nouvelle page "Fiche produit VIDAL" — consultation en ligne par les pharmacies/établissements de santé (recherche produit, voies d'administration, documents disponibles par type avec distinction HTML VIDAL direct / document externe) |
| (à venir) | Page "Liluvine — Requêtes WhatsApp" — voir section dédiée ci-dessous |

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

## Liluvine — requêtes produit par WhatsApp (règles métier, à porter)

Nouvelle page `/secure/liluvine` ("Liluvine (WhatsApp)" dans la sidebar) :
simulation de bout en bout de l'assistant WhatsApp Liluvine qui répond aux
demandes de fiche produit envoyées par un numéro WhatsApp, avec autorisation,
comptage de requêtes et abonnement. Règles métier fixées par l'utilisateur,
à réimplémenter à l'identique côté serveur au portage :

- **Stockage dans le bucket R2 dédié VIDAL, pas MongoDB** (demande explicite) :
  - `liluvine/config.json` — `{ free_requests_threshold, trial_days, formulas: {jour, semaine, mois, trimestriel, annuel} }`, chaque formule avec sa durée et son coût, éditable par l'Admin.
  - `liluvine/numbers/{phone_e164}.json` — un objet par numéro : `{ phone, authorized, manual_blocked, request_count, free_requests_used, first_request_at, last_request_at, trial_expires_at, subscription: {formula, started_at, expires_at, price} | null }`.
- **Numéro pas encore autorisé** → Liluvine répond par une invitation polie à
  s'inscrire, **et** envoie une notification à l'Admin ; l'Admin autorise le
  numéro, ce qui lui accorde un **essai de N jours** (`trial_days`, par
  défaut 3, **configurable par l'Admin**).
- **Comptage des requêtes en temps réel** par numéro. **N requêtes gratuites**
  (`free_requests_threshold`, par défaut 3, **configurable par l'Admin** —
  distinct de `trial_days` bien que l'utilisateur emploie le même "3" par
  défaut pour les deux), puis **abonnement obligatoire à partir de la
  requête N+1**.
- **Formules d'abonnement** avec expiration selon la formule souscrite :
  jour, semaine, mois, trimestriel, annuel — chacune avec son coût propre
  (montants de démonstration en FCFA, à fixer réellement par l'utilisateur).
- Un état "bloqué" manuel (indépendant du compteur) permet à l'Admin de
  couper l'accès d'un numéro abusif sans toucher à son historique.
- **Règles WhatsApp Business à respecter à l'intégration réelle** : un
  message entrant ouvre une fenêtre de service de 24h pendant laquelle
  Liluvine peut répondre librement (document produit compris) ; toute
  relance envoyée hors de cette fenêtre (invitation à s'inscrire à froid,
  rappel d'abonnement expiré) doit passer par un **modèle pré-approuvé par
  Meta, catégorie UTILITY** (même convention que le modèle
  `ordonnance_pdf_fr` déjà utilisé ailleurs dans ce prototype) — jamais
  MARKETING. WhatsApp ne filtre pas lui-même les expéditeurs autorisés :
  ce filtrage est entièrement applicatif, exactement ce que simule cette
  page.
- Comme pour le reste du module VIDAL : **aucun identifiant WhatsApp
  Business ni identifiant R2 réel n'est utilisé** dans ce prototype — la
  table des numéros et la configuration vivent en mémoire côté navigateur,
  à réimplémenter avec de vrais appels R2 (GET/PUT d'objets JSON) et de
  vrais webhooks WhatsApp Cloud API au portage.

## VIDAL — bascule vers de vrais appels API réels (10/09/2026)

**Changement majeur** : l'utilisateur a fourni un vrai couple `app_id` /
`app_key` VIDAL (compte de production) et a explicitement demandé d'arrêter
les suppositions basées sur le manuel pour tester avec de **vrais appels,
toujours en production** (pas de sandbox distincte pour ce compte — décision
explicite : « on veut être sûr des bons retours de VIDAL, l'infrastructure
peut avoir changé depuis la rédaction du manuel »). Ce dépôt (`site-meetafrican`)
reste le banc d'essai retenu pour cette étape ; la reproduction réelle sur
`Site-SawaliSmartSystems` se fera au portage, comme convenu.

**Intégration backend ajoutée** (`backend/`) :
- `config.py` — nouveaux réglages `vidal_base_url`, `vidal_app_id`,
  `vidal_app_key`, `vidal_timeout_seconds` (12s), `vidal_cache_ttl_hours`
  (168h), `vidal_quota_per_day` (200), `vidal_proxy_secret`.
- `vidal_client.py` — client HTTP vers `https://api.vidal.fr/rest/api` :
  authentification par `app_id`/`app_key` en paramètres de requête (pas de
  header dédié — confirmé dans le manuel MI_APIREST REV_03 et par test réel),
  réponses en XML ATOM uniquement (pas de JSON — également confirmé dans le
  manuel). Cache Mongo (`vidal_api_cache`, TTL réel via index Mongo
  `expireAfterSeconds` + vérification applicative) et quota journalier
  (`vidal_api_quota`) qui **bloque avant l'appel** plutôt que de laisser
  l'abonnement VIDAL être dépassé silencieusement.
- `routes/vidal.py` — premier endpoint réel : `GET /api/vidal/products/search?q=...`
  (recherche produit par libellé, `/rest/api/products?q=...` côté VIDAL),
  protégé par un secret partagé `VIDAL_PROXY_SECRET` (header
  `X-Vidal-Proxy-Secret`) — nécessaire car `/secure` est une route cachée
  mais **sans vrai login** ; sans ce garde-fou, n'importe qui tombant sur
  l'URL pourrait épuiser le quota VIDAL réel. **Point d'attention pour le
  portage** : ce secret statique est un pis-aller de prototype, pas un
  vrai contrôle d'accès — à remplacer par le futur système d'authentification
  médecin de Sawali.
- `render.yaml` / `.env.example` mis à jour (`VIDAL_APP_ID`/`VIDAL_APP_KEY`/
  `VIDAL_PROXY_SECRET` en `sync: false`, jamais commités).

**Validé avec de vrais appels contre `https://api.vidal.fr`** (10/09/2026,
credentials réels fournis par l'utilisateur, mode production) :
- Recherche produit fonctionne (`doliprane`, `efferalgan`, `aspirine` testés
  avec de vraies réponses XML ATOM, vrais `productId` VIDAL) ;
- Le garde-fou de secret partagé refuse bien une requête sans le header ;
- Le quota journalier bloque bien une requête excédentaire **avant** tout
  appel réseau vers VIDAL (testé avec un quota réduit à 1, sans consommer
  de requêtes réelles supplémentaires grâce au cache) ;
- Le cache Mongo sert bien une requête identique sans re-appeler VIDAL.
- **Bug réel corrigé pendant ce test** : MongoDB renvoie les dates stockées
  en `naive UTC` (BSON n'a pas de fuseau horaire) — comparer directement à
  un `datetime` "aware" (`tzinfo=utc`) levait une `TypeError`. Corrigé en
  requalifiant explicitement en UTC avant comparaison
  (`vidal_client.py::_get_cached`) — à surveiller si d'autres comparaisons
  de dates Mongo sont ajoutées ailleurs dans le projet.

**Confirmation utile** : le produit fictif utilisé dans toutes les
maquettes (`DOLIPRANE 1000 mg cp`, ref `19649`) est en réalité un **vrai**
productId VIDAL — la donnée de démonstration choisie pour les mockups
était donc correcte par coïncidence.

**Reste à faire** (prochaine étape, à cadrer avec l'utilisateur avant de
se lancer) : brancher le frontend `/secure` (typeahead de Sécurisation,
Posologie, Fiche produit) sur ce vrai endpoint au lieu du tableau
`typeaheadData.drug[]` simulé — nécessite de décider comment le secret
`VIDAL_PROXY_SECRET` atteint l'iframe (probablement injecté par
`SecureFrame` comme le thème/les notes VIDAL, via `postMessage`) et de
gérer les états de chargement/erreur réseau dans l'UI existante.

## Fiche produit VIDAL — branchée sur de vraies données (10/09/2026)

**Deuxième endpoint réel ajouté** : `GET /api/vidal/products/{id}/detail`
(`backend/routes/vidal.py` + `vidal_client.py::parse_product_detail`),
un seul appel VIDAL agrégé `GET /rest/api/product/{id}?aggregate=ROUTE&aggregate=DOCUMENTS`
qui renvoie en une fois les voies d'administration ET les documents
disponibles — confirmé par test réel (produit 19649, DOLIPRANE 1000 mg cp).

**Découverte utile par test réel** : les URLs de documents HTML publics
VIDAL (ex. `https://api.vidal.fr/data/mono/.../full-mono-for-product-19649.html`)
sont accessibles **sans authentification** et **sans restriction d'affichage
en iframe** (pas de `X-Frame-Options` ni CSP `frame-ancestors` dans leurs
en-têtes) — elles peuvent donc être chargées directement dans un
`<iframe src="...">`, sans avoir à en récupérer et reconstruire le contenu
côté serveur. Les documents hors référentiel HTML (RCP en PDF sur
`document-rcp.vidal.fr` notamment) restent en lien externe (`target="_blank"`),
jamais chargés en iframe.

**Frontend branché** (`frontend/src/secure/content/fiche-produit.html`,
plus aucune donnée simulée sur cette page) :
- Recherche produit : `fetch` débounced (300ms) vers `/api/vidal/products/search`,
  avec numéro de séquence pour ignorer une réponse obsolète si l'utilisateur
  retape vite. États « recherche en cours » / « erreur VIDAL » / « aucun
  résultat » gérés explicitement plutôt que masqués.
- Sélection d'un produit : appel `/api/vidal/products/{id}/detail`, affichage
  des vraies voies d'administration et des vrais types de documents
  (badge VIDAL/Externe déterminé par `is_html`, plus par une liste statique).
- Affichage d'un document : `<iframe src="...">` pointant directement vers
  l'URL VIDAL réelle pour les documents HTML ; lien externe pour le reste.
  Plus de date de révision affichée (VIDAL n'en renvoie pas dans ce flux —
  on ne recrée plus de fausse date « illustrative » comme avant).
- `SecureFrame.jsx` injecte `window.__VIDAL_API__ = {baseUrl, proxySecret}`
  dans l'iframe au premier rendu (nouvelle variable Vite
  `VITE_VIDAL_PROXY_SECRET`, à saisir dans Render en plus de
  `VITE_API_BASE_URL` — même valeur que `VIDAL_PROXY_SECRET` côté backend).

**Validé en conditions réelles de bout en bout** (backend réel + frontend
Vite + Playwright, CORS backend↔frontend en local, credentials réels) :
recherche « doliprane » → 25+ résultats réels, sélection d'un DOLIPRANE
100 mg **retiré du marché** → voie « orale » réelle, document
`MONO_SUPP` réel affiché avec le bon badge (confirmant en conditions
réelles la règle FULL_MONO/MONO_SUPP documentée dans le manuel), bouton
RCP (Externe) → lien PDF réel vers `document-rcp.vidal.fr` sans charger
d'iframe. Aucune erreur JS.

**Reste simulé, sciemment, pour l'instant** : le typeahead médicament de
Sécurisation (`onDrugSelected`, chargement d'historique de démonstration,
génération XML de `runSecure()`) n'a **pas** été branché sur ces mêmes
endpoints dans cette itération — il a plus de dépendances internes
(historique de démo, listes d'unités que VIDAL n'a pas renvoyées pour les
produits testés) qu'il aurait fallu retravailler en profondeur sans risquer
de casser un mockup déjà validé. À cadrer séparément si l'utilisateur le
souhaite.

## Fiche produit VIDAL — 3 correctifs après premier test réel en production (10/09/2026)

Suite au premier test réel de l'utilisateur sur l'environnement Render
déployé (après avoir renseigné `VIDAL_APP_ID`/`VIDAL_APP_KEY`/
`VIDAL_PROXY_SECRET` côté backend et `VITE_VIDAL_PROXY_SECRET` côté
frontend — **les deux valeurs doivent être strictement identiques**,
piège rencontré une première fois) :

1. **Saisie forcée en majuscules** dans le champ de recherche produit —
   convention VIDAL/pharma. La valeur du champ elle-même est transformée
   (pas juste un `text-transform` CSS d'affichage), avec préservation de
   la position du curseur. La recherche VIDAL reste insensible à la
   casse (confirmé par test réel) : ceci est une pure convention de
   saisie, pas un besoin fonctionnel.
2. **Liste de résultats non tronquée** : l'ancien plafond arbitraire de
   8 résultats affichés est supprimé — les ~25 résultats renvoyés par
   VIDAL (taille de page par défaut de l'API) sont tous listés dans une
   liste défilante plus haute (340px), avec un compteur en tête de liste.
3. **Documents « Externe » affichés dans la page plutôt qu'en lien
   sortant** : découverte par test réel que certains documents VIDAL
   (RCP notamment, sur `document-rcp.vidal.fr`) renvoient un en-tête
   `X-Frame-Options: SAMEORIGIN` qui empêche leur affichage direct en
   iframe depuis leur URL VIDAL d'origine. Nouvel endpoint backend
   `GET /api/vidal/documents/proxy?url=...` (liste d'hôtes autorisés
   limitée à `api.vidal.fr`/`document-rcp.vidal.fr`, pour ne jamais
   devenir un proxy ouvert) qui relaie le document depuis notre propre
   origine, sans cet en-tête restrictif. Le frontend récupère le document
   via `fetch()` (même secret partagé que les autres routes VIDAL),
   crée une URL de blob (`URL.createObjectURL`) et l'affiche dans
   l'iframe — avec repli en lien externe uniquement si ce relais échoue.
   Ces URLs de documents sont publiques (aucun `app_id`/`app_key` requis),
   donc ce nouvel endpoint ne consomme pas le quota VIDAL.

**Validé en conditions réelles de bout en bout** (backend réel + frontend
Vite + Playwright, credentials réels) : saisie "doliprane" → champ affiche
"DOLIPRANE", liste de 25 résultats avec compteur "25+ résultats — affinez
la recherche", document RCP externe (confirmé `X-Frame-Options: SAMEORIGIN`
par `curl` direct) chargé en iframe via le proxy backend en ~4s (PDF de
1,6 Mo) — pas de lien externe nécessaire, pas d'erreur JS.

## Cache local du référentiel produits VIDAL (10/09/2026)

**Problème adressé** : chaque frappe clavier dans la recherche produit
déclenchait un aller-retour réseau réel vers `api.vidal.fr`. Nouveau
mécanisme optionnel (activable par l'admin) qui synchronise localement
tout le catalogue VIDAL, pour une recherche instantanée sans appel réseau
à chaque frappe.

**Chiffres réels confirmés par test** (pas une estimation) :
- VIDAL a **15 680 produits** au total (`GET /rest/api/products?q=` avec
  `q` vide liste tout le catalogue, paginé 25/page — confirmé par appel
  réel, pas documenté explicitement comme tel dans le manuel).
- Un sync complet = **628 appels API** (15 680 ÷ 25).
- Décision utilisateur : ce job est une opération admin/développeur, **pas
  soumise au quota journalier anti-abus** (`VIDAL_QUOTA_PER_DAY`, qui
  protège contre des utilisateurs finaux, pas une synchronisation
  explicitement déclenchée) — `vidal_get(..., bypass_quota=True)`.
- Durée réelle mesurée : **975s (~16 min)** en ouvrant une connexion HTTP
  par appel, réduite à **541s (~9 min)** en réutilisant une seule
  connexion `httpx.AsyncClient` sur les 628 appels (-45%) — les deux
  runs ont synchronisé exactement 15 680/15 680 produits, 0 erreur.

**Architecture ajoutée** :
- `backend/vidal_sync.py` (nouveau) — `run_referentiel_sync()` parcourt
  tout le catalogue et upsert chaque produit dans la collection Mongo
  `vidal_cache_referentiel_produits` (nom corrigé — l'orthographe demandée
  "vidal_cacherefentiel_produits" semblait être une coquille pour
  "référentiel"). `sync_scheduler_loop()`, démarrée au boot du serveur
  (`server.py`), vérifie 1×/heure si la fréquence configurée par l'admin
  est écoulée depuis la dernière synchronisation et relance si besoin —
  pas de vrai service cron externe (pas nécessaire vu le volume, et ça
  évite de dépendre d'un service Render supplémentaire pour une fréquence
  reconfigurable dynamiquement, pas figée au déploiement).
- Config admin (`vidal_sync_config`, doc singleton) : `mode`
  (`temps_reel` par défaut | `cache`), `frequency_days` (0 = désactivée,
  sinon nombre de jours entre synchronisations — présets jour/semaine/
  mois/trimestre dans l'UI), `last_sync_at`, `sync_in_progress` (verrou
  anti-double-exécution).
- `GET/PUT /api/vidal/admin/sync-config`, `POST /api/vidal/admin/sync-now`
  (déclenchement manuel, tâche de fond — répond immédiatement, résultat
  visible ensuite dans le journal), `GET /api/vidal/admin/sync-log`.
- `GET /api/vidal/products/search` lit désormais la config : en mode
  `cache` **et** si une synchronisation a déjà eu lieu au moins une fois,
  recherche dans `vidal_cache_referentiel_produits` (regex insensible à la
  casse sur `name`, jamais d'appel VIDAL) ; sinon (mode `temps_reel`, ou
  `cache` mais jamais synchronisé) — comportement actuel inchangé. **Une
  fois un produit sélectionné, `/products/{id}/detail` reste toujours en
  temps réel**, quel que soit le mode — seule l'étape de recherche est
  concernée, comme demandé.
- Chaque exécution (planifiée ou manuelle) journalisée dans
  `vidal_sync_log` : `ts`, `type` (fixe `"sync_refer"`), `status`
  (`success`/`partial`/`error`/`skipped_already_running`), `result`
  (résumé texte), `products_synced`, `api_calls`, `duration_seconds`,
  `triggered_by` (`cron`|`manuel`).

**Frontend** :
- `admin_medecins_vidal.html` — nouvelle carte « Référentiel produits
  VIDAL — cache » : sélecteur de mode, sélecteur de fréquence (présets),
  bouton « Synchroniser maintenant », affichage de la dernière
  synchronisation, polling automatique (5s) pendant qu'une synchronisation
  est en cours.
- `journal_logs_vidal.html` — nouvelle carte « Synchronisations du
  référentiel produits » : **données réelles** (pas simulées comme le
  reste de cette page), tableau des exécutions `sync_refer` récentes
  (Date/Heure, Type, Déclenché par, Résultat, Statut) via
  `GET /vidal/admin/sync-log`.

**Validé en conditions réelles de bout en bout** : sync complet réel
(15 680/15 680 produits, 628 appels, journalisé avec succès), recherche
"doli" en mode cache → réponse en 110ms (`source: "cache"` dans la
réponse) avec de vrais produits (CODOLIPRANE, DOLIPRANE…), UI Admin
testée en conditions réelles pendant qu'une synchronisation était
effectivement en cours (statut "Synchronisation en cours…", bouton
désactivé), changement de mode/fréquence depuis l'UI persisté côté
backend, journal réel affiché correctement sur la page Suivi des logs.

**Point d'attention pour le portage** : sur un premier déploiement (jamais
synchronisé), le scheduler déclenche un sync complet dès le démarrage du
serveur (fréquence par défaut 7 jours, `last_sync_at` null = "due"
immédiatement) — comportement voulu pour peupler le cache sans action
admin, mais à confirmer explicitement lors du portage vers Sawali si ce
n'est pas le comportement désiré là-bas.

## Liluvine — commande `!doc`/`!rech` et recherche par DCI + équivalences (10/09/2026)

**Correction de convention** : le préfixe `!Aizenta` initialement retenu pour
les requêtes produit Liluvine est **abandonné** — déjà utilisé ailleurs dans
Liluvine (hors périmètre VIDAL, sur la plateforme réelle Sawali/albarka-portal
qui a ses propres routes `liluvine_*_wa.py`). Remplacé par **`!doc` et
`!rech`**, synonymes stricts, casse libre sur les deux — ex. `!doc doliprane
1000` ou `!RECH Doliprane 1000`.

**Recherche par DCI (prescription DCI généralisée au Burkina Faso)** : la
requête accepte un nom de marque (`!doc doliprane 1000` → doc + principe actif
DCI avec dosage) **ou** directement un principe actif (`!doc paracétamol
1000` → pas de marque précise, affichage direct de la liste des produits
équivalents pour cette DCI + ce dosage). Simulé côté maquette Liluvine avec un
petit catalogue de démonstration (Doliprane/Efferalgan/Dafalgan/Paracétamol
Biogaran = paracétamol 1000mg ; Advil/Nurofen/Ibuprofène Arrow = ibuprofène
400mg ; Clamoxyl/Amoxicilline Biogaran = amoxicilline 500mg).

**Équivalences = même(s) principe(s) actif(s) ET même dosage** — définition
métier donnée par l'utilisateur. Sur WhatsApp, la fiche produit est envoyée
avec un bouton de template nommé **« Équivalences »** ; l'appui renvoie la
liste sans consommer de nouvelle requête (comptée comme une action sur la
réponse déjà livrée, pas une nouvelle recherche facturable) — simulé dans la
maquette par `handleEquivalencesTap()`.

**Découverte technique réelle côté API VIDAL (testée en production, pas une
supposition)** : VIDAL expose un regroupement officiel **VMP** ("Virtual
Medicinal Product" — DCI + dosage + voie + forme galénique) directement dans
l'appel produit déjà utilisé pour la fiche produit
(`GET /product/{id}?aggregate=ROUTE&aggregate=DOCUMENTS` renvoie aussi
`<vidal:vmp vidalId="…">`, aucun appel supplémentaire nécessaire pour
l'obtenir). `GET /vmp/{vmp_id}/products` renvoie alors directement la liste
des produits équivalents (marques ET génériques mélangés) — testé en réel
sur DOLIPRANE 1000 mg (`vmp_id=3170`) : 24 produits renvoyés, dont DAFALGAN,
DAFALGANTABS, DOLIPRANETABS, EFFERALGAN et une vingtaine de génériques
PARACETAMOL, DOLIPRANE lui-même bien exclu via `exclude_product_id`. C'est
plus fiable et beaucoup moins coûteux en appels qu'un recalcul maison à
partir de `/product/{id}/molecules` (qui existe aussi et donne le détail
DCI/dosage/excipients d'un produit isolé, mais sans lien retour vers les
autres produits qui le partagent).

**Implémentation réelle (fiche produit VIDAL, site)** :
- `backend/vidal_client.py::parse_product_detail` renvoie désormais aussi
  `vmp_id` (extrait du `<vidal:vmp>` déjà présent dans la réponse existante).
- Nouvel endpoint `GET /vidal/vmp/{vmp_id}/equivalents?exclude_product_id=…`
  (`backend/routes/vidal.py`) — réutilise `parse_products_search` telle
  quelle, `/vmp/{id}/products` renvoie le même format d'entrée `PRODUCT` que
  `/products?q=…`.
- Frontend (`fiche-produit.html`) : bouton **« Voir les équivalences »**
  affiché seulement si `vmp_id` est présent (pas de liste inventée quand
  l'info est absente) ; liste chargée en différé, au premier clic seulement,
  puis mise en cache côté page (`equivalentsLoaded`) pour ne pas re-solliciter
  VIDAL à chaque toggle.

**Validé en conditions réelles de bout en bout** (backend + frontend Vite,
vrais identifiants VIDAL, navigateur Playwright) : sélection de DOLIPRANE
1000 → `vmp_id` reçu → clic « Voir les équivalences » → 24 produits réels
affichés (DOLIPRANE exclu) → re-clic masque la liste sans re-solliciter
l'API.

## Liluvine — agents nommés qui signent les réponses (10/09/2026)

**Règle métier** : jusqu'à **5 agents** configurables par l'Admin (prénom +
rôle/spécialité, texte libre — pas une liste fermée). Exemple donné par
l'utilisateur, repris comme jeu de données par défaut : Awa (Secrétaire),
Robert (Comptable), Gaspard (Technicien), Gédéon (Commercial).

- Un message qui **ne commence pas par `!`** est une **question libre** :
  Liluvine détermine quel rôle est concerné par son contenu (ex. une
  demande de prix sur un produit → rôle « Commercial ») et la réponse est
  **signée du prénom** de l'agent correspondant. En réalité c'est toujours
  l'agent IA qui exécute le prompt système du rôle concerné avant de
  signer — aucun humain ne répond en direct.
- Une **commande** (message commençant par `!`, ex. `!doc`/`!rech`) suit une
  règle stricte et différente : elle n'est **jamais relayée à un agent ni
  signée** — analysée et traitée directement par le système (réponse
  structurée). Une commande commençant par `!` mais non reconnue (ex.
  `!blabla`) reste dans cette famille : réponse de rappel des commandes
  disponibles, **aucune écriture ni compteur touché** — elle n'est jamais
  routée vers un agent.
- Les questions libres, elles, passent par la **même passerelle
  d'accès/abonnement** que les commandes `!doc`/`!rech` (essai gratuit,
  abonnement, blocage) : toute interaction réelle avec Liluvine consomme
  la même ressource, qu'il s'agisse d'une recherche VIDAL ou d'une question
  générale.

**Limite technique de cette maquette (à ne pas reproduire telle quelle au
portage)** : le classement du rôle concerné et la rédaction de la réponse
sont simulés par un **lexique de mots-clés** (`ROLE_KEYWORDS`) et de courts
modèles de texte par rôle (`draftReplyForRole`) — pas d'appel à un vrai
modèle de langage. En production, ces deux étapes seraient confiées à un
vrai agent IA exécutant le prompt système du rôle concerné (Sawali expose
déjà `liluvine_business_rag.py` côté `albarka-portal` pour ce type de
logique) ; seule la règle de signature (prénom + rôle, jamais pour une
commande) doit être conservée à l'identique.

**Piège corrigé pendant le développement** : les clés du lexique de rôles et
des modèles de réponse doivent être **sans accent**, car elles sont comparées
au résultat de `normalizeText(agent.specialite)` qui retire systématiquement
les accents (`normalizeText("Secrétaire")` → `"secretaire"`) — une clé
`'secrétaire'` (accentuée) dans ces dictionnaires ne matche jamais et
retombe silencieusement sur le premier agent de la liste, masquant le bug
tant que cet agent est justement celui attendu. Vérifié en réordonnant la
liste des agents dans un test Playwright : le routage reste bien basé sur
les mots-clés du message, pas sur la position de l'agent dans la liste.

**Validé par test Playwright** : demande de prix → Gédéon (Commercial) ;
question d'horaires → Awa (Secrétaire) ; signalement de panne → Gaspard
(Technicien) ; demande de facture → Robert (Comptable) ; `!doc Doliprane
1000` toujours traité normalement (non signé) ; `!blabla` → commande non
reconnue, compteur de requêtes inchangé ; ajout d'un 5<sup>e</sup> agent
via l'UI Admin → bouton "Ajouter" désactivé au maximum.
