"""Cycle de vie du NON-RENOUVELLEMENT de l'abonnement (spécification C, validée
le 02/10/2026). Pour beAuthentik, le « locataire » est le MEMBRE abonné.

Jours comptés en jours calendaires (UTC) depuis l'échéance impayée (grâce comprise) :
  - J+103 : avertissement « suspension dans 7 jours » ;
  - J+110 : SUSPENSION du membre (statut « SUSPENDU_NON_RENOUVELE ») + avertissement :
            compte désactivé (`is_active` = false : profil, Moments et fiche
            retirés de la découverte et de la recherche — la « vitrine »), plus
            aucun accès sauf les routes de renouvellement (formules, souscription,
            paiement, preuve de paiement, état de l'abonnement, déconnexion). Un
            paiement qui crée une nouvelle échéance lève la suspension à la
            requête suivante (et à la tâche quotidienne) ;
  - J+112 : avertissement « suppression demain » ;
  - J+113 : ARCHIVE chiffrée des données du membre (même format .baexport et même
            chiffrement que les exports, phrase SAUVEGARDE_AUTO_PHRASE), envoyée sur
            R2 dans `archives-locataires/<id>/`, RELUE et VÉRIFIÉE (déchiffrement +
            nombres de documents identiques à la base) ; SEULEMENT si la
            vérification réussit, SUPPRESSION du compte et de ses données (les
            documents archivés, par identifiant). Une fiche est conservée
            (`maf_archives_membres`, statut « ARCHIVÉ ») avec la référence de
            l'archive, la date et les nombres de documents. Échec : rien n'est
            supprimé, alerte aux administrateurs. S'il revient, le membre
            recommence tout à zéro (nouvelle inscription).
  - Conservation des archives : 1 an par défaut (paramètre de la plateforme), puis
    effacement automatique de l'archive R2 et des médias du membre (photos,
    vidéos, pièces d'identité, gardés jusque-là pour permettre une réouverture).
  - Réouverture : PAS de réouverture automatique ; l'administrateur principal peut
    rouvrir un compte depuis son archive (mot de passe exigé). Les frais de
    réouverture (montant + devise, paramètres de la plateforme) sont affichés et
    notés ; leur encaissement reste manuel.

Avertissements : WhatsApp puis SMS (envoi_messages.py — beAuthentik n'envoie pas
d'e-mail), une seule fois chacun par échéance, journalisés. Si la tâche n'a pas
tourné un jour, seul l'avertissement de l'étape atteinte est envoyé.

Mise en service (« rattrapage ») : le jour où le cycle tourne pour la première
fois est noté (`cycle_debut_le`) ; aucun membre ne peut alors être compté
au-delà de J+103 + jours écoulés depuis cette date. Un membre dont l'échéance est
déjà très ancienne reçoit donc d'abord l'avertissement J+103, puis passe par
toutes les étapes (pas de suspension ni de suppression sans prévenir).

Exclus : administrateurs, modérateurs, comptes de test (`is_test_data`), comptes
désactivés manuellement (hors cycle), membres jamais abonnés (gratuits).

Tâche quotidienne : lancée par le Cron Job de la sauvegarde
(POST /api/sauvegarde-auto/declencher) ou à la main par l'administrateur ;
interrupteur « Cycle de vie automatique » (activé par défaut) et MODE SIMULATION
(liste ce qui serait fait, sans rien faire) ; rapport quotidien
(`maf_cycle_vie_rapports`, visible dans l'administration et envoyé aux
administrateurs par WhatsApp/SMS quand il y a des actions ou des erreurs).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS
from fastapi import HTTPException, Request
from pymongo.errors import BulkWriteError

import abonnement_grace
import chiffrement_flux
import envoi_messages
import parametres_plateforme
import sauvegarde_auto
import sessions_comptes
import storage
import transfert_donnees
from config import get_settings
from db import db

logger = logging.getLogger(__name__)

STATUT_SUSPENDU = "SUSPENDU_NON_RENOUVELE"
STATUT_ARCHIVE = "ARCHIVÉ"
J_AVERTISSEMENT, J_SUSPENSION, J_VEILLE, J_SUPPRESSION = 103, 110, 112, 113
ROLES_EXCLUS = ("admin", "moderator")
MESSAGE_SUSPENDU = ("Compte suspendu : votre abonnement n'a pas été renouvelé. Renouvelez-le pour réactiver "
                    "votre compte ; sans renouvellement, il sera supprimé.")

# Routes encore ouvertes à un membre suspendu (renouvellement, déconnexion, profil minimal)
ROUTES_SUSPENDU = (
    ("GET", "/api/auth/me"), ("POST", "/api/auth/deconnexion"), ("GET", "/api/auth/inactivite"),
    ("POST", "/api/auth/activite"), ("GET", "/api/abonnement/etat"), ("GET", "/api/sauvegarde-auto/derniere"),
    ("*", "/api/subscriptions/"), ("*", "/api/payments/pawapay/"), ("POST", "/api/uploads"),
)

_verrou = asyncio.Lock()


def maintenant() -> datetime:
    return abonnement_grace.maintenant()


def _date(valeur: Optional[str]) -> Optional[datetime]:
    return abonnement_grace._date(valeur)  # noqa: SLF001


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Suspension : contrôle à chaque requête (appelé par auth.get_current_user)
# ---------------------------------------------------------------------------
def est_suspendu(user: dict) -> bool:
    return user.get("statut_cycle") == STATUT_SUSPENDU


def route_autorisee(request: Optional[Request]) -> bool:
    if request is None:
        return False
    methode, chemin = request.method.upper(), request.url.path
    for m, prefixe in ROUTES_SUSPENDU:
        if (m == "*" or m == methode) and (chemin == prefixe or (prefixe.endswith("/") and chemin.startswith(prefixe))):
            return True
    return False


async def controler_suspendu(user: dict, request: Optional[Request]) -> dict:
    """Membre suspendu : suspension levée s'il a payé, sinon seules les routes de
    renouvellement restent ouvertes (403 avec un message clair ailleurs)."""
    if await abonnement_grace.premium_actif(user["id"]):
        await lever_suspension(user["id"], "paiement")
        return {**user, "is_active": True, "statut_cycle": None}
    if not route_autorisee(request):
        raise HTTPException(403, MESSAGE_SUSPENDU)
    return user


async def lever_suspension(user_id: str, motif: str, par: Optional[dict] = None) -> None:
    res = await db.users.update_one({"id": user_id, "statut_cycle": STATUT_SUSPENDU},
                                    {"$set": {"is_active": True, "statut_cycle": None,
                                              "cycle_vie.suspension_levee_le": maintenant().isoformat()}})
    if res.modified_count:
        await _journal("suspension_levee", user_id, motif=motif, par=(par or {}).get("email"))


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
async def _journal(action: str, user_id: Optional[str], **details: Any) -> None:
    await db.cycle_vie_journal.insert_one({"id": str(uuid.uuid4()), "date": maintenant().isoformat(),
                                           "action": action, "user_id": user_id, "details": details})


# ---------------------------------------------------------------------------
# Sélection des membres concernés
# ---------------------------------------------------------------------------
def _exclu(user: dict) -> Optional[str]:
    if user.get("role") in ROLES_EXCLUS:
        return "administrateur ou modérateur"
    if user.get("is_test_data"):
        return "compte de test"
    if user.get("is_active") is False and not est_suspendu(user):
        return "compte désactivé manuellement"
    return None


async def _debut_cycle(params: dict, simulation: bool) -> date:
    debut = _date(params.get("cycle_debut_le"))
    if debut is None:
        debut = maintenant()
        if not simulation:
            await parametres_plateforme.marquer({"cycle_debut_le": debut.isoformat()})
    return debut.date()


async def situation(user: dict, debut_cycle: date) -> Optional[dict]:
    """Étape du cycle pour ce membre, ou None s'il n'est pas concerné."""
    etat = await abonnement_grace.etat(user["id"], user)
    if etat["statut"] in ("aucun", "actif", "grace") or not etat.get("echeance"):
        return None
    echeance = _date(etat["echeance"])
    reference = echeance
    repart = _date(user.get("cycle_repart_le"))
    if repart and repart > reference:
        reference = repart
    aujourd_hui = maintenant().date()
    reels = (aujourd_hui - reference.date()).days
    jours = min(reels, J_AVERTISSEMENT + (aujourd_hui - debut_cycle).days)
    if jours < J_AVERTISSEMENT:
        return None
    return {"echeance": etat["echeance"], "jours_reels": reels, "jours": jours,
            "suspension_le": _fmt(aujourd_hui + timedelta(days=max(0, J_SUSPENSION - jours))),
            "suppression_le": _fmt(aujourd_hui + timedelta(days=max(0, J_SUPPRESSION - jours)))}


def _suivi(user: dict, echeance: str) -> dict:
    """Suivi des étapes pour l'échéance en cours (remis à zéro si l'échéance change)."""
    suivi = user.get("cycle_vie") or {}
    return suivi if suivi.get("echeance") == echeance else {"echeance": echeance}


# ---------------------------------------------------------------------------
# Avertissements
# ---------------------------------------------------------------------------
def texte_avertissement(etape: int, s: dict) -> str:
    url = f"{get_settings().public_site_url}/abonnement"
    echeance = _fmt(_date(s["echeance"]).date())
    if etape == J_AVERTISSEMENT:
        return (f"beAuthentik : votre abonnement Premium a expiré le {echeance}. Sans renouvellement, votre compte "
                f"sera suspendu le {s['suspension_le']} puis supprimé le {s['suppression_le']}. Renouvelez : {url}")
    if etape == J_SUSPENSION:
        return (f"beAuthentik : votre compte est suspendu (abonnement non renouvelé depuis le {echeance}). Il sera "
                f"définitivement supprimé le {s['suppression_le']}. Renouvelez dès maintenant : {url}")
    return (f"beAuthentik : dernier rappel — votre compte sera supprimé demain ({s['suppression_le']}) faute de "
            f"renouvellement de votre abonnement. Renouvelez : {url}")


async def _avertir(user: dict, etape: int, s: dict, suivi: dict) -> dict:
    cle = f"avertissement_{etape}"
    if suivi.get(cle):
        return {}
    resultat = await envoi_messages.envoyer(user, texte_avertissement(etape, s))
    suivi[cle] = {"le": maintenant().isoformat(), "ok": resultat["ok"], "canal": resultat["canal"],
                  "erreur": resultat["erreur"]}
    # Les avertissements des étapes déjà dépassées ne seront plus envoyés
    for precedente in (J_AVERTISSEMENT, J_SUSPENSION, J_VEILLE):
        if precedente < etape and not suivi.get(f"avertissement_{precedente}"):
            suivi[f"avertissement_{precedente}"] = {"le": maintenant().isoformat(), "saute": True}
    await db.users.update_one({"id": user["id"]}, {"$set": {"cycle_vie": suivi}})
    await _journal(cle, user["id"], nom=user.get("full_name"), **{k: v for k, v in suivi[cle].items() if k != "le"})
    return {"action": cle, "envoye": resultat["ok"], "canal": resultat["canal"]}


async def suspendre(user: dict, suivi: dict) -> None:
    suivi["suspendu_le"] = maintenant().isoformat()
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "is_active": False, "statut_cycle": STATUT_SUSPENDU, "cycle_vie": suivi}})
    await _journal("suspension", user["id"], nom=user.get("full_name"))


# ---------------------------------------------------------------------------
# Archive d'un membre
# ---------------------------------------------------------------------------
async def selection_membre(user_id: str) -> dict[str, dict]:
    """Collections (noms logiques) et filtres des données d'UN membre."""
    conversations = await db.conversations.distinct("id", {"$or": [{"user_a": user_id}, {"user_b": user_id}]})
    videos = await db.videos.distinct("id", {"user_id": user_id})
    suivis = await db.tracking_sessions.distinct("id", {"owner_id": user_id})
    par_user = {"user_id": user_id}
    envoi = {"$or": [{"sender_id": user_id}, {"recipient_id": user_id}]}
    return {
        "users": {"id": user_id},
        "subscriptions": par_user, "payments": par_user, "payment_proofs": par_user,
        "wallet_transactions": par_user, "referral_shares": par_user, "identity_verifications": par_user,
        "verification_events": par_user, "support_tickets": par_user, "testimonials": par_user,
        "otp_codes": par_user, "activity_log": par_user, "sessions": par_user, "abonnements_journal": par_user,
        "hearts_sent": envoi, "gifts_sent": envoi, "points_transfers": envoi,
        "swipes": {"$or": [{"user_id": user_id}, {"target_user_id": user_id}]},
        "matches": {"$or": [{"user_a": user_id}, {"user_b": user_id}]},
        "conversations": {"id": {"$in": conversations}},
        "messages": {"$or": [{"conversation_id": {"$in": conversations}}, {"sender_id": user_id}]},
        "profile_visits": {"$or": [{"visitor_id": user_id}, {"target_id": user_id}]},
        "ratings": {"$or": [{"rated_user_id": user_id}, {"rater_user_id": user_id}]},
        "reports": {"$or": [{"reported_user_id": user_id}, {"reporter_user_id": user_id}]},
        "videos": {"id": {"$in": videos}},
        "video_likes": {"$or": [{"video_id": {"$in": videos}}, {"user_id": user_id}]},
        "video_views": {"$or": [{"video_id": {"$in": videos}}, {"user_id": user_id}]},
        "video_comments": {"$or": [{"video_id": {"$in": videos}}, {"user_id": user_id}]},
        "video_reports": {"$or": [{"video_id": {"$in": videos}}, {"user_id": user_id}]},
        "video_access_requests": {"$or": [{"owner_id": user_id}, {"requester_id": user_id}]},
        "tracking_sessions": {"$or": [{"owner_id": user_id}, {"guardian_id": user_id}]},
        "tracking_points": {"session_id": {"$in": suivis}},
    }


async def _medias(user_id: str) -> dict:
    """Fichiers du membre (supprimés seulement à l'expiration de l'archive)."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "photos": 1}) or {}
    publics = [u for p in user.get("photos") or [] for u in (p.get("url"), p.get("masked_url")) if u]
    prives = []
    async for v in db.videos.find({"user_id": user_id}, {"_id": 0, "blurred_url": 1, "poster_url": 1, "clear_key": 1}):
        publics += [u for u in (v.get("blurred_url"), v.get("poster_url")) if u]
        if v.get("clear_key"):
            prives.append(v["clear_key"])
    async for d in db.identity_verifications.find({"user_id": user_id}, {"_id": 0, "document_key": 1}):
        if d.get("document_key"):
            prives.append(d["document_key"])
    return {"publics": publics, "prives": prives}


def _lire_archive(chemin: str, phrase: str) -> tuple[dict, dict[str, list]]:
    """Déchiffre l'archive relue depuis R2 : manifest + identifiants (_id) par collection."""
    lecteur = chiffrement_flux.LecteurChiffre(chemin, phrase, transfert_donnees._cle_signature())  # noqa: SLF001
    try:
        with zipfile.ZipFile(lecteur) as archive:
            manifest = json_util.loads(archive.read("manifest.json").decode("utf-8"),
                                       json_options=CANONICAL_JSON_OPTIONS)
            ids: dict[str, list] = {}
            for c in manifest.get("collections", []):
                ids[c["nom"]] = [doc["_id"] for doc in transfert_donnees._lecteur_lignes(archive, c["fichier"])]  # noqa: SLF001
        return manifest, ids
    finally:
        lecteur.close()


def _lire_documents(chemin: str, phrase: str) -> tuple[dict, dict[str, list]]:
    """Documents complets de l'archive (réouverture)."""
    lecteur = chiffrement_flux.LecteurChiffre(chemin, phrase, transfert_donnees._cle_signature())  # noqa: SLF001
    try:
        with zipfile.ZipFile(lecteur) as archive:
            manifest = json_util.loads(archive.read("manifest.json").decode("utf-8"),
                                       json_options=CANONICAL_JSON_OPTIONS)
            docs = {c["nom"]: list(transfert_donnees._lecteur_lignes(archive, c["fichier"]))  # noqa: SLF001
                    for c in manifest.get("collections", [])}
        return manifest, docs
    finally:
        lecteur.close()


async def archiver_et_supprimer(user: dict) -> dict:
    """J+113 : archive chiffrée -> R2 -> relecture et vérification -> suppression.
    Lève une exception (rien n'est supprimé) si une étape échoue."""
    motif = sauvegarde_auto.motif_desactivation()
    if motif:
        raise RuntimeError(f"Archive impossible : {motif}")
    phrase = sauvegarde_auto.phrase()
    dep = sauvegarde_auto.depot()
    uid = user["id"]
    selection = await selection_membre(uid)
    attendus = {nom: await db[nom].count_documents(filtre) for nom, filtre in selection.items()}
    medias = await _medias(uid)
    horodatage = maintenant().strftime("%Y%m%d-%H%M%S")
    cle = (f"{sauvegarde_auto.prefixe()}{sauvegarde_auto.DOSSIER_ARCHIVES}{uid}/"
           f"beauthentik_membre_{horodatage}{transfert_donnees.EXTENSION}")
    local = str(transfert_donnees.DOSSIER / f"membre-{secrets.token_hex(8)}{transfert_donnees.EXTENSION}")
    relu = local + ".relu"
    try:
        collections = await transfert_donnees.ecrire_export(local, phrase, selection=selection)
        await asyncio.to_thread(dep.envoyer, local, cle)
        # Relecture DEPUIS R2 puis vérification complète
        await asyncio.to_thread(dep.telecharger, cle, relu)
        manifest, ids = await asyncio.to_thread(_lire_archive, relu, phrase)
        comptes = {c["nom"]: c["documents"] for c in manifest.get("collections", [])}
        ecarts = [nom for nom, n in attendus.items()
                  if n and (comptes.get(nom) != n or len(ids.get(nom, [])) != n)]
        if ecarts or not ids.get("users"):
            raise RuntimeError("Vérification de l'archive échouée (nombres différents : "
                               + ", ".join(ecarts or ["users"]) + ")")
        # Suppression : uniquement les documents archivés (par identifiant)
        supprimes = {}
        for nom, liste in ids.items():
            if liste:
                res = await db[nom].delete_many({"_id": {"$in": liste}})
                supprimes[nom] = res.deleted_count
        await sessions_comptes.fermer_toutes(uid, "compte", None)
        conservation = int((await parametres_plateforme.lire()).get("conservation_archives_jours") or 365)
        fiche = {"id": str(uuid.uuid4()), "user_id": uid, "nom": user.get("full_name"), "email": user.get("email"),
                 "phone": user.get("phone"), "statut": STATUT_ARCHIVE, "archive_le": maintenant().isoformat(),
                 "cle_r2": cle, "taille": os.path.getsize(local), "comptes": comptes, "supprimes": supprimes,
                 "echeance": (user.get("cycle_vie") or {}).get("echeance"),
                 "expire_le": (maintenant() + timedelta(days=conservation)).isoformat(), "medias": medias,
                 "collections": len(collections)}
        await db.archives_membres.insert_one(dict(fiche))
        await _journal("archive_et_suppression", uid, nom=user.get("full_name"), cle_r2=cle, comptes=comptes)
        fiche.pop("medias")
        return fiche
    finally:
        transfert_donnees._supprimer(local)  # noqa: SLF001
        transfert_donnees._supprimer(relu)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Tâche quotidienne
# ---------------------------------------------------------------------------
async def executer_quotidien(declencheur: str = "cron", simulation: Optional[bool] = None,
                             par: Optional[dict] = None) -> dict:
    params = await parametres_plateforme.lire(cache=False)
    if simulation is None:
        simulation = bool(params.get("cycle_simulation"))
    if not params.get("cycle_actif") and not simulation:
        rapport = {"statut": "DESACTIVE", "date": maintenant().isoformat(), "declencheur": declencheur}
        await db.cycle_vie_rapports.insert_one({"id": str(uuid.uuid4()), **rapport, "actions": [], "erreurs": []})
        return rapport
    if _verrou.locked():
        return {"statut": "EN_COURS"}
    async with _verrou:
        return await _executer(params, declencheur, simulation, par)


async def _executer(params: dict, declencheur: str, simulation: bool, par: Optional[dict]) -> dict:
    debut_cycle = await _debut_cycle(params, simulation)
    actions: list[dict] = []
    erreurs: list[dict] = []
    abonnes = await db.subscriptions.distinct("user_id", {"status": "active"})
    for uid in abonnes:
        user = await db.users.find_one({"id": uid}, {"_id": 0})
        if not user or _exclu(user):
            continue
        try:
            s = await situation(user, debut_cycle)
            if s is None:
                if est_suspendu(user) and not simulation:  # a payé entre-temps
                    await lever_suspension(uid, "nouvelle échéance")
                    actions.append({"user_id": uid, "nom": user.get("full_name"), "action": "suspension_levee"})
                continue
            ligne = {"user_id": uid, "nom": user.get("full_name"), "jours": s["jours"], "echeance": s["echeance"]}
            suivi = _suivi(user, s["echeance"])
            if simulation:
                actions.append({**ligne, "action": _prevu(s["jours"], user, suivi), "simulation": True})
                continue
            fait = await _etape(user, s, suivi)
            if fait:
                actions.append({**ligne, **fait})
        except Exception as exc:  # noqa: BLE001 — un membre en échec ne bloque pas les autres
            logger.exception("Cycle de vie : échec pour %s", uid)
            erreurs.append({"user_id": uid, "nom": user.get("full_name") if user else None, "erreur": str(exc)[:300]})
            if not simulation:
                await _journal("echec", uid, erreur=str(exc)[:300])
    purges = await purger_archives(simulation)
    rapport = {"id": str(uuid.uuid4()), "date": maintenant().isoformat(), "declencheur": declencheur,
               "simulation": simulation, "statut": "SIMULATION" if simulation else "TERMINE",
               "par": (par or {}).get("email"), "actions": actions, "erreurs": erreurs, "archives_effacees": purges}
    await db.cycle_vie_rapports.insert_one(dict(rapport))
    if not simulation and (actions or erreurs or purges):
        try:
            await envoi_messages.alerter_administrateurs(
                f"beAuthentik — cycle de vie du {_fmt(maintenant().date())} : {len(actions)} action(s), "
                f"{len(erreurs)} erreur(s), {len(purges)} archive(s) effacée(s). Détail dans l'administration.")
        except Exception:  # noqa: BLE001
            pass
    rapport.pop("_id", None)
    return rapport


def _prevu(jours: int, user: dict, suivi: dict) -> str:
    """Ce que la tâche ferait aujourd'hui (mode simulation)."""
    if jours >= J_SUPPRESSION and est_suspendu(user):
        return "archive_et_suppression"
    if jours >= J_SUSPENSION and not est_suspendu(user):
        return "suspension"
    if jours >= J_VEILLE and not suivi.get(f"avertissement_{J_VEILLE}"):
        return f"avertissement_{J_VEILLE}"
    if jours < J_SUSPENSION and not suivi.get(f"avertissement_{J_AVERTISSEMENT}"):
        return f"avertissement_{J_AVERTISSEMENT}"
    return "aucune"


async def _etape(user: dict, s: dict, suivi: dict) -> Optional[dict]:
    jours = s["jours"]
    if jours >= J_SUSPENSION and not est_suspendu(user):
        await suspendre(user, suivi)
        await _avertir(user, J_SUSPENSION, s, suivi)
        return {"action": "suspension"}
    if jours >= J_SUPPRESSION and est_suspendu(user):
        suspendu_le = _date(suivi.get("suspendu_le"))
        # Au moins 3 jours de suspension avant la suppression (même si la tâche a sauté des jours)
        if suspendu_le and (maintenant().date() - suspendu_le.date()).days >= J_SUPPRESSION - J_SUSPENSION:
            try:
                fiche = await archiver_et_supprimer({**user, "cycle_vie": suivi})
            except Exception as exc:
                await envoi_messages.alerter_administrateurs(
                    f"beAuthentik : archive du membre {user.get('full_name')} ÉCHOUÉE, rien n'a été supprimé "
                    f"({str(exc)[:120]}).")
                raise
            return {"action": "archive_et_suppression", "cle_r2": fiche["cle_r2"], "comptes": fiche["comptes"]}
    if jours >= J_VEILLE:
        fait = await _avertir(user, J_VEILLE, s, suivi)
        return fait or None
    if jours >= J_AVERTISSEMENT and jours < J_SUSPENSION:
        fait = await _avertir(user, J_AVERTISSEMENT, s, suivi)
        return fait or None
    return None


async def purger_archives(simulation: bool) -> list[dict]:
    """Archives arrivées au terme de leur conservation : effacées de R2 avec les médias du membre."""
    effacees = []
    dep = sauvegarde_auto.depot()
    async for fiche in db.archives_membres.find({"statut": STATUT_ARCHIVE, "expire_le": {"$lt": maintenant().isoformat()}},
                                                {"_id": 0}):
        effacees.append({"id": fiche["id"], "nom": fiche.get("nom"), "cle_r2": fiche.get("cle_r2")})
        if simulation:
            continue
        if dep is None:
            continue
        try:
            await asyncio.to_thread(dep.supprimer, fiche["cle_r2"])
            for url in (fiche.get("medias") or {}).get("publics", []):
                await storage.delete_public_media(url)
            for cle in (fiche.get("medias") or {}).get("prives", []):
                await storage.delete_private_media(cle)
        except Exception as exc:  # noqa: BLE001 — nouvel essai le lendemain
            logger.warning("Archive %s non effacée : %r", fiche.get("id"), exc)
            effacees[-1]["erreur"] = str(exc)[:200]
            continue
        await db.archives_membres.update_one({"id": fiche["id"]}, {"$set": {
            "statut": "ARCHIVE_EFFACEE", "effacee_le": maintenant().isoformat(), "medias": None}})
        await _journal("archive_effacee", fiche.get("user_id"), cle_r2=fiche.get("cle_r2"))
    return effacees


# ---------------------------------------------------------------------------
# Réouverture manuelle (administrateur principal)
# ---------------------------------------------------------------------------
async def rouvrir(archive_id: str, adm: dict, frais_encaisses: bool) -> dict:
    fiche = await db.archives_membres.find_one({"id": archive_id}, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Archive introuvable")
    if fiche.get("statut") != STATUT_ARCHIVE:
        raise HTTPException(400, "Cette archive n'est plus disponible (déjà rouverte ou effacée)")
    motif = sauvegarde_auto.motif_desactivation()
    if motif:
        raise HTTPException(503, motif)
    conflit = [{"id": fiche["user_id"]}] + [{c: fiche[c]} for c in ("email", "phone") if fiche.get(c)]
    if await db.users.find_one({"$or": conflit}, {"_id": 0, "id": 1}):
        raise HTTPException(409, "Un compte avec le même identifiant, e-mail ou téléphone existe déjà : "
                                 "réouverture impossible (le membre s'est réinscrit).")
    params = await parametres_plateforme.lire(cache=False)
    local = str(transfert_donnees.DOSSIER / f"reouverture-{secrets.token_hex(8)}{transfert_donnees.EXTENSION}")
    try:
        try:
            await asyncio.to_thread(sauvegarde_auto.depot().telecharger, fiche["cle_r2"], local)
            manifest, docs = await asyncio.to_thread(_lire_documents, local, sauvegarde_auto.phrase())
        except chiffrement_flux.ErreurChiffrement as exc:
            raise HTTPException(400, f"Archive illisible : {exc}") from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Archive introuvable sur R2 : {str(exc)[:150]}") from exc
        restaures = {}
        for nom, liste in docs.items():
            if not liste or nom == "sessions":
                continue  # les anciennes sessions ne sont pas rouvertes
            try:
                res = await db[nom].insert_many(liste, ordered=False)
                restaures[nom] = len(res.inserted_ids)
            except BulkWriteError as exc:
                restaures[nom] = (exc.details or {}).get("nInserted", 0)
        a = maintenant().isoformat()
        await db.users.update_one({"id": fiche["user_id"]}, {"$set": {
            "is_active": True, "statut_cycle": None, "cycle_repart_le": a, "cycle_vie": {},
            "rouvert_le": a, "rouvert_par": adm.get("email")}})
        frais = {"montant": params.get("frais_reouverture_montant"), "devise": params.get("frais_reouverture_devise"),
                 "encaisses": bool(frais_encaisses)}
        await db.archives_membres.update_one({"id": archive_id}, {"$set": {
            "statut": "ROUVERT", "rouvert_le": a, "rouvert_par": adm.get("email"), "frais": frais,
            "restaures": restaures}})
        await _journal("reouverture", fiche["user_id"], par=adm.get("email"), frais=frais, restaures=restaures)
        return {"ok": True, "restaures": restaures, "frais": frais, "user_id": fiche["user_id"]}
    finally:
        transfert_donnees._supprimer(local)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Lecture (administration, bandeau du membre)
# ---------------------------------------------------------------------------
async def info_membre(user: dict) -> Optional[dict]:
    """Dates prévues de suspension / suppression pour le bandeau du membre."""
    params = await parametres_plateforme.lire()
    if not params.get("cycle_actif") or _exclu(user):
        return None
    debut = _date(params.get("cycle_debut_le"))
    s = await situation(user, (debut or maintenant()).date())
    if s is None:
        etat = await abonnement_grace.etat(user["id"], user)
        if etat["statut"] != "expire":
            return None
        echeance = _date(etat["echeance"]).date()
        return {"suspension_le": _fmt(echeance + timedelta(days=J_SUSPENSION)),
                "suppression_le": _fmt(echeance + timedelta(days=J_SUPPRESSION))}
    return {"suspension_le": s["suspension_le"], "suppression_le": s["suppression_le"], "jours": s["jours"]}


async def etat_admin() -> dict:
    params = await parametres_plateforme.lire(cache=False)
    rapports = await db.cycle_vie_rapports.find({}, {"_id": 0}).sort("date", -1).to_list(15)
    archives = await db.archives_membres.find({}, {"_id": 0, "medias": 0}).sort("archive_le", -1).to_list(100)
    suspendus = await db.users.find({"statut_cycle": STATUT_SUSPENDU},
                                    {"_id": 0, "id": 1, "full_name": 1, "email": 1, "cycle_vie": 1}).to_list(200)
    return {"actif": params.get("cycle_actif"), "simulation": params.get("cycle_simulation"),
            "debut_le": params.get("cycle_debut_le"),
            "etapes": {"avertissement": J_AVERTISSEMENT, "suspension": J_SUSPENSION, "veille": J_VEILLE,
                       "suppression": J_SUPPRESSION},
            "conservation_archives_jours": params.get("conservation_archives_jours"),
            "frais_reouverture": {"montant": params.get("frais_reouverture_montant"),
                                  "devise": params.get("frais_reouverture_devise")},
            "sauvegarde_requise": sauvegarde_auto.motif_desactivation(),
            "rapports": rapports, "archives": archives, "suspendus": suspendus}
