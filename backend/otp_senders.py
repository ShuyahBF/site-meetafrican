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
  - SMS : Orange SMS API (jeton OAuth2 "client_credentials" mis en cache)
    et OVH SMS (API officielle signée HMAC-SHA1, server.py `_sms_send_ovh`).
    Numéro burkinabè (+226) : Orange d'abord, OVH en secours ; autres pays :
    OVH d'abord, Orange en secours.

Chaque fonction renvoie (ok, message_erreur_lisible).
"""
from __future__ import annotations

import base64
import hashlib
import json
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


def orange_configured() -> bool:
    s = get_settings()
    return bool(s.orange_sms_client_id and s.orange_sms_client_secret and s.orange_sms_sender_msisdn)


def ovh_configured() -> bool:
    s = get_settings()
    return bool(s.ovh_sms_application_key and s.ovh_sms_application_secret
                and s.ovh_sms_consumer_key and s.ovh_sms_service_name)


def sms_configured() -> bool:
    return orange_configured() or ovh_configured()


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


SMS_TEXT = "beAuthentik : votre code de verification est {code}. Valable 10 min. Ne le communiquez a personne."


SMS_PROVIDERS = ("orange", "ovh")


async def send_sms_code(msisdn: str, code: str, primary: str = "auto") -> Tuple[bool, Optional[str]]:
    """Envoie le code par SMS. `primary` = fournisseur principal choisi par
    l'admin ("orange" ou "ovh") ; l'autre sert de repli s'il échoue.
    "auto" : Orange d'abord pour un numéro +226, OVH d'abord ailleurs."""
    providers = [("orange", orange_configured(), _send_sms_orange), ("ovh", ovh_configured(), _send_sms_ovh)]
    if primary == "ovh" or (primary not in SMS_PROVIDERS and not msisdn.startswith("226")):
        providers.reverse()
    active = [(name, fn) for name, ok, fn in providers if ok]
    if not active:
        return False, "L'envoi de SMS n'est pas encore configuré sur le serveur"
    for name, fn in active:
        if await fn(msisdn, code):
            return True, None
    return False, "Envoi du SMS impossible pour le moment. Réessayez plus tard ou choisissez WhatsApp."


async def _send_sms_ovh(msisdn: str, code: str) -> bool:
    """OVH SMS : requête signée "$1$" + SHA1(secret+consumer+méthode+url+corps+horodatage)."""
    s = get_settings()
    host = "https://ca.api.ovh.com/1.0" if (s.ovh_sms_endpoint or "").lower() == "ovh-ca" else "https://eu.api.ovh.com/1.0"
    url = f"{host}/sms/{s.ovh_sms_service_name}/jobs"
    body = json.dumps({
        "charset": "UTF-8", "class": "phoneDisplay", "coding": "8bit",
        "message": SMS_TEXT.format(code=code), "noStopClause": True, "priority": "high",
        "receivers": [f"+{msisdn}"], "senderForResponse": False,
        "sender": s.ovh_sms_sender or "beAuthentik", "validityPeriod": 30,
    })
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            # Horloge du serveur OVH (la signature exige son horodatage)
            tr = await client.get(f"{host}/auth/time")
            ts = tr.text.strip() if tr.status_code == 200 else str(int(datetime.now(timezone.utc).timestamp()))
            to_sign = "+".join([s.ovh_sms_application_secret, s.ovh_sms_consumer_key, "POST", url, body, ts])
            r = await client.post(url, content=body, headers={
                "X-Ovh-Application": s.ovh_sms_application_key,
                "X-Ovh-Consumer": s.ovh_sms_consumer_key,
                "X-Ovh-Timestamp": ts,
                "X-Ovh-Signature": "$1$" + hashlib.sha1(to_sign.encode()).hexdigest(),
                "Content-Type": "application/json",
            })
        doc = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code < 300 and not (doc.get("invalidReceivers") and not doc.get("validReceivers")):
            return True
        print(f"[otp] échec SMS OVH vers {msisdn[:5]}… : HTTP {r.status_code} {r.text[:200]}")
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[otp] échec SMS OVH vers {msisdn[:5]}… : {exc!r}")
    return False


async def _send_sms_orange(msisdn: str, code: str) -> bool:
    s = get_settings()
    sender = s.orange_sms_sender_msisdn.strip()
    sender = sender if sender.startswith("+") else f"+{sender}"
    url = ORANGE_SMS_URL.format(sender=urllib.parse.quote(f"tel:{sender}", safe=""))
    request = {
        "address": f"tel:+{msisdn}",
        "senderAddress": f"tel:{sender}",
        "outboundSMSTextMessage": {"message": SMS_TEXT.format(code=code)},
    }
    if s.orange_sms_sender_name:
        request["senderName"] = s.orange_sms_sender_name
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _orange_access_token(client)
        if not token:
            return False
        for attempt in range(2):
            r = await client.post(url, json={"outboundSMSMessageRequest": request},
                                  headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
            if r.status_code == 401 and attempt == 0:
                token = await _orange_access_token(client, force=True)  # jeton expiré : un seul nouvel essai
                if not token:
                    break
                continue
            if 200 <= r.status_code < 300:
                return True
            break
    print(f"[otp] échec SMS Orange vers {msisdn[:5]}… : HTTP {r.status_code} {r.text[:200]}")
    return False
