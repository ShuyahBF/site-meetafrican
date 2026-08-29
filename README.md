# site-meetafrican

MeetAfrican — site de rencontre pour hommes et femmes africains.

## État du projet

- **Design** : 22 écrans de maquette générés avec Stitch AI (Google), rangés dans
  [`design/stitch-exports/`](design/stitch-exports). Charte graphique extraite dans
  [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md).
- **Implémentation** : auth, abonnements Premium, paiement PawaPay (Mobile Money),
  découverte/matching (swipe), chat, vérification d'identité et modération des
  photos de profil par IA (Claude vision) fonctionnels de bout en bout. Notation
  entre comptes, signalement de faux profils, points de parrainage social et
  back-office admin restent à construire.

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

## Prochaines étapes

- Notation entre comptes et signalement de faux profils
- Points de parrainage social (WhatsApp/Facebook/Instagram/TikTok)
- Back-office admin (interface, pas seulement l'API)
- Chat en temps réel (WebSocket — actuellement en polling côté frontend)
- Objet storage S3-compatible pour les photos/pièces d'identité (actuellement
  stockage local côté serveur, à ne pas garder en production)
