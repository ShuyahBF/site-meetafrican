"""Paramètres « Abonnements, sessions et sauvegardes » de la plateforme
(administrateur principal) — voir parametres_plateforme.py.

  - GET /api/plateforme/parametres/abonnements-sessions
  - PUT /api/plateforme/parametres/abonnements-sessions  (seuls les champs envoyés changent)

Envoi des e-mails de la plateforme (voir envoi_email.py) :
  - GET  /api/plateforme/parametres/email          (jamais de clé : seulement `a_cle`)
  - PUT  /api/plateforme/parametres/email          (champ secret vide = valeur conservée)
  - POST /api/plateforme/parametres/email/essai    (« Envoyer un essai », réglages enregistrés)
  - GET  /api/plateforme/parametres/email/journal  (modifications des réglages + derniers envois)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import envoi_email
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


# ---------------------------------------------------------------------------
# Envoi des e-mails de la plateforme (administrateur principal seulement)
# ---------------------------------------------------------------------------
class ReglagesEmail(BaseModel):
    fournisseur: Optional[str] = None       # resend | zeptomail | brevo | smtp | desactive
    actif: Optional[bool] = None
    expediteur: Optional[str] = None
    nom_expediteur: Optional[str] = None
    cle_api: Optional[str] = None           # vide = clé conservée (jamais renvoyée)
    zeptomail_hote: Optional[str] = None
    smtp_hote: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_securite: Optional[str] = None
    smtp_utilisateur: Optional[str] = None
    smtp_mot_de_passe: Optional[str] = None  # vide = mot de passe conservé (jamais renvoyé)


class EssaiEmail(BaseModel):
    destinataire: Optional[str] = None      # défaut : l'adresse de l'administrateur connecté


def _auteur(adm: dict) -> str:
    return adm.get("email") or adm.get("phone") or adm.get("id") or ""


@router.get("/email")
async def lire_email(_: dict = Depends(get_current_super_admin)):
    return await envoi_email.lire_public()


@router.put("/email")
async def modifier_email(payload: ReglagesEmail, adm: dict = Depends(get_current_super_admin)):
    changements = payload.model_dump(exclude_none=True)
    reglages = await envoi_email.modifier(changements, _auteur(adm))
    # Journal d'activité : quels champs, jamais la valeur des secrets
    details = {k: v for k, v in changements.items() if k not in ("cle_api", "smtp_mot_de_passe")}
    details["secret_modifie"] = bool(changements.get("cle_api") or changements.get("smtp_mot_de_passe"))
    await log_activity(adm["id"], "Paramètres d'envoi des e-mails modifiés", current_ip(), details=details)
    return reglages


@router.post("/email/essai")
async def essai_email(payload: EssaiEmail, adm: dict = Depends(get_current_super_admin)):
    destinataire = (payload.destinataire or adm.get("email") or "").strip()
    resultat = await envoi_email.essai(destinataire, _auteur(adm))
    await log_activity(adm["id"], "E-mail d'essai", current_ip(),
                       details={"destinataire": destinataire, "statut": resultat["statut"]})
    return {**resultat, "destinataire": destinataire}


@router.get("/email/journal")
async def journal_email(_: dict = Depends(get_current_super_admin)):
    return await envoi_email.journal()
