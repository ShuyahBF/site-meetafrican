"""Sessions des comptes et déconnexion après inactivité (voir sessions_comptes.py
et inactivite.py).

Membre connecté (« Sécurité & sessions ») :
  - GET    /api/auth/sessions                       : ses sessions ouvertes (la courante marquée) ;
  - DELETE /api/auth/sessions/{sid}                 : fermer une de ses sessions ;
  - POST   /api/auth/sessions/fermer-autres         : fermer toutes les autres ;
  - POST   /api/auth/deconnexion                    : fermer la session courante (bouton « Se déconnecter ») ;
  - GET    /api/auth/inactivite                     : durée d'inactivité qui s'applique à lui ;
  - POST   /api/auth/activite                       : le site signale une activité (au plus 1 fois / 30 s) ;
  - GET/PUT /api/auth/inactivite/reglage            : réduire lui-même la durée fixée par l'administrateur.
Administrateur principal :
  - GET  /api/admin/sessions/comptes                : nombre de sessions par compte ;
  - GET  /api/admin/membres/{id}/sessions           : sessions d'un membre ;
  - POST /api/admin/membres/{id}/sessions/{sid}/fermer, POST /api/admin/membres/{id}/sessions/fermer-toutes ;
  - GET/PUT /api/admin/membres/{id}/inactivite      : durée propre à ce membre (None = plateforme).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

import inactivite
import sessions_comptes as service
from activity import current_ip, log_activity
from auth import bearer_scheme, decode_access_payload, get_current_super_admin, get_current_user
from db import db

compte = APIRouter(prefix="/auth", tags=["Sessions et inactivité"])
admin = APIRouter(prefix="/admin", tags=["Sessions et inactivité (administrateur)"])


def _sid_courant(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Optional[str]:
    contenu = decode_access_payload(credentials.credentials) if credentials else None
    return service.id_session(contenu) if contenu else None


class Duree(BaseModel):
    secondes: Optional[int] = None  # None = reprendre la valeur fixée au-dessus


# ---------------------------------------------------------------------------
# Membre connecté
# ---------------------------------------------------------------------------
@compte.get("/sessions")
async def mes_sessions(user: dict = Depends(get_current_user), sid: Optional[str] = Depends(_sid_courant)):
    return {"sessions": await service.lister(user["id"], sid), "max": await service.sessions_max()}


@compte.delete("/sessions/{session_id}")
async def fermer_ma_session(session_id: str, user: dict = Depends(get_current_user)):
    doc = await db.sessions.find_one({"_id": session_id, "user_id": user["id"]}, {"_id": 1})
    if not doc:
        raise HTTPException(404, "Session introuvable")
    await service.fermer(session_id, "membre", user)
    await log_activity(user["id"], "Session fermée par le membre", current_ip())
    return {"ok": True}


@compte.post("/sessions/fermer-autres")
async def fermer_mes_autres_sessions(user: dict = Depends(get_current_user), sid: Optional[str] = Depends(_sid_courant)):
    n = await service.fermer_toutes(user["id"], "membre", user, sauf=sid)
    await log_activity(user["id"], "Autres sessions fermées par le membre", current_ip(), details={"sessions": n})
    return {"ok": True, "fermees": n}


@compte.post("/deconnexion")
async def deconnexion(user: dict = Depends(get_current_user), sid: Optional[str] = Depends(_sid_courant)):
    if sid:
        await service.fermer(sid, "deconnexion", user)
    return {"ok": True}


@compte.get("/inactivite")
async def ma_duree(user: dict = Depends(get_current_user)):
    secondes = await inactivite.delai_utilisateur(user)
    return {"secondes": secondes, "avertissement_secondes": inactivite.avertissement(secondes) if secondes else 0}


@compte.post("/activite")
async def signaler_activite(_: dict = Depends(get_current_user)):
    """Rien à faire ici : la requête elle-même est notée comme activité (auth.get_current_user)."""
    return {"ok": True}


@compte.get("/inactivite/reglage")
async def lire_mon_reglage(user: dict = Depends(get_current_user)):
    return inactivite.resume(user, await inactivite.delai_plateforme(cache=False))


@compte.put("/inactivite/reglage")
async def regler_mon_inactivite(payload: Duree, user: dict = Depends(get_current_user)):
    plateforme = await inactivite.delai_plateforme(cache=False)
    secondes = inactivite.reglage_membre(user, plateforme, payload.secondes)
    await db.users.update_one({"id": user["id"]}, {"$set": {"inactivite_secondes_membre": secondes}})
    return inactivite.resume({**user, "inactivite_secondes_membre": secondes}, plateforme)


# ---------------------------------------------------------------------------
# Administrateur principal
# ---------------------------------------------------------------------------
async def _membre(user_id: str) -> dict:
    membre = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not membre:
        raise HTTPException(404, "Membre introuvable")
    return membre


@admin.get("/sessions/comptes")
async def sessions_par_compte(_: dict = Depends(get_current_super_admin)):
    return {"comptes": await service.nombre_par_compte(), "max": await service.sessions_max()}


@admin.get("/membres/{user_id}/sessions")
async def sessions_membre(user_id: str, _: dict = Depends(get_current_super_admin)):
    await _membre(user_id)
    return {"sessions": await service.lister(user_id), "max": await service.sessions_max()}


@admin.post("/membres/{user_id}/sessions/{session_id}/fermer")
async def fermer_session_membre(user_id: str, session_id: str, adm: dict = Depends(get_current_super_admin)):
    if not await db.sessions.find_one({"_id": session_id, "user_id": user_id}, {"_id": 1}):
        raise HTTPException(404, "Session introuvable")
    await service.fermer(session_id, "admin", adm)
    await log_activity(adm["id"], "Session d'un membre fermée par l'administrateur", current_ip(),
                       details={"membre": user_id})
    return {"ok": True}


@admin.post("/membres/{user_id}/sessions/fermer-toutes")
async def fermer_sessions_membre(user_id: str, adm: dict = Depends(get_current_super_admin)):
    await _membre(user_id)
    n = await service.fermer_toutes(user_id, "admin", adm)
    await log_activity(adm["id"], "Toutes les sessions d'un membre fermées par l'administrateur", current_ip(),
                       details={"membre": user_id, "sessions": n})
    return {"ok": True, "fermees": n}


@admin.get("/membres/{user_id}/inactivite")
async def inactivite_membre(user_id: str, _: dict = Depends(get_current_super_admin)):
    return inactivite.resume(await _membre(user_id), await inactivite.delai_plateforme(cache=False))


@admin.put("/membres/{user_id}/inactivite")
async def regler_inactivite_membre(user_id: str, payload: Duree, _: dict = Depends(get_current_super_admin)):
    membre = await _membre(user_id)
    secondes = inactivite.valider(payload.secondes, nul_permis=True)
    await db.users.update_one({"id": user_id}, {"$set": {"inactivite_secondes": secondes}})
    return inactivite.resume({**membre, "inactivite_secondes": secondes}, await inactivite.delai_plateforme(cache=False))
