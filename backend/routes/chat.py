"""Conversations & messages entre profils matchés.

Le chat temps réel passe par WebSocket (/api/ws/conversations/{id}) ; les
routes REST restent disponibles pour lister l'historique et comme repli si
la connexion WebSocket échoue. Le WebSocket transporte aussi l'indicateur
"en train d'écrire…" et les accusés de lecture ("Vu"). Calcule aussi automatiquement le temps de
réponse moyen par utilisateur (affiché comme badge de réactivité sur les
profils, cf. maquette Stitch "Très réactive" / "Répond parfois")."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

import maintenance_plateforme
import sessions_comptes
from auth import decode_access_payload, get_current_user
from db import db
from routes.account_extras import user_settings
from storage import presigned_document_url, save_private_media
from models import Message, PhotoStatus, _is_online
from activity import ip_from_headers, log_activity
from realtime import RateLimiter, conversation_channel, hub
from routes.subscriptions import has_active_subscription

router = APIRouter(tags=["Chat"])


def _masked_photos(photos: list, unlocked: bool) -> list:
    """Même règle que routes/matching.py:_mask_photos_for_viewer, mais sur
    un dict brut plutôt qu'un UserPublic — cette route ne passe pas par
    to_user_public()."""
    if unlocked:
        return photos
    result = []
    for p in photos:
        p = dict(p)
        if p.get("status") == PhotoStatus.approved.value and p.get("masked_url"):
            p["url"] = p["masked_url"]
        result.append(p)
    return result


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


async def _persist_message(conversation: dict, sender: dict, text: str, **voice) -> Message:
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

    # Réutilise le "now" déjà capturé plus haut plutôt que de laisser Message
    # en générer un nouveau : sans ça, l'aller-retour MongoDB de la mise à
    # jour du temps de réponse ci-dessus s'intercale entre les deux captures
    # d'horloge, et created_at fini légèrement en retard sur le calcul du
    # delta qui a servi à le produire — écart mineur mais qui s'accumule sur
    # une conversation longue.
    message = Message(conversation_id=conversation_id, sender_id=sender["id"], text=text, created_at=now.isoformat(), **voice)
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
    unlocked = await has_active_subscription(user["id"])

    results = []
    for c in convs:
        other_id = c["user_b"] if c["user_a"] == user["id"] else c["user_a"]
        other = others_by_id.get(other_id)
        if not other:
            continue
        last_message = await db.messages.find_one(
            {"conversation_id": c["id"]}, {"_id": 0}, sort=[("created_at", -1)]
        )
        unread = await db.messages.count_documents(_unread_query(c["id"], user["id"]))
        results.append({
            "conversation_id": c["id"],
            "other_user": {
                "id": other["id"], "full_name": other["full_name"],
                "photos": _masked_photos(other.get("photos", []), unlocked),
                "avg_response_seconds": other.get("avg_response_seconds"),
                "gender": other.get("gender"),
                "last_seen_at": other.get("last_seen_at"),
                "is_online": _is_online(other.get("last_seen_at")),
                "is_verified": other.get("verification_status") == "verified",
                "is_test_data": bool(other.get("is_test_data")),
                # Accepte les notes vocales ? (masque le micro sinon)
                "accepts_voice_notes": user_settings(other)["voice_notes"],
            },
            "last_message": last_message,
            "unread_count": unread,
        })
    return results


def _unread_query(conversation_id: str, reader_id: str) -> dict:
    """Messages de l'AUTRE participant pas encore lus par `reader_id`."""
    return {"conversation_id": conversation_id, "sender_id": {"$ne": reader_id}, "read_at": None}


async def _mark_read(conversation_id: str, reader_id: str) -> str | None:
    """Marque comme lus tous les messages reçus dans la conversation et
    prévient l'autre participant (s'il est connecté) pour qu'il voie "Vu".
    Renvoie la date de lecture, ou None s'il n'y avait rien à marquer."""
    result = await db.messages.update_many(
        _unread_query(conversation_id, reader_id), {"$set": {"read_at": _now()}}
    )
    if not result.modified_count:
        return None
    read_at = _now()
    await hub.send(conversation_channel(conversation_id), "read", {"reader_id": reader_id, "read_at": read_at})
    return read_at


@router.get("/conversations/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    """Total de messages non lus, toutes conversations confondues, et
    demandes d'accès vidéo en attente — badge rouge sur l'onglet "Messages"
    de la barre de navigation."""
    convs = await db.conversations.find(
        {"$or": [{"user_a": user["id"]}, {"user_b": user["id"]}]}, {"_id": 0, "id": 1}
    ).to_list(500)
    total = await db.messages.count_documents({
        "conversation_id": {"$in": [c["id"] for c in convs]},
        "sender_id": {"$ne": user["id"]},
        "read_at": None,
    })
    # Demandes "Voir mes Moments en clair" en attente de réponse : elles
    # s'affichent en tête de la boîte de réception, on les compte aussi.
    video_requests = await db.video_access_requests.count_documents({"owner_id": user["id"], "status": "pending"})
    return {"unread": total, "video_requests": video_requests}


@router.post("/conversations/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, user: dict = Depends(get_current_user)):
    """Repli REST de l'événement WebSocket "read"."""
    await _get_conversation_or_403(conversation_id, user["id"])
    await _mark_read(conversation_id, user["id"])
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages", response_model=List[Message])
async def list_messages(conversation_id: str, limit: int = 100, user: dict = Depends(get_current_user)):
    await _get_conversation_or_403(conversation_id, user["id"])
    limit = min(max(limit, 1), 500)
    items = await db.messages.find(
        {"conversation_id": conversation_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    show_transcripts = user_settings(user)["voice_transcription"]
    for m in items:
        await _prepare_voice(m, show_transcripts)
    return items


async def _prepare_voice(message: dict, show_transcript: bool) -> dict:
    """Note vocale : URL temporaire vers le fichier privé ; transcription
    masquée si le lecteur l'a désactivée dans ses réglages."""
    if message.get("kind") == "voice" and message.get("audio_key"):
        message["audio_url"] = await presigned_document_url(message["audio_key"], VOICE_URL_TTL_SECONDS)
    if not show_transcript:
        message["transcript"] = None
    return message


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Notes vocales
# ---------------------------------------------------------------------------
VOICE_MAX_BYTES = 5 * 1024 * 1024       # ~5 minutes en Opus
VOICE_MAX_SECONDS = 180                 # 3 minutes par note
VOICE_URL_TTL_SECONDS = 2 * 3600
VOICE_CONTENT_TYPES = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/aac", "audio/wav", "audio/x-m4a"}


@router.post("/conversations/{conversation_id}/voice", response_model=Message, status_code=201)
async def send_voice_note(
    conversation_id: str,
    file: UploadFile = File(...),
    duration: float = Form(..., gt=0, le=VOICE_MAX_SECONDS + 1),
    transcript: Optional[str] = Form(None, max_length=4000),
    user: dict = Depends(get_current_user),
):
    """Envoie une note vocale. Refusée si l'expéditeur ou le destinataire a
    désactivé les notes vocales dans ses réglages. La transcription (faite
    par le navigateur de l'expéditeur) n'est gardée que s'il l'a activée."""
    conv = await _get_conversation_or_403(conversation_id, user["id"])
    mine = user_settings(user)
    if not mine["voice_notes"]:
        raise HTTPException(status_code=403, detail="Activez les notes vocales dans vos réglages")
    other_id = conv["user_b"] if conv["user_a"] == user["id"] else conv["user_a"]
    other = await db.users.find_one({"id": other_id}, {"_id": 0, "settings": 1, "full_name": 1})
    if not user_settings(other or {})["voice_notes"]:
        raise HTTPException(status_code=403, detail="Cette personne n'accepte pas les notes vocales")

    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in VOICE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Format audio non pris en charge")
    content = await file.read()
    if not content or len(content) > VOICE_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Note vocale vide ou trop longue")
    audio_key = await save_private_media(content, content_type)

    clean_transcript = (transcript or "").strip() or None if mine["voice_transcription"] else None
    message = await _persist_message(
        conv, user, "🎤 Note vocale", kind="voice", audio_key=audio_key,
        audio_duration=round(duration, 1), transcript=clean_transcript,
    )
    data = await _prepare_voice(message.model_dump(mode="json"), True)
    # Diffusion temps réel : chaque client masque la transcription selon ses réglages.
    await hub.send(conversation_channel(conversation_id), "message", data)
    return data


@router.post("/conversations/{conversation_id}/messages", response_model=Message, status_code=201)
async def send_message(conversation_id: str, payload: MessageCreate, user: dict = Depends(get_current_user)):
    conv = await _get_conversation_or_403(conversation_id, user["id"])
    message = await _persist_message(conv, user, payload.text)
    await hub.send(conversation_channel(conversation_id), "message", message.model_dump(mode="json"))
    return message


# ---------------------------------------------------------------------------
# WebSocket — messages, "en train d'écrire…", accusés de lecture, présence
# ---------------------------------------------------------------------------
#
# Protocole (JSON) :
#   client -> serveur : {"type": "message", "text": "..."}   (ou l'ancien
#                       format {"text": "..."}, toujours accepté)
#                       {"type": "typing"}   l'utilisateur tape au clavier
#                       {"type": "read"}     l'utilisateur a vu les messages
#   serveur -> client : {"type": "message",  "data": Message}
#                       {"type": "typing",   "data": {"user_id"}}
#                       {"type": "read",     "data": {"reader_id", "read_at"}}
#                       {"type": "presence", "data": {"user_ids": [...]}}
#                       {"type": "error",    "data": {"detail"}}

# Anti-flood : 8 messages max toutes les 10 secondes par utilisateur.
message_limiter = RateLimiter(max_events=8, window_seconds=10)


async def _broadcast_presence(conversation_id: str) -> None:
    """Qui a la conversation ouverte en ce moment (affiche "Dans la
    conversation" dans l'en-tête de l'autre participant)."""
    channel = conversation_channel(conversation_id)
    await hub.send(channel, "presence", {"user_ids": sorted(hub.user_ids(channel))})


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_ws(websocket: WebSocket, conversation_id: str, token: str = ""):
    jeton = decode_access_payload(token) if token else None
    if not jeton:
        await websocket.close(code=4401)  # non authentifié
        return
    user_id = jeton["sub"]
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("is_active", True):
        await websocket.close(code=4401)
        return
    # Maintenance de la plateforme (ou session antérieure à la dernière maintenance)
    if not await maintenance_plateforme.session_admise(user, jeton):
        await websocket.close(code=4401)
        return
    # Session fermée (limite d'appareils, fermeture manuelle, inactivité)
    if not await sessions_comptes.session_admise(user, jeton):
        await websocket.close(code=4401)
        return
    conv = await db.conversations.find_one({"id": conversation_id}, {"_id": 0})
    if not conv or user_id not in (conv["user_a"], conv["user_b"]):
        await websocket.close(code=4403)  # accès refusé
        return

    channel = conversation_channel(conversation_id)
    ws_ip = ip_from_headers(dict(websocket.headers), websocket.client.host if websocket.client else None)
    await hub.connect(channel, websocket, user_id)
    await _broadcast_presence(conversation_id)
    try:
        while True:
            payload = await websocket.receive_json()
            if not isinstance(payload, dict):
                continue
            event_type = payload.get("type") or "message"

            if event_type == "typing":
                # Relayé uniquement à l'autre participant, jamais stocké.
                await hub.send(channel, "typing", {"user_id": user_id}, exclude_user=user_id)
                continue

            if event_type == "read":
                await _mark_read(conversation_id, user_id)
                continue

            if event_type != "message":
                continue
            text = (payload.get("text") or "").strip()
            if not text or len(text) > 2000:
                continue
            if not message_limiter.allow(user_id):
                await websocket.send_json({"type": "error", "data": {"detail": "Doucement ! Trop de messages d'un coup."}})
                continue
            # L'utilisateur peut avoir changé entre-temps (réactivité, etc.) — on
            # relit son état courant avant de persister.
            fresh_user = await db.users.find_one({"id": user_id}, {"_id": 0}) or user
            message = await _persist_message(conv, fresh_user, text)
            await hub.send(channel, "message", message.model_dump(mode="json"))
            await log_activity(
                user_id, "Message envoyé", ws_ip,
                method="WS", path=f"/api/ws/conversations/{conversation_id}",
                details={"message_id": message.id},
            )
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(channel, websocket)
        await _broadcast_presence(conversation_id)
