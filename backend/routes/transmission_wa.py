"""Transmission WhatsApp — routes de contrôle (administrateur principal uniquement).

  - GET  /api/admin/transmission-wa/etat : quels canaux WhatsApp sont configurés
        {"waba_configure": bool, "liluvine_configure": bool, "emetteur": "beauthentik"}
        (jamais la clé HMAC ni le jeton WABA) ;
  - POST /api/admin/transmission-wa/test {"numero": "+226…"} : envoie le message
        « Test de transmission WhatsApp depuis beAuthentik » par le canal choisi
        automatiquement (WABA propre, sinon Transmission WA Universelle Liluvine).

  - GET  /api/admin/transmission-wa/retours : les 100 derniers retours reçus de
        SAWALI (statuts, réponses des clients, désinscriptions), du plus récent
        au plus ancien.

Réservées au rôle « admin » (les modérateurs n'y ont pas accès), comme les autres
réglages de la plateforme.

Route PUBLIQUE (appelée par SAWALI, protocole v3, section 2) :
  - POST /api/webhooks/liluvine-retour : retours signés avec la MÊME clé
        LILUVINE_WA_HMAC (en-têtes X-Emetteur: sawali, X-Timestamp, X-Signature).
        Signature fausse ou horodatage hors ±5 min → 401 ; clé absente → 503.
        Idempotente : un même retour reçu deux fois n'est stocké qu'une fois
        (collection `liluvine_retours`, clé unique `cle`).
        Une RÉPONSE d'un client est signalée aux administrateurs par e-mail
        (jamais par WhatsApp, pour ne pas créer de boucle).
"""
from __future__ import annotations

import hmac
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import transmission_wa as service
from activity import current_ip, log_activity
from auth import get_current_super_admin
from db import db

logger = logging.getLogger("transmission_wa")

router = APIRouter(prefix="/admin/transmission-wa", tags=["Transmission WhatsApp (administrateur)"])
# Routeur public des retours de SAWALI (sans session : protégé par la signature HMAC)
public = APIRouter(prefix="/webhooks", tags=["Transmission WhatsApp (retours SAWALI)"])

# Fenêtre de validité de l'horodatage d'un retour (secondes) : ±5 minutes
FENETRE_SECONDES = 300
# Types de retour prévus par le protocole v3
TYPES_RETOUR = ("statut", "reponse", "desinscription")

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


@router.get("/retours")
async def retours(_adm: dict = Depends(get_current_super_admin)):
    """Les 100 derniers retours de SAWALI, du plus récent au plus ancien."""
    curseur = db.liluvine_retours.find({}, {"_id": 0}).sort("recu_le", -1).limit(100)
    return {"retours": await curseur.to_list(100)}


# ---------------------------------------------------------------------------
# Retours de SAWALI (protocole v3, section 2)
# ---------------------------------------------------------------------------

def _cle_idempotence(donnees: dict) -> str:
    """Clé unique d'un retour : un même retour reçu deux fois a la même clé.
      - statut         : id d'origine (ou message_id) + statut (sent, delivered…) ;
      - reponse        : numéro + date (+ id d'origine) ;
      - desinscription : numéro + date."""
    type_retour = donnees["type"]
    if type_retour == "statut":
        ref = donnees.get("id") or donnees.get("message_id") or ""
        return f"statut:{ref}:{donnees.get('statut') or ''}"
    if type_retour == "reponse":
        return f"reponse:{donnees.get('id_origine') or ''}:{donnees.get('de') or ''}:{donnees.get('date') or ''}"
    return f"desinscription:{donnees.get('de') or ''}:{donnees.get('date') or ''}"


async def _signaler_reponse(document: dict) -> None:
    """Signale la réponse d'un client aux administrateurs par e-mail (canal
    interne le plus simple ; JAMAIS de WhatsApp, pour éviter toute boucle).
    Exécuté après la réponse 200 envoyée à SAWALI ; une erreur est sans effet."""
    try:
        import envoi_email
        texte = document.get("texte") or "(sans texte)"
        corps = (f"Un destinataire a répondu à un message WhatsApp de beAuthentik "
                 f"(Transmission WA Universelle Liluvine).\n\n"
                 f"Numéro : {document.get('numero') or '?'}\n"
                 f"Date : {document.get('date') or document.get('recu_le')}\n"
                 f"Message d'origine : {document.get('id_origine') or '?'}\n\n"
                 f"Réponse :\n{texte[:2000]}\n")
        if document.get("media"):
            corps += "\n(La réponse contient un fichier : voir la liste des retours dans l'administration.)\n"
        await envoi_email.envoyer_aux_administrateurs("beAuthentik — réponse WhatsApp d'un client", corps,
                                                      "liluvine_reponse")
    except Exception as exc:  # noqa: BLE001 — le signalement ne doit jamais casser le retour
        logger.warning("Retour Liluvine : signalement aux administrateurs impossible (%s)", type(exc).__name__)


@public.post("/liluvine-retour", include_in_schema=False)
async def liluvine_retour(request: Request, taches: BackgroundTasks):
    """Reçoit un retour signé de SAWALI (statut, réponse, désinscription)."""
    cle = service.cle_hmac()
    # Sans clé, impossible de vérifier quoi que ce soit : service non configuré
    if not cle:
        raise HTTPException(status_code=503, detail="Transmission universelle non configurée")
    corps_brut = await request.body()
    horodatage = (request.headers.get("X-Timestamp") or "").strip()
    signature = (request.headers.get("X-Signature") or "").strip().lower()
    # 1. Fenêtre de ±5 minutes autour de l'heure du serveur (rejeu impossible au-delà)
    try:
        ecart = abs(time.time() - int(float(horodatage)))
    except ValueError:
        raise HTTPException(status_code=401, detail="Horodatage invalide")
    if ecart > FENETRE_SECONDES:
        raise HTTPException(status_code=401, detail="Horodatage hors délai")
    # 2. Signature HMAC sur le corps EXACT reçu, comparée en temps constant
    attendu = service.signer(cle, horodatage, corps_brut)
    if not signature or not hmac.compare_digest(attendu, signature):
        raise HTTPException(status_code=401, detail="Signature invalide")
    # 3. Lecture du contenu
    try:
        donnees = json.loads(corps_brut.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="Corps JSON invalide")
    if not isinstance(donnees, dict) or donnees.get("type") not in TYPES_RETOUR:
        raise HTTPException(status_code=422, detail="Type de retour inconnu")
    type_retour = donnees["type"]
    maintenant = datetime.now(timezone.utc).isoformat()
    # Document stocké (forme minimale du protocole) ; le numéro est « de » pour
    # une réponse / désinscription, ou retrouvé dans le journal pour un statut
    document = {
        "cle": _cle_idempotence(donnees),
        "type": type_retour,
        "id_origine": donnees.get("id") if type_retour == "statut" else donnees.get("id_origine"),
        "message_id": donnees.get("message_id"),
        "numero": donnees.get("de"),
        "statut": donnees.get("statut") if type_retour == "statut" else (
            "desinscrit" if type_retour == "desinscription" else "reponse"),
        "erreur": donnees.get("erreur"),
        "texte": (str(donnees.get("texte"))[:4096] if donnees.get("texte") is not None else None),
        "media": donnees.get("media") if isinstance(donnees.get("media"), dict) else None,
        "date": donnees.get("date") or maintenant,
        "recu_le": maintenant,
    }
    # 4. Idempotence : insertion seulement si la clé n'existe pas encore
    resultat = await db.liluvine_retours.update_one({"cle": document["cle"]}, {"$setOnInsert": document},
                                                    upsert=True)
    if resultat.upserted_id is None:
        return {"ok": True, "doublon": True}
    # 5. Statut : mise à jour de l'envoi d'origine dans le journal des envois
    if type_retour == "statut":
        filtre = {"id": donnees["id"]} if donnees.get("id") else {"message_id": donnees.get("message_id")}
        if filtre.get("id") or filtre.get("message_id"):
            envoi = await db.liluvine_envois.find_one_and_update(
                filtre, {"$set": {"statut": donnees.get("statut"), "erreur": donnees.get("erreur"),
                                  "statut_le": maintenant}}, projection={"_id": 0, "numero": 1})
            if envoi and envoi.get("numero"):
                await db.liluvine_retours.update_one({"cle": document["cle"]}, {"$set": {"numero": envoi["numero"]}})
    # 6. Réponse d'un client : signalée aux administrateurs APRÈS la réponse 200
    if type_retour == "reponse":
        taches.add_task(_signaler_reponse, document)
    return {"ok": True, "doublon": False}
