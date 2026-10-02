"""Période de grâce de l'abonnement Premium (voir abonnement_grace.py).

  - GET  /api/abonnement/etat                         : état pour le bandeau du membre
                                                        (actif / grâce / expiré / suspendu + dates du cycle de vie) ;
  - GET  /api/admin/membres/{id}/abonnement           : état + historique (administrateur principal) ;
  - PUT  /api/admin/membres/{id}/grace                : délai de grâce propre au membre (0 à 30 j, None = plateforme) ;
  - POST /api/admin/membres/{id}/grace/renouveler     : « Renouveler la grâce (+3 j) », 3 fois au plus par échéance.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import abonnement_grace as service
import cycle_vie
from auth import get_current_super_admin, get_current_user
from db import db

membre = APIRouter(prefix="/abonnement", tags=["Abonnement : grâce"])
admin = APIRouter(prefix="/admin/membres", tags=["Abonnement : grâce (administrateur)"])


@membre.get("/etat")
async def mon_etat(user: dict = Depends(get_current_user)):
    etat = await service.etat(user["id"], user)
    etat["suspendu"] = cycle_vie.est_suspendu(user)
    if etat["statut"] in ("expire",) or etat["suspendu"]:
        etat["cycle_vie"] = await cycle_vie.info_membre(user)
    return etat


class Grace(BaseModel):
    jours: Optional[int] = None


async def _membre(user_id: str) -> dict:
    m = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not m:
        raise HTTPException(404, "Membre introuvable")
    return m


@admin.get("/{user_id}/abonnement")
async def etat_membre(user_id: str, _: dict = Depends(get_current_super_admin)):
    m = await _membre(user_id)
    return {"etat": await service.etat(user_id, m), "grace_jours_membre": m.get("grace_jours"),
            "suspendu": cycle_vie.est_suspendu(m), "cycle_vie": m.get("cycle_vie"),
            "historique": await service.historique(user_id)}


@admin.put("/{user_id}/grace")
async def regler_grace(user_id: str, payload: Grace, adm: dict = Depends(get_current_super_admin)):
    return await service.regler_grace(user_id, payload.jours, adm)


@admin.post("/{user_id}/grace/renouveler")
async def renouveler_grace(user_id: str, adm: dict = Depends(get_current_super_admin)):
    await _membre(user_id)
    return await service.renouveler_grace(user_id, adm)
