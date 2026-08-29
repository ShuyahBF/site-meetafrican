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
        },
        {"_id": 0},
    ).limit(limit)
    candidates = await cursor.to_list(limit)
    return [to_user_public(c) for c in candidates]


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

    results = []
    for m in matches:
        other_id = m["user_b"] if m["user_a"] == user["id"] else m["user_a"]
        other = others_by_id.get(other_id)
        if not other:
            continue
        conv = conv_by_match.get(m["id"])
        results.append({
            "match_id": m["id"],
            "created_at": m["created_at"],
            "conversation_id": conv["id"] if conv else None,
            "other_user": to_user_public(other),
        })
    return results
