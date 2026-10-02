"""Envoi de messages libres (avertissements du cycle de vie, alertes à
l'administrateur) avec les mécanismes d'envoi EXISTANTS de beAuthentik
(otp_senders.py, mêmes variables d'environnement) :

  1. WhatsApp Cloud API (message texte : il n'est remis que si la personne a
     écrit au numéro beAuthentik dans les dernières 24 h — règle de Meta) ;
  2. en repli, SMS (Orange SMS API puis OVH, ou l'inverse hors Burkina).

beAuthentik n'a PAS d'envoi d'e-mail : aucun e-mail n'est envoyé. Chaque envoi
est noté par l'appelant (journal du cycle de vie / de la sauvegarde).
Dans les tests, `envoyer` est remplacé (aucun appel réseau).
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

import otp_senders
from config import get_settings


def numero(user: dict) -> Optional[str]:
    """Numéro du membre (WhatsApp vérifié d'abord, puis téléphone), chiffres seuls avec indicatif."""
    for champ in ("whatsapp", "phone"):
        brut = re.sub(r"\D", "", str(user.get(champ) or ""))
        if not brut:
            continue
        if len(brut) <= 8:  # numéro local burkinabè sans indicatif
            brut = f"{get_settings().default_phone_country_code}{brut}"
        return brut
    return None


async def _whatsapp_texte(msisdn: str, texte: str) -> bool:
    s = get_settings()
    if not otp_senders.whatsapp_configured():
        return False
    url = otp_senders.WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json={"messaging_product": "whatsapp", "to": msisdn, "type": "text",
                                             "text": {"body": texte}},
                                  headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def _sms(msisdn: str, texte: str) -> bool:
    fournisseurs = [(otp_senders.orange_configured(), otp_senders._send_sms_orange),  # noqa: SLF001
                    (otp_senders.ovh_configured(), otp_senders._send_sms_ovh)]  # noqa: SLF001
    if not msisdn.startswith("226"):
        fournisseurs.reverse()
    for actif, fonction in fournisseurs:
        if actif:
            try:
                if await fonction(msisdn, "", texte=texte):
                    return True
            except Exception:  # noqa: BLE001 — un fournisseur en panne ne bloque pas le suivant
                continue
    return False


async def envoyer(user: dict, texte: str) -> dict:
    """Envoie le texte au membre. Renvoie {"ok", "canal", "erreur"}."""
    msisdn = numero(user)
    if not msisdn:
        return {"ok": False, "canal": None, "erreur": "Aucun numéro WhatsApp ni téléphone"}
    if await _whatsapp_texte(msisdn, texte):
        return {"ok": True, "canal": "whatsapp", "erreur": None}
    if await _sms(msisdn, texte[:600]):
        return {"ok": True, "canal": "sms", "erreur": None}
    return {"ok": False, "canal": None, "erreur": "WhatsApp et SMS indisponibles ou non configurés"}


async def alerter_administrateurs(texte: str) -> int:
    """Envoie une alerte à chaque administrateur principal ayant un numéro. Renvoie le nombre d'envois réussis."""
    from db import db
    reussis = 0
    async for adm in db.users.find({"role": "admin", "is_active": {"$ne": False}},
                                   {"_id": 0, "whatsapp": 1, "phone": 1}):
        if (await envoyer(adm, texte))["ok"]:
            reussis += 1
    return reussis
