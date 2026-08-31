"""Conversations & messages entre profils matchés.

Le chat temps réel passe par WebSocket (/api/ws/conversations/{id}) ; les
routes REST restent disponibles pour lister l'historique et comme repli si
la connexion WebSocket échoue. Calcule aussi automatiquement le temps de
réponse moyen par utilisateur (affiché comme badge de réactivité sur les
profils, cf. maquette Stitch "Très réactive" / "Répond parfois")."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from auth import decode_access_token, get_current_user
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


async def _persist_message(conversation: dict, sender: dict, text: str) -> Message:
    """Logique partagée par la route REST et le WebSocket : calcule le temps
    de réponse si applicable, enregistre le message, met à jour la
    conversation."""
    conversation_id = conversation["id"]
    previous = await db.messages.find_one(
        {"conversation_id": conversation_id}, {"_id": 0}, sort=[("created_at", -1)]
    )
    now = _now_dt()
    if previous and previous["sender_id"] != sender["id"]:
        try:
            prev_dt = datetime.fromisoformat(previous["created_at"])
        except ValueError:
            prev_dt = None
        if prev_dt:
            delta_seconds = max((now - prev_dt).total_seconds(), 0)
            count = sender.get("response_count", 0)
            current_avg = sender.get("avg_response_seconds") or 0
            new_avg = (current_avg * count + delta_seconds) / (count + 1)
            await db.users.update_one(
                {"id": sender["id"]},
                {"$set": {"avg_response_seconds": new_avg, "response_count": count + 1}},
            )

    message = Message(conversation_id=conversation_id, sender_id=sender["id"], text=text)
    await db.messages.insert_one(message.model_dump(mode="json"))
    await db.conversations.update_one({"id": conversation_id}, {"$set": {"last_message_at": message.created_at}})
    return message


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
    message = await _persist_message(conv, user, payload.text)
    await ws_manager.broadcast(conversation_id, message.model_dump(mode="json"))
    return message


# ---------------------------------------------------------------------------
# WebSocket — diffusion en temps réel des nouveaux messages
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Registre en mémoire des connexions WebSocket actives par conversation.

    Suffisant pour un seul process backend. Si le service est un jour
    déployé sur plusieurs instances, remplacer par un pub/sub partagé
    (Redis, etc.) pour que les diffusions traversent les process."""

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, conversation_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(conversation_id, set()).add(ws)

    def disconnect(self, conversation_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(conversation_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._connections.pop(conversation_id, None)

    async def broadcast(self, conversation_id: str, payload: dict) -> None:
        for ws in list(self._connections.get(conversation_id, set())):
            try:
                await ws.send_json({"type": "message", "data": payload})
            except Exception:  # noqa: BLE001
                self.disconnect(conversation_id, ws)


ws_manager = ConnectionManager()


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_ws(websocket: WebSocket, conversation_id: str, token: str = ""):
    user_id = decode_access_token(token) if token else None
    if not user_id:
        await websocket.close(code=4401)  # non authentifié
        return
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("is_active", True):
        await websocket.close(code=4401)
        return
    conv = await db.conversations.find_one({"id": conversation_id}, {"_id": 0})
    if not conv or user_id not in (conv["user_a"], conv["user_b"]):
        await websocket.close(code=4403)  # accès refusé
        return

    await ws_manager.connect(conversation_id, websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            text = (payload.get("text") or "").strip()
            if not text or len(text) > 2000:
                continue
            # L'utilisateur peut avoir changé entre-temps (réactivité, etc.) — on
            # relit son état courant avant de persister.
            fresh_user = await db.users.find_one({"id": user_id}, {"_id": 0}) or user
            message = await _persist_message(conv, fresh_user, text)
            await ws_manager.broadcast(conversation_id, message.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(conversation_id, websocket)
