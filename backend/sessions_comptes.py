"""Sessions simultanées limitées par compte (spécification B, validée le 02/10/2026).

Chaque connexion (e-mail/téléphone + mot de passe, inscription, « Continuer avec
TikTok ») ouvre une SESSION : un document de la collection `maf_sessions`
(identifiant aléatoire « sid », aussi écrit dans le jeton JWT) avec l'appareil /
navigateur, l'IP, la date d'ouverture et la dernière activité. Le document
disparaît automatiquement à l'expiration du jeton (index TTL sur `expire_le`).

  - Au plus N sessions ouvertes par compte (paramètre de la plateforme, 5 par
    défaut, réglable de 1 à 20). À la connexion suivante, la session dont la
    DERNIÈRE ACTIVITÉ est la plus ancienne est fermée automatiquement ; l'appareil
    concerné reçoit « Session fermée : nombre maximal d'appareils atteint pour ce
    compte. » à sa requête suivante.
  - Le membre voit ses sessions (« Sécurité & sessions ») et peut en fermer une ;
    l'administrateur principal voit le nombre de sessions par compte et peut les
    fermer.
  - Contrôle CÔTÉ SERVEUR à chaque requête authentifiée (auth.get_current_user)
    et à l'ouverture du chat temps réel ; la déconnexion après inactivité
    (inactivite.py) utilise la dernière activité notée ici.
  - Chaque ouverture / fermeture est journalisée (journal d'activité).

Jetons émis avant cette fonctionnalité (sans « sid ») : ils restent valables et
sont enregistrés à leur première utilisation sous l'identifiant
« ancien-<compte>-<heure d'ouverture> » (ils apparaissent donc dans la liste et
peuvent être fermés).
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status

import inactivite
import parametres_plateforme
from activity import current_ip, log_activity
from config import get_settings
from db import db

# Motifs de fermeture et message vu par l'appareil fermé
MOTIFS = {
    "limite": "Session fermée : nombre maximal d'appareils atteint pour ce compte.",
    "membre": "Session fermée depuis un autre appareil. Reconnectez-vous.",
    "admin": "Session fermée par l'administrateur.",
    "inactivite": inactivite.MESSAGE_INACTIVITE,
    "deconnexion": "Session fermée. Reconnectez-vous.",
    "compte": "Session fermée. Reconnectez-vous.",
}
LIBELLES_MOTIFS = {
    "limite": "Nombre maximal d'appareils atteint", "membre": "Fermée par le membre",
    "admin": "Fermée par l'administrateur", "inactivite": "Inactivité", "deconnexion": "Déconnexion",
    "compte": "Compte suspendu ou supprimé",
}
DUREE_CACHE = 15.0  # secondes : état d'une session relu en base au plus toutes les 15 s

# État connu de chaque session dans CE processus : sid -> {lu_a, derniere, fermee}
_connues: dict[str, dict] = {}


def _maintenant() -> float:
    return inactivite._maintenant()  # noqa: SLF001 — même horloge (remplaçable dans les tests)


def vider_cache() -> None:
    _connues.clear()


def nouveau_sid() -> str:
    return secrets.token_urlsafe(18)


def id_session(contenu: dict) -> str:
    """Identifiant de la session : « sid » du jeton (anciens jetons : compte + heure d'ouverture)."""
    sid = contenu.get("sid")
    if sid:
        return str(sid)
    return f"ancien-{contenu.get('sub')}-{int(float(contenu.get('ouv') or 0))}"


def appareil(user_agent: Optional[str]) -> str:
    """Description courte de l'appareil à partir de l'en-tête User-Agent."""
    ua = (user_agent or "").lower()
    if not ua:
        return "Appareil inconnu"
    navigateur = next((nom for cle, nom in (("edg/", "Edge"), ("opr/", "Opera"), ("samsungbrowser", "Samsung Internet"),
                                             ("firefox", "Firefox"), ("chrome", "Chrome"), ("crios", "Chrome"),
                                             ("safari", "Safari")) if cle in ua), "Navigateur")
    systeme = next((nom for cle, nom in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"),
                                          ("windows", "Windows"), ("mac os", "Mac"), ("linux", "Linux")) if cle in ua), "")
    return f"{navigateur} sur {systeme}" if systeme else navigateur


def _expiration(contenu_exp: Optional[float] = None) -> datetime:
    if contenu_exp:
        return datetime.fromtimestamp(float(contenu_exp), timezone.utc)
    return datetime.now(timezone.utc) + timedelta(minutes=get_settings().jwt_expires_minutes)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


async def sessions_max() -> int:
    return int((await parametres_plateforme.lire()).get("sessions_max") or 5)


# ---------------------------------------------------------------------------
# Ouverture (connexion)
# ---------------------------------------------------------------------------
async def ouvrir(user_id: str, user_agent: Optional[str] = None) -> str:
    """Ouvre une session pour ce compte et renvoie le jeton d'accès. Au-delà du
    nombre maximal, la session la moins récemment active est fermée."""
    from auth import create_access_token

    sid = nouveau_sid()
    maintenant = _maintenant()
    ip = current_ip()
    await db.sessions.insert_one({
        "_id": sid, "id": sid, "user_id": user_id, "ouverte_le": _iso(maintenant), "ouverture": maintenant,
        "derniere_activite": maintenant, "ip": ip, "appareil": appareil(user_agent),
        "user_agent": (user_agent or "")[:300], "expire_le": _expiration(), "fermee": False,
    })
    _connues[sid] = {"lu_a": maintenant, "derniere": maintenant, "fermee": None}
    await _appliquer_limite(user_id, garder=sid)
    return create_access_token(user_id, sid=sid, ouverture=maintenant)


async def _appliquer_limite(user_id: str, garder: Optional[str] = None) -> list[str]:
    """Ferme les sessions en trop (dernière activité la plus ancienne d'abord)."""
    maxi = await sessions_max()
    ouvertes = await db.sessions.find(
        {"user_id": user_id, "fermee": False, "expire_le": {"$gt": datetime.now(timezone.utc)}},
        {"_id": 1, "derniere_activite": 1}).sort("derniere_activite", 1).to_list(500)
    en_trop = len(ouvertes) - maxi
    fermees: list[str] = []
    for s in ouvertes:
        if en_trop <= 0:
            break
        if s["_id"] == garder:
            continue
        await fermer(s["_id"], "limite", par=None)
        fermees.append(s["_id"])
        en_trop -= 1
    if fermees:
        await log_activity(user_id, f"Session(s) fermée(s) automatiquement : plus de {maxi} appareils", current_ip(),
                           details={"sessions": len(fermees)})
    return fermees


# ---------------------------------------------------------------------------
# Contrôle de chaque requête authentifiée
# ---------------------------------------------------------------------------
async def controler(user: dict, contenu: dict, request: Optional[Request] = None, activite: bool = True) -> None:
    """Refuse (401) un jeton dont la session est fermée, et ferme la session
    restée inactive trop longtemps. Note la dernière activité (au plus une
    écriture par minute ; jamais pour une requête de fond « X-BA-Fond »)."""
    sid = id_session(contenu)
    maintenant = _maintenant()
    if request is not None and request.headers.get(inactivite.ENTETE_FOND):
        activite = False
    connue = _connues.get(sid)
    if connue is None or maintenant - connue["lu_a"] > DUREE_CACHE:
        doc = await db.sessions.find_one({"_id": sid}, {"fermee": 1, "motif": 1, "derniere_activite": 1})
        if doc is None:
            # Ancien jeton (sans sid) ou session absente de la base : enregistrée maintenant
            await _enregistrer_absente(sid, user, contenu, request, maintenant)
            connue = {"lu_a": maintenant, "derniere": maintenant, "fermee": None}
        else:
            connue = {"lu_a": maintenant, "derniere": doc.get("derniere_activite"),
                      "fermee": (doc.get("motif") or "compte") if doc.get("fermee") else None}
        _connues[sid] = connue
    if connue["fermee"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MOTIFS.get(connue["fermee"], MOTIFS["compte"]))
    delai = await inactivite.delai_utilisateur(user)
    derniere = connue.get("derniere")
    if delai and derniere is not None and maintenant - derniere > delai + inactivite.MARGE_SECONDES:
        await fermer(sid, "inactivite", par=None)
        await log_activity(user.get("id"), "Session fermée après inactivité", current_ip())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, MOTIFS["inactivite"])
    if derniere is None or (activite and maintenant - derniere >= inactivite.MARGE_SECONDES):
        champs = {"derniere_activite": maintenant}
        if current_ip():
            champs["ip"] = current_ip()
        await db.sessions.update_one({"_id": sid}, {"$set": champs})
        connue["derniere"] = maintenant


async def _enregistrer_absente(sid: str, user: dict, contenu: dict, request: Optional[Request],
                               maintenant: float) -> None:
    ouverture = float(contenu.get("ouv") or maintenant)
    ua = request.headers.get("user-agent") if request is not None else None
    await db.sessions.update_one({"_id": sid}, {"$setOnInsert": {
        "id": sid, "user_id": user.get("id"), "ouverte_le": _iso(ouverture), "ouverture": ouverture,
        "derniere_activite": maintenant, "ip": current_ip(), "appareil": appareil(ua),
        "user_agent": (ua or "")[:300], "expire_le": _expiration(contenu.get("exp")), "fermee": False}},
        upsert=True)


async def session_admise(user: dict, contenu: dict) -> bool:
    """Version « sans erreur » (chat temps réel) : n'est pas comptée comme une activité."""
    try:
        await controler(user, contenu, None, activite=False)
    except HTTPException:
        return False
    return True


# ---------------------------------------------------------------------------
# Liste et fermeture
# ---------------------------------------------------------------------------
def _publique(doc: dict, sid_courant: Optional[str] = None) -> dict:
    return {"id": doc["_id"], "appareil": doc.get("appareil") or "Appareil inconnu", "ip": doc.get("ip"),
            "ouverte_le": doc.get("ouverte_le"),
            "derniere_activite": _iso(doc["derniere_activite"]) if doc.get("derniere_activite") else None,
            "courante": doc["_id"] == sid_courant}


async def lister(user_id: str, sid_courant: Optional[str] = None) -> list[dict]:
    docs = await db.sessions.find(
        {"user_id": user_id, "fermee": False, "expire_le": {"$gt": datetime.now(timezone.utc)}}
    ).sort("derniere_activite", -1).to_list(100)
    return [_publique(d, sid_courant) for d in docs]


async def fermer(sid: str, motif: str, par: Optional[dict]) -> bool:
    """Ferme une session (le document reste, marqué « fermée », jusqu'à l'expiration du jeton)."""
    res = await db.sessions.update_one({"_id": sid, "fermee": False}, {"$set": {
        "fermee": True, "motif": motif, "fermee_le": datetime.now(timezone.utc).isoformat(),
        "fermee_par": (par or {}).get("email") or (par or {}).get("phone") or None}})
    _connues[sid] = {"lu_a": _maintenant(), "derniere": None, "fermee": motif}
    return bool(res.modified_count)


async def fermer_toutes(user_id: str, motif: str, par: Optional[dict], sauf: Optional[str] = None) -> int:
    filtre = {"user_id": user_id, "fermee": False}
    if sauf:
        filtre["_id"] = {"$ne": sauf}
    ids = [d["_id"] for d in await db.sessions.find(filtre, {"_id": 1}).to_list(1000)]
    for sid in ids:
        await fermer(sid, motif, par)
    return len(ids)


async def nombre_par_compte(limite: int = 200) -> list[dict]:
    """Comptes qui ont au moins une session ouverte, avec leur nombre de sessions."""
    lignes = await db.sessions.aggregate([
        {"$match": {"fermee": False, "expire_le": {"$gt": datetime.now(timezone.utc)}}},
        {"$group": {"_id": "$user_id", "sessions": {"$sum": 1}, "derniere": {"$max": "$derniere_activite"}}},
        {"$sort": {"sessions": -1}},
        {"$limit": limite},
    ]).to_list(limite)
    ids = [l["_id"] for l in lignes]
    comptes = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1, "full_name": 1, "email": 1, "phone": 1, "role": 1}).to_list(limite)}
    return [{"user_id": l["_id"], "sessions": l["sessions"],
             "derniere_activite": _iso(l["derniere"]) if l.get("derniere") else None,
             "nom": (comptes.get(l["_id"]) or {}).get("full_name"),
             "identifiant": (comptes.get(l["_id"]) or {}).get("email") or (comptes.get(l["_id"]) or {}).get("phone"),
             "role": (comptes.get(l["_id"]) or {}).get("role")} for l in lignes]
