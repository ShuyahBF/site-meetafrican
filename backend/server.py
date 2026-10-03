"""Point d'entrée FastAPI — beAuthentik backend."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from activity import ActivityLogMiddleware
from config import get_settings
from db import db, ensure_indexes
from models import SiteAppearance
from routes import (
    abonnement_grace,
    admin,
    auth,
    auth_tiktok,
    chat,
    cycle_vie,
    interactions,
    maintenance_plateforme,
    matching,
    account_extras,
    parametres_plateforme,
    admin_timeline,
    community,
    payments_pawapay,
    tracking,
    transfert_donnees,
    phone_verification,
    photos,
    profiles,
    ratings,
    referrals,
    sauvegarde_auto,
    sessions_comptes,
    stats,
    test_data,
    subscriptions,
    uploads,
    verification,
    videos,
    vidal,
)
from seed import ensure_admin_user, seed_default_gifts, seed_default_plans
from vidal_sync import sync_scheduler_loop
# Version et lot de la plateforme (source unique : frontend/src/version.js)
import version_plateforme

settings = get_settings()

# Le numéro affiché dans la documentation /docs suit la version de la plateforme
app = FastAPI(title="beAuthentik API", version=version_plateforme.infos_version()["libelle"])

# Journal d'activité + IP de chaque requête (cf. activity.py). Ajouté AVANT
# CORS : il s'exécute donc à l'intérieur, sur les requêtes déjà acceptées.
app.add_middleware(ActivityLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
# « Continuer avec TikTok » (TikTok Login Kit)
api.include_router(auth_tiktok.router)
api.include_router(payments_pawapay.router)
api.include_router(subscriptions.router)
api.include_router(admin.router)
api.include_router(uploads.router)
api.include_router(verification.router)
api.include_router(photos.router)
api.include_router(matching.router)
api.include_router(profiles.router)
api.include_router(videos.router)
api.include_router(chat.router)
api.include_router(ratings.router)
api.include_router(referrals.router)
api.include_router(interactions.router)
api.include_router(vidal.router)
api.include_router(stats.router)
api.include_router(phone_verification.router)
api.include_router(account_extras.router)
api.include_router(community.router)
api.include_router(tracking.router)
api.include_router(admin_timeline.router)
api.include_router(test_data.router)
# Maintenance de la plateforme : état public + déconnexion de tous les utilisateurs
api.include_router(maintenance_plateforme.public)
api.include_router(maintenance_plateforme.admin)
# Export / import complets de la base (changement de cluster MongoDB)
api.include_router(transfert_donnees.router)
# Abonnements, sessions et sauvegardes (spécification commune du 02/10/2026)
api.include_router(sessions_comptes.compte)          # sessions + inactivité du membre
api.include_router(sessions_comptes.admin)
api.include_router(abonnement_grace.membre)          # A : grâce après échéance impayée
api.include_router(abonnement_grace.admin)
api.include_router(parametres_plateforme.router)     # réglages de l'administrateur principal
api.include_router(sauvegarde_auto.public)           # E : sauvegarde automatique (Cron Job) + D
api.include_router(sauvegarde_auto.admin)
api.include_router(cycle_vie.router)                 # C : cycle de vie du non-renouvellement


@api.get("/health")
async def health():
    return {"ok": True}


@api.get("/version")
async def version():
    """Version, lot et hash du commit du backend en cours d'exécution (public,
    sans authentification). Voir version_plateforme.py."""
    return version_plateforme.infos_version()


@api.get("/appearance", response_model=SiteAppearance)
async def public_appearance():
    """Lecture publique, sans authentification — la page d'accueil (et
    d'autres pages publiques à l'avenir) en ont besoin avant tout login.
    Modifiable par l'admin via PUT /admin/settings/appearance."""
    doc = await db.settings.find_one({"id": "global_appearance"}, {"_id": 0})
    return SiteAppearance(**doc) if doc else SiteAppearance()


app.include_router(api)

if settings.storage_backend == "local":
    # Stockage local — pratique en dev/test, jamais en production (voir
    # backend/storage.py). /api/files sert l'album photo (public par nature).
    # Les pièces d'identité vont dans un répertoire totalement SÉPARÉ (pas un
    # sous-dossier de uploads_dir : StaticFiles sert récursivement tout ce
    # qu'il trouve, un sous-dossier serait donc aussi exposé par /api/files) ;
    # /api/private-files reste non protégée, acceptable uniquement parce que
    # le mode local entier est explicitement réservé au développement.
    uploads_path = Path(settings.uploads_dir)
    uploads_path.mkdir(parents=True, exist_ok=True)
    app.mount("/api/files", StaticFiles(directory=str(uploads_path)), name="files")

    private_uploads_path = uploads_path.parent / f"{uploads_path.name}-private"
    private_uploads_path.mkdir(parents=True, exist_ok=True)
    app.mount("/api/private-files", StaticFiles(directory=str(private_uploads_path)), name="private_files")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_default_plans()
    await seed_default_gifts()
    await ensure_admin_user()
    # Boucle de fond : vérifie 1x/heure si une synchronisation planifiée du
    # référentiel produits VIDAL est due (fréquence configurable par
    # l'admin) — voir vidal_sync.py. Tâche best-effort : une erreur dans la
    # boucle ne doit jamais empêcher le serveur de démarrer/répondre.
    asyncio.create_task(sync_scheduler_loop())
    # Boucle de fond : vérifie chaque minute auprès de PawaPay les paiements
    # en attente (le callback du compte PawaPay partagé pointe vers Sawali).
    asyncio.create_task(payments_pawapay.reconcile_loop())
    # Tâche de fond : repasse les photos masquées et les vidéos publiques
    # déjà publiées au floutage "visage seul" (s'arrête quand tout est fait).
    from media_migration import migration_loop
    asyncio.create_task(migration_loop())
