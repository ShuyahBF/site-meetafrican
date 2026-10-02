"""Sauvegarde générale automatique vers R2 (voir sauvegarde_auto.py).

  - POST /api/sauvegarde-auto/declencher            : Cron Job Render, en-tête X-Sauvegarde-Jeton
                                                      (répond 202 tout de suite ; sauvegarde puis cycle de vie) ;
  - GET  /api/sauvegarde-auto/derniere              : date de la dernière sauvegarde réussie (tout membre connecté) ;
  - GET  /api/plateforme/sauvegardes-auto           : état, alertes, liste R2, journal (administrateur principal) ;
  - POST /api/plateforme/sauvegardes-auto/lancer    : lancer la sauvegarde du jour maintenant ;
  - POST /api/plateforme/sauvegardes-auto/restaurer : restaurer une sauvegarde R2 (mode Remplacer, mot de passe
                                                      + mot REMPLACER ; suivi par /api/plateforme/transfert/taches/{id}).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import sauvegarde_auto as service
import transfert_donnees
from activity import current_ip
from auth import get_current_super_admin, get_current_user

public = APIRouter(prefix="/sauvegarde-auto", tags=["Sauvegarde automatique"])
admin = APIRouter(prefix="/plateforme/sauvegardes-auto", tags=["Sauvegarde automatique (administrateur)"])


@public.post("/declencher", status_code=202)
async def declencher(x_sauvegarde_jeton: Optional[str] = Header(None)):
    """Sans session : protégée par le secret SAUVEGARDE_AUTO_JETON (comparaison à temps constant)."""
    if not service.get_settings().sauvegarde_auto_jeton:
        raise HTTPException(503, "Déclenchement non configuré (variable SAUVEGARDE_AUTO_JETON absente)")
    if not service.jeton_valide(x_sauvegarde_jeton):
        raise HTTPException(403, "Jeton refusé")
    service.lancer_en_fond(service.executer_nuit())
    return {"ok": True, "message": "Sauvegarde et cycle de vie lancés en tâche de fond"}


@public.get("/derniere")
async def derniere(_: dict = Depends(get_current_user)):
    d = await service.derniere_reussite()
    return {"date": d.get("fin") if d else None}


@admin.get("")
async def etat(_: dict = Depends(get_current_super_admin)):
    return await service.etat_admin()


@admin.post("/lancer", status_code=202)
async def lancer(_: dict = Depends(get_current_super_admin)):
    motif = service.motif_desactivation()
    if motif:
        raise HTTPException(503, motif)
    service.lancer_en_fond(service.executer())
    return {"ok": True}


class Restauration(BaseModel):
    cle: str = Field(max_length=500)
    mot_de_passe: str = Field(max_length=200)
    confirmation: str = Field("", max_length=20)


@admin.post("/restaurer", status_code=202)
async def restaurer(payload: Restauration, user: dict = Depends(get_current_super_admin)):
    if payload.confirmation.strip() != transfert_donnees.MOT_REMPLACER:
        raise HTTPException(400, f"Pour remplacer les données, tapez « {transfert_donnees.MOT_REMPLACER} »")
    ip = current_ip()
    await transfert_donnees.verifier_mot_de_passe(user, payload.mot_de_passe, "restauration_sauvegarde_auto", ip)
    tache = await service.restaurer(user, payload.cle, ip)
    return {**transfert_donnees.publique(tache)}
