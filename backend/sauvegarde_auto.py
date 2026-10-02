"""Sauvegarde générale AUTOMATIQUE de la base vers Cloudflare R2 (spécification E,
règle R3), et dépôt R2 commun aux archives de membres (cycle_vie.py).

  - Contenu : export COMPLET, même format et même chiffrement que l'export manuel
    « Exporter toutes les données » (fichier .baexport, transfert_donnees.py), avec
    la phrase lue dans SAUVEGARDE_AUTO_PHRASE (12 caractères minimum). Sans phrase
    (ou sans stockage R2), la sauvegarde est DÉSACTIVÉE et une alerte s'affiche
    dans l'administration.
  - Déclenchement : POST /api/sauvegarde-auto/declencher avec l'en-tête secret
    X-Sauvegarde-Jeton (= SAUVEGARDE_AUTO_JETON, comparaison à temps constant),
    appelé chaque nuit par un « Cron Job » Render (le serveur gratuit peut dormir :
    l'appel le réveille). La route répond tout de suite (202) et la sauvegarde
    tourne en tâche de fond ; elle est IDEMPOTENTE sur la journée (UTC) : une
    sauvegarde déjà réussie le jour même n'est pas refaite. Le même appel lance
    ensuite la tâche quotidienne du cycle de vie (cycle_vie.py).
  - Stockage : identifiants R2 dédiés BEAUTHENTIK_SAUVEGARDES_R2_* s'ils existent,
    sinon RÉUTILISATION documentée de ceux des médias (R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY) ; bucket BEAUTHENTIK_SAUVEGARDES_BUCKET,
    sinon le bucket PRIVÉ R2_BUCKET_DOCUMENTS (jamais le bucket public des photos),
    sous le dossier BEAUTHENTIK_SAUVEGARDES_PREFIXE (« sauvegardes-beauthentik/ ») :
      <prefixe>generales/beauthentik_AAAAMMJJ-HHMMSS.baexport
      <prefixe>archives-locataires/<id du membre>/...   (cycle de vie)
  - Rétention : 7 quotidiennes + 4 hebdomadaires + 12 mensuelles (la plus récente
    de chaque jour / semaine ISO / mois) ; les autres sont effacées après chaque
    sauvegarde réussie.
  - Rapport : beAuthentik n'a pas d'envoi d'e-mail ; en cas d'échec, alerte par
    WhatsApp / SMS aux administrateurs principaux (envoi_messages.py) et alerte
    dans l'administration si la dernière réussite a plus de 26 h.
  - Restauration : depuis la liste des sauvegardes R2, en mode « Remplacer » avec
    les garde-fous existants (mot de passe de l'administrateur, mot REMPLACER),
    par l'import de transfert_donnees.py (suivi de progression identique).

Journal : `maf_sauvegardes_auto` (une ligne par jour, _id « jour:AAAA-MM-JJ »).
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import chiffrement_flux
import envoi_messages
import transfert_donnees
from config import get_settings
from db import db

logger = logging.getLogger(__name__)

DOSSIER_GENERALES = "generales/"
DOSSIER_ARCHIVES = "archives-locataires/"
RETENTION = {"quotidiennes": 7, "hebdomadaires": 4, "mensuelles": 12}
ALERTE_HEURES = 26
DUREE_MAX_EN_COURS = timedelta(hours=3)  # au-delà, une sauvegarde « en cours » est considérée interrompue
_MOTIF_DATE = re.compile(r"(\d{8})-(\d{6})")

# Références des tâches de fond (sinon Python peut les détruire en cours de route)
_taches: set = set()


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Dépôt (R2, ou dossier local en développement / tests)
# ---------------------------------------------------------------------------
class DepotLocal:
    """Dossier local qui imite R2 — développement et tests UNIQUEMENT."""
    nom = "local"

    def __init__(self, dossier: str):
        self.racine = Path(dossier)
        self.bucket = str(self.racine)

    def _chemin(self, cle: str) -> Path:
        chemin = (self.racine / cle).resolve()
        if self.racine.resolve() not in chemin.parents:
            raise ValueError("Clé invalide")
        return chemin

    def envoyer(self, source: str, cle: str) -> None:
        cible = self._chemin(cle)
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, cible)

    def telecharger(self, cle: str, destination: str) -> None:
        shutil.copyfile(self._chemin(cle), destination)

    def lister(self, prefixe: str) -> list[dict]:
        base = self._chemin(prefixe.rstrip("/") or ".") if prefixe else self.racine
        if not base.exists():
            return []
        objets = []
        for f in base.rglob("*"):
            if f.is_file():
                objets.append({"cle": str(f.relative_to(self.racine)).replace(os.sep, "/"), "taille": f.stat().st_size,
                               "date": datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).isoformat()})
        return objets

    def supprimer(self, cle: str) -> None:
        self._chemin(cle).unlink(missing_ok=True)


class DepotR2:
    """Cloudflare R2 (API compatible S3, boto3) — envoi/lecture en flux (multipart)."""
    nom = "r2"

    def __init__(self, compte: str, cle: str, secret: str, bucket: str):
        self._compte, self._cle, self._secret, self.bucket = compte, cle, secret, bucket

    def _client(self):
        import boto3
        return boto3.client("s3", endpoint_url=f"https://{self._compte}.r2.cloudflarestorage.com",
                            aws_access_key_id=self._cle, aws_secret_access_key=self._secret, region_name="auto")

    def envoyer(self, source: str, cle: str) -> None:
        self._client().upload_file(source, self.bucket, cle, ExtraArgs={"ContentType": "application/octet-stream"})

    def telecharger(self, cle: str, destination: str) -> None:
        self._client().download_file(self.bucket, cle, destination)

    def lister(self, prefixe: str) -> list[dict]:
        objets = []
        pages = self._client().get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefixe)
        for page in pages:
            for o in page.get("Contents", []):
                objets.append({"cle": o["Key"], "taille": o.get("Size", 0),
                               "date": o["LastModified"].astimezone(timezone.utc).isoformat()})
        return objets

    def supprimer(self, cle: str) -> None:
        self._client().delete_object(Bucket=self.bucket, Key=cle)


def depot():
    """Dépôt configuré, ou None (sauvegarde désactivée)."""
    s = get_settings()
    if s.beauthentik_sauvegardes_dossier_local:
        return DepotLocal(s.beauthentik_sauvegardes_dossier_local)
    compte = s.beauthentik_sauvegardes_r2_account_id or s.r2_account_id
    cle = s.beauthentik_sauvegardes_r2_access_key_id or s.r2_access_key_id
    secret = s.beauthentik_sauvegardes_r2_secret_access_key or s.r2_secret_access_key
    bucket = s.beauthentik_sauvegardes_bucket or s.r2_bucket_documents
    if compte and cle and secret and bucket:
        return DepotR2(compte, cle, secret, bucket)
    return None


def prefixe() -> str:
    p = (get_settings().beauthentik_sauvegardes_prefixe or "").strip().lstrip("/")
    return p if not p or p.endswith("/") else p + "/"


def phrase() -> Optional[str]:
    """Phrase de SAUVEGARDE_AUTO_PHRASE si elle est valable, sinon None."""
    brute = get_settings().sauvegarde_auto_phrase
    if not brute:
        return None
    try:
        return chiffrement_flux.valider_phrase(brute)
    except chiffrement_flux.ErreurChiffrement:
        return None


def motif_desactivation() -> Optional[str]:
    if not get_settings().sauvegarde_auto_phrase:
        return "Variable SAUVEGARDE_AUTO_PHRASE absente : sauvegarde automatique désactivée."
    if phrase() is None:
        return (f"SAUVEGARDE_AUTO_PHRASE trop courte ({chiffrement_flux.PHRASE_MIN} caractères minimum) : "
                "sauvegarde automatique désactivée.")
    if depot() is None:
        return "Stockage R2 non configuré (identifiants R2 absents) : sauvegarde automatique désactivée."
    return None


def jeton_valide(recu: Optional[str]) -> bool:
    """Comparaison à temps constant avec SAUVEGARDE_AUTO_JETON (absent = toujours refusé)."""
    attendu = get_settings().sauvegarde_auto_jeton or ""
    return bool(attendu) and hmac.compare_digest((recu or "").encode(), attendu.encode())


# ---------------------------------------------------------------------------
# Rétention 7 / 4 / 12
# ---------------------------------------------------------------------------
def _date_objet(objet: dict) -> datetime:
    m = _MOTIF_DATE.search(objet["cle"].rsplit("/", 1)[-1])
    if m:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(objet["date"])


def a_conserver(objets: list[dict]) -> set[str]:
    """Clés conservées : la plus récente de chacun des 7 derniers jours, des 4
    dernières semaines ISO et des 12 derniers mois où une sauvegarde existe."""
    tries = sorted(objets, key=_date_objet, reverse=True)
    garder: set[str] = set()
    for nombre, periode in ((RETENTION["quotidiennes"], lambda d: d.date()),
                            (RETENTION["hebdomadaires"], lambda d: tuple(d.isocalendar())[:2]),
                            (RETENTION["mensuelles"], lambda d: (d.year, d.month))):
        vues: set = set()
        for o in tries:
            p = periode(_date_objet(o))
            if p in vues:
                continue
            if len(vues) >= nombre:
                break
            vues.add(p)
            garder.add(o["cle"])
    return garder


async def appliquer_retention(dep) -> list[str]:
    objets = await asyncio.to_thread(dep.lister, prefixe() + DOSSIER_GENERALES)
    garder = a_conserver(objets)
    supprimees = [o["cle"] for o in objets if o["cle"] not in garder]
    for cle in supprimees:
        await asyncio.to_thread(dep.supprimer, cle)
    return supprimees


# ---------------------------------------------------------------------------
# Exécution
# ---------------------------------------------------------------------------
def _id_jour(a: Optional[datetime] = None) -> str:
    return f"jour:{(a or maintenant()).date().isoformat()}"


async def _reserver_journee() -> Optional[dict]:
    """Réserve la sauvegarde du jour. None si elle est déjà faite ou en cours."""
    jour = _id_jour()
    debut = maintenant()
    ligne = {"_id": jour, "jour": jour[5:], "statut": "EN_COURS", "debut": debut.isoformat(), "fin": None,
             "erreur": None, "tentatives": 1}
    try:
        await db.sauvegardes_auto.insert_one(dict(ligne))
        return ligne
    except DuplicateKeyError:
        existant = await db.sauvegardes_auto.find_one({"_id": jour}) or {}
    if existant.get("statut") == "REUSSIE":
        return None
    if existant.get("statut") == "EN_COURS":
        commence = datetime.fromisoformat(existant["debut"])
        if debut - commence < DUREE_MAX_EN_COURS:
            return None
    # Échec (ou tentative interrompue) plus tôt dans la journée : nouvel essai
    res = await db.sauvegardes_auto.update_one(
        {"_id": jour, "statut": existant.get("statut")},
        {"$set": {"statut": "EN_COURS", "debut": debut.isoformat(), "fin": None, "erreur": None},
         "$inc": {"tentatives": 1}})
    return ligne if res.modified_count else None


async def executer(force_motif: Optional[str] = None) -> dict:
    """Sauvegarde du jour (idempotente). Renvoie un petit rapport."""
    motif = motif_desactivation()
    if motif:
        await db.sauvegardes_auto.update_one({"_id": "etat"}, {"$set": {
            "derniere_tentative_desactivee": maintenant().isoformat(), "motif": motif}}, upsert=True)
        return {"statut": "DESACTIVEE", "motif": motif}
    ligne = await _reserver_journee()
    if ligne is None:
        return {"statut": "DEJA_FAITE_OU_EN_COURS"}
    dep = depot()
    horodatage = maintenant().strftime("%Y%m%d-%H%M%S")
    cle = f"{prefixe()}{DOSSIER_GENERALES}beauthentik_{horodatage}{transfert_donnees.EXTENSION}"
    chemin = str(transfert_donnees.DOSSIER / f"auto-{secrets.token_hex(8)}{transfert_donnees.EXTENSION}")
    try:
        collections = await transfert_donnees.ecrire_export(chemin, phrase())
        taille = os.path.getsize(chemin)
        await asyncio.to_thread(dep.envoyer, chemin, cle)
        # Contrôle : l'objet est bien présent sur R2 avec la bonne taille
        presents = {o["cle"]: o for o in await asyncio.to_thread(dep.lister, prefixe() + DOSSIER_GENERALES)}
        if cle not in presents or int(presents[cle]["taille"]) != taille:
            raise RuntimeError("Le fichier envoyé sur R2 est introuvable ou incomplet")
        supprimees = await appliquer_retention(dep)
        rapport = {"statut": "REUSSIE", "fin": maintenant().isoformat(), "cle": cle, "taille": taille,
                   "documents": sum(c["documents"] for c in collections), "collections": len(collections),
                   "supprimees_retention": len(supprimees), "stockage": dep.nom}
        await db.sauvegardes_auto.update_one({"_id": ligne["_id"]}, {"$set": rapport})
        return rapport
    except Exception as exc:  # noqa: BLE001 — rapporté dans le journal et aux administrateurs
        logger.exception("Échec de la sauvegarde automatique")
        erreur = str(exc)[:300]
        await db.sauvegardes_auto.update_one({"_id": ligne["_id"]}, {"$set": {
            "statut": "ECHEC", "fin": maintenant().isoformat(), "erreur": erreur}})
        try:
            await envoi_messages.alerter_administrateurs(
                f"beAuthentik : ÉCHEC de la sauvegarde automatique du {ligne['jour']} ({erreur[:150]}).")
        except Exception:  # noqa: BLE001
            pass
        return {"statut": "ECHEC", "erreur": erreur}
    finally:
        transfert_donnees._supprimer(chemin)  # noqa: SLF001 — jamais de fichier laissé sur le serveur


async def executer_nuit() -> dict:
    """Appel du Cron Job : sauvegarde générale puis tâche quotidienne du cycle de vie."""
    rapport = {"sauvegarde": await executer()}
    try:
        import cycle_vie
        rapport["cycle_vie"] = await cycle_vie.executer_quotidien(declencheur="cron")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Cycle de vie : échec de la tâche quotidienne")
        rapport["cycle_vie"] = {"statut": "ECHEC", "erreur": str(exc)[:300]}
    return rapport


def lancer_en_fond(coroutine) -> None:
    tache = asyncio.create_task(coroutine)
    _taches.add(tache)
    tache.add_done_callback(_taches.discard)


# ---------------------------------------------------------------------------
# Lecture (administration, « Dernière sauvegarde » des membres)
# ---------------------------------------------------------------------------
async def derniere_reussite() -> Optional[dict]:
    return await db.sauvegardes_auto.find_one({"statut": "REUSSIE"}, {"_id": 0}, sort=[("fin", -1)])


async def etat_admin() -> dict:
    s = get_settings()
    dep = depot()
    derniere = await derniere_reussite()
    motif = motif_desactivation()
    alerte = motif
    if not alerte:
        if not derniere:
            alerte = "Aucune sauvegarde automatique réussie pour l'instant."
        elif maintenant() - datetime.fromisoformat(derniere["fin"]) > timedelta(hours=ALERTE_HEURES):
            alerte = f"La dernière sauvegarde réussie date de plus de {ALERTE_HEURES} h."
    sauvegardes, erreur_liste = [], None
    if dep is not None:
        try:
            sauvegardes = sorted(await asyncio.to_thread(dep.lister, prefixe() + DOSSIER_GENERALES),
                                 key=lambda o: o["cle"], reverse=True)
        except Exception as exc:  # noqa: BLE001
            erreur_liste = f"Liste des sauvegardes R2 indisponible : {str(exc)[:150]}"
    journal = await db.sauvegardes_auto.find({"_id": {"$regex": "^jour:"}}, {"_id": 0}).sort("jour", -1).to_list(30)
    return {
        "active": motif is None, "motif_desactivation": motif, "alerte": alerte,
        "configuration": {"phrase": bool(s.sauvegarde_auto_phrase), "jeton": bool(s.sauvegarde_auto_jeton),
                          "stockage": dep.nom if dep else None, "bucket": dep.bucket if dep else None,
                          "prefixe": prefixe(),
                          "identifiants_dedies": bool(s.beauthentik_sauvegardes_r2_access_key_id)},
        "retention": RETENTION, "derniere_reussite": derniere, "sauvegardes": sauvegardes,
        "erreur_liste": erreur_liste, "journal": journal,
    }


# ---------------------------------------------------------------------------
# Restauration (mode « Remplacer », garde-fous de l'import existant)
# ---------------------------------------------------------------------------
class _FichierLocal:
    """Imite UploadFile (lecture asynchrone par morceaux) pour réutiliser l'import existant."""

    def __init__(self, chemin: str, nom: str):
        self._f = open(chemin, "rb")  # noqa: SIM115 — fermé par fermer()
        self.filename = nom

    async def read(self, n: int = -1) -> bytes:
        return await asyncio.to_thread(self._f.read, n)

    def fermer(self) -> None:
        self._f.close()


async def restaurer(user: dict, cle: str, ip: Optional[str]) -> dict:
    motif = motif_desactivation()
    if motif:
        raise HTTPException(503, motif)
    if not cle.startswith(prefixe() + DOSSIER_GENERALES) or ".." in cle:
        raise HTTPException(400, "Sauvegarde inconnue")
    dep = depot()
    chemin = str(transfert_donnees.DOSSIER / f"restauration-{secrets.token_hex(8)}{transfert_donnees.EXTENSION}")
    try:
        try:
            await asyncio.to_thread(dep.telecharger, cle, chemin)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(404, "Sauvegarde introuvable sur R2") from exc
        fichier = _FichierLocal(chemin, cle.rsplit("/", 1)[-1])
        try:
            tache = await transfert_donnees.preparer_import(user, fichier, phrase(), "remplacer", ip)
        finally:
            fichier.fermer()
        tache["source_r2"] = cle
        return tache
    finally:
        transfert_donnees._supprimer(chemin)  # noqa: SLF001
