"""Envoi d'un message WhatsApp — point d'entrée UNIQUE de beAuthentik.

Règle du propriétaire : chaque plateforme envoie ses WhatsApp avec SES PROPRES
paramètres WABA (WhatsApp Cloud API de Meta) s'ils sont configurés ; À DÉFAUT,
elle passe par la « Transmission WA Universelle Liluvine » (service de SAWALI).

  1. WABA propre (variables WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID,
     déjà utilisées par otp_senders.py) : message texte (ou média) via
     graph.facebook.com.
  2. Sinon, Transmission WA Universelle Liluvine (protocole v2 + v3) :
       POST {LILUVINE_WA_URL}
       en-têtes X-Emetteur, X-Timestamp, X-Signature
       signature = hex(HMAC-SHA256(LILUVINE_WA_HMAC, f"{timestamp}.{corps_brut}"))
       corps = {"id": uuid4, "to": "+226…", "message": "…", "source": "beAuthentik",
                "media": {…} (facultatif, protocole v3)}
     Délai 15 s ; UN SEUL nouvel essai (même id, nouvelle signature) sur erreur
     réseau ou réponse 5xx ; jamais de nouvel essai sur 4xx.
     409 = destinataire désinscrit (il a répondu STOP) : échec DÉFINITIF, noté
     dans la collection `liluvine_retours`.
  3. Repli (protocole v3, section 4) : si le WABA propre échoue pour une raison
     qui ne tient PAS au numéro (fenêtre de 24 h, modèle requis, panne…) et que
     la Transmission universelle est configurée, le même texte (et le même
     média) repart par Liluvine — canal « liluvine_repli ».
  4. Aucun canal : envoi impossible, avec un message d'erreur clair.

Résultat toujours de la même forme (jamais d'exception non gérée) :
    {"ok": bool, "canal": "waba" | "liluvine" | "liluvine_repli" | None,
     "message_id": str | None, "erreur": str | None}
  plus, seulement quand c'est utile : "desinscrit": True (refus 409) et
  "media_mode": "direct" | "modele" | "lien" (média accepté par SAWALI).

Médias (protocole v3, section 1) : paramètre `media` =
    {"type": "document"|"image"|"video"|"audio",
     "url": "https://…"  OU  "contenu": b"…" (octets, 10 Mo au plus),
     "nom_fichier": "facture.pdf", "mime": "application/pdf", "legende": "…"}
Le module encode les octets en base64 pour SAWALI et refuse LOCALEMENT (sans
aucun appel) un fichier de plus de 10 Mo.

Sécurité : la clé HMAC et le jeton WABA ne sont JAMAIS journalisés ni renvoyés ;
le texte du message n'est jamais journalisé en entier (seulement sa longueur).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

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
# Taille maximale d'un média (avant encodage base64) : 10 Mo
MEDIA_TAILLE_MAX = 10 * 1024 * 1024
# Types de média acceptés par le protocole v3
MEDIA_TYPES = ("document", "image", "video", "audio")
# Adresse d'envoi des fichiers au WABA (téléversement avant envoi par identifiant)
WA_MEDIA_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/media"

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


def cle_hmac() -> str:
    """Clé HMAC partagée avec SAWALI : sert aussi à vérifier les retours
    (route /api/webhooks/liluvine-retour). Vide si absente. Jamais affichée."""
    return _liluvine_cle()


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
              erreur: Optional[str] = None, **extra) -> dict:
    """Construit le résultat uniforme renvoyé à l'appelant. `extra` ajoute des
    informations facultatives (desinscrit, media_mode, numero_invalide) seulement
    quand elles ont une valeur."""
    res = {"ok": ok, "canal": canal, "message_id": message_id, "erreur": erreur}
    res.update({k: v for k, v in extra.items() if v is not None})
    return res


def _chiffres(numero: str) -> str:
    """Numéro réduit à ses chiffres, indicatif compris (ex. « 22670000000 »).
    Un numéro local burkinabè (8 chiffres) reçoit l'indicatif par défaut."""
    brut = re.sub(r"\D", "", str(numero or ""))
    if brut.startswith("00"):
        brut = brut[2:]
    if brut and len(brut) <= 8:
        brut = f"{get_settings().default_phone_country_code}{brut}"
    return brut


def signer(cle: str, horodatage: str, corps_brut) -> str:
    """Signature du protocole : hex(HMAC-SHA256(clé, "{horodatage}.{corps_brut}")).
    `corps_brut` peut être du texte ou des octets (corps HTTP reçu tel quel)."""
    if isinstance(corps_brut, str):
        corps_brut = corps_brut.encode("utf-8")
    return hmac.new(cle.encode("utf-8"), horodatage.encode("utf-8") + b"." + corps_brut,
                    hashlib.sha256).hexdigest()


def _client() -> httpx.AsyncClient:
    """Client HTTP avec le délai du protocole (et le transport simulé des tests)."""
    return httpx.AsyncClient(timeout=DELAI_SECONDES, transport=_transport)


def _maintenant_iso() -> str:
    """Date et heure courantes (UTC) au format ISO."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Médias (protocole v3, section 1) : contrôle local avant tout appel
# ---------------------------------------------------------------------------

def _preparer_media(media: Optional[dict]) -> Tuple[Optional[dict], Optional[str]]:
    """Vérifie le média demandé et le met dans une forme commune aux deux canaux.

    Renvoie (media_prepare, None) si tout va bien, (None, None) s'il n'y a pas
    de média, ou (None, "erreur lisible") si le média est refusé (aucun appel
    réseau n'est alors fait). Le média préparé garde les octets bruts (pour le
    WABA) ; le base64 n'est calculé qu'au moment d'appeler SAWALI."""
    if not media:
        return None, None
    if not isinstance(media, dict):
        return None, "Média invalide"
    type_media = str(media.get("type") or "").strip().lower()
    if type_media not in MEDIA_TYPES:
        return None, "Type de média invalide (document, image, video ou audio)"
    url = str(media.get("url") or "").strip()
    contenu = media.get("contenu")
    # Exactement UN des deux : lien OU octets
    if bool(url) == (contenu is not None):
        return None, "Média : indiquer soit un lien (url), soit le contenu du fichier, pas les deux"
    if url and not url.lower().startswith("https://"):
        return None, "Média : le lien doit commencer par https://"
    if contenu is not None:
        if isinstance(contenu, bytearray):
            contenu = bytes(contenu)
        if not isinstance(contenu, bytes) or not contenu:
            return None, "Média : contenu du fichier vide ou invalide"
        # Refus local au-delà de 10 Mo (le protocole l'interdit) : pas d'appel inutile
        if len(contenu) > MEDIA_TAILLE_MAX:
            return None, "Média trop volumineux (10 Mo au plus)"
    prepare = {"type": type_media,
               "nom_fichier": str(media.get("nom_fichier") or "").strip() or None,
               "mime": str(media.get("mime") or "").strip() or None,
               "legende": str(media.get("legende") or "").strip() or None}
    if url:
        prepare["url"] = url
    else:
        prepare["contenu"] = contenu
    return prepare, None


def _media_pour_liluvine(media: dict) -> dict:
    """Champ « media » du corps signé envoyé à SAWALI (octets encodés en base64)."""
    champ = {"type": media["type"]}
    if media.get("url"):
        champ["url"] = media["url"]
    else:
        champ["contenu_base64"] = base64.b64encode(media["contenu"]).decode("ascii")
    # Champs facultatifs : seulement s'ils sont renseignés
    for cle in ("nom_fichier", "mime", "legende"):
        if media.get(cle):
            champ[cle] = media[cle]
    return champ


# ---------------------------------------------------------------------------
# Lecture des erreurs du WABA (pour décider du repli, section 4)
# ---------------------------------------------------------------------------

# Codes Meta liés à la fenêtre de 24 h / modèle requis (repli conseillé). Pour
# mémoire : le repli se fait en fait sur TOUT échec qui ne tient pas au numéro.
CODES_FENETRE_24H = {131047, 131026, 470}
# Codes Meta qui tiennent au NUMÉRO lui-même (pas de repli : Liluvine échouerait aussi)
CODES_NUMERO_INVALIDE = {131021}  # « le destinataire ne peut pas être l'expéditeur »


def _erreur_meta(r: httpx.Response) -> Tuple[Optional[int], str]:
    """(code Meta, message) tirés d'une réponse d'erreur du WABA :
    {"error": {"code": 131047, "message": "...", "error_data": {"details": "..."}}}."""
    try:
        err = (r.json() or {}).get("error") or {}
    except (ValueError, AttributeError):
        return None, (r.text or "")[:300]
    code = err.get("code")
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    details = ((err.get("error_data") or {}).get("details") or "") if isinstance(err.get("error_data"), dict) else ""
    return code, f"{err.get('message') or ''} {details}".strip()[:300]


def erreur_numero_invalide(code: Optional[int], message: str) -> bool:
    """Vrai si l'échec WABA tient au numéro du destinataire (numéro invalide,
    inconnu de WhatsApp…) : dans ce cas, PAS de repli par Liluvine."""
    if code in CODES_NUMERO_INVALIDE:
        return True
    texte = (message or "").lower()
    parle_du_numero = any(m in texte for m in ("phone number", "recipient", "numéro", "wa_id", "param to", "'to'"))
    invalide = any(m in texte for m in ("invalid", "not a valid", "not a whatsapp", "invalide", "incorrect"))
    return parle_du_numero and invalide


# ---------------------------------------------------------------------------
# Journal des envois par Liluvine (mis à jour par les retours de SAWALI)
# ---------------------------------------------------------------------------

async def _noter_envoi(id_envoi: str, msisdn: str, canal: str, statut: str,
                       message_id: Optional[str] = None, erreur: Optional[str] = None,
                       avec_media: bool = False) -> None:
    """Note l'envoi dans `liluvine_envois` (id d'origine, numéro, statut). Le
    statut est ensuite mis à jour par les retours « statut » de SAWALI. Une
    erreur de base n'empêche JAMAIS l'envoi."""
    try:
        from db import db
        await db.liluvine_envois.update_one(
            {"id": id_envoi},
            {"$set": {"id": id_envoi, "numero": f"+{msisdn}", "canal": canal, "statut": statut,
                      "message_id": message_id, "erreur": erreur, "media": avec_media,
                      "date": _maintenant_iso()}},
            upsert=True)
    except Exception as exc:  # noqa: BLE001 — journal facultatif
        logger.warning("Liluvine : journal d'envoi non écrit (%s)", type(exc).__name__)


async def _noter_refus_desinscrit(id_envoi: str, msisdn: str) -> None:
    """Trace d'un refus 409 (destinataire désinscrit) dans `liluvine_retours`."""
    try:
        from db import db
        maintenant = _maintenant_iso()
        await db.liluvine_retours.update_one(
            {"cle": f"refus_desinscrit:{id_envoi}"},
            {"$setOnInsert": {"cle": f"refus_desinscrit:{id_envoi}", "type": "refus_desinscrit",
                              "id_origine": id_envoi, "numero": f"+{msisdn}", "statut": "desinscrit",
                              "texte": None, "date": maintenant, "recu_le": maintenant}},
            upsert=True)
    except Exception as exc:  # noqa: BLE001 — trace facultative
        logger.warning("Liluvine : trace de désinscription non écrite (%s)", type(exc).__name__)


# ---------------------------------------------------------------------------
# Canal 1 : WABA propre de beAuthentik (WhatsApp Cloud API de Meta)
# ---------------------------------------------------------------------------

async def _televerser_media_waba(client: httpx.AsyncClient, media: dict) -> Tuple[Optional[str], Optional[httpx.Response]]:
    """Téléverse des octets au WABA (POST …/media) et renvoie (identifiant, None),
    ou (None, réponse d'erreur)."""
    s = get_settings()
    mime = media.get("mime") or "application/octet-stream"
    r = await client.post(WA_MEDIA_URL.format(phone_number_id=s.whatsapp_phone_number_id),
                          data={"messaging_product": "whatsapp", "type": mime},
                          files={"file": (media.get("nom_fichier") or "fichier", media["contenu"], mime)},
                          headers={"Authorization": f"Bearer {s.whatsapp_access_token}"})
    if r.status_code != 200:
        return None, r
    try:
        return r.json().get("id"), None
    except (ValueError, AttributeError):
        return None, r


async def _envoyer_waba(msisdn: str, message: str, media: Optional[dict] = None) -> dict:
    """Message texte (ou média avec légende) via graph.facebook.com.
    Rappel Meta : un message libre n'est remis que si la personne a écrit au
    numéro beAuthentik dans les dernières 24 h (sinon code 131047 → repli).
    Le résultat porte "numero_invalide": True quand l'échec tient au numéro."""
    s = get_settings()
    url = otp_senders.WA_GRAPH_URL.format(phone_number_id=s.whatsapp_phone_number_id)
    entetes = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    try:
        async with _client() as client:
            if media:
                # Objet média : lien direct, ou identifiant après téléversement des octets
                objet = {}
                if media.get("url"):
                    objet["link"] = media["url"]
                else:
                    media_id, refus = await _televerser_media_waba(client, media)
                    if not media_id:
                        code = _erreur_meta(refus)[0] if refus is not None else None
                        logger.warning("WABA : téléversement du média refusé (code %s)", code)
                        return _resultat(False, "waba", erreur="WhatsApp (WABA) a refusé le fichier")
                    objet["id"] = media_id
                # L'audio n'accepte pas de légende ; le nom du fichier ne vaut que pour un document
                if media["type"] != "audio":
                    objet["caption"] = (media.get("legende") or message)[:1024]
                if media["type"] == "document" and media.get("nom_fichier"):
                    objet["filename"] = media["nom_fichier"]
                corps = {"messaging_product": "whatsapp", "to": msisdn, "type": media["type"], media["type"]: objet}
            else:
                corps = {"messaging_product": "whatsapp", "to": msisdn, "type": "text", "text": {"body": message}}
            r = await client.post(url, json=corps, headers=entetes)
    except httpx.HTTPError as exc:
        logger.warning("WABA : erreur réseau vers %s… (%s)", msisdn[:5], type(exc).__name__)
        return _resultat(False, "waba", erreur="WhatsApp (WABA) injoignable")
    if r.status_code != 200:
        # Lecture du code d'erreur Meta pour décider du repli (section 4)
        code, texte = _erreur_meta(r)
        logger.warning("WABA : refus HTTP %s (code Meta %s) vers %s…", r.status_code, code, msisdn[:5])
        return _resultat(False, "waba", erreur=f"WhatsApp (WABA) a refusé l'envoi (HTTP {r.status_code}"
                         + (f", code {code})" if code else ")"),
                         numero_invalide=True if erreur_numero_invalide(code, texte) else None)
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
    409: "Transmission universelle : destinataire désinscrit (il a répondu STOP)",
    413: "Transmission universelle : fichier trop volumineux",
    422: "Transmission universelle : données refusées (numéro, message ou média invalide)",
    429: "Transmission universelle : quota d'envoi dépassé",
    502: "Transmission universelle : WhatsApp a refusé l'envoi",
    503: "Transmission universelle : non configurée côté SAWALI",
}


async def _envoyer_liluvine(msisdn: str, message: str, source: str, media: Optional[dict] = None,
                            canal: str = "liluvine") -> dict:
    """Envoi signé vers SAWALI, avec un seul nouvel essai (même id) si besoin.
    `canal` vaut « liluvine_repli » quand on passe ici après un échec du WABA."""
    url, cle = _liluvine_url(), _liluvine_cle()
    # Corps sérialisé UNE SEULE FOIS : c'est exactement ce texte qui est signé et envoyé.
    # Le même corps (donc le même id) est réutilisé au nouvel essai : SAWALI ne crée pas de doublon.
    corps = {"id": str(uuid.uuid4()), "to": f"+{msisdn}", "message": message[:LONGUEUR_MAX], "source": source}
    if media:
        corps["media"] = _media_pour_liluvine(media)
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
                await _noter_envoi(corps["id"], msisdn, canal, "accepte", donnees.get("message_id"),
                                   avec_media=bool(media))
                return _resultat(True, canal, message_id=donnees.get("message_id"),
                                 media_mode=donnees.get("media_mode") if media else None)
            return _resultat(False, canal, erreur="Transmission universelle : envoi refusé")
        # 409 : destinataire désinscrit — échec DÉFINITIF, jamais de nouvel essai
        if r.status_code == 409:
            logger.warning("Liluvine : destinataire désinscrit (id %s, %s…)", corps["id"], msisdn[:5])
            await _noter_refus_desinscrit(corps["id"], msisdn)
            await _noter_envoi(corps["id"], msisdn, canal, "desinscrit", erreur="Destinataire désinscrit",
                               avec_media=bool(media))
            return _resultat(False, canal, erreur=_ERREURS_LILUVINE[409], desinscrit=True)
        # Autres 4xx (signature, données, quota…) : refus définitif, pas de nouvel essai
        logger.warning("Liluvine : refus HTTP %s (id %s, message de %s caractères)",
                       r.status_code, corps["id"], len(message))
        return _resultat(False, canal, erreur=_ERREURS_LILUVINE.get(
            r.status_code, f"Transmission universelle : refus (HTTP {r.status_code})"))
    return _resultat(False, canal, erreur=derniere_erreur)


# ---------------------------------------------------------------------------
# Point d'entrée unique
# ---------------------------------------------------------------------------

async def envoyer_whatsapp(numero: str, message: str, *, source: Optional[str] = None,
                           media: Optional[dict] = None) -> dict:
    """Envoie `message` (et éventuellement `media`) au numéro WhatsApp `numero`
    (« +226… », « 226… » ou local).

    WABA propre s'il est configuré — avec repli par Liluvine s'il échoue pour
    une raison qui ne tient pas au numéro —, sinon Transmission WA Universelle
    Liluvine. Ne lève jamais d'exception : renvoie {"ok", "canal", "message_id",
    "erreur"} (+ "desinscrit" / "media_mode" si utile)."""
    try:
        msisdn = _chiffres(numero)
        texte = (message or "").strip()
        # Contrôles de base avant tout appel réseau
        if len(msisdn) < 8:
            return _resultat(False, None, erreur="Numéro WhatsApp invalide")
        if not texte:
            return _resultat(False, None, erreur="Message vide")
        # Média : contrôle local (type, lien OU octets, 10 Mo au plus) avant tout appel
        media_prepare, erreur_media = _preparer_media(media)
        if erreur_media:
            return _resultat(False, None, erreur=erreur_media)
        source_txt = (source or SOURCE_DEFAUT).strip() or SOURCE_DEFAUT
        # 1. Paramètres WABA propres à beAuthentik
        if waba_configure():
            resultat = await _envoyer_waba(msisdn, texte, media_prepare)
            if resultat["ok"]:
                return resultat
            # Repli (section 4) : seulement si l'échec ne tient pas au numéro
            # et si la Transmission universelle est configurée
            if resultat.get("numero_invalide") or not liluvine_configure():
                return resultat
            logger.info("WABA en échec (%s) : repli par la Transmission universelle", resultat["erreur"])
            repli = await _envoyer_liluvine(msisdn, texte, source_txt, media_prepare, canal="liluvine_repli")
            if not repli["ok"]:
                # Les deux erreurs sont rendues, pour comprendre l'échec complet
                repli["erreur"] = f"{resultat['erreur']} ; repli : {repli['erreur']}"
            return repli
        # 2. À défaut : Transmission WA Universelle Liluvine
        if liluvine_configure():
            return await _envoyer_liluvine(msisdn, texte, source_txt, media_prepare)
        # 3. Aucun canal WhatsApp utilisable
        return _resultat(False, None, erreur="WhatsApp non configuré (ni WABA ni Transmission universelle)")
    except Exception as exc:  # noqa: BLE001 — filet de sécurité : jamais d'exception chez l'appelant
        logger.exception("Envoi WhatsApp : erreur inattendue (%s)", type(exc).__name__)
        return _resultat(False, None, erreur="Erreur inattendue lors de l'envoi WhatsApp")


async def envoyer_code_liluvine(msisdn: str, texte: str) -> Tuple[bool, Optional[str]]:
    """Envoi d'un code de vérification (OTP) par la Transmission universelle,
    utilisé par otp_senders.send_whatsapp_code quand le WABA propre n'est pas
    configuré ou a échoué. Renvoie (ok, erreur lisible) comme otp_senders."""
    if not liluvine_configure():
        return False, "WhatsApp n'est pas encore configuré sur le serveur"
    try:
        res = await _envoyer_liluvine(_chiffres(msisdn), texte, SOURCE_DEFAUT)
    except Exception as exc:  # noqa: BLE001 — jamais d'exception chez l'appelant
        logger.warning("Liluvine (code) : erreur inattendue (%s)", type(exc).__name__)
        return False, "Envoi WhatsApp impossible pour le moment. Choisissez le SMS."
    if res["ok"]:
        return True, None
    if res.get("desinscrit"):
        return False, "Ce numéro a refusé les messages WhatsApp de beAuthentik (STOP). Choisissez le SMS."
    return False, "Envoi WhatsApp impossible. Vérifiez que ce numéro utilise WhatsApp, ou choisissez le SMS."
