"""Envoi d'un message WhatsApp — point d'entrée UNIQUE de beAuthentik.

Règle du propriétaire : chaque plateforme envoie ses WhatsApp avec SES PROPRES
paramètres WABA (WhatsApp Cloud API de Meta) s'ils sont configurés ; À DÉFAUT,
elle passe par la « Transmission WA Universelle Liluvine » (service de SAWALI).

  1. WABA propre (variables WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID,
     déjà utilisées par otp_senders.py) : message texte via graph.facebook.com.
  2. Sinon, Transmission WA Universelle Liluvine (protocole v2) :
       POST {LILUVINE_WA_URL}
       en-têtes X-Emetteur, X-Timestamp, X-Signature
       signature = hex(HMAC-SHA256(LILUVINE_WA_HMAC, f"{timestamp}.{corps_brut}"))
       corps = {"id": uuid4, "to": "+226…", "message": "…", "source": "beAuthentik"}
     Délai 15 s ; UN SEUL nouvel essai (même id, nouvelle signature) sur erreur
     réseau ou réponse 5xx ; jamais de nouvel essai sur 4xx.
  3. Ni l'un ni l'autre : envoi impossible, avec un message d'erreur clair.

Résultat toujours de la même forme (jamais d'exception non gérée) :
    {"ok": bool, "canal": "waba" | "liluvine" | None, "message_id": str | None, "erreur": str | None}

Sécurité : la clé HMAC et le jeton WABA ne sont JAMAIS journalisés ni renvoyés ;
le texte du message n'est jamais journalisé en entier (seulement sa longueur).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from typing import Optional

import httpx

import otp_senders
from config import get_settings

logger = logging.getLogger("transmission_wa")

# Délai maximal d'un appel HTTP (secondes), imposé par le protocole
DELAI_SECONDES = 15
# Longueur maximale d'un message accepté par la Transmission universelle
LONGUEUR_MAX = 4096
# Libellé de l'émetteur affiché au destinataire (paramètre `source`)
SOURCE_DEFAUT = "beAuthentik"
# Code émetteur de beAuthentik côté SAWALI (pas secret)
EMETTEUR_DEFAUT = "beauthentik"

# Transport HTTP de remplacement : None en production ; les tests y placent un
# httpx.MockTransport pour simuler les réponses (aucun appel réseau réel).
_transport: Optional[httpx.AsyncBaseTransport] = None


# ---------------------------------------------------------------------------
# Lecture de la configuration (variables d'environnement Render)
# ---------------------------------------------------------------------------

def _liluvine_url() -> str:
    """Adresse du service SAWALI (…/api/webhook/liluvine-send), vide si absente."""
    return (os.environ.get("LILUVINE_WA_URL") or "").strip()


def _liluvine_cle() -> str:
    """Clé HMAC propre à beAuthentik (secrète : jamais affichée)."""
    return (os.environ.get("LILUVINE_WA_HMAC") or "").strip()


def emetteur() -> str:
    """Code émetteur envoyé dans l'en-tête X-Emetteur (« beauthentik » par défaut)."""
    return (os.environ.get("LILUVINE_WA_EMETTEUR") or "").strip() or EMETTEUR_DEFAUT


def waba_configure() -> bool:
    """Vrai si les paramètres WhatsApp propres à beAuthentik sont saisis."""
    return otp_senders.whatsapp_configured()


def liluvine_configure() -> bool:
    """Vrai si la Transmission universelle est utilisable (adresse ET clé présentes)."""
    return bool(_liluvine_url() and _liluvine_cle())


def etat() -> dict:
    """État de la configuration pour la page d'administration (jamais la clé)."""
    return {"waba_configure": waba_configure(), "liluvine_configure": liluvine_configure(),
            "emetteur": emetteur()}


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def _resultat(ok: bool, canal: Optional[str], message_id: Optional[str] = None,
              erreur: Optional[str] = None) -> dict:
    """Construit le résultat uniforme renvoyé à l'appelant."""
    return {"ok": ok, "canal": canal, "message_id": message_id, "erreur": erreur}


def _chiffres(numero: str) -> str:
    """Numéro réduit à ses chiffres, indicatif compris (ex. « 22670000000 »).
    Un numéro local burkinabè (8 chiffres) reçoit l'indicatif par défaut."""
    brut = re.sub(r"\D", "", str(numero or ""))
    if brut.startswith("00"):
        brut = brut[2:]
    if brut and len(brut) <= 8:
        brut = f"{get_settings().default_phone_country_code}{brut}"
    return brut


def signer(cle: str, horodatage: str, corps_brut: str) -> str:
    """Signature du protocole : hex(HMAC-SHA256(clé, "{horodatage}.{corps_brut}"))."""
    return hmac.new(cle.encode("utf-8"), f"{horodatage}.{corps_brut}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _client() -> httpx.AsyncClient:
    """Client HTTP avec le délai du protocole (et le transport simulé des tests)."""
    return httpx.AsyncClient(timeout=DELAI_SECONDES, transport=_transport)


# ---------------------------------------------------------------------------
# Canal 1 : WABA propre de beAuthentik (WhatsApp Cloud API de Meta)
# ---------------------------------------------------------------------------

async def _envoyer_waba(msisdn: str, message: str) -> dict:
    """Message texte via graph.facebook.com (même code que l'ancien envoi_messages).
    Rappel Meta : un texte libre n'est remis que si la personne a écrit au numéro
    beAuthentik dans les dernières 24 h."""
    s = get_settings()
    url = otp_senders.WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    try:
        async with _client() as client:
            r = await client.post(url, json={"messaging_product": "whatsapp", "to": msisdn, "type": "text",
                                             "text": {"body": message}},
                                  headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    except httpx.HTTPError as exc:
        logger.warning("WABA : erreur réseau vers %s… (%s)", msisdn[:5], type(exc).__name__)
        return _resultat(False, "waba", erreur="WhatsApp (WABA) injoignable")
    if r.status_code != 200:
        logger.warning("WABA : refus HTTP %s vers %s…", r.status_code, msisdn[:5])
        return _resultat(False, "waba", erreur=f"WhatsApp (WABA) a refusé l'envoi (HTTP {r.status_code})")
    # Identifiant du message renvoyé par Meta : {"messages": [{"id": "wamid…"}]}
    message_id = None
    try:
        message_id = (r.json().get("messages") or [{}])[0].get("id")
    except (ValueError, AttributeError, IndexError):
        pass
    return _resultat(True, "waba", message_id=message_id)


# ---------------------------------------------------------------------------
# Canal 2 : Transmission WA Universelle Liluvine (SAWALI)
# ---------------------------------------------------------------------------

# Messages lisibles pour les refus connus du protocole
_ERREURS_LILUVINE = {
    401: "Transmission universelle : signature ou émetteur refusé (vérifier LILUVINE_WA_HMAC / l'heure du serveur)",
    422: "Transmission universelle : données refusées (numéro ou message invalide)",
    429: "Transmission universelle : quota d'envoi dépassé",
    502: "Transmission universelle : WhatsApp a refusé l'envoi",
    503: "Transmission universelle : non configurée côté SAWALI",
}


async def _envoyer_liluvine(msisdn: str, message: str, source: str) -> dict:
    """Envoi signé vers SAWALI, avec un seul nouvel essai (même id) si besoin."""
    url, cle = _liluvine_url(), _liluvine_cle()
    # Corps sérialisé UNE SEULE FOIS : c'est exactement ce texte qui est signé et envoyé.
    # Le même corps (donc le même id) est réutilisé au nouvel essai : SAWALI ne crée pas de doublon.
    corps = {"id": str(uuid.uuid4()), "to": f"+{msisdn}", "message": message[:LONGUEUR_MAX], "source": source}
    corps_brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":"))
    derniere_erreur = "Transmission universelle injoignable"
    for essai in (1, 2):
        # Nouvel horodatage et nouvelle signature à chaque essai
        horodatage = str(int(time.time()))
        entetes = {"Content-Type": "application/json", "X-Emetteur": emetteur(),
                   "X-Timestamp": horodatage, "X-Signature": signer(cle, horodatage, corps_brut)}
        try:
            async with _client() as client:
                r = await client.post(url, content=corps_brut.encode("utf-8"), headers=entetes)
        except httpx.HTTPError as exc:
            # Erreur réseau (délai dépassé, connexion refusée…) : un seul nouvel essai
            logger.warning("Liluvine : erreur réseau (essai %s, id %s) : %s", essai, corps["id"], type(exc).__name__)
            continue
        if r.status_code >= 500:
            # Réponse 5xx : un seul nouvel essai (même id, donc pas de doublon chez SAWALI)
            logger.warning("Liluvine : HTTP %s (essai %s, id %s)", r.status_code, essai, corps["id"])
            derniere_erreur = _ERREURS_LILUVINE.get(
                r.status_code, f"Transmission universelle : erreur serveur (HTTP {r.status_code})")
            continue
        if r.status_code == 200:
            try:
                donnees = r.json()
            except ValueError:
                donnees = {}
            if donnees.get("ok", True):
                return _resultat(True, "liluvine", message_id=donnees.get("message_id"))
            return _resultat(False, "liluvine", erreur="Transmission universelle : envoi refusé")
        # 4xx (signature, données, quota…) : refus définitif, pas de nouvel essai
        logger.warning("Liluvine : refus HTTP %s (id %s, message de %s caractères)",
                       r.status_code, corps["id"], len(message))
        return _resultat(False, "liluvine", erreur=_ERREURS_LILUVINE.get(
            r.status_code, f"Transmission universelle : refus (HTTP {r.status_code})"))
    return _resultat(False, "liluvine", erreur=derniere_erreur)


# ---------------------------------------------------------------------------
# Point d'entrée unique
# ---------------------------------------------------------------------------

async def envoyer_whatsapp(numero: str, message: str, *, source: Optional[str] = None) -> dict:
    """Envoie `message` au numéro WhatsApp `numero` (« +226… », « 226… » ou local).

    WABA propre s'il est configuré, sinon Transmission WA Universelle Liluvine.
    Ne lève jamais d'exception : renvoie {"ok", "canal", "message_id", "erreur"}."""
    try:
        msisdn = _chiffres(numero)
        texte = (message or "").strip()
        # Contrôles de base avant tout appel réseau
        if len(msisdn) < 8:
            return _resultat(False, None, erreur="Numéro WhatsApp invalide")
        if not texte:
            return _resultat(False, None, erreur="Message vide")
        # 1. Paramètres WABA propres à beAuthentik
        if waba_configure():
            return await _envoyer_waba(msisdn, texte)
        # 2. À défaut : Transmission WA Universelle Liluvine
        if liluvine_configure():
            return await _envoyer_liluvine(msisdn, texte, (source or SOURCE_DEFAUT).strip() or SOURCE_DEFAUT)
        # 3. Aucun canal WhatsApp utilisable
        return _resultat(False, None, erreur="WhatsApp non configuré (ni WABA ni Transmission universelle)")
    except Exception as exc:  # noqa: BLE001 — filet de sécurité : jamais d'exception chez l'appelant
        logger.exception("Envoi WhatsApp : erreur inattendue (%s)", type(exc).__name__)
        return _resultat(False, None, erreur="Erreur inattendue lors de l'envoi WhatsApp")
