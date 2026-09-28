"""Compteurs publics du site et journal d'activité (back-office).

  - POST /stats/visit            : enregistre la visite (une par IP et par
                                   jour) et renvoie les compteurs affichés
                                   sur la page d'accueil + l'IP du visiteur.
  - GET  /admin/activity         : journal d'activité filtrable (membre, IP,
                                   action), réservé aux admins/modérateurs.
  - GET  /admin/activity/user/{id} : synthèse d'un membre (IP utilisées,
                                   IP d'inscription / dernière connexion).

Les données de test (is_test_data) et les comptes du back-office ne sont
jamais comptés dans les compteurs publics : ils doivent refléter les vrais
membres.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from activity import current_ip
from auth import get_current_admin
from db import db

router = APIRouter(tags=["Statistiques & traçabilité"])

# Vrais membres uniquement (ni back-office, ni données de test).
_REAL_MEMBERS = {"role": {"$nin": ["admin", "moderator"]}, "is_test_data": {"$ne": True}, "is_active": True}


async def _public_counters() -> dict:
    registered = await db.users.count_documents(_REAL_MEMBERS)
    verified = await db.users.count_documents({**_REAL_MEMBERS, "verification_status": "verified"})
    stats = await db.settings.find_one({"id": "site_stats"}, {"_id": 0}) or {}
    return {"registered": registered, "verified": verified, "visits": stats.get("visits", 0)}


@router.post("/stats/visit")
async def record_visit():
    """Appelée une fois par session de navigation par la page d'accueil.
    Une même IP n'est comptée qu'une fois par jour (pas de gonflement du
    compteur en rechargeant la page)."""
    ip = current_ip() or "inconnue"
    result = await db.site_visits.update_one(
        {"day": date.today().isoformat(), "ip": ip},
        # created_at_dt : purge automatique après 31 jours (index TTL, db.py) —
        # l'IP ne sert qu'à éviter le double comptage du jour.
        {"$setOnInsert": {"day": date.today().isoformat(), "ip": ip, "created_at_dt": datetime.now(timezone.utc)}},
        upsert=True,
    )
    if result.upserted_id is not None:
        await db.settings.update_one({"id": "site_stats"}, {"$inc": {"visits": 1}}, upsert=True)
    return {**await _public_counters(), "your_ip": ip}


@router.get("/stats/public")
async def public_stats():
    """Compteurs seuls (sans enregistrer de visite) + IP du visiteur."""
    return {**await _public_counters(), "your_ip": current_ip()}


# ---------------------------------------------------------------------------
# Back-office : journal d'activité
# ---------------------------------------------------------------------------

async def _user_cards(user_ids) -> dict:
    ids = [u for u in set(user_ids) if u]
    docs = await db.users.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "phone": 1, "is_test_data": 1}
    ).to_list(len(ids) or 1)
    return {d["id"]: d for d in docs}


@router.get("/admin/activity")
async def activity_log(
    q: Optional[str] = Query(None, max_length=100, description="Nom, email ou téléphone du membre"),
    user_id: Optional[str] = None,
    ip: Optional[str] = Query(None, max_length=64),
    action: Optional[str] = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _: dict = Depends(get_current_admin),
):
    query: dict = {}
    if user_id:
        query["user_id"] = user_id
    elif q:
        pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
        matching = await db.users.distinct("id", {"$or": [{"full_name": pattern}, {"email": pattern}, {"phone": pattern}]})
        query["user_id"] = {"$in": matching}
    if ip:
        query["ip"] = ip.strip()
    if action:
        query["action"] = {"$regex": re.escape(action.strip()), "$options": "i"}

    total = await db.activity_log.count_documents(query)
    items = (
        await db.activity_log.find(query, {"_id": 0, "created_at_dt": 0})
        .sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    )
    users = await _user_cards(i.get("user_id") for i in items)
    for item in items:
        item["user"] = users.get(item.get("user_id"))
    return {"total": total, "items": items}


@router.get("/admin/activity/user/{user_id}")
async def user_ip_summary(user_id: str, _: dict = Depends(get_current_admin)):
    """Toutes les IP utilisées par un membre (nombre d'actions, première et
    dernière utilisation) + IP d'inscription et de dernière connexion."""
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "registration_ip": 1, "last_login_ip": 1, "last_login_at": 1},
    )
    cursor = db.activity_log.aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$ip", "count": {"$sum": 1}, "first": {"$min": "$created_at"}, "last": {"$max": "$created_at"}}},
        {"$sort": {"last": -1}},
    ])
    ips = [{"ip": row["_id"], "count": row["count"], "first": row["first"], "last": row["last"]} async for row in cursor]
    return {"user": user, "ips": ips}


# ---------------------------------------------------------------------------
# Back-office : journal horodaté des vérifications (verification_log.py)
# ---------------------------------------------------------------------------

@router.get("/admin/verification-events")
async def verification_events(
    user_id: Optional[str] = None,
    kind: Optional[str] = Query(None, pattern="^(photo|document|phone|whatsapp)$"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _: dict = Depends(get_current_admin),
):
    query: dict = {}
    if user_id:
        query["user_id"] = user_id
    if kind:
        query["kind"] = kind
    total = await db.verification_events.count_documents(query)
    items = await db.verification_events.find(query, {"_id": 0}).sort("at", -1).skip(skip).limit(limit).to_list(limit)
    users = await _user_cards([i.get("user_id") for i in items] + [i.get("actor_id") for i in items])
    for item in items:
        item["user"] = users.get(item.get("user_id"))
        item["actor_user"] = users.get(item.get("actor_id"))
    return {"total": total, "items": items}
