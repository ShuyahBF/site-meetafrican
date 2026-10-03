"""Routes /api/admin — réglages paramétrables par l'administrateur système :
barème de points de parrainage, gestion des formules d'abonnement.

La bascule vérification/modération auto par IA vit dans
routes/verification.py (/admin/settings/moderation), à côté des prompts
système qu'elle contrôle."""
from __future__ import annotations

import re
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr

from auth import get_current_admin, get_current_super_admin
from config import get_settings
from db import db
from models import ReferralPointsSettings, SiteAppearance, SubscriptionPlan
from storage import save_public_media

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/settings/appearance", response_model=SiteAppearance)
async def get_appearance_settings(_: dict = Depends(get_current_admin)):
    doc = await db.settings.find_one({"id": "global_appearance"}, {"_id": 0})
    return SiteAppearance(**doc) if doc else SiteAppearance()


@router.put("/settings/appearance", response_model=SiteAppearance)
async def update_appearance_settings(payload: SiteAppearance, _: dict = Depends(get_current_admin)):
    doc = payload.model_dump()
    doc["id"] = "global_appearance"
    await db.settings.update_one({"id": "global_appearance"}, {"$set": doc}, upsert=True)
    return payload


# Formats acceptés pour la vidéo de présentation des Moments : ceux que tous
# les navigateurs récents lisent nativement dans une balise <video>.
HOME_VIDEO_TYPES = {"video/mp4", "video/webm"}


@router.post("/settings/appearance/moments-video")
async def upload_moments_video(file: UploadFile = File(...), _: dict = Depends(get_current_admin)):
    """Envoi du fichier vidéo de l'encart « Moments » de la page d'accueil.
    Le fichier est rangé dans le stockage public existant (même bucket que
    les photos et les Moments) et son URL est renvoyée ; c'est l'interface
    d'administration qui l'enregistre ensuite via PUT /settings/appearance.
    Pas de retraitement (floutage…) : la vidéo est fournie par l'admin."""
    settings = get_settings()
    if file.content_type not in HOME_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="Format non autorisé (MP4 ou WebM uniquement)")
    content = await file.read()
    if len(content) > settings.max_home_video_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Vidéo trop volumineuse (max {settings.max_home_video_upload_bytes // (1024 * 1024)} Mo)",
        )
    url = await save_public_media(content, file.content_type)
    return {"url": url}


@router.get("/settings/referral-points", response_model=ReferralPointsSettings)
async def get_referral_points_settings(_: dict = Depends(get_current_admin)):
    doc = await db.settings.find_one({"id": "global_referral_points"}, {"_id": 0})
    return doc or ReferralPointsSettings()


@router.put("/settings/referral-points", response_model=ReferralPointsSettings)
async def update_referral_points_settings(
    payload: ReferralPointsSettings, _: dict = Depends(get_current_admin)
):
    doc = payload.model_dump()
    doc["id"] = "global_referral_points"
    await db.settings.update_one({"id": "global_referral_points"}, {"$set": doc}, upsert=True)
    return payload


@router.get("/subscription-plans", response_model=List[SubscriptionPlan])
async def list_all_plans(_: dict = Depends(get_current_admin)):
    return await db.subscription_plans.find({}, {"_id": 0}).sort("duration_days", 1).to_list(50)


@router.post("/subscription-plans", response_model=SubscriptionPlan, status_code=201)
async def create_plan(payload: SubscriptionPlan, adm: dict = Depends(get_current_admin)):
    doc = payload.model_dump()
    # Case « Autorise le Mode Invisible » : seul le super-administrateur peut la cocher
    if adm.get("role") != "admin":
        doc["autorise_mode_invisible"] = False
    await db.subscription_plans.insert_one(dict(doc))
    return doc


@router.put("/subscription-plans/{plan_id}", response_model=SubscriptionPlan)
async def update_plan(plan_id: str, payload: SubscriptionPlan, adm: dict = Depends(get_current_admin)):
    existing = await db.subscription_plans.find_one({"id": plan_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Formule introuvable")
    doc = payload.model_dump()
    doc["id"] = plan_id
    # Case « Autorise le Mode Invisible » : un modérateur ne peut pas la changer
    # (la valeur enregistrée est conservée)
    if adm.get("role") != "admin":
        doc["autorise_mode_invisible"] = bool(existing.get("autorise_mode_invisible"))
    await db.subscription_plans.update_one({"id": plan_id}, {"$set": doc})
    return doc


# ---------------------------------------------------------------------------
# Équipe de modération
# ---------------------------------------------------------------------------
# L'administrateur désigne des modérateurs parmi les comptes existants (par
# email). Un modérateur accède au back-office (photos à revoir, vidéos,
# vérifications, signalements…) mais ne peut pas gérer l'équipe. Les comptes
# de l'équipe ne sont jamais visibles des membres (découverte, Moments,
# recherche, fiches profil, compteurs publics).

_TEAM_FIELDS = {"_id": 0, "id": 1, "full_name": 1, "email": 1, "role": 1, "last_seen_at": 1}


@router.get("/team")
async def list_team(_: dict = Depends(get_current_super_admin)):
    return await db.users.find({"role": {"$in": ["admin", "moderator"]}}, _TEAM_FIELDS).sort("full_name", 1).to_list(200)


class ModeratorAdd(BaseModel):
    email: EmailStr


@router.post("/team")
async def add_moderator(payload: ModeratorAdd, _: dict = Depends(get_current_super_admin)):
    # Email comparé sans tenir compte des majuscules.
    user = await db.users.find_one({"email": {"$regex": f"^{re.escape(payload.email)}$", "$options": "i"}}, _TEAM_FIELDS)
    if not user:
        raise HTTPException(status_code=404, detail="Aucun compte avec cet email : la personne doit d'abord s'inscrire")
    if user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Ce compte est déjà administrateur")
    await db.users.update_one({"id": user["id"]}, {"$set": {"role": "moderator"}})
    return {**user, "role": "moderator"}


@router.delete("/team/{user_id}")
async def remove_moderator(user_id: str, _: dict = Depends(get_current_super_admin)):
    result = await db.users.update_one({"id": user_id, "role": "moderator"}, {"$set": {"role": "user"}})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Modérateur introuvable")
    return {"ok": True}
