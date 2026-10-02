"""Paramètres « Abonnements, sessions et sauvegardes » de la plateforme
(administrateur principal) — voir parametres_plateforme.py.

  - GET /api/plateforme/parametres/abonnements-sessions
  - PUT /api/plateforme/parametres/abonnements-sessions  (seuls les champs envoyés changent)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import parametres_plateforme as service
from activity import current_ip, log_activity
from auth import get_current_super_admin

router = APIRouter(prefix="/plateforme/parametres", tags=["Paramètres de la plateforme (administrateur)"])


class Reglages(BaseModel):
    grace_jours_defaut: Optional[int] = None
    sessions_max: Optional[int] = None
    inactivite_secondes: Optional[int] = None
    cycle_actif: Optional[bool] = None
    cycle_simulation: Optional[bool] = None
    conservation_archives_jours: Optional[int] = None
    frais_reouverture_montant: Optional[int] = None
    frais_reouverture_devise: Optional[str] = None


def _reponse(valeurs: dict) -> dict:
    return {**valeurs, "bornes": service.BORNES, "inactivite_bornes": [60, 86_400]}


@router.get("/abonnements-sessions")
async def lire(_: dict = Depends(get_current_super_admin)):
    return _reponse(await service.lire(cache=False))


@router.put("/abonnements-sessions")
async def modifier(payload: Reglages, adm: dict = Depends(get_current_super_admin)):
    changements = payload.model_dump(exclude_none=True)
    valeurs = await service.modifier(changements, adm.get("email") or adm.get("phone") or "")
    await log_activity(adm["id"], "Paramètres abonnements / sessions modifiés", current_ip(), details=changements)
    return _reponse(valeurs)
