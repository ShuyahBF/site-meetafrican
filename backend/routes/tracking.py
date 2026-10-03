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

Lot 53 — sécurité renforcée (demande du propriétaire) :
  - POST /tracking/sessions/{id}/points/lot : positions mémorisées dans le
    téléphone pendant une coupure d'Internet, renvoyées au retour du réseau
    avec leur heure RÉELLE (le trajet est reconstitué sans trou) ;
  - POST /tracking/sessions/{id}/arrive   : « Je suis arrivé·e » (fin du suivi,
    la personne de confiance et l'administrateur sont prévenus) ;
  - alerte « signal perdu » : aucune position depuis 10 minutes pendant un
    suivi actif -> WhatsApp / SMS + e-mail à la personne de confiance ET aux
    administrateurs (boucle de fond, server.py) ; « signal rétabli » quand une
    position revient ;
  - GET  /admin/tracking/alertes         : historique des alertes (équipe) ;
  - pas de déconnexion pour inactivité pendant un suivi actif, ni pour le
    membre suivi ni pour la personne de confiance (sessions_comptes.py).

Seul le propriétaire peut démarrer ou arrêter un suivi. Contrairement à
"Près de moi", la position est ici PRÉCISE (c'est le but) : elle n'est
visible que du compte désigné et de l'équipe, et les points sont effacés
automatiquement 30 jours après leur envoi (index TTL, db.py).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from auth import get_current_admin, get_current_user
from db import db

router = APIRouter(tags=["Me suivre (sécurité)"])

MIN_POINT_INTERVAL_SECONDS = 5  # anti-flood : une position toutes les 5 s au plus
_STAFF = ("admin", "moderator")
# Lot 53 — aucune position depuis ce délai pendant un suivi actif : alerte « signal perdu »
MINUTES_ALERTE_SIGNAL = 10
MAX_POINTS_LOT = 500          # positions renvoyées en une fois après une coupure d'Internet
logger = logging.getLogger("beauthentik.suivi")


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
    await _signal_retabli(session)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Lot 53 — positions mémorisées hors connexion, renvoyées au retour du réseau
# ---------------------------------------------------------------------------
class PointDate(Point):
    at: datetime  # heure RÉELLE de la mesure dans le téléphone (ISO 8601)


class LotPoints(BaseModel):
    points: List[PointDate] = Field(..., min_length=1, max_length=MAX_POINTS_LOT)


@router.post("/tracking/sessions/{session_id}/points/lot")
async def add_points_lot(session_id: str, payload: LotPoints, user: dict = Depends(get_current_user)):
    """Enregistre les positions prises pendant une coupure d'Internet, avec leur heure
    d'origine. Seules les positions prises PENDANT le suivi sont gardées (entre le
    début et la fin ou l'arrêt, une minute de tolérance pour l'horloge du téléphone)."""
    session = await db.tracking_sessions.find_one({"id": session_id, "owner_id": user["id"]}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Suivi introuvable")
    debut = datetime.fromisoformat(session["started_at"]) - timedelta(minutes=1)
    fin = min(_now_dt(), datetime.fromisoformat(session.get("stopped_at") or session["ends_at"])) + timedelta(minutes=1)
    if fin < _now_dt() - timedelta(hours=1):
        raise HTTPException(status_code=410, detail="Ce suivi est terminé depuis plus d'une heure")
    gardes = []
    for p in sorted(payload.points, key=lambda x: x.at):
        at = p.at if p.at.tzinfo else p.at.replace(tzinfo=timezone.utc)
        if debut <= at <= fin:
            gardes.append({"lat": p.lat, "lng": p.lng, "accuracy": p.accuracy, "at": at.isoformat(), "hors_connexion": True})
    if gardes:
        await db.tracking_points.insert_many([{"session_id": session_id, **g, "at_dt": datetime.fromisoformat(g["at"])} for g in gardes])
        dernier = gardes[-1]
        ancien = session.get("last_point")
        if not ancien or datetime.fromisoformat(ancien["at"]) < datetime.fromisoformat(dernier["at"]):
            await db.tracking_sessions.update_one({"id": session_id}, {"$set": {"last_point": dernier}})
        await _signal_retabli(session)
    return {"ok": True, "enregistres": len(gardes), "ignores": len(payload.points) - len(gardes)}


# ---------------------------------------------------------------------------
# Lot 53 — « Je suis arrivé·e »
# ---------------------------------------------------------------------------
@router.post("/tracking/sessions/{session_id}/arrive")
async def arrive(session_id: str, user: dict = Depends(get_current_user)):
    """Termine le suivi en signalant que le membre est bien arrivé : la personne de
    confiance et l'administrateur sont prévenus."""
    maintenant = _now_dt().isoformat()
    session = await db.tracking_sessions.find_one_and_update(
        {"id": session_id, "owner_id": user["id"], "status": "active"},
        {"$set": {"status": "stopped", "stopped_at": maintenant, "motif_fin": "arrive", "arrive_le": maintenant}},
        projection={"_id": 0},
    )
    if not session:
        raise HTTPException(status_code=404, detail="Suivi introuvable ou déjà terminé")
    _vider_cache_suivi()
    _lancer(_notifier(session, "arrivee",
                      f"✅ beAuthentik — {session['owner_name']} est bien arrivé·e (suivi « Me suivre » terminé à {_heure(maintenant)})."))
    return {"ok": True}


@router.post("/tracking/sessions/{session_id}/stop")
async def stop_session(session_id: str, user: dict = Depends(get_current_user)):
    result = await db.tracking_sessions.update_one(
        {"id": session_id, "owner_id": user["id"], "status": "active"},
        {"$set": {"status": "stopped", "stopped_at": _now_dt().isoformat(), "motif_fin": "arret"}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Suivi introuvable ou déjà terminé")
    _vider_cache_suivi()
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


@router.get("/admin/tracking/alertes")
async def admin_tracking_alertes(_: dict = Depends(get_current_admin)):
    """Lot 53 — historique des alertes de suivi (signal perdu / rétabli, arrivées), les plus récentes d'abord."""
    return await db.tracking_alertes.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


# ===========================================================================
# Lot 53 — exemption de la déconnexion pour inactivité pendant un suivi
# ===========================================================================
_cache_suivi: dict = {}
DUREE_CACHE_SUIVI = 30  # secondes


def _vider_cache_suivi() -> None:
    _cache_suivi.clear()


async def suivi_en_cours(user_id: Optional[str]) -> bool:
    """Vrai si ce compte est le membre suivi OU la personne de confiance d'un suivi actif
    (non expiré). Lu au plus toutes les 30 s par compte (appelé à chaque requête)."""
    if not user_id:
        return False
    connu = _cache_suivi.get(user_id)
    if connu and time.monotonic() - connu[0] < DUREE_CACHE_SUIVI:
        return connu[1]
    actif = await db.tracking_sessions.find_one(
        {"status": "active", "ends_at": {"$gt": _now_dt().isoformat()}, "$or": [{"owner_id": user_id}, {"guardian_id": user_id}]},
        {"_id": 0, "id": 1},
    ) is not None
    _cache_suivi[user_id] = (time.monotonic(), actif)
    return actif


# ===========================================================================
# Lot 53 — alertes : personne de confiance + administrateurs
# ===========================================================================
def _heure(iso: str) -> str:
    """Heure lisible « JJ/MM/AAAA à HH:MM » (fuseau Ouagadougou = UTC)."""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y à %H:%M")
    except (TypeError, ValueError):
        return str(iso)


def _lancer(coro) -> None:
    """Envoi en tâche de fond : la réponse au membre n'attend jamais WhatsApp / SMS / e-mail."""
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:  # pas de boucle (tests synchrones) : ignoré
        coro.close()


async def _notifier(session: dict, type_alerte: str, texte: str) -> None:
    """Note l'alerte (historique de l'administrateur), puis prévient la personne de
    confiance (WhatsApp / SMS + e-mail) et les administrateurs (WhatsApp / SMS + e-mail).
    Ne lève jamais d'exception : un envoi en échec ne bloque rien."""
    import envoi_email
    import envoi_messages
    alerte = {
        "id": str(uuid.uuid4()), "session_id": session["id"], "type": type_alerte, "texte": texte,
        "owner_id": session.get("owner_id"), "owner_name": session.get("owner_name"),
        "guardian_id": session.get("guardian_id"), "guardian_name": session.get("guardian_name"),
        "created_at": _now_dt().isoformat(), "envois": {},
    }
    try:
        gardien = await db.users.find_one({"id": session.get("guardian_id")}, {"_id": 0, "id": 1, "email": 1, "whatsapp": 1, "phone": 1})
        if gardien:
            alerte["envois"]["gardien_message"] = (await envoi_messages.envoyer(gardien, texte)).get("ok", False)
            alerte["envois"]["gardien_email"] = (await envoi_email.envoyer_journalise(
                gardien.get("email"), envoi_messages.sujet_alerte(texte), texte, f"suivi_{type_alerte}", gardien.get("id")))["statut"]
        alerte["envois"]["administrateurs"] = await envoi_messages.alerter_administrateurs(texte)
    except Exception:  # noqa: BLE001 — l'alerte reste au moins notée dans l'historique
        logger.exception("Envoi d'une alerte de suivi impossible")
    await db.tracking_alertes.insert_one(dict(alerte))


async def _signal_retabli(session: dict) -> None:
    """Une position est arrivée alors qu'une alerte « signal perdu » était en cours."""
    if not session.get("alerte_signal"):
        return
    r = await db.tracking_sessions.update_one({"id": session["id"], "alerte_signal": {"$ne": None}}, {"$set": {"alerte_signal": None}})
    if r.modified_count:
        _lancer(_notifier(session, "signal_retabli",
                          f"🟢 beAuthentik — signal rétabli : la position de {session['owner_name']} est de nouveau reçue ({_heure(_now_dt().isoformat())})."))


async def verifier_signaux() -> int:
    """Une passe de surveillance : alerte « signal perdu » pour chaque suivi actif sans
    position depuis MINUTES_ALERTE_SIGNAL minutes (une seule alerte jusqu'au retour du
    signal). Renvoie le nombre d'alertes envoyées."""
    maintenant = _now_dt()
    limite = maintenant - timedelta(minutes=MINUTES_ALERTE_SIGNAL)
    envoyees = 0
    sessions = await db.tracking_sessions.find({"status": "active", "alerte_signal": {"$in": [None, False]}}, {"_id": 0}).to_list(500)
    for s in await _refresh_status(sessions):
        if s["status"] != "active":
            continue
        reference = datetime.fromisoformat((s.get("last_point") or {}).get("at") or s["started_at"])
        if reference > limite:
            continue
        r = await db.tracking_sessions.update_one(
            {"id": s["id"], "alerte_signal": {"$in": [None, False]}},
            {"$set": {"alerte_signal": {"depuis": reference.isoformat(), "alerte_le": maintenant.isoformat()}}},
        )
        if not r.modified_count:
            continue
        minutes = int((maintenant - reference).total_seconds() // 60)
        lieu = ""
        if s.get("last_point"):
            lieu = f" Dernière position connue ({_heure(s['last_point']['at'])}) : https://www.google.com/maps?q={s['last_point']['lat']},{s['last_point']['lng']}"
        await _notifier(s, "signal_perdu",
                        f"⚠️ beAuthentik — signal perdu : aucune position de {s['owner_name']} depuis {minutes} min "
                        f"(suivi « Me suivre » avec {s['guardian_name']}).{lieu}")
        envoyees += 1
    return envoyees


async def boucle_alertes_suivi() -> None:
    """Boucle de fond (server.py) : surveillance des suivis actifs, chaque minute."""
    while True:
        try:
            await verifier_signaux()
        except Exception:  # noqa: BLE001 — la surveillance ne s'arrête jamais
            logger.exception("Surveillance des suivis : erreur")
        await asyncio.sleep(60)
