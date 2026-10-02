"""Envoi des e-mails de la PLATEFORME beAuthentik (spécification « choix du service
d'envoi des e-mails », validée le 02/10/2026).

L'administrateur principal choisit le service d'envoi parmi :
  - Resend            (API HTTPS, port 443) ;
  - ZeptoMail (Zoho)  (API HTTPS, port 443 ; hôte .com, .eu ou .in) ;
  - Brevo             (API HTTPS, port 443) ;
  - SMTP              (bloqué sur les services Render GRATUITS — ports 25, 465, 587 ;
                       fonctionne avec une offre payante, sauf sur le port 25) ;
ou « Désactivé » (par défaut).

Les e-mails s'ajoutent TOUJOURS aux messages WhatsApp / SMS (envoi_messages.py),
jamais à leur place. beAuthentik n'a pas de messagerie par membre : seul le niveau
PLATEFORME existe (pas de réglage par locataire).

Stockage :
  - réglages : `maf_parametres_plateforme`, document _id « email ». Clés API et mot de
    passe SMTP gardés CHIFFRÉS (Fernet, clé dérivée de JWT_SECRET) ; jamais renvoyés
    au navigateur (seulement `a_cle` : vrai / faux) ;
  - journal des modifications : `maf_email_reglages_journal` (qui, quand, quel
    fournisseur, quels champs — jamais la clé) ;
  - journal des envois : `maf_emails_journal` (statut ENVOYE / ECHEC / NON_CONFIGURE).

Repli quand rien n'est réglé dans l'écran (aucun document « email ») : variables
d'environnement, par ordre de priorité RESEND_API_KEY + RESEND_EXPEDITEUR, puis
PLATEFORME_SMTP_* (ou SMTP_*), puis BREVO_API_KEY, puis ZEPTOMAIL_API_KEY
(+ ZEPTOMAIL_HOTE), avec EMAIL_EXPEDITEUR.

Erreurs : chaque fournisseur lève une exception « <Fournisseur> <code HTTP> : <message> »
(250 caractères au plus, jamais la clé) ; `envoyer_journalise` la capte et la note, sans
jamais bloquer l'action en cours.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Optional

import httpx

from config import get_settings
from db import db

logger = logging.getLogger(__name__)

ID_DOC = "email"
DESACTIVE = "desactive"
FOURNISSEURS = ("resend", "zeptomail", "brevo", "smtp")
NOMS = {"resend": "Resend", "zeptomail": "ZeptoMail", "brevo": "Brevo", "smtp": "SMTP", DESACTIVE: "Désactivé"}
FOURNISSEURS_A_CLE = ("resend", "zeptomail", "brevo")

RESEND_URL = "https://api.resend.com/emails"
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
ZEPTOMAIL_URL = "https://{hote}/v1.1/email"
ZEPTOMAIL_HOTES = ("api.zeptomail.com", "api.zeptomail.eu", "api.zeptomail.in")
ZEPTOMAIL_PREFIXE = "Zoho-enczapikey"
SMTP_SECURITES = ("starttls", "ssl", "aucune")
DELAI = 20  # secondes, pour chaque appel à un fournisseur

# Aide affichée dans l'écran d'administration (une ligne par fournisseur, lien d'inscription)
AIDE = {
    "resend": {"lien": "https://resend.com", "texte": "resend.com — gratuit jusqu'à 3 000 e-mails/mois (100/jour)."},
    "zeptomail": {"lien": "https://www.zoho.com/zeptomail/",
                  "texte": "zoho.com/zeptomail — 10 000 premiers offerts, puis 2,50 $ les 10 000 ; boîtes mail "
                           "possibles avec Zoho Mail."},
    "brevo": {"lien": "https://www.brevo.com", "texte": "brevo.com — gratuit jusqu'à 300/jour."},
    "smtp": {"lien": None, "texte": "Serveur SMTP de votre hébergeur de messagerie (hôte, port, utilisateur, mot de passe)."},
}
AVERTISSEMENT_SMTP = ("Bloqué sur les services Render gratuits (ports 25, 465, 587). Fonctionne seulement avec une "
                      "offre payante (Starter).")

# Transport httpx remplaçable dans les tests (httpx.MockTransport : aucun appel réseau)
_transport: Optional[httpx.AsyncBaseTransport] = None


class ErreurEnvoi(Exception):
    """Erreur d'un fournisseur, lisible par l'administrateur (jamais la clé)."""


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Chiffrement des secrets gardés en base (Fernet, clé dérivée de JWT_SECRET)
# ---------------------------------------------------------------------------
def _cle_chiffrement() -> bytes:
    """Clé Fernet dérivée de JWT_SECRET (jamais le secret lui-même)."""
    graine = ("beauthentik-secrets-email|" + get_settings().jwt_secret).encode()
    return base64.urlsafe_b64encode(hashlib.sha256(graine).digest())


def chiffrer(valeur: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_cle_chiffrement()).encrypt(valeur.encode()).decode()


def dechiffrer(valeur: Optional[str]) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    if not valeur:
        return ""
    try:
        return Fernet(_cle_chiffrement()).decrypt(valeur.encode()).decode()
    except (InvalidToken, ValueError):
        return ""  # JWT_SECRET changé : la clé est à ressaisir


# ---------------------------------------------------------------------------
# Petits nettoyages
# ---------------------------------------------------------------------------
_MOTIF_EMAIL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")


def email_valide(adresse: Optional[str]) -> bool:
    return bool(adresse) and len(adresse) <= 254 and bool(_MOTIF_EMAIL.match(adresse))


def nettoyer_nom(nom: Optional[str], defaut: str = "beAuthentik") -> str:
    """Nom affiché : sans < > ni retour à la ligne, 60 caractères au plus."""
    propre = " ".join(str(nom or "").replace("<", "").replace(">", "").split())[:60].strip()
    return propre or defaut


def _tronquer(texte: Any) -> str:
    return str(texte or "").replace("\n", " ").strip()[:250]


def _erreur_http(fournisseur: str, r: httpx.Response) -> ErreurEnvoi:
    """« <Fournisseur> <code HTTP> : <message du fournisseur> » (250 caractères au plus)."""
    try:
        corps = r.json()
    except ValueError:
        corps = None
    message = ""
    if isinstance(corps, dict):
        if fournisseur == "ZeptoMail" and isinstance(corps.get("error"), dict):
            err = corps["error"]
            details = [d.get("message") for d in err.get("details") or [] if isinstance(d, dict) and d.get("message")]
            message = " ; ".join([m for m in [err.get("message"), *details] if m])
        else:
            message = corps.get("message") or corps.get("error") or ""
    if not message:
        message = r.text
    return ErreurEnvoi(_tronquer(f"{fournisseur} {r.status_code} : {_tronquer(message)}"))


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=DELAI, transport=_transport)


# ---------------------------------------------------------------------------
# Les 4 fournisseurs (chacun lève ErreurEnvoi en cas d'échec)
# ---------------------------------------------------------------------------
async def envoyer_resend(c: dict, dest: str, sujet: str, corps: str, reponse_a: Optional[str] = None) -> None:
    charge: dict = {"from": formataddr((nettoyer_nom(c.get("nom_expediteur")), c["expediteur"])), "to": [dest],
                    "subject": sujet, "text": corps}
    if reponse_a:
        charge["reply_to"] = reponse_a
    async with _client() as client:
        r = await client.post(RESEND_URL, json=charge, headers={"Authorization": f"Bearer {c['cle']}"})
    if r.status_code >= 300:
        raise _erreur_http("Resend", r)


async def envoyer_brevo(c: dict, dest: str, sujet: str, corps: str, reponse_a: Optional[str] = None) -> None:
    charge: dict = {"sender": {"name": nettoyer_nom(c.get("nom_expediteur")), "email": c["expediteur"]},
                    "to": [{"email": dest}], "subject": sujet, "textContent": corps}
    if reponse_a:
        charge["replyTo"] = {"email": reponse_a}
    async with _client() as client:
        r = await client.post(BREVO_URL, json=charge, headers={"api-key": c["cle"], "accept": "application/json"})
    if r.status_code >= 300:
        raise _erreur_http("Brevo", r)


def entete_zeptomail(cle: str) -> str:
    """En-tête d'autorisation ZeptoMail ; le préfixe n'est jamais doublé."""
    cle = (cle or "").strip()
    if cle.lower().startswith(ZEPTOMAIL_PREFIXE.lower()):
        return cle
    return f"{ZEPTOMAIL_PREFIXE} {cle}"


async def envoyer_zeptomail(c: dict, dest: str, sujet: str, corps: str, reponse_a: Optional[str] = None) -> None:
    hote = c.get("zeptomail_hote") if c.get("zeptomail_hote") in ZEPTOMAIL_HOTES else ZEPTOMAIL_HOTES[0]
    charge: dict = {"from": {"address": c["expediteur"], "name": nettoyer_nom(c.get("nom_expediteur"))},
                    "to": [{"email_address": {"address": dest}}], "subject": sujet, "textbody": corps}
    if reponse_a:
        charge["reply_to"] = [{"address": reponse_a}]
    async with _client() as client:
        r = await client.post(ZEPTOMAIL_URL.format(hote=hote), json=charge,
                              headers={"Authorization": entete_zeptomail(c["cle"]), "accept": "application/json"})
    if r.status_code >= 300:
        raise _erreur_http("ZeptoMail", r)


def _smtp_synchrone(c: dict, dest: str, sujet: str, corps: str, reponse_a: Optional[str]) -> None:
    """Envoi SMTP (bloquant, lancé dans un thread)."""
    msg = EmailMessage()
    msg["Subject"], msg["To"] = sujet, dest
    msg["From"] = formataddr((nettoyer_nom(c.get("nom_expediteur")), c.get("expediteur") or c.get("smtp_utilisateur") or ""))
    if reponse_a:
        msg["Reply-To"] = reponse_a
    msg.set_content(corps)
    port = int(c.get("smtp_port") or 587)
    if c.get("smtp_securite") == "ssl":
        serveur = smtplib.SMTP_SSL(c["smtp_hote"], port, timeout=DELAI)
    else:
        serveur = smtplib.SMTP(c["smtp_hote"], port, timeout=DELAI)
        if c.get("smtp_securite", "starttls") == "starttls":
            serveur.starttls()
    with serveur:
        if c.get("smtp_utilisateur"):
            serveur.login(c["smtp_utilisateur"], c.get("smtp_mot_de_passe") or "")
        serveur.send_message(msg)


async def envoyer_smtp(c: dict, dest: str, sujet: str, corps: str, reponse_a: Optional[str] = None) -> None:
    try:
        await asyncio.to_thread(_smtp_synchrone, c, dest, sujet, corps, reponse_a)
    except (smtplib.SMTPException, OSError) as exc:
        # Le mot de passe n'apparaît jamais dans les messages de smtplib
        code = getattr(exc, "smtp_code", None) or "connexion"
        raise ErreurEnvoi(_tronquer(f"SMTP {code} : {exc}")) from exc


ENVOYEURS = {"resend": envoyer_resend, "brevo": envoyer_brevo, "zeptomail": envoyer_zeptomail, "smtp": envoyer_smtp}


# ---------------------------------------------------------------------------
# Réglages : écran d'administration, sinon variables d'environnement
# ---------------------------------------------------------------------------
async def lire_document() -> dict:
    return await db.parametres_plateforme.find_one({"_id": ID_DOC}) or {}


def _fournisseur_document(doc: dict) -> Optional[str]:
    """Fournisseur du document ; un ancien document sans `fournisseur` mais avec un
    serveur SMTP vaut « smtp » (compatibilité) ; None = rien de réglé dans l'écran."""
    if doc.get("fournisseur") in (*FOURNISSEURS, DESACTIVE):
        return doc["fournisseur"]
    if doc.get("smtp_hote") or doc.get("hote"):
        return "smtp"
    return None


def _config_document(doc: dict, fournisseur: str) -> dict:
    cles = doc.get("cles_chiffrees") or {}
    return {
        "fournisseur": fournisseur, "source": "administration",
        "actif": bool(doc.get("actif", True)) and fournisseur != DESACTIVE,
        "expediteur": (doc.get("expediteur") or "").strip(),
        "nom_expediteur": nettoyer_nom(doc.get("nom_expediteur")),
        "cle": dechiffrer(cles.get(fournisseur)) if fournisseur in FOURNISSEURS_A_CLE else "",
        "zeptomail_hote": doc.get("zeptomail_hote") or ZEPTOMAIL_HOTES[0],
        # anciens noms (hote, port, ssl...) acceptés pour les réglages SMTP déjà en base
        "smtp_hote": doc.get("smtp_hote") or doc.get("hote") or "",
        "smtp_port": int(doc.get("smtp_port") or doc.get("port") or 587),
        "smtp_securite": doc.get("smtp_securite") or ("ssl" if doc.get("ssl") else "starttls"),
        "smtp_utilisateur": doc.get("smtp_utilisateur") or doc.get("utilisateur") or "",
        "smtp_mot_de_passe": dechiffrer(doc.get("smtp_mot_de_passe_chiffre") or doc.get("mot_de_passe_chiffre")),
    }


def _config_environnement() -> dict:
    """Repli sur les variables d'environnement (ordre de priorité de la spécification)."""
    s = get_settings()
    base = {"source": "variables d'environnement", "actif": True, "nom_expediteur": nettoyer_nom(s.email_nom_expediteur),
            "cle": "", "zeptomail_hote": ZEPTOMAIL_HOTES[0], "smtp_hote": "", "smtp_port": 587,
            "smtp_securite": "starttls", "smtp_utilisateur": "", "smtp_mot_de_passe": ""}
    if s.resend_api_key and s.resend_expediteur:
        return {**base, "fournisseur": "resend", "cle": s.resend_api_key, "expediteur": s.resend_expediteur.strip()}
    hote = s.plateforme_smtp_hote or s.smtp_host
    if hote:
        if s.plateforme_smtp_hote:
            port, user, mdp, ssl = (s.plateforme_smtp_port, s.plateforme_smtp_utilisateur,
                                    s.plateforme_smtp_mot_de_passe, s.plateforme_smtp_ssl)
            expediteur = s.plateforme_expediteur
        else:
            port, user, mdp, ssl, expediteur = s.smtp_port, s.smtp_user, s.smtp_password, s.smtp_ssl, s.smtp_from
        return {**base, "fournisseur": "smtp", "smtp_hote": hote, "smtp_port": int(port or 587),
                "smtp_securite": "ssl" if ssl else "starttls", "smtp_utilisateur": user or "",
                "smtp_mot_de_passe": mdp or "", "expediteur": (expediteur or s.email_expediteur or user or "").strip()}
    if s.brevo_api_key and s.email_expediteur:
        return {**base, "fournisseur": "brevo", "cle": s.brevo_api_key, "expediteur": s.email_expediteur.strip()}
    if s.zeptomail_api_key and s.email_expediteur:
        hote = (s.zeptomail_hote or "").strip()
        return {**base, "fournisseur": "zeptomail", "cle": s.zeptomail_api_key, "expediteur": s.email_expediteur.strip(),
                "zeptomail_hote": hote if hote in ZEPTOMAIL_HOTES else ZEPTOMAIL_HOTES[0]}
    return {**base, "fournisseur": DESACTIVE, "actif": False, "expediteur": "", "source": "aucune"}


async def config_effective() -> dict:
    """Réglages en vigueur (avec les secrets en clair : usage INTERNE seulement)."""
    doc = await lire_document()
    fournisseur = _fournisseur_document(doc)
    if fournisseur is None:
        return _config_environnement()
    return _config_document(doc, fournisseur)


def motif_non_configure(c: dict) -> Optional[str]:
    """Pourquoi l'envoi est impossible avec ces réglages (None = prêt)."""
    if c["fournisseur"] == DESACTIVE:
        return "Envoi des e-mails désactivé"
    if not c.get("actif"):
        return f"{NOMS[c['fournisseur']]} réglé mais désactivé"
    if not email_valide(c.get("expediteur")):
        return "Adresse d'expéditeur manquante ou invalide"
    if c["fournisseur"] in FOURNISSEURS_A_CLE and not c.get("cle"):
        return f"Clé API {NOMS[c['fournisseur']]} manquante"
    if c["fournisseur"] == "smtp" and not c.get("smtp_hote"):
        return "Serveur SMTP manquant"
    return None


# ---------------------------------------------------------------------------
# Envoi
# ---------------------------------------------------------------------------
async def envoyer(dest: str, sujet: str, corps: str, reponse_a: Optional[str] = None,
                  config: Optional[dict] = None) -> str:
    """Envoie un e-mail texte. Lève ErreurEnvoi ; renvoie le fournisseur utilisé."""
    c = config or await config_effective()
    motif = motif_non_configure(c)
    if motif:
        raise ErreurEnvoi(motif)
    await ENVOYEURS[c["fournisseur"]](c, dest, sujet, corps, reponse_a)
    return c["fournisseur"]


async def envoyer_journalise(dest: Optional[str], sujet: str, corps: str, contexte: str,
                             user_id: Optional[str] = None) -> dict:
    """Envoi qui ne lève JAMAIS d'exception : renvoie {"statut", "erreur", "fournisseur"}
    (ENVOYE / ECHEC / NON_CONFIGURE) et note l'envoi dans `maf_emails_journal`."""
    resultat: dict = {"statut": "NON_CONFIGURE", "erreur": None, "fournisseur": None}
    try:
        c = await config_effective()
        resultat["fournisseur"] = c["fournisseur"]
        motif = motif_non_configure(c)
        if not email_valide(dest):
            resultat["erreur"] = "Aucune adresse e-mail valable"
        elif motif:
            resultat["erreur"] = motif
        else:
            await envoyer(dest, sujet, corps, config=c)
            resultat["statut"] = "ENVOYE"
    except Exception as exc:  # noqa: BLE001 — un e-mail en échec ne bloque jamais l'action en cours
        resultat.update(statut="ECHEC", erreur=_tronquer(exc))
    try:
        await db.emails_journal.insert_one({"id": str(uuid.uuid4()), "date": maintenant(), "contexte": contexte,
                                            "destinataire": dest, "user_id": user_id, "sujet": sujet[:200],
                                            **resultat})
    except Exception:  # noqa: BLE001
        logger.exception("Journal des e-mails indisponible")
    return resultat


async def emails_administrateurs() -> list[str]:
    """Adresses e-mail des comptes administrateurs principaux actifs."""
    adresses = []
    async for adm in db.users.find({"role": "admin", "is_active": {"$ne": False}}, {"_id": 0, "email": 1}):
        if email_valide(adm.get("email")) and adm["email"] not in adresses:
            adresses.append(adm["email"])
    return adresses


async def envoyer_aux_administrateurs(sujet: str, corps: str, contexte: str) -> int:
    """E-mail à chaque administrateur principal. Renvoie le nombre d'envois réussis."""
    reussis = 0
    for adresse in await emails_administrateurs():
        if (await envoyer_journalise(adresse, sujet, corps, contexte))["statut"] == "ENVOYE":
            reussis += 1
    return reussis


# ---------------------------------------------------------------------------
# Écran d'administration (lecture sans secrets, modification journalisée)
# ---------------------------------------------------------------------------
async def lire_public() -> dict:
    """Réglages pour le navigateur : JAMAIS de clé ni de mot de passe (seulement `a_cle`)."""
    doc = await lire_document()
    fournisseur = _fournisseur_document(doc)
    c = _config_document(doc, fournisseur or DESACTIVE)
    cles = doc.get("cles_chiffrees") or {}
    effectif = await config_effective()
    return {
        "fournisseur": fournisseur or DESACTIVE, "actif": bool(doc.get("actif", True)) if fournisseur else False,
        "expediteur": c["expediteur"], "nom_expediteur": c["nom_expediteur"],
        "a_cle": {f: bool(cles.get(f)) for f in FOURNISSEURS_A_CLE},
        "zeptomail_hote": c["zeptomail_hote"],
        "smtp_hote": c["smtp_hote"], "smtp_port": c["smtp_port"], "smtp_securite": c["smtp_securite"],
        "smtp_utilisateur": c["smtp_utilisateur"],
        "a_mot_de_passe_smtp": bool(doc.get("smtp_mot_de_passe_chiffre") or doc.get("mot_de_passe_chiffre")),
        "modifie_le": doc.get("modifie_le"), "modifie_par": doc.get("modifie_par"),
        "en_vigueur": {"fournisseur": effectif["fournisseur"], "source": effectif["source"],
                       "pret": motif_non_configure(effectif) is None, "motif": motif_non_configure(effectif)},
        "choix": [{"valeur": f, "nom": NOMS[f], **AIDE.get(f, {})} for f in (*FOURNISSEURS, DESACTIVE)],
        "zeptomail_hotes": list(ZEPTOMAIL_HOTES), "smtp_securites": list(SMTP_SECURITES),
        "avertissement_smtp": AVERTISSEMENT_SMTP,
    }


def _erreur(message: str):
    from fastapi import HTTPException
    return HTTPException(400, message)


async def modifier(changements: dict, par: str) -> dict:
    """Enregistre les réglages (champ secret vide = valeur conservée) et journalise
    la modification (qui, quand, quel fournisseur — jamais la clé)."""
    doc = await lire_document()
    a_ecrire: dict = {}
    fournisseur = changements.get("fournisseur")
    if fournisseur is not None:
        if fournisseur not in (*FOURNISSEURS, DESACTIVE):
            raise _erreur("Service d'envoi inconnu")
        a_ecrire["fournisseur"] = fournisseur
    else:
        fournisseur = _fournisseur_document(doc) or DESACTIVE
    if changements.get("actif") is not None:
        a_ecrire["actif"] = bool(changements["actif"])
    if changements.get("expediteur") is not None:
        adresse = str(changements["expediteur"]).strip()
        if adresse and not email_valide(adresse):
            raise _erreur("Adresse d'expéditeur invalide")
        a_ecrire["expediteur"] = adresse
    if changements.get("nom_expediteur") is not None:
        a_ecrire["nom_expediteur"] = nettoyer_nom(changements["nom_expediteur"])
    if changements.get("zeptomail_hote") is not None:
        if changements["zeptomail_hote"] not in ZEPTOMAIL_HOTES:
            raise _erreur("Région ZeptoMail invalide (.com, .eu ou .in)")
        a_ecrire["zeptomail_hote"] = changements["zeptomail_hote"]
    if changements.get("smtp_hote") is not None:
        a_ecrire["smtp_hote"] = str(changements["smtp_hote"]).strip()[:200]
    if changements.get("smtp_port") is not None:
        try:
            port = int(changements["smtp_port"])
        except (TypeError, ValueError) as exc:
            raise _erreur("Port SMTP invalide") from exc
        if port == 25:
            raise _erreur("Le port 25 est bloqué par Render : utilisez 465 (SSL) ou 587 (STARTTLS).")
        if not 1 <= port <= 65535:
            raise _erreur("Port SMTP invalide")
        a_ecrire["smtp_port"] = port
    if changements.get("smtp_securite") is not None:
        if changements["smtp_securite"] not in SMTP_SECURITES:
            raise _erreur("Sécurité SMTP invalide (starttls, ssl ou aucune)")
        a_ecrire["smtp_securite"] = changements["smtp_securite"]
    if changements.get("smtp_utilisateur") is not None:
        a_ecrire["smtp_utilisateur"] = str(changements["smtp_utilisateur"]).strip()[:200]
    # Secrets : champ vide = valeur conservée ; jamais écrits en clair
    secret_change = False
    cle = str(changements.get("cle_api") or "").strip()
    if cle:
        if fournisseur not in FOURNISSEURS_A_CLE:
            raise _erreur("Ce service d'envoi n'utilise pas de clé API")
        a_ecrire[f"cles_chiffrees.{fournisseur}"] = chiffrer(cle)
        secret_change = True
    mdp = str(changements.get("smtp_mot_de_passe") or "")
    if mdp:
        a_ecrire["smtp_mot_de_passe_chiffre"] = chiffrer(mdp)
        secret_change = True
    if not a_ecrire:
        return await lire_public()
    # Ancien document SMTP sans `fournisseur` : on le fixe pour ne plus dépendre de la règle de compatibilité
    if "fournisseur" not in a_ecrire and _fournisseur_document(doc) == "smtp" and not doc.get("fournisseur"):
        a_ecrire["fournisseur"] = "smtp"
    champs = sorted({k.split(".")[0] for k in a_ecrire} - {"cles_chiffrees", "smtp_mot_de_passe_chiffre"})
    a_ecrire.update(modifie_le=maintenant(), modifie_par=par)
    await db.parametres_plateforme.update_one({"_id": ID_DOC}, {"$set": a_ecrire}, upsert=True)
    await db.email_reglages_journal.insert_one({
        "id": str(uuid.uuid4()), "date": a_ecrire["modifie_le"], "par": par,
        "fournisseur": a_ecrire.get("fournisseur") or fournisseur, "champs": champs, "secret_modifie": secret_change})
    return await lire_public()


async def journal(limite: int = 30) -> dict:
    """Journal des modifications des réglages et derniers e-mails envoyés."""
    modifications = await db.email_reglages_journal.find({}, {"_id": 0}).sort("date", -1).to_list(limite)
    envois = await db.emails_journal.find({}, {"_id": 0}).sort("date", -1).to_list(limite)
    return {"modifications": modifications, "envois": envois}


async def essai(destinataire: str, par: str) -> dict:
    """« Envoyer un essai » avec les réglages ENREGISTRÉS ; renvoie le message du fournisseur."""
    if not email_valide(destinataire):
        raise _erreur("Adresse de destination invalide")
    c = await config_effective()
    sujet = "beAuthentik — e-mail d'essai"
    corps = (f"Ceci est un e-mail d'essai envoyé par beAuthentik ({NOMS[c['fournisseur']]}, réglages : {c['source']}).\n"
             f"Demandé par {par} le {maintenant()[:16].replace('T', ' ')} UTC.\n\n"
             "Si vous le recevez, l'envoi des e-mails de la plateforme fonctionne.")
    return await envoyer_journalise(destinataire, sujet, corps, "essai")
