"""Hachage de mot de passe, émission/vérification JWT, dépendance FastAPI
`get_current_user`."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

import maintenance_plateforme
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
    maintenant = datetime.now(timezone.utc)
    expires_at = maintenant + timedelta(minutes=settings.jwt_expires_minutes)
    # « ouv » : heure d'ouverture de la session (secondes, avec décimales) —
    # sert à invalider les sessions ouvertes avant une maintenance
    # (voir maintenance_plateforme.session_valide).
    payload = {"sub": user_id, "exp": expires_at, "ouv": maintenant.timestamp()}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_payload(token: str) -> Optional[dict]:
    """Contenu du jeton (None s'il est invalide ou expiré)."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload if payload.get("sub") else None


def decode_access_token(token: str) -> Optional[str]:
    payload = decode_access_payload(token)
    return payload.get("sub") if payload else None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    payload = decode_access_payload(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalide ou expirée")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte introuvable ou désactivé")
    # Maintenance de la plateforme : 503 pendant la maintenance, 401 pour une
    # session ouverte avant la dernière maintenance (administrateur jamais bloqué)
    await maintenance_plateforme.controler_session(user, payload)
    _touch_last_seen(user)
    return user


def _touch_last_seen(user: dict) -> None:
    """Marque l'utilisateur comme actif "maintenant", en tâche de fond pour
    ne pas ralentir la requête en cours. Throttle à 60s (au lieu d'écrire à
    chaque requête authentifiée) : largement suffisant vu le seuil "en
    ligne" de 5 minutes (models.ONLINE_THRESHOLD_SECONDS).
    Mode invisible (réglages du compte) : rien n'est enregistré, le membre
    n'apparaît jamais "en ligne"."""
    if (user.get("settings") or {}).get("invisible_mode"):
        return
    last_seen_at = user.get("last_seen_at")
    now = datetime.now(timezone.utc)
    if last_seen_at:
        try:
            if (now - datetime.fromisoformat(last_seen_at)).total_seconds() < 60:
                return
        except ValueError:
            pass
    asyncio.create_task(
        db.users.update_one({"id": user["id"]}, {"$set": {"last_seen_at": now.isoformat()}})
    )


async def get_current_super_admin(user: dict = Depends(get_current_user)) -> dict:
    """Administrateur principal uniquement (pas les modérateurs) : gestion
    de l'équipe de modération."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé à l'administrateur")
    return user


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Réservé aux administrateurs")
    return user
