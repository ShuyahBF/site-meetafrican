"""Parrainage social — un utilisateur qui partage le lien du site sur
WhatsApp/Facebook/Instagram/TikTok gagne des points, selon un barème
paramétrable par l'admin (voir routes/admin.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from config import get_settings
from db import db
from models import ReferralPointsSettings, ReferralShare

router = APIRouter(prefix="/me/referrals", tags=["Parrainage"])

Platform = Literal["whatsapp", "facebook", "instagram", "tiktok"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _points_settings() -> ReferralPointsSettings:
    doc = await db.settings.find_one({"id": "global_referral_points"}, {"_id": 0})
    return ReferralPointsSettings(**doc) if doc else ReferralPointsSettings()


def _points_for(settings: ReferralPointsSettings, platform: str) -> int:
    return {
        "whatsapp": settings.points_whatsapp,
        "facebook": settings.points_facebook,
        "instagram": settings.points_instagram,
        "tiktok": settings.points_tiktok,
    }[platform]


@router.get("")
async def my_referrals(user: dict = Depends(get_current_user)):
    app_settings = get_settings()
    history = await db.referral_shares.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {
        "referral_code": user["referral_code"],
        "referral_link": f"{app_settings.frontend_origin}/inscription?ref={user['referral_code']}",
        "points": user.get("points", 0),
        "history": history,
    }


class ShareCreate(BaseModel):
    platform: Platform


@router.post("/share", response_model=ReferralShare, status_code=201)
async def share_for_points(payload: ShareCreate, user: dict = Depends(get_current_user)):
    points_settings = await _points_settings()

    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    shares_today = await db.referral_shares.count_documents(
        {"user_id": user["id"], "created_at": {"$gte": since}}
    )
    if shares_today >= points_settings.max_shares_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {points_settings.max_shares_per_day} partages/jour atteinte",
        )

    points_awarded = _points_for(points_settings, payload.platform)
    share = ReferralShare(user_id=user["id"], platform=payload.platform, points_awarded=points_awarded)
    await db.referral_shares.insert_one(share.model_dump(mode="json"))
    await db.users.update_one(
        {"id": user["id"]},
        {"$inc": {"points": points_awarded}, "$set": {"updated_at": _now()}},
    )
    return share
