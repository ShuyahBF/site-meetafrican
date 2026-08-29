"""Photos de profil — chaque photo ajoutée ou remplacée passe par la
modération IA (même logique activable/désactivable et escalade humaine que
la vérification d'identité, mais avec son propre prompt système)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_moderation import analyze_image
from auth import get_current_admin, get_current_user
from db import db
from models import DEFAULT_PHOTO_MODERATION_PROMPT, ModerationSettings, Photo, PhotoStatus

router = APIRouter(tags=["Photos de profil"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _moderation_settings() -> ModerationSettings:
    doc = await db.settings.find_one({"id": "global_moderation"}, {"_id": 0})
    return ModerationSettings(**doc) if doc else ModerationSettings()


class PhotoCreate(BaseModel):
    url: str
    is_primary: bool = False


@router.post("/me/photos", response_model=Photo, status_code=201)
async def add_photo(payload: PhotoCreate, user: dict = Depends(get_current_user)):
    settings = await _moderation_settings()
    photo = Photo(url=payload.url, is_primary=payload.is_primary)

    if settings.ai_auto_enabled:
        result = await analyze_image(payload.url, settings.photo_moderation_prompt or DEFAULT_PHOTO_MODERATION_PROMPT)
        photo.moderation_notes = result.reason
        photo.moderated_at = _now()
        if result.decision == "approved":
            photo.status = PhotoStatus.approved
        elif result.decision == "rejected":
            photo.status = PhotoStatus.rejected
        else:
            photo.status = PhotoStatus.needs_review
    else:
        photo.status = PhotoStatus.needs_review

    current = await db.users.find_one({"id": user["id"]}, {"_id": 0, "photos": 1})
    existing_photos = (current or {}).get("photos", [])
    if payload.is_primary:
        for p in existing_photos:
            p["is_primary"] = False
    new_photos = existing_photos + [photo.model_dump(mode="json")]

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"photos": new_photos, "updated_at": _now()}},
    )
    return photo


@router.delete("/me/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
    result = await db.users.update_one(
        {"id": user["id"]},
        {"$pull": {"photos": {"id": photo_id}}, "$set": {"updated_at": _now()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    return {"ok": True}


@router.get("/admin/photos/pending")
async def pending_photos(_: dict = Depends(get_current_admin)):
    """File d'attente de revue humaine — utilisateurs ayant au moins une
    photo needs_review ou rejected en attente d'un second regard."""
    users = await db.users.find(
        {"photos.status": {"$in": [PhotoStatus.needs_review.value]}},
        {"_id": 0, "id": 1, "full_name": 1, "photos": 1},
    ).to_list(200)
    items = []
    for u in users:
        for p in u.get("photos", []):
            if p.get("status") == PhotoStatus.needs_review.value:
                items.append({"user_id": u["id"], "full_name": u["full_name"], **p})
    return items


@router.post("/admin/photos/{user_id}/{photo_id}/review")
async def review_photo(user_id: str, photo_id: str, approve: bool, _: dict = Depends(get_current_admin)):
    new_status = PhotoStatus.approved.value if approve else PhotoStatus.rejected.value
    result = await db.users.update_one(
        {"id": user_id, "photos.id": photo_id},
        {"$set": {"photos.$.status": new_status, "photos.$.moderated_at": _now()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    return {"ok": True, "status": new_status}
