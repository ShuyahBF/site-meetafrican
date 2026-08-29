"""Hachage de mot de passe, émission/vérification JWT, dépendance FastAPI
`get_current_user`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from config import get_settings
from db import db
from models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


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


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide ou expirée")
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte introuvable ou désactivé")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return user


async def get_current_super_admin(user: dict = Depends(get_current_user)) -> dict:
    """Réservé aux comptes role="admin" (pas les modérateurs) — pour les
    actions sensibles comme changer le rôle d'un autre compte."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs (pas modérateur)")
    return user
