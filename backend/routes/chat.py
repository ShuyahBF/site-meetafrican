"""Conversations & messages entre profils matchés, avec calcul automatique
du temps de réponse moyen par utilisateur (affiché comme badge de
réactivité sur les profils, cf. maquette Stitch "Très réactive" /
"Répond parfois")."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from db import db
from models import Message

router = APIRouter(tags=["Chat"])


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


async def _get_conversation_or_403(conversation_id: str, user_id: str) -> dict:
    conv = await db.conversations.find_one({"id": conversation_id}, {"_id": 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    if user_id not in (conv["user_a"], conv["user_b"]):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return conv


@router.get("/conversations")
async def list_conversations(user: dict = Depends(get_current_user)):
    convs = await db.conversations.find(
        {"$or": [{"user_a": user["id"]}, {"user_b": user["id"]}]}, {"_id": 0}
    ).sort("last_message_at", -1).to_list(200)

    other_ids = [c["user_b"] if c["user_a"] == user["id"] else c["user_a"] for c in convs]
    others = await db.users.find({"id": {"$in": other_ids}}, {"_id": 0}).to_list(len(other_ids) or 1)
    others_by_id = {o["id"]: o for o in others}

    results = []
    for c in convs:
        other_id = c["user_b"] if c["user_a"] == user["id"] else c["user_a"]
        other = others_by_id.get(other_id)
        if not other:
            continue
        last_message = await db.messages.find_one(
            {"conversation_id": c["id"]}, {"_id": 0}, sort=[("created_at", -1)]
        )
        results.append({
            "conversation_id": c["id"],
            "other_user": {
                "id": other["id"], "full_name": other["full_name"],
                "photos": other.get("photos", []),
                "avg_response_seconds": other.get("avg_response_seconds"),
            },
            "last_message": last_message,
        })
    return results


@router.get("/conversations/{conversation_id}/messages", response_model=List[Message])
async def list_messages(conversation_id: str, limit: int = 100, user: dict = Depends(get_current_user)):
    await _get_conversation_or_403(conversation_id, user["id"])
    limit = min(max(limit, 1), 500)
    items = await db.messages.find(
        {"conversation_id": conversation_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    return items


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


@router.post("/conversations/{conversation_id}/messages", response_model=Message, status_code=201)
async def send_message(conversation_id: str, payload: MessageCreate, user: dict = Depends(get_current_user)):
    conv = await _get_conversation_or_403(conversation_id, user["id"])

    # Temps de réponse : si le dernier message de la conversation venait de
    # l'autre personne, celui-ci compte comme une réponse -> on met à jour
    # la moyenne glissante de l'expéditeur.
    previous = await db.messages.find_one(
        {"conversation_id": conversation_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    now = _now_dt()
    if previous and previous["sender_id"] != user["id"]:
        try:
            prev_dt = datetime.fromisoformat(previous["created_at"])
        except ValueError:
            prev_dt = None
        if prev_dt:
            delta_seconds = max((now - prev_dt).total_seconds(), 0)
            count = user.get("response_count", 0)
            current_avg = user.get("avg_response_seconds") or 0
            new_avg = (current_avg * count + delta_seconds) / (count + 1)
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"avg_response_seconds": new_avg, "response_count": count + 1}},
            )

    message = Message(conversation_id=conversation_id, sender_id=user["id"], text=payload.text)
    await db.messages.insert_one(message.model_dump(mode="json"))
    await db.conversations.update_one({"id": conversation_id}, {"$set": {"last_message_at": message.created_at}})
    return message
