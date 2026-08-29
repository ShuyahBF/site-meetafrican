# site-meetafrican

MeetAfrican — site de rencontre pour hommes et femmes africains.

## État du projet

- **Design** : 22 écrans de maquette générés avec Stitch AI (Google), rangés dans
  [`design/stitch-exports/`](design/stitch-exports). Charte graphique extraite dans
  [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md).
- **Implémentation** : auth, abonnements Premium, paiement PawaPay (Mobile Money),
  découverte/matching (swipe), chat temps réel (WebSocket), vérification
  d'identité et modération des photos de profil par IA (Claude vision), notation
  entre comptes, signalement de faux profils, points de parrainage social,
  stockage objet Cloudflare R2 et back-office admin (`/admin` — modération,
  formules d'abonnement, réglages, gestion des comptes) fonctionnels de bout en
  bout — testés en local et contre un vrai bucket R2 (voir section Tests
  ci-dessous).

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

### Accéder au back-office admin

Définir `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` dans `backend/.env`
avant le premier démarrage : le compte est créé (ou promu admin s'il existe déjà)
automatiquement. Se connecter ensuite sur `/connexion` avec cet email — la
redirection vers `/admin` est automatique pour les comptes admin/modérateur.

### Tests sans accès à MongoDB Atlas

`MONGO_URL=mongomock://` dans `.env` bascule vers une base MongoDB **en
mémoire** (`backend/requirements-dev.txt`), pratique pour développer/tester sans
connexion réseau — les données ne persistent pas entre redémarrages, **à ne
jamais utiliser en production**.

### Configurer Cloudflare R2 (production)

1. Dashboard Cloudflare → **R2** → créer deux buckets : `meetafrican-photos` et
   `meetafrican-documents`.
2. Sur `meetafrican-photos` : Settings → Public access → activer un accès public
   (domaine personnalisé recommandé, ex. `photos.meetafrican.com` ; l'URL
   `r2.dev` fournie par défaut convient pour tester). Renseigner cette URL dans
   `R2_PUBLIC_PHOTOS_BASE_URL`.
3. `meetafrican-documents` reste **privé** — ne rien activer dessus.
4. R2 → **Manage API Tokens** → créer un token avec droits Read & Write sur ces
   deux buckets → récupérer Account ID, Access Key ID, Secret Access Key.
5. Dans `backend/.env` : `STORAGE_BACKEND=r2` + les 5 variables `R2_*`
   correspondantes.

## Prochaines étapes

- Auto-hébergement de la police d'icônes (Material Symbols) : actuellement
  chargée depuis Google Fonts, donc dépendante de sa disponibilité réseau
