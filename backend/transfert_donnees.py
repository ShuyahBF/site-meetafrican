"""Export et import COMPLETS de la base (changement de cluster MongoDB Atlas).

Usage prévu (administrateur principal, rôle « admin », uniquement) :
  1. sur l'ancien serveur : « Exporter toutes les données » -> fichier .baexport ;
  2. dans Render : remplacer MONGO_URL par l'adresse du nouveau cluster ;
  3. sur le nouveau serveur : « Importer » ce fichier (ou, si la nouvelle base
     ne contient AUCUN compte, « Restauration initiale » depuis la page de
     connexion, voir plus bas).

Contenu du fichier (avant chiffrement, voir chiffrement_flux.py) : une archive
ZIP avec
  - manifest.json : application « beauthentik », nom de la base, préfixe des
    collections, date UTC, version du format (1), et pour chaque collection
    son nombre de documents et ses index (tels que renvoyés par list_indexes) ;
  - collections/<nom>.jsonl : un document par ligne, en Extended JSON
    « canonique » (les types MongoDB sont conservés : dates, ObjectId,
    entiers 64 bits, décimaux, binaires...).

Collections exportées : toutes celles du projet, c'est-à-dire celles qui
portent le préfixe MONGO_COLLECTION_PREFIX (« maf_ ») — le cluster pouvant être
partagé avec d'autres projets, on ne touche jamais aux collections d'autrui.
Les noms sont écrits SANS le préfixe dans le fichier et recréés avec le
préfixe du serveur de destination.

Contraintes du serveur Render (mémoire limitée, requêtes longues
interrompues) : export et import tournent en TÂCHE DE FOND, par lots de 1000
documents, avec un fichier temporaire chiffré sur le disque (jamais de
données en clair sur le disque). Le navigateur suit la progression.

Mode « Base vide uniquement » — collections créées automatiquement au
démarrage d'un serveur neuf (server.py : ensure_indexes, seed_default_plans,
seed_default_gifts, ensure_admin_user, boucle VIDAL) ou par les toutes
premières requêtes (journal d'activité, compteur de visites), donc présentes
dans une base « vide » :
  - users : le compte admin créé depuis ADMIN_BOOTSTRAP_EMAIL /
    ADMIN_BOOTSTRAP_PASSWORD. Tolérée seulement si elle ne contient QUE des
    comptes de rôle « admin » ; vidée puis remplacée par les comptes du fichier ;
  - subscription_plans, gifts : formules et cadeaux par défaut. Tolérées
    seulement si elles ne contiennent que les codes par défaut ; vidées puis
    remplacées ;
  - settings : tolérée seulement si elle ne contient que le compteur de visites
    (« site_stats ») ; vidée puis remplacée ;
  - vidal_sync_config : réglage créé par la boucle VIDAL ; vidée puis remplacée ;
  - activity_log, site_visits, vidal_sync_log, journal_transferts,
    maintenance_plateforme, maintenance_plateforme_journal : traces et états
    du serveur ; jamais vidées, les lignes du fichier y sont AJOUTÉES (doublons
    ignorés). Un état de maintenance déjà présent dans la base de destination est
    donc conservé ; sinon, celui du fichier (maintenance annoncée avant l'export)
    est repris, et les membres restent bloqués jusqu'à la réactivation.
  Les index créés au démarrage ne comptent pas (une collection sans document
  est vide). Toute autre collection du fichier qui contient déjà des
  documents dans la base cible bloque l'import (utiliser alors « Remplacer »).

Restauration initiale (base neuve SANS AUCUN compte, donc personne ne peut se
connecter pour cliquer sur « Importer ») : possible SANS session, depuis la
page publique /restauration-initiale, uniquement si
  1. la collection des comptes est vide (si ADMIN_BOOTSTRAP_EMAIL est défini
     dans Render, le démarrage crée ce compte : on se connecte alors avec lui
     et on utilise l'import normal, mode « Base vide ») ;
  2. JWT_SECRET n'a pas sa valeur par défaut (publique) ;
  3. le fichier porte la signature d'un serveur partageant le même JWT_SECRET
     (inchangé sur Render quand seule MONGO_URL change) ;
  4. la phrase secrète ouvre le fichier ;
  5. l'e-mail (ou le téléphone) et le mot de passe saisis sont ceux d'un
     compte « admin » actif CONTENU DANS LE FICHIER — vérifiés avant toute
     écriture.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from bson import json_util
from bson.json_util import CANONICAL_JSON_OPTIONS
from fastapi import HTTPException
from pymongo.errors import BulkWriteError, PyMongoError

import chiffrement_flux
from auth import verify_password
from config import Settings, get_settings
from db import db
from seed import DEFAULT_GIFTS, DEFAULT_PLANS

logger = logging.getLogger(__name__)

APPLICATION = "beauthentik"
VERSION_FORMAT = 1
EXTENSION = ".baexport"
LOT = 1000  # documents lus / insérés à la fois
DUREE_VIE_SECONDES = 3600  # fichier d'export supprimé au bout d'une heure s'il n'est pas téléchargé
TAILLE_MAX_IMPORT = 4 * 1024 * 1024 * 1024  # 4 Go
LIGNE_MAX = 64 * 1024 * 1024  # un document MongoDB fait au plus 16 Mo (davantage en JSON)
MANIFEST_MAX = 64 * 1024 * 1024
MODES = ("vide", "remplacer")
MOT_REMPLACER = "REMPLACER"
# Mots de passe erronés tolérés par compte, sur 15 minutes
MAX_ECHECS_MOT_DE_PASSE = 5
# Rôle autorisé : l'administrateur principal (les modérateurs n'ont pas accès)
ROLE_AUTORISE = "admin"
# Valeur par défaut (publique, dans config.py) du secret JWT : la restauration
# initiale sans session est refusée tant qu'elle est utilisée.
SECRET_JWT_PAR_DEFAUT = Settings.model_fields["jwt_secret"].default

# Nom LOGIQUE (sans préfixe) du journal des exports / imports
JOURNAL = "journal_transferts"
# Collections techniques (noms logiques) : voir la docstring du module
TECHNIQUES_REMPLACEES = ("users", "subscription_plans", "gifts", "settings", "vidal_sync_config")
TECHNIQUES_FUSIONNEES = (JOURNAL, "activity_log", "site_visits", "vidal_sync_log",
                         "maintenance_plateforme", "maintenance_plateforme_journal",
                         # Sessions ouvertes (la connexion de l'administrateur qui importe en crée une),
                         # journaux de la sauvegarde automatique et du cycle de vie, paramètres
                         "sessions", "sauvegardes_auto", "cycle_vie_journal", "cycle_vie_rapports", "abonnements_journal",
                         "parametres_plateforme")
# Options d'index propres au serveur, à ne pas renvoyer à create_index
_OPTIONS_INDEX_IGNOREES = {"v", "key", "ns", "background", "textIndexVersion", "2dsphereIndexVersion"}

DOSSIER = Path(tempfile.gettempdir()) / "beauthentik_transferts"

# Tâches en cours ou récentes (mémoire du serveur) : id -> état. L'id est un
# jeton aléatoire de 256 bits, impossible à deviner.
_taches: dict[str, dict] = {}
# Références des tâches asyncio (sinon Python peut les détruire en cours de route)
_en_cours: dict[str, asyncio.Task] = {}
_boucle_nettoyage: dict[str, asyncio.Task] = {}


class ErreurTransfert(Exception):
    """Erreur expliquée à l'administrateur (message en français)."""


def base_brute():
    """Base MongoDB complète (sans préfixage automatique). Fonction séparée
    pour que les tests puissent la remplacer par une base neuve."""
    return db._database  # noqa: SLF001 — accès volontaire à la base entière


def _prefixe() -> str:
    return get_settings().mongo_collection_prefix or ""


def _physique(logique: str) -> str:
    """Nom réel d'une collection du projet (users -> maf_users)."""
    return f"{_prefixe()}{logique}"


def _maintenant_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cle_signature() -> bytes:
    return chiffrement_flux.cle_signature_serveur(get_settings().jwt_secret)


# ---------------------------------------------------------------------------
# Tâches de fond : état, nettoyage
# ---------------------------------------------------------------------------
def _maintenant() -> float:
    return time.time()


def tache_active() -> Optional[dict]:
    return next((t for t in _taches.values() if t["statut"] == "EN_COURS"), None)


def _nouvelle_tache(type_: str, user: dict) -> dict:
    if tache_active():
        raise HTTPException(409, "Un export ou un import est déjà en cours : attendez qu'il se termine")
    tache = {"id": secrets.token_urlsafe(32), "type": type_, "statut": "EN_COURS", "etape": "Préparation…",
             "progression": 0, "documents_traites": 0, "documents_total": 0, "debut": _maintenant_iso(),
             "fin": None, "erreur": None, "rapport": None, "par": user.get("email") or user.get("phone") or "",
             "_creee": _maintenant(), "_user": {"id": user.get("id"), "email": user.get("email") or user.get("phone") or ""}}
    _taches[tache["id"]] = tache
    return tache


def publique(tache: dict) -> dict:
    """État renvoyé au navigateur : jamais le chemin du fichier ni les secrets."""
    return {k: v for k, v in tache.items() if not k.startswith("_")}


def lire_tache(tache_id: str) -> dict:
    tache = _taches.get(tache_id)
    if not tache:
        raise HTTPException(404, "Opération introuvable ou expirée")
    return tache


def _supprimer(chemin: Optional[str]) -> None:
    if chemin:
        try:
            os.remove(chemin)
        except FileNotFoundError:
            pass


def nettoyer(tout: bool = False) -> None:
    """Supprime les fichiers temporaires expirés (tous, au démarrage) et oublie
    les tâches terminées depuis plus d'une heure."""
    limite = _maintenant() - DUREE_VIE_SECONDES
    actifs = {t.get("_chemin") for t in _taches.values() if t["statut"] == "EN_COURS"}
    if DOSSIER.exists():
        for f in DOSSIER.iterdir():
            try:
                if str(f) not in actifs and (tout or f.stat().st_mtime < limite):
                    f.unlink()
            except OSError:
                pass
    for tid, t in list(_taches.items()):
        if t["statut"] != "EN_COURS" and t.get("_fini", _maintenant()) < limite:
            _supprimer(t.get("_chemin"))
            _taches.pop(tid, None)
            _en_cours.pop(tid, None)


async def _boucle() -> None:
    while True:
        await asyncio.sleep(600)
        try:
            nettoyer()
        except Exception:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
            logger.exception("Nettoyage des fichiers de transfert")


async def au_demarrage() -> None:
    """Au démarrage du serveur : fichiers temporaires d'une exécution précédente
    supprimés, puis nettoyage toutes les 10 minutes."""
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    nettoyer(tout=True)
    if "boucle" not in _boucle_nettoyage or _boucle_nettoyage["boucle"].done():
        _boucle_nettoyage["boucle"] = asyncio.create_task(_boucle())


def _lancer(tache: dict, coroutine) -> None:
    _en_cours[tache["id"]] = asyncio.create_task(coroutine)


def _terminer(tache: dict, statut: str, erreur: Optional[str] = None) -> None:
    tache.update({"statut": statut, "erreur": erreur, "fin": _maintenant_iso(), "_fini": _maintenant()})
    if statut == "TERMINE":
        tache["progression"] = 100


# ---------------------------------------------------------------------------
# Ré-authentification et journal
# ---------------------------------------------------------------------------
async def journaliser(action: str, statut: str, user: dict, ip: Optional[str], **details: Any) -> None:
    """Trace de chaque export / import / téléchargement (jamais la phrase secrète)."""
    ligne = {"id": str(uuid.uuid4()), "date": _maintenant_iso(), "action": action, "statut": statut,
             "user_id": user.get("id"), "email": user.get("email") or user.get("phone") or "", "ip": ip, **details}
    try:
        await db[JOURNAL].insert_one(ligne)
    except PyMongoError:
        logger.exception("Journal des transferts indisponible")


async def verifier_mot_de_passe(user: dict, mot_de_passe: str, action: str, ip: Optional[str]) -> None:
    """Chaque action exige le mot de passe de l'administrateur (vérifié ici,
    côté serveur). Après 5 erreurs en 15 minutes, l'action est bloquée.
    Refus en 403 (et non 401) : une simple faute de frappe ne doit pas
    déconnecter l'administrateur."""
    depuis = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    echecs = await db[JOURNAL].count_documents({"user_id": user.get("id"), "statut": "MOT_DE_PASSE_REFUSE",
                                                "date": {"$gte": depuis}})
    if echecs >= MAX_ECHECS_MOT_DE_PASSE:
        raise HTTPException(429, "Trop de mots de passe erronés : réessayez dans 15 minutes")
    ok = False
    if mot_de_passe and user.get("password_hash"):
        try:
            ok = await asyncio.to_thread(verify_password, mot_de_passe, user["password_hash"])
        except ValueError:  # hachage illisible : refus, jamais une erreur 500
            ok = False
    if not ok:
        await journaliser(action, "MOT_DE_PASSE_REFUSE", user, ip)
        raise HTTPException(403, "Mot de passe incorrect")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _nom_fichier_export() -> str:
    nom_base = re.sub(r"[^A-Za-z0-9_-]+", "_", get_settings().mongo_db_name) or "base"
    return f"beauthentik_{nom_base}_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}{EXTENSION}"


async def collections_du_projet(base) -> list[str]:
    """Noms RÉELS des collections du projet (préfixées), hors collections système."""
    p = _prefixe()
    return sorted(n for n in await base.list_collection_names()
                  if not n.startswith("system.") and (not p or n.startswith(p)))


async def lancer_export(user: dict, phrase: str, ip: Optional[str]) -> dict:
    tache = _nouvelle_tache("export", user)
    tache.update({"fichier_nom": _nom_fichier_export(), "fichier_disponible": False, "taille": 0})
    tache["_chemin"] = str(DOSSIER / f"{tache['id']}{EXTENSION}")
    # Jeton du lien de téléchargement : remis au seul administrateur qui lance l'export
    tache["_jeton"] = secrets.token_urlsafe(32)
    await journaliser("export", "DEMARRE", user, ip, tache=tache["id"])
    _lancer(tache, _executer_export(tache, phrase, user, ip))
    return tache


async def ecrire_export(chemin: str, phrase: str, selection: Optional[dict[str, dict]] = None,
                        tache: Optional[dict] = None) -> list[dict]:
    """Écrit un fichier .baexport chiffré à `chemin` (via un fichier « .partiel »
    renommé à la fin) et renvoie la description des collections exportées.

    `selection` : None = toutes les collections du projet ; sinon
    {nom logique: filtre MongoDB} — seules ces collections, et dans chacune les
    seuls documents du filtre (archive d'un membre, voir cycle_vie.py).
    Réutilisé par la sauvegarde automatique (sauvegarde_auto.py) : même format,
    même chiffrement que l'export manuel."""
    partiel = chemin + ".partiel"
    try:
        Path(chemin).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        base = base_brute()
        p = _prefixe()
        if selection is None:
            noms = await collections_du_projet(base)
            filtres = {n: {} for n in noms}
        else:
            existantes = set(await base.list_collection_names())
            filtres = {_physique(n): q for n, q in selection.items()}
            noms = sorted(n for n in filtres if n in existantes)
        if tache is not None:
            tache["documents_total"] = sum([await base[n].estimated_document_count() for n in noms])
            tache["etape"] = "Préparation du chiffrement…"
        collections: list[dict] = []
        with open(partiel, "wb") as fichier:
            os.chmod(partiel, 0o600)
            ecrivain = await asyncio.to_thread(chiffrement_flux.EcrivainChiffre, fichier, phrase, _cle_signature())
            # zipfile écrit en « flux » (sans retour en arrière) dans le fichier chiffré
            archive = zipfile.ZipFile(ecrivain, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6)
            for nom_reel in noms:
                nom = nom_reel[len(p):] if p else nom_reel
                if tache is not None:
                    tache["etape"] = f"Export de « {nom} »…"
                collection = base[nom_reel]
                index = [dict(i) async for i in collection.list_indexes()]
                compte = 0
                with archive.open(f"collections/{nom}.jsonl", "w", force_zip64=True) as entree:
                    lignes: list[str] = []

                    async def _vider(lignes_: list[str]) -> None:
                        await asyncio.to_thread(entree.write, ("\n".join(lignes_) + "\n").encode("utf-8"))
                        if tache is not None:
                            tache["documents_traites"] += len(lignes_)
                            tache["progression"] = _pourcentage(tache)

                    async for doc in collection.find(filtres[nom_reel], batch_size=LOT):
                        lignes.append(json_util.dumps(doc, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False))
                        if len(lignes) >= LOT:
                            await _vider(lignes)
                            compte += len(lignes)
                            lignes = []
                    if lignes:
                        await _vider(lignes)
                        compte += len(lignes)
                collections.append({"nom": nom, "fichier": f"collections/{nom}.jsonl", "documents": compte,
                                    "index": index})
            manifest = {"application": APPLICATION, "version_format": VERSION_FORMAT,
                        "base": get_settings().mongo_db_name, "prefixe": p,
                        "date_utc": _maintenant_iso(), "collections": collections}
            if selection is not None:
                manifest["partiel"] = True  # archive limitée (un membre), pas toute la base
            archive.writestr("manifest.json", json_util.dumps(manifest, json_options=CANONICAL_JSON_OPTIONS,
                                                             ensure_ascii=False, indent=2).encode("utf-8"))
            await asyncio.to_thread(archive.close)
            await asyncio.to_thread(ecrivain.fermer_flux)
        os.replace(partiel, chemin)
        return collections
    except BaseException:
        _supprimer(partiel)
        raise


async def _executer_export(tache: dict, phrase: str, user: dict, ip: Optional[str]) -> None:
    chemin = tache["_chemin"]
    try:
        collections = await ecrire_export(chemin, phrase, tache=tache)
        total = sum(c["documents"] for c in collections)
        tache.update({"etape": "Export terminé : le fichier est prêt à être téléchargé", "fichier_disponible": True,
                      "taille": os.path.getsize(chemin), "documents_traites": total, "documents_total": total,
                      "rapport": {"collections": [{"nom": c["nom"], "documents": c["documents"]} for c in collections],
                                  "documents": total}})
        _terminer(tache, "TERMINE")
        await journaliser("export", "TERMINE", user, ip, tache=tache["id"], collections=len(collections),
                          documents=total, taille=tache["taille"])
    except Exception as exc:  # noqa: BLE001 — l'erreur est rapportée à l'administrateur
        logger.exception("Échec de l'export complet")
        _supprimer(chemin)
        _terminer(tache, "ECHEC", str(exc) if isinstance(exc, ErreurTransfert) else f"L'export a échoué : {exc}")
        await journaliser("export", "ECHEC", user, ip, tache=tache["id"], erreur=str(exc)[:300])


def _pourcentage(tache: dict) -> int:
    total = tache["documents_total"] or 1
    return min(99, int(tache["documents_traites"] * 100 / total))


async def fichier_export(tache_id: str, jeton: str, ip: Optional[str]) -> tuple[str, str]:
    """Chemin et nom du fichier d'export à télécharger (une seule fois).
    Le lien est protégé par un jeton aléatoire (256 bits) remis au seul
    administrateur qui a lancé l'export — et le fichier reste chiffré."""
    tache = lire_tache(tache_id)
    attendu = tache.get("_jeton") or ""
    if tache["type"] != "export" or not attendu or not secrets.compare_digest(jeton or "", attendu):
        raise HTTPException(403, "Lien de téléchargement invalide")
    if tache["statut"] != "TERMINE" or not tache.get("fichier_disponible"):
        raise HTTPException(404, "Fichier indisponible (déjà téléchargé ou expiré) : relancez l'export")
    if not os.path.exists(tache["_chemin"]):
        tache["fichier_disponible"] = False
        raise HTTPException(404, "Fichier expiré : relancez l'export")
    # Téléchargement unique : le lien ne sert plus, même si l'envoi est en cours
    tache["fichier_disponible"] = False
    await journaliser("telechargement_export", "TERMINE", tache["_user"], ip, tache=tache_id, taille=tache.get("taille"))
    return tache["_chemin"], tache["fichier_nom"]


def apres_telechargement(tache_id: str) -> None:
    """Le fichier d'export est supprimé du serveur dès qu'il a été envoyé."""
    tache = _taches.get(tache_id)
    if tache:
        _supprimer(tache.get("_chemin"))
        tache["fichier_disponible"] = False


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
async def _recevoir(upload, tache: dict, phrase: str) -> int:
    """Enregistre le fichier envoyé sur le disque (par morceaux) puis contrôle
    la phrase secrète sur l'en-tête (réponse immédiate si elle est fausse)."""
    chemin = tache["_chemin"]
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    tache["etape"] = "Réception du fichier…"
    taille = 0
    with open(chemin, "wb") as f:
        os.chmod(chemin, 0o600)
        while True:
            morceau = await upload.read(1024 * 1024)
            if not morceau:
                break
            taille += len(morceau)
            if taille > TAILLE_MAX_IMPORT:
                raise HTTPException(413, "Fichier trop volumineux")
            await asyncio.to_thread(f.write, morceau)
    if not taille:
        raise HTTPException(400, "Aucun fichier reçu")
    tache["taille"] = taille

    def _controle() -> None:
        with open(chemin, "rb") as f:
            chiffrement_flux.ouvrir_cle(chiffrement_flux.lire_entete(f), phrase)

    try:
        await asyncio.to_thread(_controle)
    except chiffrement_flux.ErreurChiffrement as exc:
        raise HTTPException(400, str(exc)) from exc
    return taille


async def preparer_import(user: dict, upload, phrase: str, mode: str, ip: Optional[str]) -> dict:
    """Import par l'administrateur connecté : réception, contrôle de la phrase,
    puis import en tâche de fond."""
    tache = _nouvelle_tache("import", user)
    tache.update({"mode": mode, "fichier_nom": getattr(upload, "filename", "") or "",
                  "_chemin": str(DOSSIER / f"{tache['id']}.import")})
    try:
        taille = await _recevoir(upload, tache, phrase)
    except BaseException:
        _supprimer(tache["_chemin"])
        _taches.pop(tache["id"], None)
        raise
    await journaliser("import", "DEMARRE", user, ip, tache=tache["id"], mode=mode, taille=taille)
    _lancer(tache, _executer_import(tache, phrase, mode, user, ip))
    return tache


# --- Restauration initiale (base sans aucun compte, sans session) ---
async def motif_restauration_impossible() -> Optional[str]:
    """None si la restauration initiale sans session est permise, sinon la raison."""
    secret = get_settings().jwt_secret or ""
    if not secret or secret == SECRET_JWT_PAR_DEFAUT:
        return "Le secret JWT_SECRET du serveur a sa valeur par défaut : restauration initiale désactivée."
    if await base_brute()[_physique("users")].count_documents({}, limit=1):
        return ("La base contient déjà des comptes : connectez-vous avec un compte administrateur puis "
                "utilisez « Importer » dans l'espace d'administration (Données & maintenance).")
    return None


async def preparer_import_initial(upload, phrase: str, identifiant: str, mot_de_passe: str,
                                  ip: Optional[str]) -> dict:
    motif = await motif_restauration_impossible()
    if motif:
        raise HTTPException(403, motif)
    utilisateur = {"id": None, "email": identifiant}
    tache = _nouvelle_tache("import_initial", utilisateur)
    tache.update({"mode": "vide", "fichier_nom": getattr(upload, "filename", "") or "",
                  "_chemin": str(DOSSIER / f"{tache['id']}.import"),
                  "_identifiant": identifiant, "_mot_de_passe": mot_de_passe})
    try:
        taille = await _recevoir(upload, tache, phrase)
    except BaseException:
        _supprimer(tache["_chemin"])
        _taches.pop(tache["id"], None)
        raise
    await journaliser("restauration_initiale", "DEMARRE", utilisateur, ip, tache=tache["id"], taille=taille)
    _lancer(tache, _executer_import(tache, phrase, "vide", utilisateur, ip))
    return tache


def _valider_manifest(manifest: Any, archive: zipfile.ZipFile) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("application") != APPLICATION:
        raise ErreurTransfert("Ce fichier ne provient pas de beAuthentik")
    if manifest.get("version_format") != VERSION_FORMAT:
        raise ErreurTransfert(f"Version du fichier non prise en charge ({manifest.get('version_format')})")
    if manifest.get("partiel"):
        # Archive d'UN membre (cycle de vie) : ne doit jamais remplacer toute la base
        raise ErreurTransfert("Ce fichier est l'archive d'un seul membre : utilisez « Rouvrir » dans "
                              "Abonnements & cycle de vie, pas l'import complet")
    collections = manifest.get("collections")
    if not isinstance(collections, list):
        raise ErreurTransfert("Fichier invalide : liste des collections absente")
    noms = set(archive.namelist())
    vus = set()
    for c in collections:
        nom = c.get("nom") if isinstance(c, dict) else None
        if (not isinstance(nom, str) or not nom or len(nom) > 200 or "$" in nom or "\0" in nom
                or "/" in nom or nom.startswith("system.") or nom in vus):
            raise ErreurTransfert(f"Fichier invalide : nom de collection incorrect ({nom!r})")
        vus.add(nom)
        if c.get("fichier") != f"collections/{nom}.jsonl" or c["fichier"] not in noms:
            raise ErreurTransfert(f"Fichier invalide : données de « {nom} » absentes")
        if not isinstance(c.get("documents"), int) or not isinstance(c.get("index", []), list):
            raise ErreurTransfert(f"Fichier invalide : description de « {nom} » incorrecte")
    return collections


async def _remplacable(base, logique: str) -> bool:
    """Mode « base vide » : une collection technique déjà remplie au démarrage
    peut-elle être remplacée sans risque ? (voir la docstring du module)"""
    collection = base[_physique(logique)]
    if logique == "users":
        return await collection.count_documents({"role": {"$ne": ROLE_AUTORISE}}) == 0
    if logique == "subscription_plans":
        codes = [p.code for p in DEFAULT_PLANS]
        return await collection.count_documents({"code": {"$nin": codes}}) == 0
    if logique == "gifts":
        codes = [g.code for g in DEFAULT_GIFTS]
        return await collection.count_documents({"code": {"$nin": codes}}) == 0
    if logique == "settings":
        return await collection.count_documents({"id": {"$ne": "site_stats"}}) == 0
    return logique in TECHNIQUES_REMPLACEES or logique in TECHNIQUES_FUSIONNEES


def definition_vers_index(definition: dict) -> tuple[list, dict]:
    """Transforme une définition renvoyée par list_indexes en arguments de
    create_index. Index texte : MongoDB les décrit avec les clés internes
    « _fts / _ftsx » ; les champs indexés sont alors reconstruits depuis
    `weights`."""
    cle = list(dict(definition["key"]).items())
    noms = [k for k, _ in cle]
    if "_fts" in noms:
        poids = dict(definition.get("weights") or {})
        # Champs ordinaires placés avant _fts (préfixe) et après _ftsx (suffixe)
        debut_texte = noms.index("_fts")
        fin_texte = noms.index("_ftsx") if "_ftsx" in noms else debut_texte
        avant = list(cle[:debut_texte])
        apres = [(k, v) for k, v in cle[fin_texte + 1:] if k not in ("_fts", "_ftsx")]
        cle = avant + [(champ, "text") for champ in poids] + apres
    options = {k: v for k, v in dict(definition).items() if k not in _OPTIONS_INDEX_IGNOREES}
    return cle, options


def _lecteur_lignes(archive: zipfile.ZipFile, fichier: str):
    """Documents d'un fichier .jsonl, lus ligne par ligne (jamais en entier)."""
    with archive.open(fichier) as flux:
        while True:
            ligne = flux.readline(LIGNE_MAX + 1)
            if not ligne:
                return
            if len(ligne) > LIGNE_MAX:
                raise ErreurTransfert(f"Document trop volumineux dans {fichier}")
            ligne = ligne.strip()
            if ligne:
                yield json_util.loads(ligne.decode("utf-8"), json_options=CANONICAL_JSON_OPTIONS)


def _lot_suivant(generateur) -> list:
    lot = []
    for doc in generateur:
        lot.append(doc)
        if len(lot) >= LOT:
            break
    return lot


def _verifier_identifiants_dans_fichier(archive: zipfile.ZipFile, collections: list[dict],
                                        identifiant: str, mot_de_passe: str) -> None:
    """Restauration initiale : l'identifiant (e-mail ou téléphone) et le mot de
    passe saisis doivent être ceux d'un compte « admin » ACTIF contenu dans le
    fichier — vérifié AVANT toute écriture en base."""
    refus = ErreurTransfert("Identifiants refusés : ils ne correspondent à aucun administrateur actif "
                            "contenu dans le fichier. Aucune donnée n'a été modifiée.")
    entree = next((c for c in collections if c["nom"] == "users"), None)
    identifiant = (identifiant or "").strip()
    if entree is None or not identifiant or not mot_de_passe:
        raise refus
    for utilisateur in _lecteur_lignes(archive, entree["fichier"]):
        if identifiant not in (utilisateur.get("email"), utilisateur.get("phone")):
            continue
        hache = utilisateur.get("password_hash") or ""
        if utilisateur.get("role") == ROLE_AUTORISE and utilisateur.get("is_active", True) and hache:
            try:
                if verify_password(mot_de_passe, hache):
                    return
            except ValueError:
                pass
        raise refus
    raise refus


async def _executer_import(tache: dict, phrase: str, mode: str, user: dict, ip: Optional[str]) -> None:
    chemin = tache["_chemin"]
    initiale = tache["type"] == "import_initial"
    identifiant = tache.pop("_identifiant", None)
    mot_de_passe = tache.pop("_mot_de_passe", None)
    action = "restauration_initiale" if initiale else "import"
    lecteur = archive = None
    try:
        # 1. Vérification COMPLÈTE du fichier avant de toucher à la base
        tache["etape"] = "Vérification du fichier (déchiffrement)…"

        def _progression(lu: int, total: int) -> None:
            tache["progression"] = min(20, int(lu * 20 / max(total, 1)))

        try:
            lecteur = await asyncio.to_thread(chiffrement_flux.LecteurChiffre, chemin, phrase, _cle_signature(),
                                              _progression)
            phrase = None
            archive = await asyncio.to_thread(zipfile.ZipFile, lecteur)
            info = archive.getinfo("manifest.json")
            if info.file_size > MANIFEST_MAX:
                raise ErreurTransfert("Fichier invalide : description trop volumineuse")
            manifest = json_util.loads((await asyncio.to_thread(archive.read, "manifest.json")).decode("utf-8"),
                                       json_options=CANONICAL_JSON_OPTIONS)
        except chiffrement_flux.ErreurChiffrement as exc:
            raise ErreurTransfert(str(exc)) from exc
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise ErreurTransfert("Fichier invalide : contenu illisible") from exc
        collections = _valider_manifest(manifest, archive)
        tache["documents_total"] = sum(c["documents"] for c in collections)
        tache["source"] = {"base": manifest.get("base"), "date_utc": manifest.get("date_utc")}

        base = base_brute()
        if initiale:
            # Garde-fous de la restauration sans session (voir la docstring du module)
            if not lecteur.signature_valide:
                raise ErreurTransfert(
                    "Restauration initiale refusée : ce fichier n'a pas été produit par un serveur beAuthentik "
                    "utilisant le même JWT_SECRET (gardez la même valeur dans Render). Aucune donnée n'a été modifiée.")
            tache["etape"] = "Contrôle des identifiants dans le fichier…"
            await asyncio.to_thread(_verifier_identifiants_dans_fichier, archive, collections,
                                    identifiant or "", mot_de_passe or "")
            motif = await motif_restauration_impossible()
            if motif:
                raise ErreurTransfert(motif)
        mot_de_passe = None

        # 2. Contrôle de la base cible selon le mode choisi
        tache["etape"] = "Contrôle de la base de destination…"
        existants = {c["nom"]: await base[_physique(c["nom"])].count_documents({}) for c in collections}
        if mode == "vide":
            bloquantes = [n for n, nb in existants.items() if nb and not await _remplacable(base, n)]
            if bloquantes:
                raise ErreurTransfert(
                    "La base de destination contient déjà des données (" + ", ".join(sorted(bloquantes)[:10])
                    + (" …" if len(bloquantes) > 10 else "") + "). Aucune donnée n'a été modifiée. "
                    "Choisissez le mode « Remplacer » si vous voulez écraser ces données.")

        # 3. Import collection par collection
        rapport: list[dict] = []
        avertissements: list[str] = []
        for c in collections:
            nom = c["nom"]
            collection = base[_physique(nom)]
            tache["etape"] = f"Import de « {nom} »…"
            if existants[nom] and nom not in TECHNIQUES_FUSIONNEES:
                # « Remplacer », ou collection technique créée au démarrage (mode « base vide »)
                await collection.delete_many({})
            inseres = doublons = lus = 0
            generateur = _lecteur_lignes(archive, c["fichier"])
            while True:
                lot = await asyncio.to_thread(_lot_suivant, generateur)
                if not lot:
                    break
                lus += len(lot)
                try:
                    resultat = await collection.insert_many(lot, ordered=False)
                    inseres += len(resultat.inserted_ids)
                except BulkWriteError as exc:
                    details = exc.details or {}
                    inseres += details.get("nInserted", 0)
                    erreurs = details.get("writeErrors", [])
                    doublons += sum(1 for e in erreurs if e.get("code") == 11000)
                    autres = [e for e in erreurs if e.get("code") != 11000]
                    if autres:
                        avertissements.append(f"{nom} : {len(autres)} document(s) refusé(s) ({str(autres[0].get('errmsg', ''))[:120]})")
                tache["documents_traites"] += len(lot)
                tache["progression"] = 20 + int(tache["documents_traites"] * 75 / max(tache["documents_total"], 1))
            if doublons and nom not in TECHNIQUES_FUSIONNEES:
                avertissements.append(f"{nom} : {doublons} document(s) en double ignoré(s)")
            if lus != c["documents"]:
                avertissements.append(f"{nom} : {lus} document(s) lu(s) au lieu de {c['documents']} annoncé(s)")
            # Index (sauf _id_, créé d'office) — un index déjà présent et identique est sans effet
            index_crees = 0
            for definition in c.get("index", []):
                if definition.get("name") == "_id_":
                    continue
                try:
                    cle, options = definition_vers_index(definition)
                    await collection.create_index(cle, **options)
                    index_crees += 1
                except Exception as exc:  # noqa: BLE001 — signalé dans le rapport
                    avertissements.append(f"{nom} : index « {definition.get('name')} » non recréé ({str(exc)[:120]})")
            rapport.append({"nom": nom, "attendus": c["documents"], "importes": inseres,
                            "dans_la_base": await collection.count_documents({}), "index": index_crees})

        # 4. Comparaison des nombres de documents
        tache["etape"] = "Vérification des nombres de documents…"
        ecarts = [r["nom"] for r in rapport if r["dans_la_base"] < r["attendus"]
                  or (r["nom"] not in TECHNIQUES_FUSIONNEES and r["dans_la_base"] != r["attendus"])]
        for nom in ecarts:
            avertissements.append(f"{nom} : le nombre de documents ne correspond pas au fichier")
        if manifest.get("base") != get_settings().mongo_db_name:
            avertissements.append(f"Base d'origine « {manifest.get('base')} », importée dans « {get_settings().mongo_db_name} »")
        tache["rapport"] = {"collections": rapport, "avertissements": avertissements, "conforme": not ecarts,
                            "documents": sum(r["importes"] for r in rapport),
                            "signature_reconnue": lecteur.signature_valide}
        tache["etape"] = "Import terminé"
        _terminer(tache, "TERMINE")
        await journaliser(action, "TERMINE", user, ip, tache=tache["id"], mode=mode, collections=len(rapport),
                          documents=tache["rapport"]["documents"], ecarts=ecarts)
    except Exception as exc:  # noqa: BLE001 — l'erreur est rapportée à l'administrateur
        if not isinstance(exc, ErreurTransfert):
            logger.exception("Échec de l'import complet")
        message = str(exc) if isinstance(exc, ErreurTransfert) else f"L'import a échoué : {exc}"
        _terminer(tache, "ECHEC", message)
        await journaliser(action, "ECHEC", user, ip, tache=tache["id"], mode=mode, erreur=message[:300])
    finally:
        for objet in (archive, lecteur):
            if objet is not None:
                try:
                    objet.close()
                except Exception:  # noqa: BLE001
                    pass
        _supprimer(chemin)  # le fichier importé ne reste jamais sur le serveur
        # L'état de maintenance a pu changer (collections fusionnées) : relu aussitôt
        try:
            import maintenance_plateforme
            maintenance_plateforme.vider_cache()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Informations pour la page d'administration
# ---------------------------------------------------------------------------
async def etat_base() -> dict:
    base = base_brute()
    noms = await collections_du_projet(base)
    documents = 0
    for n in noms:
        documents += await base[n].estimated_document_count()
    active = tache_active()
    historique = await db[JOURNAL].find({}, {"_id": 0}).sort("date", -1).to_list(20)
    tache_en_cours = None
    if active:
        tache_en_cours = publique(active)
        if active["type"] == "export":
            tache_en_cours["jeton_telechargement"] = active.get("_jeton")
    return {"base": get_settings().mongo_db_name, "prefixe": _prefixe(), "collections": len(noms),
            "documents": documents, "tache_en_cours": tache_en_cours, "historique": historique,
            "phrase_min": chiffrement_flux.PHRASE_MIN, "extension": EXTENSION}


# Dossier temporaire privé, créé dès le chargement du module
try:
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
except OSError:  # pragma: no cover — disque en lecture seule : créé plus tard
    pass
