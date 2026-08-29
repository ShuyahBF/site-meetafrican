"""Stockage des fichiers (photos de profil, pièces d'identité).

Deux backends :
  - "local"  : écrit sur le disque du serveur, servi via /api/files/<nom>.
               Pratique en dev/test, MAIS les fichiers sont perdus à chaque
               redéploiement — ne jamais utiliser en production.
  - "r2"     : Cloudflare R2 (API compatible S3, via boto3), avec DEUX
               buckets aux usages différents :
                 - r2_bucket_photos    : PUBLIC — l'album profil doit être
                   visible par les autres utilisateurs (fil de découverte).
                 - r2_bucket_documents : PRIVÉ — les pièces d'identité ne
                   sont jamais exposées via une URL permanente ; on génère
                   une URL présignée à la demande (courte durée de vie),
                   uniquement pour l'analyse IA au moment de la soumission
                   et pour l'affichage en revue admin.

Cette séparation est délibérée : une fuite de l'URL d'une photo de profil
est sans conséquence, une fuite de l'URL d'une pièce d'identité en est une.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from config import get_settings

CONTENT_TYPE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def _r2_client():
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _new_key(content_type: str) -> str:
    ext = CONTENT_TYPE_EXT.get(content_type, "")
    return f"{uuid.uuid4().hex}{ext}"


async def save_photo(content: bytes, content_type: str) -> str:
    """Enregistre une photo de profil et renvoie une URL PUBLIQUE stable."""
    settings = get_settings()
    key = _new_key(content_type)

    if settings.storage_backend == "r2":
        def _put():
            _r2_client().put_object(
                Bucket=settings.r2_bucket_photos, Key=key, Body=content, ContentType=content_type,
            )
        await asyncio.to_thread(_put)
        base = (settings.r2_public_photos_base_url or "").rstrip("/")
        return f"{base}/{key}"

    from pathlib import Path
    uploads_path = Path(settings.uploads_dir)
    uploads_path.mkdir(parents=True, exist_ok=True)
    (uploads_path / key).write_bytes(content)
    return f"{settings.public_base_url}/api/files/{key}"


async def save_document(content: bytes, content_type: str) -> str:
    """Enregistre une pièce d'identité et renvoie sa CLÉ d'objet (jamais une
    URL publique) — utiliser `presigned_document_url` pour y accéder."""
    settings = get_settings()
    key = _new_key(content_type)

    if settings.storage_backend == "r2":
        def _put():
            _r2_client().put_object(
                Bucket=settings.r2_bucket_documents, Key=key, Body=content, ContentType=content_type,
            )
        await asyncio.to_thread(_put)
        return key

    # Mode local : répertoire totalement séparé de uploads_dir (jamais un
    # sous-dossier — StaticFiles sert tout un répertoire récursivement, un
    # sous-dossier de uploads_dir serait donc aussi exposé par /api/files,
    # le mount public). Voir le mount /api/private-files dans server.py.
    from pathlib import Path
    uploads_path = Path(settings.uploads_dir)
    private_uploads_path = uploads_path.parent / f"{uploads_path.name}-private"
    private_uploads_path.mkdir(parents=True, exist_ok=True)
    (private_uploads_path / key).write_bytes(content)
    return key


async def presigned_document_url(key: str) -> Optional[str]:
    """URL d'accès temporaire à une pièce d'identité — jamais stockée, générée
    à chaque besoin (analyse IA, affichage en revue admin)."""
    settings = get_settings()

    if settings.storage_backend == "r2":
        def _presign():
            return _r2_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.r2_bucket_documents, "Key": key},
                ExpiresIn=settings.r2_presigned_url_ttl_seconds,
            )
        return await asyncio.to_thread(_presign)

    # Mode local : pas de présignature réelle (dev/test uniquement) — l'URL
    # pointe vers le mount /api/private-files (voir server.py), lisible aussi
    # bien par l'analyse IA (téléchargement http) que par le navigateur.
    return f"{settings.public_base_url}/api/private-files/{key}"
