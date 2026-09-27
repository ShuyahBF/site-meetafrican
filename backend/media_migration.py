"""Retraitement automatique des médias déjà publiés vers le floutage
"visage seul" (face_blur.py).

Tâche de fond lancée au démarrage du serveur (server.py) : elle traite UN
média à la fois, avec une pause entre chaque, pour ne jamais ralentir le
site. Elle s'arrête d'elle-même quand tout est à jour, et reprend là où
elle en était après un redémarrage (l'état est lu en base à chaque tour).

  - photos : la version masquée (visiteurs sans abonnement) est régénérée
    à partir de la photo filigranée publique ;
  - vidéos : la version publique et sa vignette sont régénérées à partir
    de la version CLAIRE privée.
Les anciens fichiers sont supprimés une fois les nouveaux enregistrés.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx

from db import db
from image_processing import MASK_VERSION, apply_face_mask
from storage import delete_public_media, presigned_document_url, save_photo, save_public_media
from video_processing import BLUR_MODE_FACE, make_poster, make_public_version, probe_duration

PAUSE_BETWEEN_ITEMS_SECONDS = 3


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def _remember_if_test(is_test: bool, *urls: str) -> None:
    """Fichiers régénérés d'une donnée de test : inventoriés pour la purge."""
    if is_test:
        from routes.test_data import _remember_media

        for url in urls:
            await _remember_media("public", url)


async def migrate_one_photo() -> bool:
    """Régénère UNE photo masquée d'ancienne version. False s'il n'en reste plus."""
    user = await db.users.find_one(
        {"photos": {"$elemMatch": {"masked_url": {"$nin": [None, ""]}, "mask_version": {"$ne": MASK_VERSION}}}},
        {"_id": 0, "id": 1, "photos": 1, "is_test_data": 1},
    )
    if not user:
        return False
    photo = next(p for p in user["photos"] if p.get("masked_url") and p.get("mask_version") != MASK_VERSION)
    try:
        masked = await asyncio.to_thread(apply_face_mask, await _download(photo["url"]))
        new_url = await save_photo(masked, "image/jpeg")
    except Exception as exc:  # noqa: BLE001 — photo illisible : on la marque pour ne pas boucler
        print(f"[media_migration] photo {photo['id']} : {exc!r}")
        await db.users.update_one(
            {"id": user["id"], "photos.id": photo["id"]}, {"$set": {"photos.$.mask_version": MASK_VERSION}}
        )
        return True
    await db.users.update_one(
        {"id": user["id"], "photos.id": photo["id"]},
        {"$set": {"photos.$.masked_url": new_url, "photos.$.mask_version": MASK_VERSION}},
    )
    await _remember_if_test(bool(user.get("is_test_data")), new_url)
    await delete_public_media(photo["masked_url"])
    return True


async def migrate_one_video() -> bool:
    """Régénère la version publique d'UNE vidéo. False s'il n'en reste plus."""
    video = await db.videos.find_one(
        {"status": "published", "clear_key": {"$nin": [None, ""]}, "blur_mode": {"$ne": BLUR_MODE_FACE}},
        {"_id": 0, "id": 1, "clear_key": 1, "blurred_url": 1, "poster_url": 1, "is_test_data": 1},
    )
    if not video:
        return False
    try:
        clear_url = await presigned_document_url(video["clear_key"], 600)
        clear_bytes = await _download(clear_url)
        with tempfile.TemporaryDirectory(prefix="maf-migr-") as tmp:
            clear, blurred, poster = Path(tmp) / "clear.mp4", Path(tmp) / "blurred.mp4", Path(tmp) / "poster.jpg"
            clear.write_bytes(clear_bytes)
            mode = await asyncio.to_thread(make_public_version, clear, blurred)
            duration = await asyncio.to_thread(probe_duration, clear) or 1
            await asyncio.to_thread(make_poster, blurred, poster, duration)
            blurred_url = await save_public_media(blurred.read_bytes(), "video/mp4")
            poster_url = await save_photo(poster.read_bytes(), "image/jpeg")
    except Exception as exc:  # noqa: BLE001 — on garde l'ancienne version (déjà floutée)
        print(f"[media_migration] vidéo {video['id']} : {exc!r}")
        await db.videos.update_one({"id": video["id"]}, {"$set": {"blur_mode": BLUR_MODE_FACE, "blur_migration_error": str(exc)[:200]}})
        return True
    await db.videos.update_one(
        {"id": video["id"]},
        # Si la détection a échoué, mode "full" : on marque quand même la
        # vidéo comme traitée (face-v1 tenté) pour ne pas la retraiter en boucle.
        {"$set": {"blurred_url": blurred_url, "poster_url": poster_url, "blur_mode": BLUR_MODE_FACE, "blur_result": mode}},
    )
    await _remember_if_test(bool(video.get("is_test_data")), blurred_url, poster_url)
    for old in (video.get("blurred_url"), video.get("poster_url")):
        if old:
            await delete_public_media(old)
    return True


async def migrate_all() -> dict:
    """Traite tout ce qui reste (utilisé par la boucle et par les tests)."""
    done = {"photos": 0, "videos": 0}
    while await migrate_one_photo():
        done["photos"] += 1
    while await migrate_one_video():
        done["videos"] += 1
    return done


async def migration_loop() -> None:
    await asyncio.sleep(30)  # laisse le serveur démarrer tranquillement
    while True:
        try:
            worked = await migrate_one_photo() or await migrate_one_video()
        except Exception as exc:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter
            print(f"[media_migration] erreur : {exc!r}")
            worked = True
        if not worked:
            return  # tout est à jour
        await asyncio.sleep(PAUSE_BETWEEN_ITEMS_SECONDS)
