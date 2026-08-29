"""Point d'entrée FastAPI — MeetAfrican backend."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings
from db import ensure_indexes
from routes import admin, auth, chat, matching, payments_pawapay, photos, subscriptions, uploads, verification
from seed import seed_default_plans

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


@api.get("/health")
async def health():
    return {"ok": True}


app.include_router(api)

uploads_path = Path(settings.uploads_dir)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/api/files", StaticFiles(directory=str(uploads_path)), name="files")


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_default_plans()
