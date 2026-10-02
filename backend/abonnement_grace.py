"""Période de grâce après l'échéance impayée de l'abonnement Premium
(spécification A, validée le 02/10/2026). Le « locataire » est le MEMBRE abonné.

Modèle d'abonnement existant (inchangé) : collection `maf_subscriptions`, une
ligne par souscription, `status` = pending | active | expired | cancelled,
`expires_at` = échéance (date ISO UTC) fixée au paiement (PawaPay ou preuve de
paiement validée). L'abonnement de référence est la DERNIÈRE souscription au
statut « active » (même règle que l'ancien `has_active_subscription`). Un
renouvellement crée une nouvelle souscription (nouvelle échéance).

États calculés à chaque requête (aucune tâche de fond nécessaire, coupure à
l'heure exacte) :
  - « aucun »  : jamais abonné (membre gratuit) ;
  - « actif »  : échéance non atteinte ;
  - « grace »  : échéance dépassée depuis moins de N jours (N = délai de grâce du
                 membre, 3 par défaut, réglable de 0 à 30 par l'administrateur,
                 + 3 jours par renouvellement de la grâce) : accès Premium normal,
                 bandeau rouge « Abonnement expiré — N jour(s) de grâce restant(s) » ;
  - « expire » : grâce écoulée : les FONCTIONS PAYANTES sont coupées côté serveur.

Fonctions payantes de beAuthentik (seules réservées aux abonnés dans le code) :
le visage en clair sur les photos des AUTRES membres — découverte, recherche,
fiches profil, liste des conversations (routes/matching.py, routes/profiles.py,
routes/chat.py, via `routes.subscriptions.has_active_subscription`). Après la
grâce, ces routes renvoient de nouveau les versions floutées (« Visage flouté ·
abonnez-vous pour le voir »), à la requête suivante. Le membre garde l'usage
gratuit du site (profil, messages, Moments…) comme tout membre non abonné.

Renouvellement de la grâce par l'administrateur : « +3 jours », au plus 3 fois
par échéance impayée (compteur lié à l'échéance : il repart à zéro dès qu'un
paiement crée une nouvelle échéance). Chaque action est journalisée
(`maf_abonnements_journal` + journal d'activité).
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

import parametres_plateforme
from activity import current_ip, log_activity
from db import db

JOURS_PAR_RENOUVELLEMENT = 3
RENOUVELLEMENTS_MAX = 3
GRACE_MIN, GRACE_MAX = 0, 30


def maintenant() -> datetime:
    """Heure courante (remplacée dans les tests)."""
    return datetime.now(timezone.utc)


def _date(valeur: Optional[str]) -> Optional[datetime]:
    if not valeur:
        return None
    try:
        d = datetime.fromisoformat(valeur)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


async def souscription_de_reference(user_id: str) -> Optional[dict]:
    return await db.subscriptions.find_one({"user_id": user_id, "status": "active"}, {"_id": 0},
                                           sort=[("created_at", -1)])


def renouvellements(sub: dict) -> int:
    """Nombre de « +3 jours » accordés pour l'échéance ACTUELLE de la souscription."""
    p = sub.get("grace_prolongation") or {}
    return int(p.get("fois") or 0) if p.get("echeance") == sub.get("expires_at") else 0


async def etat(user_id: str, user: Optional[dict] = None) -> dict:
    """État de l'abonnement du membre (voir la docstring du module)."""
    sub = await souscription_de_reference(user_id)
    if not sub:
        return {"statut": "aucun"}
    echeance = _date(sub.get("expires_at"))
    base = {"subscription_id": sub.get("id"), "plan_id": sub.get("plan_id"), "echeance": sub.get("expires_at")}
    if echeance is None:
        return {**base, "statut": "actif"}
    if user is None:
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "grace_jours": 1}) or {}
    grace = user.get("grace_jours")
    if grace is None:
        grace = (await parametres_plateforme.lire()).get("grace_jours_defaut", 3)
    n = renouvellements(sub)
    fin_grace = echeance + timedelta(days=int(grace) + JOURS_PAR_RENOUVELLEMENT * n)
    a = maintenant()
    base.update({"grace_jours": int(grace), "renouvellements_grace": n, "renouvellements_max": RENOUVELLEMENTS_MAX,
                 "fin_grace": fin_grace.isoformat()})
    if a < echeance:
        return {**base, "statut": "actif"}
    if a < fin_grace:
        restant = math.ceil((fin_grace - a).total_seconds() / 86400)
        return {**base, "statut": "grace", "jours_grace_restants": max(1, restant)}
    return {**base, "statut": "expire", "jours_grace_restants": 0}


async def premium_actif(user_id: str) -> bool:
    """Accès aux fonctions payantes : abonnement actif OU en période de grâce."""
    return (await etat(user_id))["statut"] in ("actif", "grace")


async def journaliser(action: str, user_id: str, par: Optional[dict], **details) -> None:
    await db.abonnements_journal.insert_one({
        "id": str(uuid.uuid4()), "date": maintenant().isoformat(), "action": action, "user_id": user_id,
        "par": (par or {}).get("email") or (par or {}).get("phone") or "systeme", "par_id": (par or {}).get("id"),
        "details": details})
    await log_activity((par or {}).get("id"), f"Abonnement : {action}", current_ip(),
                       details={"membre": user_id, **details})


async def regler_grace(user_id: str, jours: Optional[int], adm: dict) -> dict:
    """Délai de grâce propre au membre (None = valeur de la plateforme)."""
    if jours is not None and not GRACE_MIN <= int(jours) <= GRACE_MAX:
        raise HTTPException(400, f"Délai de grâce : entre {GRACE_MIN} et {GRACE_MAX} jours")
    res = await db.users.update_one({"id": user_id}, {"$set": {"grace_jours": None if jours is None else int(jours)}})
    if not res.matched_count:
        raise HTTPException(404, "Membre introuvable")
    await journaliser("délai de grâce modifié", user_id, adm, jours=jours)
    return await etat(user_id)


async def renouveler_grace(user_id: str, adm: dict) -> dict:
    """« Renouveler la grâce (+3 j) » sur une échéance impayée, au plus 3 fois."""
    sub = await souscription_de_reference(user_id)
    actuel = await etat(user_id)
    if not sub or actuel["statut"] not in ("grace", "expire"):
        raise HTTPException(400, "Aucune échéance impayée pour ce membre : la grâce ne peut pas être renouvelée")
    n = renouvellements(sub)
    if n >= RENOUVELLEMENTS_MAX:
        raise HTTPException(400, f"La grâce a déjà été renouvelée {RENOUVELLEMENTS_MAX} fois pour cette échéance")
    await db.subscriptions.update_one({"id": sub["id"]}, {"$set": {"grace_prolongation": {
        "echeance": sub.get("expires_at"), "fois": n + 1, "dernier_le": maintenant().isoformat(),
        "par": adm.get("email") or adm.get("phone")}}})
    await journaliser("grâce renouvelée (+3 jours)", user_id, adm, fois=n + 1, echeance=sub.get("expires_at"))
    return await etat(user_id)


async def historique(user_id: str, limite: int = 30) -> list[dict]:
    return await db.abonnements_journal.find({"user_id": user_id}, {"_id": 0}).sort("date", -1).to_list(limite)
