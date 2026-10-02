"""Cycle de vie du non-renouvellement (voir cycle_vie.py) — administrateur principal.

  - GET  /api/plateforme/cycle-vie                          : état, rapports, membres suspendus, archives ;
  - POST /api/plateforme/cycle-vie/executer                 : lancer la tâche maintenant (simulation : rapport immédiat) ;
  - GET  /api/plateforme/cycle-vie/journal                  : journal (filtrable par membre) ;
  - POST /api/plateforme/cycle-vie/archives/{id}/rouvrir    : réouverture manuelle depuis l'archive (mot de passe).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import cycle_vie as service
import sauvegarde_auto
import transfert_donnees
from activity import current_ip
from auth import get_current_super_admin
from db import db

router = APIRouter(prefix="/plateforme/cycle-vie", tags=["Cycle de vie (administrateur)"])


@router.get("")
async def etat(_: dict = Depends(get_current_super_admin)):
    return await service.etat_admin()


class Execution(BaseModel):
    simulation: bool = True


@router.post("/executer")
async def executer(payload: Execution, adm: dict = Depends(get_current_super_admin)):
    if payload.simulation:
        return await service.executer_quotidien("administrateur", simulation=True, par=adm)
    sauvegarde_auto.lancer_en_fond(service.executer_quotidien("administrateur", simulation=False, par=adm))
    return {"ok": True, "statut": "LANCE"}


@router.get("/journal")
async def journal(user_id: Optional[str] = None, _: dict = Depends(get_current_super_admin)):
    filtre = {"user_id": user_id} if user_id else {}
    return await db.cycle_vie_journal.find(filtre, {"_id": 0}).sort("date", -1).to_list(200)


class Reouverture(BaseModel):
    mot_de_passe: str = Field(max_length=200)
    frais_encaisses: bool = False


@router.post("/archives/{archive_id}/rouvrir")
async def rouvrir(archive_id: str, payload: Reouverture, adm: dict = Depends(get_current_super_admin)):
    await transfert_donnees.verifier_mot_de_passe(adm, payload.mot_de_passe, "reouverture_membre", current_ip())
    return await service.rouvrir(archive_id, adm, payload.frais_encaisses)
