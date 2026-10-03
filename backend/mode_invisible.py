"""Mode Invisible : droits, durée de 14 jours et bonus payant.

Ce que fait le Mode Invisible (inchangé) : le membre n'apparaît plus « en ligne »
(ni « vu il y a… ») et ses visites de profils / vues de Moments ne sont pas
montrées aux autres membres (voir routes/account_extras.py, auth.py, videos.py).

Règles (demande du propriétaire, lot 45) :
  - Une activation dure 14 JOURS, puis le mode se coupe tout seul. La date de fin
    est enregistrée dans le profil (`settings.invisible_mode_expire_le`) et
    contrôlée côté serveur à CHAQUE lecture (`est_actif`) : aucune tâche de fond
    n'est nécessaire, la coupure se fait à l'heure exacte.
  - Le droit d'activer vient :
      (a) d'un BONUS acheté avec le portefeuille beAuthentik (solde en XOF,
          même mécanisme que les cadeaux payants) — l'achat active aussitôt le
          mode pour 14 jours (`mode_invisible_bonus_jusqu_au` sur le membre) ;
      (b) ou de la FORMULE d'abonnement en cours (case « Autorise le Mode
          Invisible » cochée par le super-administrateur sur la formule ;
          abonnement actif ou en période de grâce).
  - Le prix du bonus est réglé par le super-administrateur (document
    `settings` id « mode_invisible », champ `prix_bonus_xof`). Tant qu'il n'est
    pas réglé, l'achat est indisponible (message clair, rien n'est inventé).
  - Sans droit : activation refusée par le serveur (403, message en français).

Anciennes activations (avant ce lot, sans date de fin) : considérées comme
terminées — le membre doit réactiver le mode avec un droit valable.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

import abonnement_grace
from db import db

# Durée d'une activation (jours)
DUREE_JOURS = 14

# Identifiant du document de réglage dans la collection `settings`
ID_REGLAGE = "mode_invisible"

# Bornes du prix du bonus (XOF, montant entier comme partout dans beAuthentik)
PRIX_MIN, PRIX_MAX = 1, 10_000_000

# Message affiché quand le membre n'a pas le droit d'activer le mode
MESSAGE_SANS_DROIT = ("Le Mode Invisible est réservé aux membres qui ont acheté le bonus Mode Invisible "
                      "ou dont la formule d'abonnement l'inclut.")


def maintenant() -> datetime:
    """Heure courante (remplacée dans les tests pour simuler les 14 jours)."""
    return datetime.now(timezone.utc)


def _date(valeur: Optional[str]) -> Optional[datetime]:
    """Convertit une date ISO enregistrée en datetime (UTC), None si absente ou illisible."""
    if not valeur:
        return None
    try:
        d = datetime.fromisoformat(valeur)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# État du mode pour un membre (lecture pure, sans accès base)
# ---------------------------------------------------------------------------
def est_actif(user: dict) -> bool:
    """Vrai si le membre est invisible EN CE MOMENT : interrupteur allumé ET date
    de fin non atteinte. Utilisé partout où le mode a un effet (présence,
    visites, vues de Moments)."""
    reglages = user.get("settings") or {}
    if not reglages.get("invisible_mode"):
        return False
    fin = _date(reglages.get("invisible_mode_expire_le"))
    return fin is not None and maintenant() < fin


def bonus_actif(user: dict) -> bool:
    """Vrai si le bonus acheté est encore valable (14 jours après l'achat)."""
    fin = _date(user.get("mode_invisible_bonus_jusqu_au"))
    return fin is not None and maintenant() < fin


# ---------------------------------------------------------------------------
# Droits liés à la formule d'abonnement
# ---------------------------------------------------------------------------
async def formule_autorise(user_id: str) -> bool:
    """Vrai si l'abonnement en cours (actif ou en grâce) porte sur une formule
    dont la case « Autorise le Mode Invisible » est cochée."""
    etat = await abonnement_grace.etat(user_id)
    if etat.get("statut") not in ("actif", "grace") or not etat.get("plan_id"):
        return False
    plan = await db.subscription_plans.find_one({"id": etat["plan_id"]}, {"_id": 0, "autorise_mode_invisible": 1})
    return bool((plan or {}).get("autorise_mode_invisible"))


# ---------------------------------------------------------------------------
# Prix du bonus (réglé par le super-administrateur)
# ---------------------------------------------------------------------------
async def prix_bonus() -> Optional[int]:
    """Prix du bonus en XOF, ou None tant que le super-administrateur ne l'a pas fixé."""
    doc = await db.settings.find_one({"id": ID_REGLAGE}, {"_id": 0}) or {}
    prix = doc.get("prix_bonus_xof")
    return int(prix) if prix else None


async def regler_prix(prix: Optional[int], adm: dict) -> dict:
    """Enregistre le prix du bonus (None = achat indisponible)."""
    if prix is not None and not PRIX_MIN <= int(prix) <= PRIX_MAX:
        raise HTTPException(400, f"Prix du bonus : entre {PRIX_MIN} et {PRIX_MAX:,} XOF (vide = achat indisponible)"
                            .replace(",", " "))
    await db.settings.update_one(
        {"id": ID_REGLAGE},
        {"$set": {"id": ID_REGLAGE, "prix_bonus_xof": None if prix is None else int(prix),
                  "modifie_le": maintenant().isoformat(), "modifie_par": adm.get("email") or adm.get("phone")}},
        upsert=True,
    )
    return await reglage_admin()


async def reglage_admin() -> dict:
    """Réglage affiché dans l'écran super-administrateur."""
    doc = await db.settings.find_one({"id": ID_REGLAGE}, {"_id": 0}) or {}
    return {"prix_bonus_xof": doc.get("prix_bonus_xof"), "duree_jours": DUREE_JOURS,
            "modifie_le": doc.get("modifie_le"), "modifie_par": doc.get("modifie_par")}


# ---------------------------------------------------------------------------
# Désactivation automatique et état complet pour l'interface
# ---------------------------------------------------------------------------
async def couper_si_expire(user: dict) -> dict:
    """Si l'interrupteur est encore allumé mais que la date de fin est passée (ou
    absente), on l'éteint en base. Renvoie le membre à jour (en mémoire)."""
    reglages = user.get("settings") or {}
    if reglages.get("invisible_mode") and not est_actif(user):
        await db.users.update_one({"id": user["id"]}, {"$set": {"settings.invisible_mode": False}})
        user = {**user, "settings": {**reglages, "invisible_mode": False}}
    return user


async def etat_membre(user: dict) -> dict:
    """Tout ce que la page Réglages doit savoir sur le Mode Invisible du membre."""
    reglages = user.get("settings") or {}
    prix = await prix_bonus()
    actif = est_actif(user)
    return {
        "actif": actif,
        "expire_le": reglages.get("invisible_mode_expire_le") if actif else None,
        "duree_jours": DUREE_JOURS,
        "bonus_actif": bonus_actif(user),
        "bonus_jusqu_au": user.get("mode_invisible_bonus_jusqu_au") if bonus_actif(user) else None,
        "formule_autorise": await formule_autorise(user["id"]),
        "prix_bonus_xof": prix,
        "achat_disponible": prix is not None,
        "solde_xof": int(user.get("wallet_balance_xof") or 0),
    }


async def date_fin_activation(user: dict) -> str:
    """Contrôle du droit au moment d'ACTIVER le mode, et date de fin à enregistrer.

    - mode déjà actif : on garde la date de fin en cours (pas de prolongation) ;
    - bonus valable    : fin = fin du bonus (14 jours après l'achat) ;
    - formule l'incluant : fin = maintenant + 14 jours ;
    - sinon : 403 avec un message en français."""
    if est_actif(user):
        return (user.get("settings") or {})["invisible_mode_expire_le"]
    if bonus_actif(user):
        return user["mode_invisible_bonus_jusqu_au"]
    if await formule_autorise(user["id"]):
        return (maintenant() + timedelta(days=DUREE_JOURS)).isoformat()
    raise HTTPException(403, MESSAGE_SANS_DROIT)
