"""Paramètres de la plateforme réglés par l'administrateur principal (rôle « admin ») :
abonnements (grâce), sessions, inactivité, cycle de vie, frais de réouverture.

Stockage : document unique `maf_parametres_plateforme` (_id « abonnements_sessions »).
Les valeurs absentes prennent les valeurs par défaut ci-dessous. Lecture mise en
cache quelques secondes (les paramètres sont lus à chaque requête authentifiée).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from db import db

ID_DOC = "abonnements_sessions"

# Valeurs par défaut (spécification validée par le propriétaire le 02/10/2026)
DEFAUTS: dict[str, Any] = {
    "grace_jours_defaut": 3,          # A : jours de grâce après l'échéance impayée
    "sessions_max": 5,                # B : sessions simultanées par compte
    "inactivite_secondes": 0,         # déconnexion après inactivité (0 = désactivée)
    "cycle_actif": True,              # C : cycle de vie automatique du non-renouvellement
    "cycle_simulation": False,        # C : mode simulation (liste sans rien faire)
    "conservation_archives_jours": 365,  # C : durée de conservation des archives de membres
    "frais_reouverture_montant": 0,   # C : frais de réouverture (réouverture manuelle seulement)
    "frais_reouverture_devise": "XOF",
}

# Bornes de chaque réglage
BORNES = {
    "grace_jours_defaut": (0, 30),
    "sessions_max": (1, 20),
    "conservation_archives_jours": (30, 3650),
    "frais_reouverture_montant": (0, 10_000_000),
}

DUREE_CACHE = 5.0
_cache: dict = {"lu_a": 0.0, "doc": None}


def vider_cache() -> None:
    _cache.update(lu_a=0.0, doc=None)


async def lire(cache: bool = True) -> dict:
    """Paramètres complets (valeurs par défaut pour les réglages jamais modifiés)."""
    if cache and _cache["doc"] is not None and time.monotonic() - _cache["lu_a"] < DUREE_CACHE:
        return _cache["doc"]
    doc = await db.parametres_plateforme.find_one({"_id": ID_DOC}) or {}
    valeurs = {**DEFAUTS, **{k: v for k, v in doc.items() if k in DEFAUTS}}
    for k in ("cycle_debut_le", "modifie_le", "modifie_par"):
        if doc.get(k):
            valeurs[k] = doc[k]
    _cache.update(lu_a=time.monotonic(), doc=valeurs)
    return valeurs


def _valider(cle: str, valeur: Any) -> Any:
    if cle in ("cycle_actif", "cycle_simulation"):
        return bool(valeur)
    if cle == "frais_reouverture_devise":
        devise = str(valeur or "").strip().upper()
        if not (2 <= len(devise) <= 5 and devise.isalpha()):
            raise HTTPException(400, "Devise invalide (ex. XOF, EUR)")
        return devise
    if cle == "inactivite_secondes":
        import inactivite
        return inactivite.valider(valeur)
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"Valeur invalide pour {cle}") from exc
    mini, maxi = BORNES[cle]
    if not mini <= nombre <= maxi:
        raise HTTPException(400, f"{cle} : valeur attendue entre {mini} et {maxi}")
    return nombre


async def modifier(changements: dict, par: str) -> dict:
    """Enregistre les réglages fournis (les autres ne changent pas)."""
    a_ecrire = {k: _valider(k, v) for k, v in changements.items() if k in DEFAUTS and v is not None}
    if not a_ecrire:
        return await lire(cache=False)
    a_ecrire.update(modifie_le=datetime.now(timezone.utc).isoformat(), modifie_par=par)
    await db.parametres_plateforme.update_one({"_id": ID_DOC}, {"$set": a_ecrire}, upsert=True)
    vider_cache()
    try:  # les délais d'inactivité sont mis en cache à part
        import inactivite
        inactivite.vider_cache()
    except ImportError:  # pragma: no cover
        pass
    return await lire(cache=False)


async def marquer(champs: dict) -> None:
    """Écriture interne (ex. date de première exécution du cycle de vie)."""
    await db.parametres_plateforme.update_one({"_id": ID_DOC}, {"$set": champs}, upsert=True)
    vider_cache()
