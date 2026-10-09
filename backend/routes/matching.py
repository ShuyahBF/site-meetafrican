"""Découverte de profils et matching (like mutuel)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from db import db
from models import Conversation, Match, PhotoStatus, Swipe, UserPublic, to_user_public

router = APIRouter(tags=["Matching"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _opposite(gender: str) -> str:
    return "femme" if gender == "homme" else "homme"


async def matched_ids(viewer_id: str, other_ids: List[str]) -> set:
    """Parmi `other_ids`, les membres avec qui `viewer_id` a matché (une seule requête)."""
    if not other_ids:
        return set()
    cursor = db.matches.find(
        {"$or": [{"user_a": viewer_id, "user_b": {"$in": other_ids}}, {"user_b": viewer_id, "user_a": {"$in": other_ids}}]},
        {"_id": 0, "user_a": 1, "user_b": 1},
    )
    return {m["user_b"] if m["user_a"] == viewer_id else m["user_a"] async for m in cursor}


async def _mask_photos_for_viewer(profiles: List[UserPublic], viewer_id: str) -> List[UserPublic]:
    """09/10/2026 — règle du propriétaire : « Le bandeau n'est mis sur une photo que si le visiteur n'a pas matché
    avec le propriétaire de la photo. » Le visage d'un profil est donc caché (bandeau noir ou masque sanitaire,
    voir image_processing.apply_face_mask) tant qu'il n'y a pas de match ; après un match, la photo est en clair.
    Le super-administrateur voit les photos en clair (validation). S'applique aux photos approuvées."""
    if not profiles:
        return profiles
    viewer = await db.users.find_one({"id": viewer_id}, {"_id": 0, "role": 1}) or {}
    if viewer.get("role") == "admin":
        return profiles
    en_clair = await matched_ids(viewer_id, [p.id for p in profiles])
    for p in profiles:
        if p.id in en_clair or p.id == viewer_id:
            continue
        for photo in p.photos:
            if photo.status == PhotoStatus.approved and photo.masked_url:
                photo.url = photo.masked_url
    return profiles


async def _with_likes_received(profiles: List[UserPublic]) -> List[UserPublic]:
    """Complète likes_received (compteur non stockable sur le seul document
    utilisateur — nécessite d'agréger la collection swipes) en une seule
    requête groupée plutôt qu'une par profil."""
    if not profiles:
        return profiles
    ids = [p.id for p in profiles]
    cursor = db.swipes.aggregate([
        {"$match": {"target_user_id": {"$in": ids}, "action": "like"}},
        {"$group": {"_id": "$target_user_id", "count": {"$sum": 1}}},
    ])
    counts = {row["_id"]: row["count"] async for row in cursor}
    for p in profiles:
        p.likes_received = counts.get(p.id, 0)
    return profiles


@router.get("/discover", response_model=List[UserPublic])
async def discover(limit: int = 20, user: dict = Depends(get_current_user)):
    limit = min(max(limit, 1), 50)
    already_swiped = await db.swipes.distinct("target_user_id", {"user_id": user["id"]})
    excluded_ids = set(already_swiped) | {user["id"]}

    cursor = db.users.find(
        {
            "id": {"$nin": list(excluded_ids)},
            "gender": _opposite(user["gender"]),
            "is_active": True,
            "photos.status": PhotoStatus.approved.value,
            # Admin et modérateurs ne sont jamais proposés aux membres.
            "role": {"$nin": ["admin", "moderator"]},
        },
        {"_id": 0},
    ).limit(limit)
    candidates = await cursor.to_list(limit)
    profiles = [to_user_public(c) for c in candidates]
    profiles = await _with_likes_received(profiles)
    return await _mask_photos_for_viewer(profiles, user["id"])


class SwipeCreate(BaseModel):
    target_user_id: str
    action: Literal["like", "pass"]


class SwipeResult(BaseModel):
    matched: bool
    match_id: Optional[str] = None


@router.post("/swipe", response_model=SwipeResult)
async def swipe(payload: SwipeCreate, user: dict = Depends(get_current_user)):
    if payload.target_user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Action invalide")
    target = await db.users.find_one({"id": payload.target_user_id}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    swipe_doc = Swipe(user_id=user["id"], target_user_id=payload.target_user_id, action=payload.action)
    await db.swipes.update_one(
        {"user_id": user["id"], "target_user_id": payload.target_user_id},
        {"$set": swipe_doc.model_dump(mode="json")},
        upsert=True,
    )

    if payload.action != "like":
        return SwipeResult(matched=False)

    reciprocal = await db.swipes.find_one(
        {"user_id": payload.target_user_id, "target_user_id": user["id"], "action": "like"}
    )
    if not reciprocal:
        return SwipeResult(matched=False)

    user_a, user_b = sorted([user["id"], payload.target_user_id])
    existing_match = await db.matches.find_one({"user_a": user_a, "user_b": user_b})
    if existing_match:
        return SwipeResult(matched=True, match_id=existing_match["id"])

    match = Match(user_a=user_a, user_b=user_b)
    await db.matches.insert_one(match.model_dump(mode="json"))
    conversation = Conversation(match_id=match.id, user_a=user_a, user_b=user_b)
    await db.conversations.insert_one(conversation.model_dump(mode="json"))
    return SwipeResult(matched=True, match_id=match.id)


@router.post("/swipe/undo")
async def undo_last_swipe(user: dict = Depends(get_current_user)):
    """Annule le dernier swipe de l'utilisateur — le profil réapparaîtra
    dans /discover. Refusé si ce swipe a déjà donné lieu à un match (annuler
    romprait silencieusement une conversation déjà commencée)."""
    last = await db.swipes.find_one(
        {"user_id": user["id"]}, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not last:
        raise HTTPException(status_code=404, detail="Aucun swipe à annuler")

    user_a, user_b = sorted([user["id"], last["target_user_id"]])
    if await db.matches.find_one({"user_a": user_a, "user_b": user_b}):
        raise HTTPException(status_code=400, detail="Impossible d'annuler : ce profil est déjà un match")

    await db.swipes.delete_one({"id": last["id"]})
    return {"ok": True, "target_user_id": last["target_user_id"]}


@router.get("/matches")
async def list_matches(user: dict = Depends(get_current_user)):
    matches = await db.matches.find(
        {"$or": [{"user_a": user["id"]}, {"user_b": user["id"]}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    other_ids = [m["user_b"] if m["user_a"] == user["id"] else m["user_a"] for m in matches]
    others = await db.users.find({"id": {"$in": other_ids}}, {"_id": 0}).to_list(len(other_ids) or 1)
    others_by_id = {o["id"]: o for o in others}

    conversations = await db.conversations.find(
        {"match_id": {"$in": [m["id"] for m in matches]}}, {"_id": 0}
    ).to_list(len(matches) or 1)
    conv_by_match = {c["match_id"]: c for c in conversations}

    other_profiles = [to_user_public(o) for o in others]
    other_profiles = await _mask_photos_for_viewer(other_profiles, user["id"])
    profile_by_id = {p.id: p for p in other_profiles}

    results = []
    for m in matches:
        other_id = m["user_b"] if m["user_a"] == user["id"] else m["user_a"]
        other = profile_by_id.get(other_id)
        if not other:
            continue
        conv = conv_by_match.get(m["id"])
        results.append({
            "match_id": m["id"],
            "created_at": m["created_at"],
            "conversation_id": conv["id"] if conv else None,
            "other_user": other,
        })
    return results
