"""Maintenance de la plateforme : déconnexion programmée de tous les utilisateurs.

L'administrateur principal (rôle « admin ») annonce une opération importante :
message + durée avant la déconnexion forcée (ex. 5 minutes) + part de cette
durée pendant laquelle l'écran est verrouillé (ex. 80 %). Trois phases
s'enchaînent, calculées UNIQUEMENT à partir de l'heure du serveur :

  1. « annonce »      : modale fermable chez tous les utilisateurs (puis bandeau)
                        — de l'annonce jusqu'au début du verrouillage ;
  2. « verrouillage » : écran verrouillé, non fermable, décompte à la seconde
                        — du début du verrouillage jusqu'à l'échéance ;
  3. « maintenance »  : à l'échéance, déconnexion forcée. Toute requête
                        authentifiée d'un utilisateur autre qu'un administrateur
                        principal reçoit 503 ; la connexion (e-mail/mot de passe
                        ou TikTok), l'inscription et le chat temps réel sont
                        refusés, jusqu'à la RÉACTIVATION par l'administrateur.

À la réactivation, l'horodatage « sessions valides après » est fixé à
l'échéance : toutes les sessions ouvertes avant restent invalides, chacun se
reconnecte. Une annonce peut être annulée avant l'échéance (personne n'est
déconnecté, aucune session n'est invalidée).

Les administrateurs principaux (rôle « admin ») ne sont JAMAIS bloqués ni
déconnectés. Les modérateurs, eux, sont traités comme les membres (ils
écrivent des données : ils ne doivent pas travailler pendant l'opération).

Le blocage passe uniquement par les sessions (auth.get_current_user, le chat
WebSocket, la connexion et l'inscription). NE SONT PAS BLOQUÉS, car ils
n'utilisent pas de session :
  - webhook PawaPay : POST /api/payments/pawapay/webhooks/deposits/{secret} ;
  - retour OAuth TikTok : GET /api/auth/tiktok/callback (+ /config, /start) ;
  - pages et données publiques : /api/health, /api/appearance,
    /api/maintenance/etat, /api/stats/visit, /api/stats/public,
    GET /api/testimonials, GET /api/profile-options, GET /api/gifts,
    GET /api/subscriptions/plans, GET /api/users/{id}/rating-summary,
    /api/files/... (stockage local) ;
  - outil VIDAL (/api/vidal/..., protégé par son propre secret) ;
  - restauration initiale et suivi des transferts (/api/plateforme/transfert/...) ;
  - tâches de fond (rapprochement PawaPay chaque minute, synchronisation
    VIDAL, floutage des médias) : elles ne passent pas par l'API. Les
    paiements Mobile Money confirmés pendant la maintenance sont donc bien
    appliqués (abonnement, portefeuille).

Stockage : document unique `maf_maintenance_plateforme` (_id « etat ») et journal
des actions dans `maf_maintenance_plateforme_journal`.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from db import db
import uuid

ID_ETAT = "etat"
# Rôle jamais bloqué (administrateur principal)
ROLE_EXEMPTE = "admin"
# Bornes et valeurs par défaut du formulaire de l'administrateur
DUREE_DEFAUT, DUREE_MIN, DUREE_MAX = 5, 1, 120  # minutes avant la déconnexion forcée
PART_VERROUILLAGE_DEFAUT = 80  # % de la durée avec écran verrouillé
MESSAGE_MAX = 1000

# Phases renvoyées au site
AUCUNE, ANNONCE, VERROUILLAGE, MAINTENANCE = "aucune", "annonce", "verrouillage", "maintenance"

MESSAGE_BLOCAGE = ("Plateforme en maintenance : les connexions sont suspendues. "
                   "Elles seront rétablies par l'administrateur.")
MESSAGE_SESSION_EXPIREE = "Session expirée : reconnectez-vous"

# Petit cache mémoire : l'état est lu à CHAQUE requête authentifiée ; on évite un
# aller-retour en base à chaque fois. Les écritures de ce module le vident aussitôt ;
# les changements de phase, eux, se calculent à partir de l'heure (sans relecture).
DUREE_CACHE_SECONDES = 3.0
_cache: dict = {"lu_a": 0.0, "doc": None}


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _date(valeur: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(valeur) if valeur else None


def vider_cache() -> None:
    _cache["lu_a"] = 0.0
    _cache["doc"] = None


async def lire_document(cache: bool = True) -> dict:
    """Document d'état (vide s'il n'existe pas encore)."""
    if cache and _cache["lu_a"] and time.monotonic() - _cache["lu_a"] < DUREE_CACHE_SECONDES:
        return _cache["doc"] or {}
    doc = await db.maintenance_plateforme.find_one({"_id": ID_ETAT}) or {}
    _cache.update(lu_a=time.monotonic(), doc=doc)
    return doc


def phase_de(doc: dict, a: Optional[datetime] = None) -> str:
    """Phase en cours d'après les dates de l'annonce et l'heure du serveur."""
    if not doc.get("actif"):
        return AUCUNE
    a = a or maintenant()
    if a >= _date(doc["echeance"]):
        return MAINTENANCE
    if a >= _date(doc["debut_verrouillage"]):
        return VERROUILLAGE
    return ANNONCE


def etat_public(doc: dict) -> dict:
    """État diffusé à tous (route publique) : aucune donnée sensible (ni auteur, ni journal)."""
    a = maintenant()
    phase = phase_de(doc, a)
    etat = {"phase": phase, "active": phase != AUCUNE, "maintenant_serveur": a.isoformat()}
    if phase != AUCUNE:
        etat.update({k: doc.get(k) for k in ("message", "annonce_le", "debut_verrouillage", "echeance",
                                              "duree_minutes", "part_verrouillage")})
        a_echeance = (_date(doc["echeance"]) - a).total_seconds()
        etat["secondes_restantes"] = max(0, int(a_echeance + 0.999))
    return etat


def calendrier(duree_minutes: int, part_verrouillage: int, depart: Optional[datetime] = None) -> dict:
    """Dates de l'annonce : début du verrouillage = départ + (100 - part) % de la durée."""
    depart = depart or maintenant()
    total = timedelta(minutes=duree_minutes)
    libre = total * (100 - part_verrouillage) / 100
    return {"annonce_le": depart.isoformat(), "debut_verrouillage": (depart + libre).isoformat(),
            "echeance": (depart + total).isoformat()}


# ---------------------------------------------------------------------------
# Contrôles appelés par l'authentification
# ---------------------------------------------------------------------------
async def controler_session(user: dict, jeton: dict) -> None:
    """Appelé pour CHAQUE requête authentifiée (auth.get_current_user) et à
    l'ouverture du chat temps réel. Administrateur principal : jamais bloqué.
    Autres : 503 pendant la maintenance ; 401 si la session a été ouverte avant
    l'échéance d'une maintenance terminée."""
    if est_exempte(user):
        return
    doc = await lire_document()
    if not doc:
        return
    if phase_de(doc) == MAINTENANCE:
        raise HTTPException(503, MESSAGE_BLOCAGE)
    if not session_valide(doc, jeton):
        raise HTTPException(401, MESSAGE_SESSION_EXPIREE)


def session_valide(doc: dict, jeton: dict) -> bool:
    """Faux si le jeton a été émis avant l'horodatage « sessions valides après »
    (les jetons émis avant cette fonctionnalité n'ont pas d'heure : ouverture = 0)."""
    seuil = _date(doc.get("sessions_valides_apres"))
    return not seuil or float(jeton.get("ouv") or 0) >= seuil.timestamp()


async def session_admise(user: dict, jeton: dict) -> bool:
    """Version « sans erreur » de controler_session (pages publiques qui s'adaptent au visiteur)."""
    try:
        await controler_session(user, jeton)
    except HTTPException:
        return False
    return True


def est_exempte(user: Optional[dict]) -> bool:
    return bool(user) and user.get("role") == ROLE_EXEMPTE


async def refuser_si_maintenance(user: Optional[dict] = None) -> None:
    """Connexion (e-mail/mot de passe, TikTok) et inscription : refusées pendant
    la maintenance, sauf pour un administrateur principal."""
    if est_exempte(user):
        return
    if phase_de(await lire_document()) == MAINTENANCE:
        raise HTTPException(503, MESSAGE_BLOCAGE)


# ---------------------------------------------------------------------------
# Actions de l'administrateur principal
# ---------------------------------------------------------------------------
def _auteur(adm: dict) -> dict:
    return {"id": adm.get("id"), "nom": adm.get("full_name", ""), "email": adm.get("email") or ""}


async def _journaliser(action: str, adm: dict, doc: dict, **extra) -> None:
    await db.maintenance_plateforme_journal.insert_one({
        "id": str(uuid.uuid4()), "action": action, "date": maintenant().isoformat(), "par": _auteur(adm),
        **{k: doc.get(k) for k in ("message", "duree_minutes", "part_verrouillage", "annonce_le",
                                   "debut_verrouillage", "echeance")}, **extra})


async def annoncer(message: str, duree_minutes: int, part_verrouillage: int, adm: dict) -> dict:
    doc = await lire_document(cache=False)
    phase = phase_de(doc)
    if phase == MAINTENANCE:
        raise HTTPException(409, "Une maintenance est en cours : réactivez d'abord les connexions")
    if phase != AUCUNE:
        raise HTTPException(409, "Une déconnexion est déjà programmée : annulez-la avant d'en annoncer une autre")
    nouveau = {"actif": True, "message": message, "duree_minutes": duree_minutes,
               "part_verrouillage": part_verrouillage, "annonce_par": _auteur(adm),
               **calendrier(duree_minutes, part_verrouillage)}
    # Champs conservés d'une maintenance précédente (sessions valides après…)
    await db.maintenance_plateforme.update_one({"_id": ID_ETAT}, {"$set": nouveau}, upsert=True)
    vider_cache()
    await _journaliser("ANNONCE", adm, nouveau)
    return await lire_document(cache=False)


async def annuler(adm: dict) -> dict:
    """Annulation AVANT l'échéance : personne n'est déconnecté."""
    doc = await lire_document(cache=False)
    phase = phase_de(doc)
    if phase == AUCUNE:
        raise HTTPException(409, "Aucune déconnexion programmée")
    if phase == MAINTENANCE:
        raise HTTPException(409, "L'échéance est passée : utilisez « Réactiver les connexions »")
    await db.maintenance_plateforme.update_one({"_id": ID_ETAT}, {"$set": {"actif": False}})
    vider_cache()
    await _journaliser("ANNULATION", adm, doc)
    return await lire_document(cache=False)


async def reactiver(adm: dict) -> dict:
    """Fin de la maintenance : les connexions sont rétablies, mais les sessions
    ouvertes avant l'échéance restent invalides (chacun se reconnecte)."""
    doc = await lire_document(cache=False)
    if phase_de(doc) != MAINTENANCE:
        raise HTTPException(409, "Aucune maintenance en cours (avant l'échéance, utilisez « Annuler »)")
    seuil = doc["echeance"]
    ancien = _date(doc.get("sessions_valides_apres"))
    if ancien and ancien > _date(seuil):
        seuil = ancien.isoformat()
    await db.maintenance_plateforme.update_one({"_id": ID_ETAT}, {"$set": {
        "actif": False, "sessions_valides_apres": seuil, "reactive_le": maintenant().isoformat(),
        "reactive_par": _auteur(adm)}})
    vider_cache()
    await _journaliser("REACTIVATION", adm, doc, sessions_valides_apres=seuil)
    return await lire_document(cache=False)


async def journal(limite: int = 30) -> list[dict]:
    curseur = db.maintenance_plateforme_journal.find({}, {"_id": 0}).sort("date", -1).limit(limite)
    return await curseur.to_list(limite)
