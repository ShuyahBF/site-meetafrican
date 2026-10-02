"""Sauvegarde / transfert COMPLET des données (changement de cluster MongoDB)
— réservé à l'administrateur principal (rôle « admin », pas aux modérateurs),
avec ressaisie de son mot de passe à chaque action. Logique : voir
transfert_donnees.py.

- GET  /api/plateforme/transfert                              : état de la base + journal ;
- POST /api/plateforme/transfert/export                       : lancer l'export (tâche de fond) ;
- GET  /api/plateforme/transfert/taches/{id}                  : progression (export / import) ;
- GET  /api/plateforme/transfert/taches/{id}/fichier?jeton=…  : téléchargement unique ;
- POST /api/plateforme/transfert/import                       : importer un fichier ;
- GET  /api/plateforme/transfert/restauration-initiale        : restauration sans session possible ? ;
- POST /api/plateforme/transfert/restauration-initiale        : restauration sur base sans compte.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

import chiffrement_flux
import transfert_donnees as service
from activity import current_ip
from auth import get_current_super_admin

# on_startup : nettoyage des fichiers temporaires (repris par l'application
# lors de l'inclusion du routeur, sans toucher au démarrage de server.py)
router = APIRouter(prefix="/plateforme/transfert", tags=["Transfert des données (administrateur)"],
                   on_startup=[service.au_demarrage])


class DemandeExport(BaseModel):
    mot_de_passe: str = Field(max_length=200)
    phrase: str = Field(max_length=chiffrement_flux.PHRASE_MAX)
    phrase_confirmation: str = Field(max_length=chiffrement_flux.PHRASE_MAX)


def _phrase_valide(phrase: str, confirmation=None) -> str:
    try:
        return chiffrement_flux.valider_phrase(phrase, confirmation)
    except chiffrement_flux.ErreurChiffrement as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
async def etat(_: dict = Depends(get_current_super_admin)):
    """Base actuelle, opération en cours, dernières opérations du journal."""
    return await service.etat_base()


@router.post("/export", status_code=202)
async def exporter(payload: DemandeExport, user: dict = Depends(get_current_super_admin)):
    phrase = _phrase_valide(payload.phrase, payload.phrase_confirmation)
    if phrase == payload.mot_de_passe:
        raise HTTPException(400, "La phrase secrète doit être différente de votre mot de passe")
    ip = current_ip()
    await service.verifier_mot_de_passe(user, payload.mot_de_passe, "export", ip)
    tache = await service.lancer_export(user, phrase, ip)
    # Le jeton du lien de téléchargement n'est remis qu'ici (et à l'état de la
    # base, lui aussi réservé à l'administrateur), jamais par le suivi public.
    return {**service.publique(tache), "jeton_telechargement": tache["_jeton"]}


@router.post("/import", status_code=202)
async def importer(
    fichier: UploadFile = File(...),
    phrase: str = Form(..., max_length=chiffrement_flux.PHRASE_MAX),
    mot_de_passe: str = Form(..., max_length=200),
    mode: str = Form("vide"),
    confirmation: str = Form(""),
    user: dict = Depends(get_current_super_admin),
):
    if mode not in service.MODES:
        raise HTTPException(400, "Mode d'import inconnu")
    if mode == "remplacer" and confirmation.strip() != service.MOT_REMPLACER:
        raise HTTPException(400, f"Pour remplacer les données, tapez « {service.MOT_REMPLACER} »")
    ip = current_ip()
    await service.verifier_mot_de_passe(user, mot_de_passe, "import", ip)
    return service.publique(await service.preparer_import(user, fichier, phrase, mode, ip))


@router.get("/taches/{tache_id}")
async def suivre(tache_id: str):
    """Progression d'un export / import. Sans session : pendant un import, les
    comptes (dont celui de l'administrateur) sont remplacés et la session en
    cours devient invalide ; l'identifiant de la tâche, aléatoire (256 bits)
    et connu du seul navigateur qui l'a lancée, sert de clé de suivi. Seuls la
    progression et les nombres de documents sont renvoyés, jamais de données."""
    return service.publique(service.lire_tache(tache_id))


@router.get("/taches/{tache_id}/fichier")
async def telecharger(tache_id: str, jeton: str = ""):
    """Téléchargement (unique) du fichier chiffré, EN FLUX ; il est ensuite
    supprimé du serveur. Pas de session ici : un simple lien de
    téléchargement ne peut pas porter l'en-tête Authorization, et passer par
    JavaScript chargerait tout le fichier en mémoire dans le navigateur. Le
    lien est protégé par un jeton aléatoire (256 bits) remis au seul
    administrateur qui a lancé l'export, et le fichier reste chiffré."""
    chemin, nom = await service.fichier_export(tache_id, jeton, current_ip())
    return FileResponse(chemin, media_type="application/octet-stream", filename=nom,
                        background=BackgroundTask(service.apres_telechargement, tache_id))


# ---------------------------------------------------------------------------
# Restauration initiale (base neuve SANS AUCUN compte) — voir transfert_donnees.py
# ---------------------------------------------------------------------------
@router.get("/restauration-initiale")
async def restauration_disponible():
    motif = await service.motif_restauration_impossible()
    return {"disponible": motif is None, "motif": motif, "extension": service.EXTENSION}


@router.post("/restauration-initiale", status_code=202)
async def restaurer(
    fichier: UploadFile = File(...),
    phrase: str = Form(..., max_length=chiffrement_flux.PHRASE_MAX),
    identifiant: str = Form(..., max_length=200),
    mot_de_passe: str = Form(..., max_length=200),
):
    if not identifiant.strip() or not mot_de_passe:
        raise HTTPException(400, "E-mail (ou téléphone) et mot de passe de l'administrateur requis")
    return service.publique(await service.preparer_import_initial(fichier, phrase, identifiant.strip(),
                                                                  mot_de_passe, current_ip()))
