# site-meetafrican

MeetAfrican — site de rencontre pour hommes et femmes africains.

## État du projet

- **Design** : 22 écrans de maquette générés avec Stitch AI (Google), rangés dans
  [`design/stitch-exports/`](design/stitch-exports). Charte graphique extraite dans
  [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md).
- **Implémentation** : auth, abonnements Premium, paiement PawaPay (Mobile Money),
  découverte/matching (swipe), chat temps réel (WebSocket), vérification
  d'identité et modération des photos de profil par IA (Claude vision), notation
  entre comptes, signalement de faux profils, points de parrainage social et
  back-office admin (`/admin`) fonctionnels de bout en bout — testés en local
  (voir section Tests ci-dessous).
- **Esprit TikTok** : fil vidéo vertical plein écran **« Moments »** (`/moments`)
  — lecture auto, double-tap = J'aime avec cœur animé, colonne d'actions
  (profil + « Ça me plaît » qui peut créer un match, commentaires en tiroir,
  cadeau, partage), onglets *Pour toi* / *Près de moi* / *Mes matchs*,
  #hashtags cliquables et tendances, défilement infini. Publication réservée
  aux identités **vérifiées** (gage d'authenticité), signalement en un clic
  (retrait automatique à 3 signalements, revue dans `/admin/videos`).
- **Vidéos floutées par défaut** : chaque vidéo est compressée puis
  **entièrement floutée côté serveur** (ffmpeg via `imageio-ffmpeg`, sans
  son) — c'est cette version que tout le monde voit. La version **claire**
  est rangée dans le stockage **privé** et n'est servie (URL temporaire)
  qu'aux membres **vérifiés acceptés par l'auteur** : par un match, ou en
  acceptant leur demande « Voir en clair » (boîte de réception ; accès
  révocable depuis *Mon profil*). Voir `backend/video_processing.py`.
- **Recherche avancée** (`/recherche`, maquette 10), **profil détaillé**
  éditable (centres d'intérêt, type de relation, enfants, profession —
  maquette 11) et **fiche publique** des membres (`/profils/:id`).
- **Chat enrichi** : « en train d'écrire… », accusés de lecture « Vu »,
  présence dans la conversation, compteur de messages non lus.
- **Charte** : fond **blanc** pour toutes les fenêtres, dégradé signature
  rose → orange, micro-animations (voir `frontend/tailwind.config.js`).

## Adresses publiques

| Rôle | Adresse |
|------|---------|
| Site | https://beauthentik.net (et https://www.beauthentik.net) |
| API  | https://api.beauthentik.net/api |
| Webhook PawaPay (à déclarer chez PawaPay) | https://api.beauthentik.net/api/payments/pawapay/webhooks/deposits/`<PAWAPAY_CALLBACK_SECRET>` |

Toutes les URL visibles par les membres (liens de parrainage, retour après
paiement, liens de partage des Moments) utilisent `beauthentik.net`. DNS chez
Cloudflare : `beauthentik.net`, `www` et `api` pointent vers les services
Render déclarés dans `render.yaml` (clé `domains`).

## Stack

- **Backend** : FastAPI (Python) + MongoDB (Motor), JWT.
- **Frontend** : React (Vite) + Tailwind CSS, aux couleurs de la charte MeetAfrican.
- **Paiement** : PawaPay Hosted Payment Page (Orange/Moov/Telecel), porté et adapté
  depuis `ShuyahBF/Emergent` (branche `Site-SawaliSmartSystems`) — voir
  `backend/routes/payments_pawapay.py`.
- **Base de données** : MongoDB Atlas, cluster `Cluster0` partagé, base dédiée
  `site_meetafrican` isolée des autres projets, toutes les collections préfixées
  `maf_` (voir `backend/db.py`).
- **IA de vérification/modération** : Claude (API Anthropic) analyse chaque pièce
  d'identité et chaque photo de profil soumise selon un prompt système modifiable
  par l'admin (`/api/admin/settings/moderation`) ; décision `approved` /
  `rejected` / `needs_review` — ce dernier cas et la désactivation globale de l'IA
  déclenchent une revue humaine (voir `backend/ai_moderation.py`).
- **Stockage des fichiers** : Cloudflare R2 (compatible S3), deux buckets aux
  usages différents (voir `backend/storage.py`) :
  - `meetafrican-photos` — **public**, album profil (visible dans le fil de
    découverte) ;
  - `meetafrican-documents` — **privé**, pièces d'identité. Jamais d'URL
    publique permanente : une URL présignée à courte durée de vie est générée
    à la demande (analyse IA, revue admin), jamais stockée.
  Un mode `STORAGE_BACKEND=local` (disque du serveur) reste disponible pour
  développer sans configurer R2 — à ne jamais utiliser en production (fichiers
  perdus à chaque redéploiement, `/api/private-files` non protégée).

## Démarrer en local

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis compléter MONGO_URL, JWT_SECRET, clés PawaPay…
uvicorn server:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL doit pointer vers le backend
npm run dev
```

L'app tourne sur http://localhost:5173, l'API sur http://localhost:8000/api
(docs interactives sur `/docs`).

### Traçabilité (adresses IP)

Chaque action qui modifie des données (inscription, connexion, abonnement,
paiement, publication, message, J'aime, signalement…) est journalisée avec
l'adresse IP de son auteur (`backend/activity.py`), consultable dans
**/admin/activite** (filtres par membre, IP, action ; synthèse des IP d'un
membre). Les comptes gardent aussi leur IP d'inscription et de dernière
connexion ; abonnements, paiements, vidéos et commentaires leur IP de
création. Purge automatique du journal après 12 mois.

### Données de test

**/admin/donnees-test** génère une centaine de profils fictifs (photos,
vidéos floutées, swipes, matchs, conversations…) tous marqués
`is_test_data` et affichés avec un badge « Test », puis les supprime d'un
clic (fichiers compris). Mot de passe commun des comptes de test affiché
sur la page. Les compteurs publics de la page d'accueil ne les comptent pas.

### Accéder au back-office admin

Définir `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` dans `backend/.env`
avant le premier démarrage : le compte est créé (ou promu admin s'il existe déjà)
automatiquement. Mot de passe oublié : mettre
`ADMIN_BOOTSTRAP_RESET_PASSWORD=true` le temps d'un redéploiement (le compte
reprend `ADMIN_BOOTSTRAP_PASSWORD`), puis revenir à `false`. Se connecter ensuite sur `/connexion` avec cet email — la
redirection vers `/admin` est automatique pour les comptes admin/modérateur.

### Tests automatisés

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Base MongoDB en mémoire et stockage local temporaire : aucune donnée réelle
touchée.

### Tests sans accès à MongoDB Atlas

`MONGO_URL=mongomock://` dans `.env` bascule vers une base MongoDB **en
mémoire** (`backend/requirements-dev.txt`), pratique pour développer/tester sans
connexion réseau — les données ne persistent pas entre redémarrages, **à ne
jamais utiliser en production**.

### Configurer Cloudflare R2 (production)

1. Dashboard Cloudflare → **R2** → créer deux buckets : `meetafrican-photos` et
   `meetafrican-documents`.
2. Sur `meetafrican-photos` : Settings → Public access → activer un accès public
   (domaine personnalisé recommandé, ex. `photos.beauthentik.net` ; l'URL
   `r2.dev` fournie par défaut convient pour tester). Renseigner cette URL dans
   `R2_PUBLIC_PHOTOS_BASE_URL`.
3. `meetafrican-documents` reste **privé** — ne rien activer dessus.
4. R2 → **Manage API Tokens** → créer un token avec droits Read & Write sur ces
   deux buckets → récupérer Account ID, Access Key ID, Secret Access Key.
5. Dans `backend/.env` : `STORAGE_BACKEND=r2` + les 5 variables `R2_*`
   correspondantes.

## Prochaines étapes

- Vidéos : le traitement (compression + flou) tourne dans le process web ;
  à déplacer vers un worker dédié si le volume de publications augmente
- Hub temps réel en mémoire (`backend/realtime.py`) : passer à Redis
  pub/sub si le backend tourne un jour sur plusieurs instances

- Gestion des comptes utilisateurs côté admin (liste, désactivation directe,
  changement de rôle) au-delà des files de modération
- Auto-hébergement de la police d'icônes (Material Symbols) : actuellement
  chargée depuis Google Fonts, donc dépendante de sa disponibilité réseau
