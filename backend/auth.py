"""Hachage de mot de passe, émission/vérification JWT, dépendance FastAPI
`get_current_user`.

Deux mécanismes d'authentification coexistent :
- JWT local (POST /api/auth/login avec identifier+password) — Bearer header.
- Session Emergent Auth (Google) — cookie httpOnly `session_token`, ou
  Bearer avec la même valeur. Stockée dans la collection `maf_sessions`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext

from config import get_settings
from db import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": user_id, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


async def _user_id_from_session_token(token: str) -> Optional[str]:
    """Vérifie un session_token Emergent Auth stocké en base.

    Rappel: MongoDB stocke des datetimes naïfs ; on force UTC avant
    comparaison (playbook)."""
    doc = await db.sessions.find_one({"session_token": token}, {"_id": 0})
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return doc.get("user_id")


async def get_current_user(request: Request) -> dict:
    """Résout l'utilisateur courant depuis :
    1. le cookie httpOnly `session_token` (flux Emergent Auth), OU
    2. l'en-tête Authorization: Bearer <token> — d'abord essayé comme
       session_token en base, puis comme JWT local.

    N.B. On n'utilise pas la dépendance HTTPBearer de FastAPI : elle
    empêche l'auth par cookie (playbook)."""
    user_id: Optional[str] = None

    # 1) Cookie session_token
    cookie_token = request.cookies.get("session_token")
    if cookie_token:
        user_id = await _user_id_from_session_token(cookie_token)

    # 2) Bearer (session_token en base OU JWT local)
    if not user_id:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            user_id = await _user_id_from_session_token(token)
            if not user_id:
                user_id = decode_access_token(token)

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")

    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte introuvable ou désactivé")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return user
