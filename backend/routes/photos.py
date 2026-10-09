"""Photos de profil — chaque photo ajoutée ou remplacée passe par la
modération IA (même logique activable/désactivable et escalade humaine que
la vérification d'identité, mais avec son propre prompt système).

Une fois approuvée (IA ou admin), la photo est doublée en deux versions
dérivées (voir image_processing.py) :
  - `url` devient la version filigranée (remplace l'original brut) ;
  - `masked_url` est la version floutée + bandeau de marque, servie aux
    visiteurs sans abonnement actif.
"""
from __future__ import annotations

import asyncio

from datetime import datetime, timezone
from typing import List, Optional, Tuple

import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_moderation import analyze_image
from auth import get_current_admin, get_current_user
from db import db
from image_processing import MASK_VERSION, apply_face_mask, apply_watermark
from models import DEFAULT_PHOTO_MODERATION_PROMPT, ModerationSettings, Photo, PhotoStatus
from storage import save_photo
from verification_log import log_verification

router = APIRouter(tags=["Photos de profil"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _moderation_settings() -> ModerationSettings:
    doc = await db.settings.find_one({"id": "global_moderation"}, {"_id": 0})
    return ModerationSettings(**doc) if doc else ModerationSettings()


async def _generate_masked(original_url: str) -> Optional[str]:
    """Aperçu masqué (bande des yeux au nez) dès l'envoi : le membre voit comment les autres le verront, et
    l'administrateur valide en connaissance de cause. Jamais bloquant : None en cas d'échec."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(original_url)
            r.raise_for_status()
        return await save_photo(await asyncio.to_thread(apply_face_mask, r.content), "image/jpeg")
    except Exception as exc:  # noqa: BLE001 — l'aperçu ne bloque jamais l'envoi de la photo
        print(f"[photos] aperçu masqué impossible : {exc}")
        return None


async def _generate_approved_variants(original_url: str) -> Tuple[str, str]:
    """Télécharge la photo brute (déjà publique sur R2/local) et produit ses
    deux versions dérivées, chacune ré-uploadée comme une photo normale."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(original_url)
        r.raise_for_status()
        original_bytes = r.content
    watermarked_url = await save_photo(apply_watermark(original_bytes), "image/jpeg")
    # Détection de visage : calcul de quelques centaines de ms, hors de la
    # boucle asynchrone pour ne pas bloquer les autres requêtes.
    masked_url = await save_photo(await asyncio.to_thread(apply_face_mask, original_bytes), "image/jpeg")
    return watermarked_url, masked_url


# Au-delà de ce nombre de visages, la photo est refusée d'office : une
# photo de profil doit montrer la personne, pas un groupe.
MAX_FACES_PER_PHOTO = 2


async def _count_faces(url: str) -> Optional[int]:
    """Nombre de visages détectés sur la photo (détecteur YuNet,
    face_blur.py), ou None si l'analyse est impossible."""
    try:
        import numpy as np
        from face_blur import detect_faces
        from image_processing import _load_rgb

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
        rgb = np.asarray(_load_rgb(r.content))
        return len(await asyncio.to_thread(lambda: detect_faces(rgb[:, :, ::-1].copy())))
    except Exception as exc:  # noqa: BLE001
        print(f"[photos] détection de visage impossible : {exc!r}")
        return None


class PhotoCreate(BaseModel):
    url: str
    is_primary: bool = False


@router.post("/me/photos", response_model=Photo, status_code=201)
async def add_photo(payload: PhotoCreate, user: dict = Depends(get_current_user)):
    settings = await _moderation_settings()
    photo = Photo(url=payload.url, is_primary=payload.is_primary)
    uid = user["id"]
    await log_verification("photo", "submitted", uid, target_id=photo.id)

    # 1) Contrôle automatique du nombre de visages (avant l'IA).
    photo.faces_detected = await _count_faces(payload.url)
    await log_verification("photo", "faces_counted", uid, actor="systeme", target_id=photo.id,
                           details={"faces": photo.faces_detected})

    if photo.faces_detected is not None and photo.faces_detected > MAX_FACES_PER_PHOTO:
        # Refus systématique, raison expliquée au membre… mais la photo est
        # quand même soumise à un modérateur, qui peut revenir sur ce refus.
        photo.status = PhotoStatus.rejected
        photo.rejection_reason = (
            f"Photo refusée : {photo.faces_detected} visages détectés. Votre photo de profil doit vous montrer "
            f"seul(e) ou à deux au maximum. Un modérateur va quand même la vérifier."
        )
        photo.moderation_notes = f"Refus automatique : {photo.faces_detected} visages détectés (maximum {MAX_FACES_PER_PHOTO})"
        photo.pending_human_review = True
        photo.moderated_at = await log_verification(
            "photo", "auto_rejected_faces", uid, actor="systeme", target_id=photo.id,
            details={"faces": photo.faces_detected, "max": MAX_FACES_PER_PHOTO},
        )
    elif settings.ai_auto_enabled:
        # 2) Analyse IA (prompt système modifiable dans Admin > Paramètres).
        result = await analyze_image(payload.url, settings.photo_moderation_prompt or DEFAULT_PHOTO_MODERATION_PROMPT)
        photo.moderation_notes = result.reason
        photo.ai_decision = result.decision
        photo.ai_checked_at = photo.moderated_at = await log_verification(
            "photo", f"ai_{result.decision}", uid, actor="ia", target_id=photo.id, details={"reason": result.reason},
        )
        if result.decision == "approved" and not photo.faces_detected:
            # Double contrôle : l'IA a approuvé mais le détecteur ne trouve
            # aucun visage -> un modérateur humain tranche.
            photo.status = PhotoStatus.needs_review
            photo.moderation_notes = f"{result.reason} — aucun visage détecté automatiquement, à vérifier"
        elif result.decision == "approved" and settings.validation_admin_obligatoire:
            # 09/10/2026 — l'IA la juge conforme, mais un administrateur valide toujours (son avis est affiché)
            photo.status = PhotoStatus.needs_review
            photo.moderation_notes = f"Conforme selon l'IA : {result.reason} — en attente de validation par l'administrateur"
        elif result.decision == "approved":
            photo.status = PhotoStatus.approved
            photo.url, photo.masked_url = await _generate_approved_variants(payload.url)
            photo.mask_version = MASK_VERSION
        elif result.decision == "rejected":
            photo.status = PhotoStatus.rejected
            photo.rejection_reason = f"Photo refusée : {result.reason}"
        else:
            photo.status = PhotoStatus.needs_review
    else:
        photo.status = PhotoStatus.needs_review

    # 09/10/2026 — aperçu masqué dès l'envoi (photo pas encore approuvée) : visible par le membre et par
    # l'administrateur ; il n'est servi aux autres membres qu'après approbation (routes/matching.py).
    if photo.status != PhotoStatus.approved and not photo.masked_url:
        photo.masked_url = await _generate_masked(payload.url)
        if photo.masked_url:
            photo.mask_version = MASK_VERSION

    current = await db.users.find_one({"id": user["id"]}, {"_id": 0, "photos": 1})
    existing_photos = (current or {}).get("photos", [])
    if payload.is_primary:
        for p in existing_photos:
            p["is_primary"] = False
    new_photos = existing_photos + [photo.model_dump(mode="json")]

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"photos": new_photos, "updated_at": _now()}},
    )
    return photo


@router.delete("/me/photos/{photo_id}")
async def delete_photo(photo_id: str, user: dict = Depends(get_current_user)):
    result = await db.users.update_one(
        {"id": user["id"]},
        {"$pull": {"photos": {"id": photo_id}}, "$set": {"updated_at": _now()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    return {"ok": True}


@router.get("/admin/photos/pending")
async def pending_photos(_: dict = Depends(get_current_admin)):
    """File d'attente de revue humaine — utilisateurs ayant au moins une
    photo needs_review ou rejected en attente d'un second regard."""
    # Photos "à revoir" + photos refusées d'office mais soumises quand même
    # à un modérateur (trop de visages).
    to_review = lambda p: p.get("status") == PhotoStatus.needs_review.value or p.get("pending_human_review")
    users = await db.users.find(
        {"$or": [{"photos.status": PhotoStatus.needs_review.value}, {"photos.pending_human_review": True}]},
        {"_id": 0, "id": 1, "full_name": 1, "photos": 1},
    ).to_list(200)
    items = []
    for u in users:
        for p in u.get("photos", []):
            if to_review(p):
                # 09/10/2026 — photo envoyée avant l'aperçu masqué : il est produit ici, une seule fois, pour que
                # l'administrateur voie ce que verront les autres membres (bande des yeux au nez)
                if not p.get("masked_url"):
                    p["masked_url"] = await _generate_masked(p["url"])
                    if p["masked_url"]:
                        await db.users.update_one({"id": u["id"], "photos.id": p["id"]}, {"$set": {
                            "photos.$.masked_url": p["masked_url"], "photos.$.mask_version": MASK_VERSION}})
                items.append({"user_id": u["id"], "full_name": u["full_name"], **p})
    return sorted(items, key=lambda p: p.get("created_at", ""))


@router.post("/admin/photos/{user_id}/{photo_id}/review")
async def review_photo(user_id: str, photo_id: str, approve: bool, admin: dict = Depends(get_current_admin)):
    owner = await db.users.find_one({"id": user_id, "photos.id": photo_id}, {"_id": 0, "photos": 1})
    if not owner:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    photo_doc = next(p for p in owner["photos"] if p["id"] == photo_id)

    reviewed_at = await log_verification(
        "photo", "human_approved" if approve else "human_rejected", user_id,
        actor="moderateur", actor_id=admin["id"], target_id=photo_id,
    )
    update: dict = {
        "photos.$.moderated_at": reviewed_at, "photos.$.reviewed_at": reviewed_at,
        "photos.$.reviewed_by": admin["id"], "photos.$.pending_human_review": False,
    }
    if approve:
        update["photos.$.status"] = PhotoStatus.approved.value
        watermarked_url, masked_url = await _generate_approved_variants(photo_doc["url"])
        update["photos.$.url"] = watermarked_url
        update["photos.$.masked_url"] = masked_url
        update["photos.$.mask_version"] = MASK_VERSION
        update["photos.$.rejection_reason"] = None
    else:
        update["photos.$.status"] = PhotoStatus.rejected.value
        update["photos.$.rejection_reason"] = photo_doc.get("rejection_reason") or "Photo refusée par un modérateur"

    await db.users.update_one({"id": user_id, "photos.id": photo_id}, {"$set": update})
    return {"ok": True, "status": update["photos.$.status"]}
