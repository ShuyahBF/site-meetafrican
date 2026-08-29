"""Upload de fichiers (photos de profil, pièces d'identité).

Stockage local pour démarrer (backend/uploads/, servi via /api/files/<nom>).
À remplacer par un object storage S3-compatible avant la mise en production
— l'API exposée (POST /me/uploads -> {url}) ne change pas pour les
consommateurs (photos, vérification d'identité)."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from auth import get_current_user
from config import get_settings

router = APIRouter(prefix="/uploads", tags=["Uploads"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.post("")
async def upload_file(file: UploadFile, user: dict = Depends(get_current_user)):
    settings = get_settings()
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Type de fichier non autorisé (image uniquement)")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"Fichier trop volumineux (max {settings.max_upload_bytes // (1024*1024)} Mo)")

    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic", "image/heif": ".heif"}[file.content_type]
    filename = f"{uuid.uuid4().hex}{ext}"

    uploads_dir = Path(settings.uploads_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / filename).write_bytes(content)

    return {"url": f"{settings.public_base_url}/api/files/{filename}", "filename": filename}
