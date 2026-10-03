"""Routes /api/auth/tiktok — « Continuer avec TikTok » (TikTok Login Kit, OAuth v2).

Parcours :
  1. GET  /auth/tiktok/start      -> adresse de la page d'autorisation TikTok ;
  2. GET  /auth/tiktok/callback   -> retour de TikTok : le serveur échange le code,
     lit le profil (identifiant, nom affiché, avatar) et renvoie le navigateur vers
     /connexion?tiktok=<code à usage unique, valable 5 minutes> ;
  3. POST /auth/tiktok/finaliser  -> le site échange ce code :
       - compte déjà lié à ce TikTok -> jeton de connexion ;
       - sinon -> nom et avatar pour pré-remplir l'inscription, et un code de
         liaison à joindre à l'inscription (ou à une connexion classique).
Seul le scope `user.info.basic` est demandé : beAuthentik ne publie JAMAIS sur
TikTok. L'âge (18+) et la vérification d'identité restent exigés comme pour
toute inscription.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import blocages_acces
import cycle_vie
import maintenance_plateforme
import sessions_comptes
from activity import current_ip, log_activity
from config import get_settings
from db import db
from models import to_user_public

router = APIRouter(prefix="/auth/tiktok", tags=["Auth"])

URL_AUTORISATION = "https://www.tiktok.com/v2/auth/authorize/"
URL_JETON = "https://open.tiktokapis.com/v2/oauth/token/"
URL_PROFIL = "https://open.tiktokapis.com/v2/user/info/"
SCOPES = "user.info.basic"
DUREE_CODE = timedelta(minutes=5)


def configure() -> bool:
    s = get_settings()
    return bool(s.tiktok_client_key and s.tiktok_client_secret)


def redirect_uri() -> str:
    s = get_settings()
    return s.tiktok_redirect_uri or f"{s.public_base_url.rstrip('/')}/api/auth/tiktok/callback"


def _etat() -> str:
    """Paramètre « state » signé (anti-CSRF), valable 10 minutes."""
    s = get_settings()
    return jwt.encode({"t": "tiktok_login", "n": secrets.token_hex(8),
                       "exp": datetime.now(timezone.utc) + timedelta(minutes=10)}, s.jwt_secret, algorithm=s.jwt_algorithm)


def _etat_valide(etat: str) -> bool:
    s = get_settings()
    try:
        return jwt.decode(etat, s.jwt_secret, algorithms=[s.jwt_algorithm]).get("t") == "tiktok_login"
    except jwt.PyJWTError:
        return False


# --- Appels à TikTok (fonctions séparées : simulées dans les tests) ---
async def echanger_code(code: str) -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(URL_JETON, data={
            "client_key": s.tiktok_client_key, "client_secret": s.tiktok_client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri()},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
    donnees = r.json()
    if r.status_code >= 400 or donnees.get("error"):
        raise HTTPException(502, "Connexion TikTok refusée")
    return donnees


async def lire_profil(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(URL_PROFIL, params={"fields": "open_id,avatar_url,display_name"},
                             headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code >= 400:
        raise HTTPException(502, "Profil TikTok illisible")
    return (r.json().get("data") or {}).get("user") or {}


@router.get("/config")
async def config_tiktok():
    """Le site n'affiche le bouton « Continuer avec TikTok » que si TikTok est configuré."""
    return {"actif": configure()}


@router.get("/start")
async def demarrer():
    if not configure():
        raise HTTPException(503, "Connexion avec TikTok indisponible pour le moment")
    return {"url": f"{URL_AUTORISATION}?" + urlencode({
        "client_key": get_settings().tiktok_client_key, "scope": SCOPES, "response_type": "code",
        "redirect_uri": redirect_uri(), "state": _etat()})}


@router.get("/callback")
async def retour(code: str = "", state: str = "", error: str = ""):
    connexion = f"{get_settings().public_site_url}/connexion"
    if error:
        return RedirectResponse(f"{connexion}?tiktok_erreur=refuse")
    if not code or not _etat_valide(state):
        return RedirectResponse(f"{connexion}?tiktok_erreur=invalide")
    try:
        jetons = await echanger_code(code)
        profil = await lire_profil(jetons["access_token"])
    except (HTTPException, httpx.HTTPError, KeyError, ValueError):
        return RedirectResponse(f"{connexion}?tiktok_erreur=echec")
    open_id = profil.get("open_id") or jetons.get("open_id")
    if not open_id:
        return RedirectResponse(f"{connexion}?tiktok_erreur=echec")
    # Code à usage unique : ni jeton ni identifiant TikTok dans l'adresse
    code_unique = secrets.token_urlsafe(24)
    await db.tiktok_codes.insert_one({
        "code": code_unique, "open_id": open_id, "display_name": profil.get("display_name") or "",
        "avatar_url": profil.get("avatar_url") or "", "expire_le": datetime.now(timezone.utc) + DUREE_CODE,
        "utilise": False})
    return RedirectResponse(f"{connexion}?tiktok={code_unique}")


class Finalisation(BaseModel):
    code: str = Field(min_length=10, max_length=64)


async def lire_code(code: str, consommer: bool) -> dict:
    """Code valable (non expiré, non utilisé) ; le consomme si demandé."""
    doc = await db.tiktok_codes.find_one({"code": code, "utilise": False}, {"_id": 0})
    expire = doc and doc["expire_le"]
    if expire and expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    if not doc or expire < datetime.now(timezone.utc):
        raise HTTPException(400, "Connexion TikTok expirée : recommencez")
    if consommer:
        await db.tiktok_codes.update_one({"code": code}, {"$set": {"utilise": True}})
    return doc


@router.post("/finaliser")
async def finaliser(data: Finalisation, request: Request):
    doc = await lire_code(data.code, consommer=False)
    user = await db.users.find_one({"tiktok_open_id": doc["open_id"]}, {"_id": 0})
    if user:
        if not user.get("is_active", True) and not cycle_vie.est_suspendu(user):
            raise HTTPException(403, "Compte désactivé")
        # Maintenance : connexion refusée (sauf administrateur principal)
        await maintenance_plateforme.refuser_si_maintenance(user)
        # Lot 47 : compte ou adresse IP bloqué -> 403 « acces_suspendu »
        await blocages_acces.controler_connexion(user, "tiktok", request.headers.get("user-agent"),
                                                 identifiant=user.get("email") or user.get("phone"))
        await lire_code(data.code, consommer=True)
        ip = current_ip()
        await db.users.update_one({"id": user["id"]}, {"$set": {
            "last_login_ip": ip, "last_login_at": datetime.now().astimezone().isoformat()}})
        await log_activity(user["id"], "Connexion réussie (TikTok)", ip)
        jeton = await sessions_comptes.ouvrir(user["id"], request.headers.get("user-agent"), methode="tiktok")
        return {"access_token": jeton, "token_type": "bearer", "user": to_user_public(user)}
    # Pas encore de compte lié : infos pour pré-remplir l'inscription
    return {"inscription": {"nom": doc["display_name"], "avatar_url": doc["avatar_url"], "lien": data.code}}


async def lier_si_demande(user_id: str, code_lien: Optional[str]) -> None:
    """Lie le compte TikTok (code de /finaliser) au compte qui vient de s'inscrire ou de se connecter."""
    if not code_lien:
        return
    doc = await lire_code(code_lien, consommer=True)
    if await db.users.find_one({"tiktok_open_id": doc["open_id"], "id": {"$ne": user_id}}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "Ce compte TikTok est déjà lié à un autre membre")
    await db.users.update_one({"id": user_id}, {"$set": {
        "tiktok_open_id": doc["open_id"], "tiktok_lie_le": datetime.now().astimezone().isoformat()}})
