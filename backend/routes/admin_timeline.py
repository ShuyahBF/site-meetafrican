"""Back-office : chronologie globale et fiche membre (lecture seule).

  - GET /admin/timeline          : TOUT ce qui se passe sur le site, du plus
                                   récent au plus ancien, avec le nom du
                                   membre : inscriptions, activité (journal
                                   IP), paiements, Moments, vérifications,
                                   signalements, support, témoignages, suivis.
                                   Filtres : type, membre (user_id), recherche
                                   par nom/email/téléphone ; pagination par
                                   date ("avant telle date").
  - GET /admin/members/{id}      : fiche complète d'un membre, en lecture
                                   seule, consultée "en invisible" : aucune
                                   visite enregistrée, photos non masquées,
                                   tous ses Moments, paiements, signalements
                                   reçus/émis, vérifications.

Réservé à l'équipe (admin et modérateurs).
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_admin
from db import db

router = APIRouter(prefix="/admin", tags=["Administration — chronologie"])

# type -> (collection, champ date, champ membre, fabrique du libellé)
_SOURCES = {
    "inscription": ("users", "created_at", "id",
                    lambda d: ("Inscription", {"email": d.get("email"), "téléphone": d.get("phone"), "ville": d.get("city")},
                               d.get("registration_ip"))),
    "activite": ("activity_log", "created_at", "user_id",
                 lambda d: (d.get("action") or d.get("path") or "Action",
                            {"requête": f"{d.get('method') or ''} {d.get('path') or ''}".strip(), "code": d.get("status_code")},
                            d.get("ip"))),
    "paiement": ("payments", "created_at", "user_id",
                 lambda d: (f"Paiement {d.get('purpose') or ''} — {d.get('amount')} {d.get('currency') or ''}".strip(),
                            {"statut": d.get("status"), "référence": d.get("deposit_id")}, d.get("ip"))),
    "moment": ("videos", "created_at", "user_id",
               lambda d: ("Moment publié", {"légende": (d.get("caption") or "")[:80], "statut": d.get("status"),
                                            "signalements": d.get("reports_count")}, d.get("ip"))),
    "verification": ("verification_events", "at", "user_id",
                     lambda d: (f"Vérification {d.get('kind')} : {d.get('action')}", {"par": d.get("actor"), **(d.get("details") or {})},
                                d.get("ip"))),
    "signalement": ("reports", "created_at", "reported_user_id",
                    lambda d: (f"Signalé ({d.get('reason')})", {"détails": d.get("details"), "statut": d.get("status"),
                                                                "par": d.get("reporter_user_id")}, None)),
    "support": ("support_tickets", "created_at", "user_id",
                lambda d: (f"Support : {d.get('subject')}", {"thème": d.get("topic"), "statut": d.get("status")}, None)),
    "temoignage": ("testimonials", "created_at", "user_id",
                   lambda d: ("Témoignage", {"texte": (d.get("text") or "")[:80], "statut": d.get("status")}, None)),
    "suivi": ("tracking_sessions", "started_at", "owner_id",
              lambda d: (f"Me suivre → {d.get('guardian_name')}", {"statut": d.get("status"), "fin": d.get("ends_at")}, None)),
}

_USER_CARD = {"_id": 0, "id": 1, "full_name": 1, "email": 1, "phone": 1, "is_test_data": 1, "role": 1}


async def _matching_user_ids(q: str) -> list:
    pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
    return await db.users.distinct("id", {"$or": [{"full_name": pattern}, {"email": pattern}, {"phone": pattern}]})


@router.get("/timeline")
async def timeline(
    type: Optional[str] = Query(None, description="inscription, activite, paiement, moment, verification…"),
    user_id: Optional[str] = None,
    q: Optional[str] = Query(None, max_length=100, description="Nom, email ou téléphone du membre"),
    before: Optional[str] = Query(None, description="Date ISO : événements plus anciens que celle-ci (page suivante)"),
    limit: int = Query(100, ge=1, le=300),
    _: dict = Depends(get_current_admin),
):
    if type and type not in _SOURCES:
        raise HTTPException(status_code=400, detail="Type inconnu")
    ids = [user_id] if user_id else (await _matching_user_ids(q) if q else None)

    events = []
    for kind, (collection, date_field, user_field, describe) in _SOURCES.items():
        if type and kind != type:
            continue
        query: dict = {date_field: {"$lt": before} if before else {"$ne": None}}
        if ids is not None:
            query[user_field] = {"$in": ids}
        docs = await getattr(db, collection).find(query, {"_id": 0, "password_hash": 0}).sort(date_field, -1).limit(limit).to_list(limit)
        for d in docs:
            title, details, ip = describe(d)
            events.append({
                "type": kind, "at": d.get(date_field), "user_id": d.get(user_field), "title": title,
                "details": {k: v for k, v in details.items() if v not in (None, "", {})}, "ip": ip,
            })

    # Fusion : du plus récent au plus ancien, puis noms des membres
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    events = events[:limit]
    user_ids = {e["user_id"] for e in events if e["user_id"]}
    user_ids |= {e["details"].get("par") for e in events if e["type"] == "signalement"} - {None}
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": list(user_ids)}}, _USER_CARD).to_list(len(user_ids) or 1)}
    for e in events:
        e["user"] = users.get(e["user_id"])
        if e["type"] == "signalement" and e["details"].get("par") in users:
            e["details"]["par"] = users[e["details"]["par"]]["full_name"]
    return {
        "items": events,
        # Curseur de la page suivante : date du dernier événement affiché
        "next_before": events[-1]["at"] if len(events) == limit else None,
    }


@router.get("/members/{user_id}")
async def member_file(user_id: str, _: dict = Depends(get_current_admin)):
    """Fiche membre en lecture seule, consultée en invisible (rien n'est
    enregistré dans son historique "Qui m'a vu")."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Membre introuvable")
    videos = await db.videos.find({"user_id": user_id}, {"_id": 0, "clear_key": 0}).sort("created_at", -1).to_list(100)
    payments = await db.payments.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    reports_received = await db.reports.find({"reported_user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    reports_sent = await db.reports.find({"reporter_user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    verifications = await db.identity_verifications.find({"user_id": user_id}, {"_id": 0, "document_key": 0}).sort("created_at", -1).to_list(20)
    reporter_ids = {r["reporter_user_id"] for r in reports_received} | {r["reported_user_id"] for r in reports_sent}
    names = {u["id"]: u["full_name"] for u in await db.users.find({"id": {"$in": list(reporter_ids)}}, {"_id": 0, "id": 1, "full_name": 1}).to_list(200)}
    for r in reports_received:
        r["reporter_name"] = names.get(r["reporter_user_id"])
    for r in reports_sent:
        r["reported_name"] = names.get(r["reported_user_id"])
    matches = await db.matches.count_documents({"$or": [{"user_a": user_id}, {"user_b": user_id}]})
    messages = await db.messages.count_documents({"sender_id": user_id})
    return {
        "user": user, "videos": videos, "payments": payments,
        "reports_received": reports_received, "reports_sent": reports_sent,
        "verifications": verifications, "counts": {"matches": matches, "messages_sent": messages},
    }
