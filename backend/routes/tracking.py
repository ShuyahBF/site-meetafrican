"""« Me suivre » : partage de position EN TEMPS RÉEL, pour la sécurité
(par exemple pendant un premier rendez-vous).

Le membre démarre un suivi pour une durée donnée et désigne un compte
beAuthentik de confiance (un match, ou n'importe quel compte via son email).
Tant que le suivi est actif, son navigateur envoie sa position au serveur
beAuthentik (toutes les ~20 s) ; le compte désigné — et l'équipe
beAuthentik — voient la dernière position et le trajet, horodatés.

  - POST /tracking/sessions             : démarrer (compte désigné, durée)
  - POST /tracking/sessions/{id}/points : envoyer une position (propriétaire)
  - POST /tracking/sessions/{id}/stop   : arrêter (propriétaire)
  - GET  /tracking/me                   : mes suivis + ceux où je suis désigné(e)
  - GET  /tracking/sessions/{id}        : détail + trajet (propriétaire,
                                          compte désigné, équipe)
  - GET  /admin/tracking                : suivis actifs (équipe)

Seul le propriétaire peut démarrer ou arrêter un suivi. Contrairement à
"Près de moi", la position est ici PRÉCISE (c'est le but) : elle n'est
visible que du compte désigné et de l'équipe, et les points sont effacés
automatiquement 30 jours après leur envoi (index TTL, db.py).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from auth import get_current_admin, get_current_user
from db import db

router = APIRouter(tags=["Me suivre (sécurité)"])

MIN_POINT_INTERVAL_SECONDS = 5  # anti-flood : une position toutes les 5 s au plus
_STAFF = ("admin", "moderator")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


class SessionStart(BaseModel):
    guardian_id: Optional[str] = None
    guardian_email: Optional[str] = Field(None, max_length=200)
    duration_minutes: int = Field(120, ge=15, le=24 * 60)
    note: Optional[str] = Field(None, max_length=300)  # ex. "Rendez-vous avec X au maquis Y"

    @model_validator(mode="after")
    def _one_guardian(self):
        if not self.guardian_id and not self.guardian_email:
            raise ValueError("Désignez le compte qui pourra vous suivre")
        return self


@router.post("/tracking/sessions", status_code=201)
async def start_session(payload: SessionStart, user: dict = Depends(get_current_user)):
    query = ({"id": payload.guardian_id} if payload.guardian_id
             else {"email": {"$regex": f"^{re.escape(payload.guardian_email.strip())}$", "$options": "i"}})
    guardian = await db.users.find_one({**query, "is_active": True}, {"_id": 0, "id": 1, "full_name": 1})
    if not guardian:
        raise HTTPException(status_code=404, detail="Aucun compte beAuthentik trouvé pour ce contact")
    if guardian["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Choisissez une autre personne que vous-même")

    # Un seul suivi actif à la fois : le précédent est arrêté.
    now = _now_dt()
    await db.tracking_sessions.update_many(
        {"owner_id": user["id"], "status": "active"}, {"$set": {"status": "stopped", "stopped_at": now.isoformat()}}
    )
    session = {
        "id": str(uuid.uuid4()), "owner_id": user["id"], "owner_name": user["full_name"],
        "guardian_id": guardian["id"], "guardian_name": guardian["full_name"],
        "note": (payload.note or "").strip() or None, "status": "active",
        "started_at": now.isoformat(), "ends_at": (now + timedelta(minutes=payload.duration_minutes)).isoformat(),
        "stopped_at": None, "last_point": None,
    }
    await db.tracking_sessions.insert_one(dict(session))
    return session


def _is_live(session: dict) -> bool:
    return session["status"] == "active" and _now_dt() < datetime.fromisoformat(session["ends_at"])


class Point(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0, le=100000)  # précision en mètres


@router.post("/tracking/sessions/{session_id}/points")
async def add_point(session_id: str, payload: Point, user: dict = Depends(get_current_user)):
    session = await db.tracking_sessions.find_one({"id": session_id, "owner_id": user["id"]}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Suivi introuvable")
    if not _is_live(session):
        if session["status"] == "active":  # durée écoulée : clôture automatique
            await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"status": "expired"}})
        raise HTTPException(status_code=410, detail="Ce suivi est terminé")
    now = _now_dt()
    last = session.get("last_point")
    if last and (now - datetime.fromisoformat(last["at"])).total_seconds() < MIN_POINT_INTERVAL_SECONDS:
        return {"ok": True, "skipped": True}
    point = {"lat": payload.lat, "lng": payload.lng, "accuracy": payload.accuracy, "at": now.isoformat()}
    await db.tracking_points.insert_one({"session_id": session_id, **point, "at_dt": now})
    await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"last_point": point}})
    return {"ok": True}


@router.post("/tracking/sessions/{session_id}/stop")
async def stop_session(session_id: str, user: dict = Depends(get_current_user)):
    result = await db.tracking_sessions.update_one(
        {"id": session_id, "owner_id": user["id"], "status": "active"},
        {"$set": {"status": "stopped", "stopped_at": _now_dt().isoformat()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Suivi introuvable ou déjà terminé")
    return {"ok": True}


async def _refresh_status(sessions: list) -> list:
    for s in sessions:
        if s["status"] == "active" and not _is_live(s):
            s["status"] = "expired"
            await db.tracking_sessions.update_one({"id": s["id"]}, {"$set": {"status": "expired"}})
    return sessions


@router.get("/tracking/me")
async def my_tracking(user: dict = Depends(get_current_user)):
    mine = await db.tracking_sessions.find({"owner_id": user["id"]}, {"_id": 0}).sort("started_at", -1).to_list(10)
    watching = await db.tracking_sessions.find({"guardian_id": user["id"]}, {"_id": 0}).sort("started_at", -1).to_list(20)
    return {"mine": await _refresh_status(mine), "watching": await _refresh_status(watching)}


@router.get("/tracking/sessions/{session_id}")
async def session_detail(session_id: str, user: dict = Depends(get_current_user)):
    session = await db.tracking_sessions.find_one({"id": session_id}, {"_id": 0})
    allowed = session and (user["id"] in (session["owner_id"], session["guardian_id"]) or user.get("role") in _STAFF)
    if not allowed:
        raise HTTPException(status_code=404, detail="Suivi introuvable")
    [session] = await _refresh_status([session])
    points = await db.tracking_points.find({"session_id": session_id}, {"_id": 0, "at_dt": 0, "session_id": 0}).sort("at", 1).to_list(2000)
    return {**session, "points": points}


@router.get("/admin/tracking")
async def admin_tracking(_: dict = Depends(get_current_admin)):
    sessions = await db.tracking_sessions.find({"status": "active"}, {"_id": 0}).sort("started_at", -1).to_list(200)
    return await _refresh_status(sessions)
