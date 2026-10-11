# signal_connexions_sawali.py — Connexions et visites signalées à SAWALI (lot 71, SAWALI lot 109).
#
# Demande du propriétaire (11/10/2026) : recevoir un WhatsApp (envoyé par SAWALI) à chaque connexion sur
# beAuthentik, et quand un visiteur non connecté arrive sur le site.
#
# En résumé (pour un développeur WinDev) :
#   - beAuthentik envoie à SAWALI une requête SIGNÉE :
#       POST <SAWALI>/api/webhook/plateforme-connexion
#     en-têtes X-Emetteur, X-Timestamp, X-Signature = HMAC-SHA256(clé, "<horodatage>.<corps brut>") en hexadécimal,
#     c'est-à-dire EXACTEMENT la signature déjà utilisée pour la Transmission WhatsApp et l'Assistance SAWALI ;
#   - clé, code émetteur et adresse de SAWALI : variables Render DÉJÀ saisies (aucune nouvelle variable) :
#       LILUVINE_WA_HMAC     → clé (secrète, jamais affichée ni envoyée dans le corps) ;
#       LILUVINE_WA_EMETTEUR → code émetteur (« beauthentik » par défaut) ;
#       SAWALI_API_URL, sinon hôte de LILUVINE_WA_URL, sinon https://api.sawalismartsystems.com ;
#   - adresse publique du site (url_site) : première origine de FRONTEND_ORIGIN (https://beauthentik.net) ;
#   - deux types de signal :
#       « connexion » : à CHAQUE ouverture de session (mot de passe, inscription, TikTok…) — branché dans
#                       sessions_comptes.ouvrir(), passage obligé de tout jeton de connexion ;
#       « visite »    : visiteur non connecté, via la route publique POST /api/presence/visite
#                       (au plus 1 signal / 30 min par visiteur ou par adresse IP, robots ignorés) ;
#   - l'envoi se fait EN ARRIÈRE-PLAN (tâche asyncio), délai réseau 5 s, ne lève JAMAIS d'exception et ne
#     ralentit jamais la connexion ; rien n'est envoyé si la clé n'est pas saisie ;
#   - SAWALI gère l'anti-répétition, les robots résiduels et le plafond des alertes WhatsApp.
#   - Désactivable sans redéploiement du code : variable SIGNAL_CONNEXIONS_SAWALI=0.
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

# Signature, clé et adresse : on réutilise EXACTEMENT celles déjà en service (Transmission WA, Assistance SAWALI)
import support_sawali
import transmission_wa
from activity import current_ip, ip_from_headers
from config import get_settings

logger = logging.getLogger("beauthentik.signal_connexions")

CHEMIN = "/api/webhook/plateforme-connexion"   # route de SAWALI (lot 109)
DELAI_SECONDES = 5.0                           # délai réseau maximal d'un signal
INTERVALLE_VISITE = 30 * 60                    # une visite signalée au plus toutes les 30 min (visiteur ou IP)
MAX_MEMOIRE_VISITES = 5000                     # taille maximale du cache mémoire des visites

# Transport HTTP de remplacement (tests : httpx.MockTransport) ; None en production
_transport: Optional[httpx.AsyncBaseTransport] = None

# Tâches en cours : on garde une référence pour qu'asyncio ne les détruise pas avant la fin
_taches: set = set()

# Cache mémoire des visites déjà signalées : {"v:<visiteur>" ou "ip:<adresse>": horodatage}
_visites: Dict[str, float] = {}

# Robots évidents (moteurs de recherche, aperçus de liens, outils en ligne de commande, surveillance…)
_ROBOTS = re.compile(
    r"bot|crawl|spider|slurp|mediapartners|facebookexternalhit|facebot|embedly|preview|whatsapp|telegram|"
    r"curl|wget|python-requests|python-httpx|aiohttp|okhttp|go-http-client|java/|libwww|headless|"
    r"lighthouse|pagespeed|monitor|uptime|pingdom|statuscake|render/health",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Configuration (variables d'environnement saisies sur Render par le propriétaire)
# ---------------------------------------------------------------------------
def actif() -> bool:
    """Vrai si la clé SAWALI est saisie ET que le signal n'est pas désactivé (SIGNAL_CONNEXIONS_SAWALI=0)."""
    interrupteur = (os.environ.get("SIGNAL_CONNEXIONS_SAWALI") or "1").strip().lower()
    if interrupteur in ("0", "false", "non", "no", "off"):
        return False
    return bool(transmission_wa.cle_hmac())


def url_signal() -> str:
    """Adresse complète de la route SAWALI (même hôte que l'Assistance SAWALI)."""
    return f"{support_sawali.url_sawali()}{CHEMIN}"


def url_site() -> str:
    """Adresse publique du site beAuthentik = première origine de FRONTEND_ORIGIN."""
    try:
        return get_settings().public_site_url
    except Exception:  # noqa: BLE001 — jamais bloquant
        return "https://beauthentik.net"


# ---------------------------------------------------------------------------
# Construction du corps (fonctions PURES, faciles à tester)
# ---------------------------------------------------------------------------
def role_lisible(role: Any) -> str:
    """Rôle tel qu'attendu par SAWALI : « membre », « admin », « moderateur »…"""
    valeur = str(getattr(role, "value", role) or "user")
    return {"user": "membre", "moderator": "moderateur"}.get(valeur, valeur)


def telephone_chiffres(numero: Any) -> Optional[str]:
    """Numéro réduit à ses chiffres avec indicatif (ex. « 22670000000 »), None si absent."""
    if not numero:
        return None
    try:
        return transmission_wa._chiffres(str(numero)) or None  # noqa: SLF001 — même règle que la Transmission WA
    except Exception:  # noqa: BLE001
        return re.sub(r"\D", "", str(numero)) or None


def corps_signal(type_signal: str, *, ip: Optional[str], agent: Optional[str],
                 utilisateur: Optional[str] = None, telephone: Optional[str] = None,
                 role: Optional[str] = None, visiteur: Optional[str] = None,
                 page: Optional[str] = None) -> Dict[str, Any]:
    """Corps JSON attendu par SAWALI. Aucun secret, aucun mot de passe, aucune donnée de profil."""
    return {
        "type": type_signal,                                   # « connexion » ou « visite »
        "le": datetime.now(timezone.utc).isoformat(),          # date et heure UTC (ISO 8601)
        "ip": ip or "",
        "utilisateur": utilisateur,
        "telephone": telephone,
        "role": role,
        "visiteur": visiteur,
        "url_site": url_site(),
        "page": page,
        "agent": (agent or "")[:300],
    }


def est_robot(agent: Optional[str]) -> bool:
    """Vrai pour un navigateur sans user-agent ou un robot évident."""
    return not (agent or "").strip() or bool(_ROBOTS.search(agent or ""))


# ---------------------------------------------------------------------------
# Envoi signé (jamais d'exception)
# ---------------------------------------------------------------------------
async def envoyer(corps: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """POST signé vers SAWALI. Renvoie la réponse JSON ({ok, alerte, raison}) ou None en cas d'échec.
    Ne lève JAMAIS d'exception (SAWALI injoignable, clé absente, réponse illisible…)."""
    try:
        if not actif():
            return None
        # Corps sérialisé UNE fois : c'est exactement ce texte qui est signé puis envoyé
        brut = json.dumps(corps, ensure_ascii=False)
        ts = str(int(time.time()))
        entetes = {"Content-Type": "application/json", "X-Emetteur": support_sawali.emetteur(),
                   "X-Timestamp": ts, "X-Signature": transmission_wa.signer(transmission_wa.cle_hmac(), ts, brut)}
        async with httpx.AsyncClient(timeout=DELAI_SECONDES, transport=_transport) as client:
            r = await client.post(url_signal(), content=brut.encode("utf-8"), headers=entetes)
        if r.status_code >= 400:
            logger.info("Signal %s refusé par SAWALI (HTTP %s)", corps.get("type"), r.status_code)
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001 — jamais bloquant, jamais la clé dans le journal
        logger.debug("Signal %s non transmis à SAWALI : %s", corps.get("type"), type(exc).__name__)
        return None


def _lancer(coro) -> bool:
    """Lance la coroutine en arrière-plan (sans l'attendre). Faux si impossible (aucune boucle active)."""
    try:
        tache = asyncio.get_running_loop().create_task(coro)
    except Exception:  # noqa: BLE001 — hors boucle asyncio : on abandonne proprement
        coro.close()
        return False
    _taches.add(tache)
    tache.add_done_callback(_taches.discard)
    return True


# ---------------------------------------------------------------------------
# « connexion » : appelé par sessions_comptes.ouvrir() à chaque session ouverte
# ---------------------------------------------------------------------------
async def _signal_connexion(user_id: str, ip: Optional[str], agent: Optional[str]) -> None:
    """Lit le strict nécessaire du compte (nom, téléphone, rôle) puis envoie le signal « connexion »."""
    try:
        from db import db  # import différé : base lue seulement si le signal est actif
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "full_name": 1, "phone": 1, "role": 1}) or {}
        await envoyer(corps_signal(
            "connexion", ip=ip, agent=agent,
            utilisateur=user.get("full_name") or None,
            telephone=telephone_chiffres(user.get("phone")),
            role=role_lisible(user.get("role")),
        ))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Signal de connexion non transmis : %s", type(exc).__name__)


def signaler_connexion(user_id: str, ip: Optional[str] = None, user_agent: Optional[str] = None) -> bool:
    """Programme le signal « connexion » en arrière-plan. Ne bloque pas, ne lève jamais d'exception.
    Renvoie vrai si un envoi a été programmé."""
    try:
        if not actif() or not user_id:
            return False
        return _lancer(_signal_connexion(user_id, ip or current_ip(), user_agent))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# « visite » : visiteur non connecté (route publique POST /api/presence/visite)
# ---------------------------------------------------------------------------
def visite_a_signaler(visiteur: Optional[str], ip: Optional[str], maintenant: Optional[float] = None) -> bool:
    """Limite : 1 signal / 30 min par visiteur OU par adresse IP (cache mémoire du serveur).
    Vrai si la visite doit être signalée (et la mémorise), faux si déjà signalée récemment."""
    maintenant = time.time() if maintenant is None else maintenant
    cles = [c for c in (f"v:{visiteur}" if visiteur else None, f"ip:{ip}" if ip else None) if c]
    if any(maintenant - _visites.get(c, 0) < INTERVALLE_VISITE for c in cles):
        return False
    # Ménage : on oublie les entrées périmées quand le cache devient trop gros
    if len(_visites) > MAX_MEMOIRE_VISITES:
        for c in [c for c, t in _visites.items() if maintenant - t >= INTERVALLE_VISITE]:
            _visites.pop(c, None)
        if len(_visites) > MAX_MEMOIRE_VISITES:
            _visites.clear()
    for c in cles:
        _visites[c] = maintenant
    return True


class VisiteEntree(BaseModel):
    """Corps envoyé par le navigateur : identifiant anonyme aléatoire et page d'arrivée."""
    visiteur: Optional[str] = Field(None, max_length=80)
    page: Optional[str] = Field(None, max_length=300)


public = APIRouter(prefix="/presence", tags=["Signal SAWALI (connexions et visites)"])


@public.post("/visite")
async def visite(entree: VisiteEntree, request: Request):
    """Visiteur non connecté arrivé sur le site. Réponse immédiate : le signal part en arrière-plan.
    Ignoré si SAWALI n'est pas configuré, si la requête porte un jeton (membre connecté), pour un robot
    évident ou si ce visiteur / cette IP a déjà été signalé il y a moins de 30 minutes."""
    try:
        agent = request.headers.get("user-agent")
        ip = ip_from_headers(request.headers, request.client.host if request.client else None)
        visiteur = re.sub(r"[^A-Za-z0-9_-]", "", entree.visiteur or "")[:80] or None
        page = (entree.page or "").strip()[:300] or None
        if not actif() or request.headers.get("authorization") or est_robot(agent):
            return {"ok": True, "signale": False}
        if not visite_a_signaler(visiteur, ip):
            return {"ok": True, "signale": False}
        lance = _lancer(envoyer(corps_signal("visite", ip=ip, agent=agent, visiteur=visiteur, page=page)))
        return {"ok": True, "signale": lance}
    except Exception:  # noqa: BLE001 — une route de suivi ne doit jamais renvoyer d'erreur au visiteur
        return {"ok": True, "signale": False}
