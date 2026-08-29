# site-meetafrican

MeetAfrican — site de rencontre pour hommes et femmes africains.

## État du projet

- **Design** : 22 écrans de maquette générés avec Stitch AI (Google), rangés dans
  [`design/stitch-exports/`](design/stitch-exports). Charte graphique extraite dans
  [`design/DESIGN_SYSTEM.md`](design/DESIGN_SYSTEM.md).
- **Implémentation** : socle en place — auth, abonnements Premium, paiement PawaPay
  (Mobile Money) fonctionnels de bout en bout. Matching, chat, notation,
  vérification d'identité et modération photo par IA restent à construire.

## Stack

- **Backend** : FastAPI (Python) + MongoDB (Motor), JWT.
- **Frontend** : React (Vite) + Tailwind CSS, aux couleurs de la charte MeetAfrican.
- **Paiement** : PawaPay Hosted Payment Page (Orange/Moov/Telecel), porté et adapté
  depuis `ShuyahBF/Emergent` (branche `Site-SawaliSmartSystems`) — voir
  `backend/routes/payments_pawapay.py`.
- **Base de données** : MongoDB Atlas, cluster `Cluster0` partagé, base dédiée
  `site_meetafrican` isolée des autres projets, toutes les collections préfixées
  `maf_` (voir `backend/db.py`).

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

- Fil de découverte / algorithme de matching
- Chat temps réel
- Vérification d'identité (pièce d'identité) avec bascule auto/manuelle et
  escalade humaine
- Modération des photos par IA (prompt système dédié)
- Notation entre comptes, signalement de faux profils, temps de réponse moyen
- Points de parrainage social (WhatsApp/Facebook/Instagram/TikTok)
- Back-office admin
