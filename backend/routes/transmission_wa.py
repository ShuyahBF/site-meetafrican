"""Transmission WhatsApp — routes de contrôle (administrateur principal uniquement).

  - GET  /api/admin/transmission-wa/etat : quels canaux WhatsApp sont configurés
        {"waba_configure": bool, "liluvine_configure": bool, "emetteur": "beauthentik"}
        (jamais la clé HMAC ni le jeton WABA) ;
  - POST /api/admin/transmission-wa/test {"numero": "+226…"} : envoie le message
        « Test de transmission WhatsApp depuis beAuthentik » par le canal choisi
        automatiquement (WABA propre, sinon Transmission WA Universelle Liluvine).

Réservées au rôle « admin » (les modérateurs n'y ont pas accès), comme les autres
réglages de la plateforme.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import transmission_wa as service
from activity import current_ip, log_activity
from auth import get_current_super_admin

router = APIRouter(prefix="/admin/transmission-wa", tags=["Transmission WhatsApp (administrateur)"])

# Texte du message d'essai (imposé)
MESSAGE_TEST = "Test de transmission WhatsApp depuis beAuthentik"


class DemandeTest(BaseModel):
    """Numéro WhatsApp du destinataire de l'essai, au format international."""
    numero: str = Field(..., min_length=8, max_length=30)


@router.get("/etat")
async def etat(_adm: dict = Depends(get_current_super_admin)):
    """État de la configuration WhatsApp (booléens seulement, aucun secret)."""
    return service.etat()


@router.post("/test")
async def test(data: DemandeTest, adm: dict = Depends(get_current_super_admin)):
    """Envoie le message d'essai et renvoie le résultat uniforme
    {"ok", "canal", "message_id", "erreur"} (jamais d'erreur 500)."""
    resultat = await service.envoyer_whatsapp(data.numero, MESSAGE_TEST)
    # Trace dans le journal d'activité : canal et résultat, numéro masqué
    numero_masque = (data.numero.strip()[:6] + "…") if data.numero else ""
    await log_activity(adm.get("id"), "Essai de transmission WhatsApp", current_ip(),
                       details={"numero": numero_masque, "ok": resultat["ok"], "canal": resultat["canal"]})
    return resultat
