"""Signal de présence auprès de SAWALI (règle 4 du propriétaire).

Toute plateforme déployée doit déclarer sa présence à SAWALI :
    POST https://api.sawalismartsystems.com/api/presence-logiciel
au démarrage (ici 10 s après), puis toutes les 5 minutes.

Suivi côté SAWALI : Plateformes en temps réel → « Postes Windows — versions
déployées » (poste en ligne si le dernier signal date de moins de 12 min).

Principes :
  - envoi en arrière-plan, JAMAIS bloquant : toute erreur est ignorée ;
  - aucun secret ni donnée membre dans le signal ;
  - en-tête facultatif X-Cle-Loois = variable d'environnement
    LOOIS_SUPPORT_CLE (lue à l'exécution, jamais écrite dans le code) ;
  - désactivable avec la variable d'environnement PRESENCE_SAWALI=0.

Version envoyée : la MÊME que celle affichée sur le site, lue dans la source
unique frontend/src/version.js par version_plateforme.py (déjà utilisé par
GET /api/version). À défaut (fichier illisible), hash court du commit.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
from datetime import datetime, timezone
from typing import Optional

import httpx

import version_plateforme

logger = logging.getLogger("presence_sawali")

# Adresse du service de présence de SAWALI
URL_PRESENCE = "https://api.sawalismartsystems.com/api/presence-logiciel"
# Nom de l'application tel qu'il apparaît dans SAWALI
APPLICATION = "beAuthentik"
# Domaine public de beAuthentik (cf. FRONTEND_ORIGIN dans config.py)
SITE = "beauthentik.net"
# Délai avant le premier envoi, puis intervalle entre deux signaux (secondes)
DELAI_PREMIER_ENVOI = 10
INTERVALLE = 5 * 60
# Délai réseau maximal d'un envoi (secondes)
DELAI_RESEAU = 10.0

# Heure de démarrage de ce processus (UTC)
DEMARRE_LE = datetime.now(timezone.utc)


def presence_active() -> bool:
    """Vrai sauf si PRESENCE_SAWALI vaut 0 / false / non / off."""
    valeur = os.environ.get("PRESENCE_SAWALI", "1").strip().lower()
    return valeur not in ("0", "false", "non", "no", "off")


def nom_machine() -> str:
    """Nom du service Render (RENDER_SERVICE_NAME), sinon nom d'hôte."""
    return os.environ.get("RENDER_SERVICE_NAME", "").strip() or socket.gethostname()


def version_deployee() -> str:
    """Version affichée sur le site (VERSION de version.js), sinon le hash
    court du commit (RENDER_GIT_COMMIT sur 7 caractères)."""
    if version_plateforme.VERSION is not None:
        return str(version_plateforme.VERSION)
    return version_plateforme.COMMIT or "dev"


def corps_signal(version: str, machine: str, deploye_le: Optional[datetime],
                 demarre_le: datetime) -> dict:
    """Fonction PURE : construit le corps JSON du signal de présence.
    Les dates sont converties en ISO UTC ; deploye_le peut être None."""
    return {
        "application": APPLICATION,
        "version": version,
        "deploye_le": deploye_le.astimezone(timezone.utc).isoformat() if deploye_le else None,
        "machine": machine,
        "utilisateur": "serveur",
        "site": SITE,
        "systeme": f"Render · Python {platform.python_version()}",
        "demarre_le": demarre_le.astimezone(timezone.utc).isoformat(),
    }


def entetes() -> dict:
    """En-têtes HTTP : X-Cle-Loois seulement si LOOIS_SUPPORT_CLE existe."""
    cle = os.environ.get("LOOIS_SUPPORT_CLE", "").strip()
    return {"X-Cle-Loois": cle} if cle else {}


async def envoyer_signal() -> None:
    """Envoie UN signal ; toute erreur (réseau, HTTP…) est ignorée."""
    try:
        # Date de déploiement du backend = démarrage relevé par
        # version_plateforme (même valeur que « déployée le » de /api/version)
        corps = corps_signal(version_deployee(), nom_machine(),
                             version_plateforme.DEMARRAGE, DEMARRE_LE)
        async with httpx.AsyncClient(timeout=DELAI_RESEAU) as client:
            await client.post(URL_PRESENCE, json=corps, headers=entetes())
    except Exception as exc:  # noqa: BLE001 — jamais bloquant
        logger.debug("Signal de présence SAWALI non envoyé : %s", exc)


async def boucle_presence() -> None:
    """Tâche de fond : premier signal 10 s après le démarrage, puis toutes
    les 5 minutes. Ne s'arrête qu'avec le serveur (ou si désactivée)."""
    if not presence_active():
        return
    await asyncio.sleep(DELAI_PREMIER_ENVOI)
    while True:
        await envoyer_signal()
        await asyncio.sleep(INTERVALLE)
