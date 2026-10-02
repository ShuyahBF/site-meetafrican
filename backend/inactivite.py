"""Déconnexion après inactivité (durée réglable en SECONDES, 0 = désactivée).

Modèle : adLyn (backend/inactivite.py), adapté à beAuthentik où le « locataire »
est le MEMBRE lui-même :
  - plateforme (administrateur principal) : `inactivite_secondes` dans les
    paramètres de la plateforme (parametres_plateforme.py) — s'applique à tous,
    administrateur compris ;
  - membre, par l'administrateur (`users.inactivite_secondes`) : remplace la valeur
    de la plateforme pour ce compte (None = valeur de la plateforme) ;
  - membre, par lui-même (`users.inactivite_secondes_membre`) : ne peut que RÉDUIRE
    la durée fixée par l'administrateur (le « plafond »), jamais l'allonger.

Le contrôle côté serveur est fait avec celui des sessions (sessions_comptes.py) :
la dernière activité de chaque session y est notée (au plus une écriture par
minute) ; une session restée inactive plus longtemps que la durée (+ 1 minute de
marge, due à cette écriture espacée) est fermée : « Session expirée après
inactivité ». Les rafraîchissements automatiques du site (compteurs, état de la
maintenance…) portent l'en-tête « X-BA-Fond » : contrôlés, mais ils ne comptent
PAS comme une activité (sinon un onglet oublié resterait connecté indéfiniment).
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import HTTPException

MIN_SECONDES, MAX_SECONDES = 60, 86_400  # de 1 minute à 24 heures (0 = désactivée)
MARGE_SECONDES = 60  # écriture de l'activité au plus une fois par minute
ENTETE_FOND = "x-ba-fond"
MESSAGE_INACTIVITE = "Session expirée après inactivité. Reconnectez-vous."


def _maintenant() -> float:
    """Heure courante (remplacée dans les tests pour simuler l'inactivité)."""
    return time.time()


def vider_cache() -> None:
    """Rien à vider ici (les paramètres de la plateforme ont leur propre cache) ;
    gardé pour la symétrie avec adLyn."""
    import parametres_plateforme
    parametres_plateforme.vider_cache()


def valider(secondes: Optional[int], *, nul_permis: bool = False) -> Optional[int]:
    """0 (désactivée) ou entre 60 et 86 400 secondes ; None seulement si `nul_permis`."""
    if secondes is None and nul_permis:
        return None
    try:
        valeur = int(secondes) if secondes is not None else None
    except (TypeError, ValueError):
        valeur = None
    if valeur is None or not (valeur == 0 or MIN_SECONDES <= valeur <= MAX_SECONDES):
        raise HTTPException(400, f"Durée d'inactivité invalide : 0 (désactivée) ou entre {MIN_SECONDES} "
                                 f"et {MAX_SECONDES} secondes")
    return valeur


async def delai_plateforme(cache: bool = True) -> int:
    import parametres_plateforme
    return int((await parametres_plateforme.lire(cache)).get("inactivite_secondes") or 0)


def plafond_membre(user: dict, plateforme: int) -> int:
    """Durée fixée par l'administrateur pour ce compte (sinon celle de la plateforme)."""
    propre = user.get("inactivite_secondes")
    return plateforme if propre is None else int(propre)


def delai_membre(user: dict, plateforme: int) -> int:
    """Durée effective : le réglage du membre s'il est plus court que le plafond."""
    plafond = plafond_membre(user, plateforme)
    perso = user.get("inactivite_secondes_membre")
    if perso and (plafond == 0 or int(perso) < plafond):
        return int(perso)
    return plafond


def resume(user: dict, plateforme: int) -> dict:
    return {"plateforme": plateforme, "admin": user.get("inactivite_secondes"),
            "membre": user.get("inactivite_secondes_membre"), "plafond": plafond_membre(user, plateforme),
            "effective": delai_membre(user, plateforme), "min": MIN_SECONDES, "max": MAX_SECONDES}


async def delai_utilisateur(user: dict) -> int:
    return delai_membre(user, await delai_plateforme())


def avertissement(secondes: int) -> int:
    """Avertissement 60 s avant la déconnexion, ou 20 % de la durée si elle est courte."""
    return 60 if secondes >= 300 else max(5, round(secondes * 0.2))


def reglage_membre(user: dict, plateforme: int, secondes: Optional[int]) -> Optional[int]:
    """Valeur que le membre veut se fixer : il peut seulement RÉDUIRE le plafond."""
    plafond = plafond_membre(user, plateforme)
    secondes = valider(secondes, nul_permis=True)
    if secondes == 0:
        if plafond:
            raise HTTPException(400, "Vous ne pouvez pas désactiver la déconnexion fixée par l'administrateur")
        return None
    if secondes is not None and plafond and secondes > plafond:
        raise HTTPException(400, f"Vous pouvez seulement réduire la durée : {plafond} secondes au maximum")
    return secondes
