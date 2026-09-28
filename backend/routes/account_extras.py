"""Réglages du compte et historique des visites.

  - GET/PUT /me/settings : notes vocales (envoyer/recevoir), transcription
    écrite des notes vocales, mode invisible.
  - GET /me/visitors     : qui a consulté mon profil et regardé mes Moments
    (horodaté). Les visiteurs en mode invisible et l'équipe n'y figurent pas.
  - record_profile_visit : appelé à l'ouverture d'une fiche profil.

Mode invisible : le membre n'apparaît plus "en ligne" (ni "vu il y a…"),
et ses propres visites ne sont pas montrées aux profils qu'il consulte.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_current_user
from db import db

router = APIRouter(tags=["Réglages & visites"])

# Réglages par défaut d'un compte (stockés dans users.settings)
DEFAULT_SETTINGS = {
    "voice_notes": True,          # envoyer et recevoir des notes vocales
    "voice_transcription": True,  # transcrire mes notes / voir les transcriptions
    "invisible_mode": False,      # masquer ma présence et mes visites
}
_STAFF = ("admin", "moderator")


def user_settings(user: dict) -> dict:
    return {**DEFAULT_SETTINGS, **(user.get("settings") or {})}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/me/settings")
async def get_settings_(user: dict = Depends(get_current_user)):
    return user_settings(user)


class SettingsUpdate(BaseModel):
    voice_notes: Optional[bool] = None
    voice_transcription: Optional[bool] = None
    invisible_mode: Optional[bool] = None


@router.put("/me/settings")
async def update_settings(payload: SettingsUpdate, user: dict = Depends(get_current_user)):
    changes = {f"settings.{k}": v for k, v in payload.model_dump(exclude_none=True).items()}
    update: dict = {"$set": changes} if changes else {}
    if payload.invisible_mode:
        # Passage en invisible : on efface immédiatement la trace "vu il y a…"
        update["$unset"] = {"last_seen_at": ""}
    if update:
        await db.users.update_one({"id": user["id"]}, update)
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0, "settings": 1})
    return user_settings(fresh or {})


async def record_profile_visit(visitor: dict, target_id: str) -> None:
    """Une visite par visiteur, par profil et par jour (compteur + dernière date)."""
    if visitor["id"] == target_id or visitor.get("role") in _STAFF:
        return
    now = _now()
    await db.profile_visits.update_one(
        {"visitor_id": visitor["id"], "target_id": target_id, "day": now[:10]},
        {"$set": {"last_at": now, "invisible": bool(user_settings(visitor)["invisible_mode"])},
         "$setOnInsert": {"first_at": now}, "$inc": {"count": 1}},
        upsert=True,
    )


async def _cards(ids) -> dict:
    ids = [i for i in set(ids) if i]
    docs = await db.users.find(
        {"id": {"$in": ids}, "role": {"$nin": list(_STAFF)}, "is_active": True},
        {"_id": 0, "id": 1, "full_name": 1, "city": 1, "photos": 1, "verification_status": 1, "is_test_data": 1,
         "settings": 1},
    ).to_list(len(ids) or 1)
    out = {}
    for d in docs:
        approved = [p for p in d.get("photos", []) if p.get("status") == "approved"]
        primary = next((p for p in approved if p.get("is_primary")), approved[0] if approved else None)
        out[d["id"]] = {
            "id": d["id"], "full_name": d["full_name"], "city": d.get("city"),
            "is_verified": d.get("verification_status") == "verified", "is_test_data": bool(d.get("is_test_data")),
            "avatar_url": (primary.get("masked_url") or primary.get("url")) if primary else None,
        }
    return out


@router.get("/me/visitors")
async def my_visitors(user: dict = Depends(get_current_user)):
    """Historique horodaté : visites de mon profil et vues de mes Moments."""
    visits = await db.profile_visits.find(
        {"target_id": user["id"], "invisible": {"$ne": True}}, {"_id": 0}
    ).sort("last_at", -1).to_list(300)
    my_videos = await db.videos.find({"user_id": user["id"]}, {"_id": 0, "id": 1, "caption": 1, "poster_url": 1}).to_list(500)
    videos_by_id = {v["id"]: v for v in my_videos}
    views = await db.video_views.find(
        {"video_id": {"$in": list(videos_by_id)}, "user_id": {"$ne": user["id"]}, "invisible": {"$ne": True}}, {"_id": 0}
    ).to_list(1000)
    views.sort(key=lambda v: v.get("created_at") or v.get("viewed_at") or "", reverse=True)
    cards = await _cards([v["visitor_id"] for v in visits] + [v["user_id"] for v in views])

    profile_items = [
        {"visitor": cards[v["visitor_id"]], "at": v["last_at"], "count": v.get("count", 1)}
        for v in visits if v["visitor_id"] in cards
    ]
    moment_items = [
        {"viewer": cards[v["user_id"]], "at": v.get("created_at") or v.get("viewed_at"),
         "video": videos_by_id.get(v["video_id"])}
        for v in views if v["user_id"] in cards
    ]
    return {"profile_visits": profile_items[:200], "moment_views": moment_items[:200]}
