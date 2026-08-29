"""Point d'entrée FastAPI — MeetAfrican backend."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db import ensure_indexes
from routes import admin, auth, payments_pawapay, subscriptions
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


@api.get("/health")
async def health():
    return {"ok": True}


app.include_router(api)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await seed_default_plans()
