"""Point d'entrée FastAPI — MeetAfrican backend."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db import ensure_indexes
from routes import (
    admin,
    auth,
    chat,
    matching,
    payments_pawapay,
    photos,
    ratings,
    referrals,
    subscriptions,
    uploads,
    verification,
)
from seed import ensure_admin_user, seed_default_plans

settings = get_settings()

app = FastAPI(title="MeetAfrican API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(payments_pawapay.router)
api.include_router(subscriptions.router)
api.include_router(admin.router)
api.include_router(uploads.router)
api.include_router(verification.router)
api.include_router(photos.router)
api.include_router(matching.router)
api.include_router(chat.router)
api.include_router(ratings.router)
api.include_router(referrals.router)


@api.get("/health")
async def health():
    return {"ok": True}


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
    await ensure_admin_user()
