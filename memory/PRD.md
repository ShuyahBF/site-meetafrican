# MeetAfrican — PRD (Product Requirements Document)

## Original problem statement
Reprise et mise en route d'une app web de rencontre africaine existante (repo GitHub `ShuyahBF/site-meetafrican`). Stack: FastAPI (Python) + MongoDB (Motor) + JWT côté backend, React + Vite + Tailwind côté frontend. Intégrations prévues: PawaPay (paiements mobile money), Anthropic Claude (modération IA), Cloudflare R2 (stockage). Objectif: démarrage progressif — Phase 1 (mode dégradé) validé puis intégrations branchées une par une.

## Architecture (in place)
- Backend `/app/backend/` (FastAPI, uvicorn `server:app` sur 0.0.0.0:8001 via supervisor)
  - Routes `/api/*` : auth, subscriptions, admin, uploads, verification, photos, matching, chat, ratings, referrals, payments (PawaPay)
  - MongoDB accédé via `PrefixedDatabase` (préfixe `maf_`), fallback dev `mongomock://` en mémoire
  - Stockage: backend "local" (dev) ou "r2" (prod)
  - Modération IA: `ai_moderation.py` (Anthropic Claude, désactivable)
  - Seed automatique au démarrage: 3 plans d'abonnement + compte admin bootstrap
- Frontend `/app/frontend/` (React 18, Vite 5, Tailwind 3, servi sur port 3000 via `yarn start` → alias `vite`)
  - Router (react-router v6) : `/`, `/inscription`, `/connexion`, `/decouverte`, `/matchs`, `/messages`, `/profil`, `/parrainage`, `/abonnement`, `/admin/*`
  - AuthContext + axios interceptor JWT

## User personas
- **Membres** : inscription, profil, photos, découverte/swipe, chat, ratings, parrainage, abonnement Premium via PawaPay.
- **Admins/modérateurs** : back-office `/admin` (dashboard, photos, vérifications d'identité, paiements, signalements, plans d'abonnement, paramètres IA).

## Core requirements
- Authentification JWT (email OU téléphone comme identifiant)
- Blocage inscription < 18 ans
- Découverte + swipe → match mutuel → conversation chat
- Modération photos + pièces d'identité (IA Claude + revue humaine)
- Paiement mobile money (Orange/Moov/Telecel) via PawaPay Hosted Payment Page
- Séparation stricte photos publiques / documents privés (R2 deux buckets)
- Système de parrainage + points
- Ratings entre utilisateurs

## What's been implemented — Phase 1 (2026-01-31)
- ✅ Import du repo `ShuyahBF/site-meetafrican` dans `/app`
- ✅ Backend démarré en mode dégradé (`MONGO_URL=mongomock://`, `STORAGE_BACKEND=local`, IA désactivée)
- ✅ Admin bootstrap créé automatiquement (`Admin@sawalismartsystems.com` / `Admin@Sawali2026`)
- ✅ 3 plans d'abonnement seedés (1 semaine 5000 XOF, 1 mois 12000 XOF, 12 mois 55000 XOF)
- ✅ Frontend adapté à l'env Emergent (Vite sur port 3000, `VITE_API_BASE_URL` pointe sur preview URL)
- ✅ CORS configuré sur l'origine preview
- ✅ Testing subagent : 79/80 tests pytest passent (98.8%)
- ✅ Bug fix : DELETE `/api/me/photos/{id}` retourne bien 404 pour photo inconnue
- ✅ Bug fix : `PUBLIC_BASE_URL` mis à jour vers l'URL preview (URLs de photos uploadées désormais chargeables depuis le navigateur)

## Prioritized backlog

### P0 — Phase 2 (bascule MongoDB Atlas)
- Ajouter IP de l'hôte au Network Access d'Atlas
- Remplacer `MONGO_URL=mongomock://` par la vraie URI Atlas (`site_meetafrican`, préfixe `maf_`)
- Rejouer parcours clés sur la vraie base
- Vérifier l'unicité des index (mongomock ne les applique pas — Atlas oui)

### P0 — Phase 3 (Stockage Cloudflare R2)
- `STORAGE_BACKEND=r2` + 5 variables `R2_*` + `R2_PUBLIC_PHOTOS_BASE_URL`
- Valider upload photo (URL publique OK) et upload document (privé, URL présignée courte)

### P0 — Phase 4 (Modération IA Claude)
- Activer `ANTHROPIC_API_KEY` + `ai_auto_enabled=true` dans les paramètres admin
- Tester les 3 décisions IA (approved/rejected/needs_review)
- Valider fallback si API indisponible (les photos passent en `needs_review`)

### P0 — Phase 5 (Paiement PawaPay)
- Clés `PAWAPAY_API_TOKEN_SANDBOX` puis production
- URL webhook stable (tunnel temporaire acceptable en preview, mais pas de vrai paiement avant URL webhook définitive)
- Test bout-en-bout d'un dépôt sandbox

### P1 — Phase 6 (Durcissement)
- Confirmer `STORAGE_BACKEND=r2` (jamais `local` en prod)
- Vérifier que `/api/private-files` n'est pas montée en mode r2 (déjà OK dans `server.py`)
- Aucune clé en dur, repo privé
- Logs/gestion d'erreurs sur IA, paiement, stockage

### P2 — Améliorations produit (post-stabilisation)
- Notifications push / chat temps réel enrichi (websockets déjà partiellement présents via `useConversationSocket.js`)
- Amélioration algo de matching (préférences utilisateur, plusieurs genres)
- Tableau de bord analytics admin
- Auto-hébergement de la police Material Symbols (retirer la dépendance Google Fonts)
- Gestion admins (liste, désactivation, rôles) au-delà des files de modération
- Exposer email/phone dans `/api/auth/me` pour affichage compte

### Dette technique connue
- Cluster Atlas partagé tier gratuit : limites de connexions sous charge → prévoir cluster dédié
- `matching.discover` : `_opposite(gender)` binaire, à généraliser si support d'un 3e genre
- `subscriptions.list_pending_proofs` : RBAC dupliqué inline au lieu de `get_current_admin`

## Notes techniques
- Les données sont **en mémoire** (mongomock) et perdues à chaque restart backend — le seed recrée automatiquement l'admin et les plans à chaque démarrage.
- Le champ de login s'appelle `identifier` (pas `email`), acceptant email OU téléphone.
- Les routes `matching`, `chat`, `ratings`, `referrals` sont montées **sans préfixe** — vrais chemins : `/api/discover`, `/api/swipe`, `/api/matches`, `/api/conversations`, `/api/me/ratings`, `/api/me/referrals`.
- Genre : uniquement `homme` | `femme` dans `models.Gender` (pas de `autre`).
