"""Routes /api/auth — inscription, connexion, profil courant."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from activity import current_ip, log_activity

# Version des CGU / politique de confidentialité en vigueur (date de
# publication, affichée en tête des pages /cgu et /confidentialite).
TERMS_VERSION = "2026-09-28"
from fastapi import APIRouter, Depends, HTTPException, Request, status

import blocages_acces
import cycle_vie
import sessions_comptes

import maintenance_plateforme
from auth import get_current_user, hash_password, verify_password
from db import db
from models import Token, User, UserLogin, UserPublic, UserRegister, to_user_public, user_insert_doc
from routes.auth_tiktok import lier_si_demande, lire_code

router = APIRouter(prefix="/auth", tags=["Auth"])

MIN_AGE_YEARS = 18


def _age_years(birthdate: str) -> int:
    d = date.fromisoformat(birthdate)
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, request: Request):
    # Pas de nouveau compte pendant une maintenance (il serait perdu lors d'un transfert)
    await maintenance_plateforme.refuser_si_maintenance()
    if not payload.email and not payload.phone:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")
    try:
        if _age_years(payload.birthdate) < MIN_AGE_YEARS:
            raise HTTPException(status_code=400, detail="Inscription réservée aux 18 ans et plus")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date de naissance invalide")

    existing_query = []
    if payload.email:
        existing_query.append({"email": payload.email})
    if payload.phone:
        existing_query.append({"phone": payload.phone})
    if existing_query and await db.users.find_one({"$or": existing_query}):
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email/téléphone")
    # Lot 47 : adresse IP bloquée pour tous les comptes -> inscription refusée
    # (403 « acces_suspendu », tentative inscrite au journal des connexions)
    await blocages_acces.controler_connexion(None, "inscription", request.headers.get("user-agent"),
                                             identifiant=payload.email or payload.phone)

    # Code de liaison TikTok vérifié AVANT de créer le compte (expiré -> refus)
    if payload.tiktok_lien:
        await lire_code(payload.tiktok_lien, consommer=False)

    referred_by: Optional[str] = None
    if payload.referral_code:
        referrer = await db.users.find_one({"referral_code": payload.referral_code}, {"_id": 0, "id": 1})
        if referrer:
            referred_by = referrer["id"]

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        gender=payload.gender,
        birthdate=payload.birthdate,
        referred_by=referred_by,
    )
    doc = user_insert_doc(user)
    # IP d'inscription et de dernière connexion, consultables par l'admin.
    doc["registration_ip"] = doc["last_login_ip"] = current_ip()
    doc["last_login_at"] = datetime.now().astimezone().isoformat()
    # Acceptation des CGU et de la politique de confidentialité (mention
    # affichée sous le bouton d'inscription) : date + version acceptée.
    doc["terms_accepted_at"] = doc["last_login_at"]
    doc["terms_version"] = TERMS_VERSION
    await db.users.insert_one(doc.copy())
    # Inscription commencée par « Continuer avec TikTok » : liaison du compte TikTok
    await lier_si_demande(user.id, payload.tiktok_lien)
    # Ouverture d'une session (appareil, IP) — limite d'appareils, voir sessions_comptes.py
    token = await sessions_comptes.ouvrir(user.id, request.headers.get("user-agent"), methode="inscription")
    return Token(access_token=token, user=to_user_public(doc))


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, request: Request):
    user = await db.users.find_one(
        {"$or": [{"email": payload.identifier}, {"phone": payload.identifier}]},
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    # Membre suspendu pour non-renouvellement : il peut se connecter pour renouveler
    # son abonnement (seules les routes de renouvellement lui sont ouvertes)
    if not user.get("is_active", True) and not cycle_vie.est_suspendu(user):
        raise HTTPException(status_code=403, detail="Compte désactivé")
    # Maintenance : seul l'administrateur principal peut se connecter
    await maintenance_plateforme.refuser_si_maintenance(user)
    user.pop("_id", None)
    # Lot 47 : compte ou adresse IP bloqué par le super-administrateur -> 403
    # « acces_suspendu » (le site affiche « Accès momentanément suspendu »)
    await blocages_acces.controler_connexion(user, "mot_de_passe", request.headers.get("user-agent"),
                                             identifiant=payload.identifier)
    ip = current_ip()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"last_login_ip": ip, "last_login_at": datetime.now().astimezone().isoformat()}},
    )
    # La tentative est déjà journalisée par le middleware (sans identité,
    # le membre n'ayant pas encore de jeton) : on ajoute la connexion réussie.
    await log_activity(user["id"], "Connexion réussie", ip)
    # Compte existant + « Continuer avec TikTok » : liaison du compte TikTok
    await lier_si_demande(user["id"], payload.tiktok_lien)
    token = await sessions_comptes.ouvrir(user["id"], request.headers.get("user-agent"), methode="mot_de_passe")
    return Token(access_token=token, user=to_user_public(user))


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    profile = to_user_public(user)
    profile.likes_received = await db.swipes.count_documents(
        {"target_user_id": user["id"], "action": "like"}
    )
    return profile
