"""Statistiques internes quotidiennes demandées par SAWALI (lot 57).

SAWALI appelle chaque plateforme une fois par jour pour connaître ses
statistiques internes. La demande arrive sur la route PUBLIQUE et signée
POST /api/webhooks/liluvine-retour (même clé LILUVINE_WA_HMAC que la
Transmission WA), avec le corps :
    {"type": "stats_du_jour", "debut": "<ISO>", "fin": "<ISO>"}
(dates UTC, période [debut, fin), 31 jours au plus).

Réponse 200 :
    {"indicateurs": [{"cle", "libelle", "valeur"}, …],   # 10 indicateurs
     "faits_marquants": ["…", …],                         # 5 au plus, en français
     "utilisateurs_connectes": <int>}                      # actifs depuis 5 min

Tout est en LECTURE seule (comptages MongoDB) et borné dans le temps
(réponse en moins de 8 s exigée par SAWALI). Les données de test et les
comptes du back-office ne sont pas comptés dans les inscriptions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import db

logger = logging.getLogger("stats_sawali")

# Période maximale acceptée (au-delà : 422)
DUREE_MAX = timedelta(days=31)
# Fenêtre « connecté maintenant » : activité dans les 5 dernières minutes
FENETRE_CONNECTES_SECONDES = 5 * 60
# Temps maximal accordé aux comptages (SAWALI attend au plus 8 s)
DELAI_MAX_SECONDES = 6.5
# Nombre maximal de faits marquants renvoyés
MAX_FAITS = 5


class PeriodeInvalide(ValueError):
    """Période absente, illisible, inversée ou trop longue (→ 422)."""


# ---------------------------------------------------------------------------
# Lecture et contrôle de la période
# ---------------------------------------------------------------------------

def _lire_date(valeur) -> datetime:
    """Convertit une date ISO (avec « Z » ou un décalage) en datetime UTC.
    Une date sans fuseau est considérée comme UTC."""
    if not isinstance(valeur, str) or not valeur.strip():
        raise PeriodeInvalide("Date absente")
    texte = valeur.strip()
    if texte.endswith(("Z", "z")):
        texte = texte[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(texte)
    except ValueError as exc:
        raise PeriodeInvalide("Date illisible") from exc
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def lire_periode(donnees: dict) -> tuple[datetime, datetime]:
    """Renvoie (debut, fin) en UTC ; lève PeriodeInvalide si la période est
    illisible, vide / inversée, ou plus longue que 31 jours."""
    debut = _lire_date(donnees.get("debut"))
    fin = _lire_date(donnees.get("fin"))
    if fin <= debut:
        raise PeriodeInvalide("La fin doit être postérieure au début")
    if fin - debut > DUREE_MAX:
        raise PeriodeInvalide("Période de plus de 31 jours")
    return debut, fin


# ---------------------------------------------------------------------------
# Comptages élémentaires (lecture seule)
# ---------------------------------------------------------------------------

def _plage(champ: str, debut: datetime, fin: datetime) -> dict:
    """Filtre MongoDB « champ dans [debut, fin) » pour les dates stockées en
    texte ISO UTC (format datetime.isoformat(), comparable alphabétiquement)."""
    return {champ: {"$gte": debut.isoformat(), "$lt": fin.isoformat()}}


# Vrais membres : ni comptes du back-office, ni données de test
_VRAIS_MEMBRES = {"role": {"$nin": ["admin", "moderator"]}, "is_test_data": {"$ne": True}}


async def _compter(collection: str, filtre: dict) -> int:
    """Nombre de documents d'une collection (préfixée maf_) pour ce filtre."""
    return await db[collection].count_documents(filtre)


async def _somme_paiements(debut: datetime, fin: datetime) -> int:
    """Montant total (FCFA) des paiements Mobile Money aboutis sur la période."""
    curseur = db.payments.aggregate([
        {"$match": {"status": "completed", **_plage("updated_at", debut, fin)}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ])
    total = 0
    async for ligne in curseur:
        total = ligne.get("total") or 0
    return int(round(float(total)))


async def utilisateurs_connectes(maintenant: Optional[float] = None) -> int:
    """Nombre de comptes DISTINCTS actifs dans les 5 dernières minutes.

    Deux sources déjà tenues à jour à chaque requête authentifiée (au plus une
    écriture par minute, voir auth._touch_last_seen et sessions_comptes.controler) :
      - sessions ouvertes (`maf_sessions.derniere_activite`, horodatage en s) ;
      - fiche du membre (`maf_users.last_seen_at`, texte ISO UTC).
    L'union des deux évite d'oublier un membre en « mode invisible » (pas de
    last_seen_at) ou une session ancienne. Aucun nom n'est renvoyé, juste le nombre."""
    t = time.time() if maintenant is None else maintenant
    seuil = t - FENETRE_CONNECTES_SECONDES
    ids_sessions = await db.sessions.distinct(
        "user_id", {"fermee": False, "derniere_activite": {"$gte": seuil}})
    seuil_iso = datetime.fromtimestamp(seuil, timezone.utc).isoformat()
    ids_fiches = await db.users.distinct("id", {"last_seen_at": {"$gte": seuil_iso}})
    return len({i for i in ids_sessions if i} | {i for i in ids_fiches if i})


# ---------------------------------------------------------------------------
# Calcul complet
# ---------------------------------------------------------------------------

# (clé, libellé) des indicateurs, dans l'ordre d'affichage chez SAWALI
LIBELLES = {
    "connexions": "Connexions réussies",
    "inscriptions": "Nouvelles inscriptions",
    "identites_verifiees": "Identités vérifiées",
    "matchs": "Nouveaux matchs",
    "messages": "Messages échangés",
    "moments_publies": "Vidéos « Moments » publiées",
    "paiements_reussis": "Paiements Mobile Money aboutis",
    "montant_paiements_fcfa": "Montant encaissé (FCFA)",
    "signalements": "Signalements reçus (profils et vidéos)",
    "verifications_en_attente": "Vérifications d'identité en attente",
}


async def _calculer_valeurs(debut: datetime, fin: datetime) -> dict:
    """Lance tous les comptages en parallèle et renvoie {clé: valeur}."""
    taches = {
        "connexions": _compter("connexions_journal", {"etat": "reussie", **_plage("date", debut, fin)}),
        "inscriptions": _compter("users", {**_VRAIS_MEMBRES, **_plage("created_at", debut, fin)}),
        "identites_verifiees": _compter("identity_verifications",
                                        {"status": "verified", **_plage("reviewed_at", debut, fin)}),
        "matchs": _compter("matches", _plage("created_at", debut, fin)),
        "messages": _compter("messages", _plage("created_at", debut, fin)),
        "moments_publies": _compter("videos", {"status": "published", **_plage("created_at", debut, fin)}),
        "paiements_reussis": _compter("payments", {"status": "completed", **_plage("updated_at", debut, fin)}),
        "montant_paiements_fcfa": _somme_paiements(debut, fin),
        "signalements_profils": _compter("reports", _plage("created_at", debut, fin)),
        "signalements_videos": _compter("video_reports", _plage("created_at", debut, fin)),
        # État à l'instant de la demande (file d'attente des modérateurs)
        "verifications_en_attente": _compter("identity_verifications", {"status": "pending"}),
    }
    resultats = await asyncio.gather(*taches.values(), return_exceptions=True)
    valeurs = {}
    for cle, res in zip(taches.keys(), resultats):
        if isinstance(res, Exception):
            # Un comptage en échec ne doit pas faire échouer toute la réponse
            logger.warning("Statistiques SAWALI : comptage « %s » impossible (%s)", cle, type(res).__name__)
            res = 0
        valeurs[cle] = res
    valeurs["signalements"] = valeurs.pop("signalements_profils") + valeurs.pop("signalements_videos")
    return valeurs


def _pluriel(n: int, singulier: str, pluriel: str) -> str:
    """« 1 match » / « 3 matchs » (nombre formaté à la française)."""
    nombre = f"{n:,}".replace(",", " ")
    return f"{nombre} {singulier if n <= 1 else pluriel}"


def _faits_marquants(v: dict, connectes: int) -> list[str]:
    """Jusqu'à 5 phrases courtes, en français, sur les points saillants."""
    faits: list[str] = []
    if v["inscriptions"]:
        faits.append(_pluriel(v["inscriptions"], "nouvelle inscription", "nouvelles inscriptions") + " sur la période.")
    if v["paiements_reussis"]:
        montant = f"{v['montant_paiements_fcfa']:,}".replace(",", " ")
        faits.append(_pluriel(v["paiements_reussis"], "paiement abouti", "paiements aboutis")
                     + f" pour {montant} FCFA.")
    if v["matchs"]:
        faits.append(_pluriel(v["matchs"], "nouveau match", "nouveaux matchs") + " entre membres.")
    if v["signalements"]:
        faits.append(_pluriel(v["signalements"], "signalement reçu", "signalements reçus")
                     + " : à examiner par la modération.")
    if v["verifications_en_attente"]:
        faits.append(_pluriel(v["verifications_en_attente"], "vérification d'identité", "vérifications d'identité")
                     + " en attente de décision.")
    if v["moments_publies"]:
        faits.append(_pluriel(v["moments_publies"], "vidéo « Moments » publiée", "vidéos « Moments » publiées") + ".")
    if connectes:
        faits.append(_pluriel(connectes, "membre connecté", "membres connectés") + " au moment de la demande.")
    if not faits:
        faits.append("Aucune activité notable sur la période.")
    return faits[:MAX_FAITS]


async def stats_du_jour(debut: datetime, fin: datetime) -> dict:
    """Réponse complète pour SAWALI. Les comptages sont bornés à
    DELAI_MAX_SECONDES : au-delà, des zéros sont renvoyés plutôt qu'une erreur."""
    try:
        valeurs = await asyncio.wait_for(_calculer_valeurs(debut, fin), timeout=DELAI_MAX_SECONDES)
    except asyncio.TimeoutError:
        logger.warning("Statistiques SAWALI : délai dépassé, valeurs à zéro")
        valeurs = {cle: 0 for cle in LIBELLES}
    try:
        connectes = await asyncio.wait_for(utilisateurs_connectes(), timeout=1.0)
    except Exception as exc:  # noqa: BLE001 — jamais d'erreur 500 pour SAWALI
        logger.warning("Statistiques SAWALI : connectés indisponibles (%s)", type(exc).__name__)
        connectes = 0
    indicateurs = [{"cle": cle, "libelle": libelle, "valeur": int(valeurs.get(cle) or 0)}
                   for cle, libelle in LIBELLES.items()]
    return {"indicateurs": indicateurs, "faits_marquants": _faits_marquants(valeurs, connectes),
            "utilisateurs_connectes": int(connectes)}
