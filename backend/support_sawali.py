# support_sawali.py — « Assistance SAWALI » dans l'espace membre beAuthentik (SAWALI lot 90).
#
# Demande du propriétaire (09/10/2026) : un petit pictogramme d'assistance dans l'espace membre ouvre une fenêtre
# de discussion avec le support SAWALI (support technique de la plateforme). Côté SAWALI, les messages arrivent
# dans le chat de l'équipe, espace « beAuthentik - Support », avec un numéro de requête (SUP-…).
#
# À ne pas confondre avec la page /support de beAuthentik (tickets internes avec l'équipe beAuthentik) : elle
# reste inchangée.
#
# En résumé (pour un développeur WinDev) :
#   - le NAVIGATEUR ne parle jamais directement à SAWALI : il appelle CE serveur (membre connecté), qui relaie
#     vers SAWALI une requête SIGNÉE avec la clé d'émetteur déjà utilisée pour la Transmission WhatsApp
#     (variables Render LILUVINE_WA_HMAC et LILUVINE_WA_EMETTEUR, lues par transmission_wa.py) :
#     en-têtes X-Emetteur, X-Timestamp, X-Signature = HMAC-SHA256 de « <horodatage>.<corps> » ;
#   - adresse de SAWALI : SAWALI_API_URL si elle existe, sinon déduite de LILUVINE_WA_URL, sinon
#     https://api.sawalismartsystems.com ;
#   - routes (membre connecté) :
#       GET  /api/support-sawali/etat      → pictogramme affiché ou non (clé présente)
#       POST /api/support-sawali/messages  {texte}   → message envoyé au support
#       POST /api/support-sawali/fil       {depuis}  → messages et réponses du support, état de la requête
#     SAWALI lot 93 (pictogrammes de la fenêtre, comme dans le chat SAWALI) :
#       POST /api/support-sawali/fichier     {fichier (data URL), nom, legende} → photo, document ou vidéo
#       POST /api/support-sawali/transcrire  {audio (data URL), nom}            → texte de la note vocale
#       GET  /api/support-sawali/media/{id}                                     → fichier d'un message du fil
#   - aucun secret n'est renvoyé au navigateur ; seule une identité réduite du membre est envoyée à SAWALI
#     (identifiant, nom affiché, rôle, contexte, e-mail, téléphone).
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

# Signature et clé : on réutilise EXACTEMENT celles de la Transmission WhatsApp (même protocole, même clé)
import transmission_wa
from auth import get_current_user

DELAI_FICHIER_SECONDES = 90   # SAWALI lot 93 : envoi d'un fichier, transcription d'une note vocale
DELAI_SECONDES = 15                                  # délai maximal d'un appel à SAWALI
SAWALI_PAR_DEFAUT = "https://api.sawalismartsystems.com"
EMETTEUR_DEFAUT = "beauthentik"                      # code de la plateforme dans SAWALI (pas secret)
CONTEXTE = "membre beAuthentik"                      # contexte affiché à l'équipe SAWALI

# Transport HTTP de remplacement (tests) : None en production
_transport: Optional[httpx.AsyncBaseTransport] = None


# ---------------------------------------------------------------------------
# Configuration (variables d'environnement saisies sur Render par le propriétaire)
# ---------------------------------------------------------------------------
def cle() -> str:
    """Clé HMAC de la plateforme (secrète : jamais affichée ni renvoyée)."""
    return transmission_wa.cle_hmac()


def emetteur() -> str:
    """Code de la plateforme dans SAWALI (en-tête X-Emetteur), « beauthentik » par défaut."""
    return (os.environ.get("LILUVINE_WA_EMETTEUR") or "").strip() or EMETTEUR_DEFAUT


def url_sawali() -> str:
    """Adresse de SAWALI : SAWALI_API_URL, sinon schéma + hôte de LILUVINE_WA_URL, sinon l'adresse par défaut."""
    direct = (os.environ.get("SAWALI_API_URL") or "").strip().rstrip("/")
    if direct:
        return direct
    lu = urlparse((os.environ.get("LILUVINE_WA_URL") or "").strip())
    if lu.scheme and lu.netloc:
        return f"{lu.scheme}://{lu.netloc}"
    return SAWALI_PAR_DEFAUT


def configure() -> bool:
    """Vrai si la clé est saisie (sinon le pictogramme reste caché)."""
    return bool(cle())


def signer(secret: str, horodatage: str, corps: str) -> str:
    """hex(HMAC-SHA256(clé, "<horodatage>.<corps>")) — même règle que SAWALI (cf. transmission_wa.signer)."""
    return transmission_wa.signer(secret, horodatage, corps)


# ---------------------------------------------------------------------------
# Identité du membre envoyée à SAWALI : le strict nécessaire, rien de plus personnel
# (ni date de naissance, ni photos, ni ville, ni bio…)
# ---------------------------------------------------------------------------
def identite(user: Dict[str, Any]) -> Dict[str, str]:
    """{id, nom, role, contexte, email, telephone} à partir du document du membre connecté."""
    role = user.get("role") or "user"
    return {
        "id": str(user.get("id") or ""),
        "nom": str(user.get("full_name") or "Membre"),
        "role": str(getattr(role, "value", role)),
        "contexte": CONTEXTE,
        "email": str(user.get("email") or ""),
        "telephone": str(user.get("phone") or ""),
    }


# ---------------------------------------------------------------------------
# Appel signé vers SAWALI
# ---------------------------------------------------------------------------
async def appeler_sawali(chemin: str, corps: Dict[str, Any], delai: float = DELAI_SECONDES) -> Dict[str, Any]:
    """POST signé vers SAWALI ; renvoie le JSON ou lève une HTTPException lisible pour le membre."""
    if not configure():
        raise HTTPException(status_code=503, detail="Assistance SAWALI non configurée sur cette plateforme")
    # Corps sérialisé UNE fois : c'est exactement ce texte qui est signé puis envoyé
    brut = json.dumps(corps, ensure_ascii=False)
    ts = str(int(time.time()))
    entetes = {"Content-Type": "application/json", "X-Emetteur": emetteur(), "X-Timestamp": ts,
               "X-Signature": signer(cle(), ts, brut)}
    try:
        async with httpx.AsyncClient(timeout=delai, transport=_transport) as client:
            r = await client.post(f"{url_sawali()}/api{chemin}", content=brut.encode("utf-8"), headers=entetes)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Assistance SAWALI injoignable : réessayez dans un instant")
    # Erreurs de SAWALI traduites en messages clairs (jamais la clé ni la réponse brute)
    if r.status_code == 403:
        raise HTTPException(status_code=503, detail="Assistance SAWALI pas encore activée pour cette plateforme")
    if r.status_code in (404, 413, 415, 422):
        # SAWALI lot 93 : fichier refusé (type, taille, illisible) ou introuvable → message de SAWALI transmis tel quel
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        raise HTTPException(status_code=r.status_code, detail=detail if isinstance(detail, str) else "Demande refusée par le support SAWALI")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail="L'assistance SAWALI a refusé la demande")
    try:
        return r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Réponse illisible de l'assistance SAWALI")


# ---------------------------------------------------------------------------
# Routes (membre connecté)
# ---------------------------------------------------------------------------
class MessageEntree(BaseModel):
    texte: str = Field(..., min_length=1, max_length=2000)


class FichierEntree(BaseModel):
    """SAWALI lot 93 : photo, document ou vidéo (data URL base64, 15 Mo au plus une fois décodé)."""
    fichier: str = Field(..., min_length=10, max_length=21_000_000)
    nom: str = Field("", max_length=200)
    legende: str = Field("", max_length=500)


class AudioEntree(BaseModel):
    """SAWALI lot 93 : note vocale enregistrée par le navigateur (data URL base64)."""
    audio: str = Field(..., min_length=10, max_length=35_000_000)
    nom: str = Field("note.webm", max_length=200)


class FilEntree(BaseModel):
    depuis: Optional[str] = Field(None, max_length=40)
    marquer_lu: bool = True   # faux : simple vérification des non-lus (fenêtre fermée), rien n'est marqué lu


def creer_router(utilisateur_courant: Callable,
                 identite_de: Callable[[Dict[str, Any]], Dict[str, str]]) -> APIRouter:
    """Routeur /support-sawali. `identite_de(user)` → {id, nom, role, contexte, email, telephone}."""
    router = APIRouter(prefix="/support-sawali", tags=["Assistance SAWALI"])

    @router.get("/etat")
    async def etat(u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Pictogramme affiché seulement si la plateforme est reliée à SAWALI."""
        return {"actif": configure()}

    @router.post("/messages")
    async def envoyer(entree: MessageEntree, u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Message du membre vers le support SAWALI."""
        texte = entree.texte.strip()
        if not texte:
            raise HTTPException(status_code=422, detail="Message vide")
        return await appeler_sawali("/support-plateforme/messages", {"utilisateur": identite_de(u), "texte": texte})

    @router.post("/fil")
    async def fil(entree: FilEntree, u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Messages du membre et réponses du support (depuis une date), état de sa requête."""
        corps: Dict[str, Any] = {"utilisateur": identite_de(u), "marquer_lu": entree.marquer_lu}
        if entree.depuis:
            corps["depuis"] = entree.depuis
        return await appeler_sawali("/support-plateforme/fil", corps)

    # --- SAWALI lot 93 : pictogrammes de la fenêtre (photo, trombone, note vocale) ---
    @router.post("/fichier")
    async def fichier(entree: FichierEntree, u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Photo, document ou vidéo envoyé au support (SAWALI vérifie le type et la taille)."""
        return await appeler_sawali("/support-plateforme/fichier", {
            "utilisateur": identite_de(u), "fichier": entree.fichier, "nom": entree.nom, "legende": entree.legende.strip()},
            delai=DELAI_FICHIER_SECONDES)

    @router.post("/transcrire")
    async def transcrire(entree: AudioEntree, u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Note vocale → texte, placé dans la zone de saisie (l'utilisateur le relit avant d'envoyer)."""
        return await appeler_sawali("/support-plateforme/transcrire", {
            "utilisateur": identite_de(u), "audio": entree.audio, "nom": entree.nom}, delai=DELAI_FICHIER_SECONDES)

    @router.get("/media/{message_id}")
    async def media(message_id: str, u: Dict[str, Any] = Depends(utilisateur_courant)):
        """Fichier d'un message du fil (le sien ou une réponse du support), servi au navigateur."""
        r = await appeler_sawali("/support-plateforme/media", {"utilisateur": identite_de(u), "message_id": message_id[:80]},
                                 delai=DELAI_FICHIER_SECONDES)
        try:
            contenu = base64.b64decode(r.get("contenu") or "")
        except ValueError:
            raise HTTPException(status_code=502, detail="Fichier illisible")
        return Response(content=contenu, media_type=r.get("type") or "application/octet-stream",
                        headers={"Cache-Control": "private, max-age=86400"})

    return router


# Routeur branché sous /api dans server.py (membre connecté : get_current_user)
router = creer_router(get_current_user, identite)
