"""Envoi des codes OTP (vérification des numéros) par WhatsApp ou par SMS.

Repris de sawalismartsystems.com (ShuyahBF/Emergent, branche
Site-SawaliSmartSystems : routes/wa_otp_login_9o.py pour WhatsApp,
server.py `_orange_get_token` / `_sms_send_orange_oauth` pour Orange),
simplifié pour beAuthentik : la configuration vient des variables
d'environnement (config.py) au lieu de la base.

  - WhatsApp : API WhatsApp Cloud de Meta. On tente d'abord le MODÈLE
    (template) approuvé — obligatoire pour écrire à quelqu'un qui n'a pas
    écrit au numéro dans les dernières 24 h — en catégorie
    "Authentication" (corps + bouton "copier le code"), puis "Utility"
    (corps seul) ; en dernier recours, un simple message texte.
  - SMS : Orange SMS API (jeton OAuth2 "client_credentials" mis en cache).

Chaque fonction renvoie (ok, message_erreur_lisible).
"""
from __future__ import annotations

import base64
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import httpx

from config import get_settings

WA_GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"
ORANGE_OAUTH_URL = "https://api.orange.com/oauth/v3/token"
ORANGE_SMS_URL = "https://api.orange.com/smsmessaging/v1/outbound/{sender}/requests"

# Catégorie du modèle WhatsApp qui a fonctionné (mémorisée pour les envois suivants)
_wa_template_category: Dict[str, str] = {}
# Jeton OAuth Orange en cache : {"token": ..., "expires_at": timestamp}
_orange_token: Dict[str, float | str] = {}


def whatsapp_configured() -> bool:
    s = get_settings()
    return bool(s.whatsapp_access_token and s.whatsapp_phone_number_id)


def sms_configured() -> bool:
    s = get_settings()
    return bool(s.orange_sms_client_id and s.orange_sms_client_secret and s.orange_sms_sender_msisdn)


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

async def send_whatsapp_code(msisdn: str, code: str) -> Tuple[bool, Optional[str]]:
    """msisdn : chiffres uniquement, indicatif compris (ex. 22670000000)."""
    s = get_settings()
    if not whatsapp_configured():
        return False, "WhatsApp n'est pas encore configuré sur le serveur"
    url = WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    headers = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    template = (s.whatsapp_otp_template or "").strip()
    body_param = {"type": "body", "parameters": [{"type": "text", "text": code}]}

    def template_payload(category: str) -> dict:
        components = [body_param]
        if category == "authentication":
            # Modèle "Authentication" : le bouton "copier le code" doit aussi recevoir le code.
            components.append({"type": "button", "sub_type": "url", "index": "0",
                               "parameters": [{"type": "text", "text": code}]})
        return {"messaging_product": "whatsapp", "to": msisdn, "type": "template",
                "template": {"name": template, "language": {"code": s.whatsapp_otp_template_lang},
                             "components": components}}

    errors = []
    async with httpx.AsyncClient(timeout=15) as client:
        if template:
            order = ["authentication", "utility"]
            if _wa_template_category.get(template) == "utility":
                order.reverse()
            for category in order:
                r = await client.post(url, json=template_payload(category), headers=headers)
                if r.status_code == 200:
                    _wa_template_category[template] = category
                    return True, None
                errors.append(f"{category}: HTTP {r.status_code} {r.text[:200]}")
        # Repli : message texte (ne passe que si la personne a écrit au numéro dans les 24 h)
        text = {"messaging_product": "whatsapp", "to": msisdn, "type": "text",
                "text": {"body": f"beAuthentik — votre code de vérification : {code}. Valable 10 minutes. Ne le communiquez à personne."}}
        r = await client.post(url, json=text, headers=headers)
        if r.status_code == 200:
            return True, None
        errors.append(f"texte: HTTP {r.status_code} {r.text[:200]}")
    print(f"[otp] échec WhatsApp vers {msisdn[:5]}… : {' | '.join(errors)}")
    return False, "Envoi WhatsApp impossible. Vérifiez que ce numéro utilise WhatsApp, ou choisissez le SMS."


# ---------------------------------------------------------------------------
# SMS — Orange SMS API
# ---------------------------------------------------------------------------

async def _orange_access_token(client: httpx.AsyncClient, force: bool = False) -> Optional[str]:
    """Jeton OAuth2 Orange, mis en cache jusqu'à 1 minute avant expiration."""
    now = datetime.now(timezone.utc).timestamp()
    if not force and _orange_token.get("token") and float(_orange_token.get("expires_at", 0)) > now:
        return str(_orange_token["token"])
    s = get_settings()
    basic = base64.b64encode(f"{s.orange_sms_client_id}:{s.orange_sms_client_secret}".encode()).decode()
    r = await client.post(
        ORANGE_OAUTH_URL,
        headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
        data={"grant_type": "client_credentials"},  # corps "form-urlencoded", exigé par Orange
    )
    if r.status_code >= 300:
        print(f"[otp] OAuth Orange en échec : HTTP {r.status_code} {r.text[:200]}")
        return None
    doc = r.json()
    _orange_token.update({"token": doc["access_token"],
                          "expires_at": now + max(60, int(doc.get("expires_in") or 3600) - 60)})
    return doc["access_token"]


async def send_sms_code(msisdn: str, code: str) -> Tuple[bool, Optional[str]]:
    s = get_settings()
    if not sms_configured():
        return False, "L'envoi de SMS n'est pas encore configuré sur le serveur"
    sender = s.orange_sms_sender_msisdn.strip()
    sender = sender if sender.startswith("+") else f"+{sender}"
    url = ORANGE_SMS_URL.format(sender=urllib.parse.quote(f"tel:{sender}", safe=""))
    request = {
        "address": f"tel:+{msisdn}",
        "senderAddress": f"tel:{sender}",
        "outboundSMSTextMessage": {"message": f"beAuthentik : votre code de verification est {code}. Valable 10 min. Ne le communiquez a personne."},
    }
    if s.orange_sms_sender_name:
        request["senderName"] = s.orange_sms_sender_name
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _orange_access_token(client)
        if not token:
            return False, "Service SMS momentanément indisponible"
        for attempt in range(2):
            r = await client.post(url, json={"outboundSMSMessageRequest": request},
                                  headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            if r.status_code == 401 and attempt == 0:
                token = await _orange_access_token(client, force=True)  # jeton expiré : un seul nouvel essai
                if not token:
                    break
                continue
            if 200 <= r.status_code < 300:
                return True, None
            break
    print(f"[otp] échec SMS Orange vers {msisdn[:5]}… : HTTP {r.status_code} {r.text[:200]}")
    return False, "Envoi du SMS impossible pour le moment. Réessayez plus tard ou choisissez WhatsApp."
