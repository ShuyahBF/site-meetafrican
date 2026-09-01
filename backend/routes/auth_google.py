"""Routes /api/auth/session et /api/auth/logout — Emergent-managed Google Auth.

Flux :
1. Le frontend redirige vers https://auth.emergentagent.com/?redirect=<origin>/decouverte.
2. Après consentement Google, l'utilisateur revient sur <origin>/decouverte#session_id=...
3. Le frontend envoie ce session_id à POST /api/auth/session (X-Session-ID header).
4. Le backend appelle https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data
   pour récupérer le profil + un session_token (durée 7 jours).
5. Le backend upsert l'utilisateur dans `maf_users`, stocke la session dans
   `maf_sessions`, pose un cookie httpOnly `session_token` et renvoie le profil.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response
from pydantic import BaseModel

from auth import get_current_user
from db import db
from models import Gender, Role, User, UserPublic, VerificationStatus, to_user_public

router = APIRouter(prefix="/auth", tags=["Auth"])

EMERGENT_SESSION_DATA_URL = (
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
)
SESSION_TTL_DAYS = 7


class EmergentSessionData(BaseModel):
    id: str  # Google sub (identifiant stable)
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str


async def _fetch_session_data(session_id: str) -> EmergentSessionData:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            EMERGENT_SESSION_DATA_URL,
            headers={"X-Session-ID": session_id},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Session Google invalide ou expirée")
    try:
        return EmergentSessionData(**resp.json())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Réponse Emergent Auth invalide: {exc}")


async def _upsert_google_user(profile: EmergentSessionData) -> dict:
    """Trouve l'utilisateur par google_sub puis par email, sinon en crée un.

    Les comptes créés via Google n'ont PAS de password_hash — ils ne peuvent
    pas se connecter via POST /api/auth/login. gender et birthdate sont
    initialisés à des valeurs par défaut ; `needs_profile_completion=True`
    signale au frontend qu'il faut proposer un écran de complétion."""
    existing = await db.users.find_one({"google_sub": profile.id}, {"_id": 0})
    if not existing and profile.email:
        existing = await db.users.find_one({"email": profile.email}, {"_id": 0})

    now = datetime.now(timezone.utc).isoformat()

    if existing:
        updates = {
            "google_sub": profile.id,
            "avatar_url": profile.picture,
            "updated_at": now,
        }
        # Ne pas écraser un nom déjà personnalisé si l'utilisateur l'a modifié.
        if not existing.get("full_name") or existing.get("full_name") == existing.get("email"):
            updates["full_name"] = profile.name
        await db.users.update_one({"id": existing["id"]}, {"$set": updates})
        existing.update(updates)
        return existing

    new_user = User(
        full_name=profile.name or profile.email,
        email=profile.email,
        password_hash=None,
        gender=Gender.homme,          # défaut — écrasé par la page de complétion
        birthdate="1990-01-01",       # défaut — idem
        role=Role.user,
        verification_status=VerificationStatus.unverified,
        google_sub=profile.id,
        avatar_url=profile.picture,
        needs_profile_completion=True,
    )
    doc = new_user.model_dump(mode="json")
    await db.users.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc


class GoogleSessionResponse(BaseModel):
    user: UserPublic


@router.post("/session", response_model=GoogleSessionResponse)
async def google_session_exchange(
    response: Response,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
):
    """Échange un session_id (URL fragment après OAuth) contre un cookie
    httpOnly `session_token` valable 7 jours. Renvoie le profil utilisateur."""
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Header X-Session-ID manquant")

    profile = await _fetch_session_data(x_session_id)
    user_doc = await _upsert_google_user(profile)

    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    await db.sessions.insert_one({
        "user_id": user_doc["id"],
        "session_token": profile.session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Cookie httpOnly, cross-site (SameSite=None + Secure requis) pour que le
    # frontend hébergé sur le même domaine que /api puisse le renvoyer.
    response.set_cookie(
        key="session_token",
        value=profile.session_token,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return {"user": to_user_public(user_doc)}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if token:
        await db.sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}
