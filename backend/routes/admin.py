"""Routes /api/admin — réglages paramétrables par l'administrateur système :
barème de points de parrainage, activation/désactivation de la vérification
automatique, gestion des formules d'abonnement."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_admin
from db import db
from models import ReferralPointsSettings, SubscriptionPlan

router = APIRouter(prefix="/admin", tags=["Administration"])


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


@router.put("/settings/verification-auto")
async def toggle_verification_auto(enabled: bool, _: dict = Depends(get_current_admin)):
    """Active/désactive la vérification d'identité automatique par IA au
    niveau global. Quand désactivée, toute soumission passe directement en
    revue humaine."""
    await db.settings.update_one(
        {"id": "global"}, {"$set": {"verification_auto_enabled": enabled}}, upsert=True
    )
    return {"ok": True, "verification_auto_enabled": enabled}


@router.get("/subscription-plans", response_model=List[SubscriptionPlan])
async def list_all_plans(_: dict = Depends(get_current_admin)):
    return await db.subscription_plans.find({}, {"_id": 0}).sort("duration_days", 1).to_list(50)


@router.post("/subscription-plans", response_model=SubscriptionPlan, status_code=201)
async def create_plan(payload: SubscriptionPlan, _: dict = Depends(get_current_admin)):
    await db.subscription_plans.insert_one(payload.model_dump())
    return payload


@router.put("/subscription-plans/{plan_id}", response_model=SubscriptionPlan)
async def update_plan(plan_id: str, payload: SubscriptionPlan, _: dict = Depends(get_current_admin)):
    existing = await db.subscription_plans.find_one({"id": plan_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Formule introuvable")
    doc = payload.model_dump()
    doc["id"] = plan_id
    await db.subscription_plans.update_one({"id": plan_id}, {"$set": doc})
    return doc
