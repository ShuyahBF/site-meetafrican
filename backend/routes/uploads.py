"""Upload de fichiers (photos de profil, pièces d'identité).

Deux natures bien distinctes, jamais interchangeables :
  - kind="photo"    -> album profil, PUBLIC par nature (fil de découverte) ;
                       renvoie une URL stable et publique.
  - kind="document" -> pièce d'identité, PRIVÉE ; renvoie uniquement une clé
                       d'objet — jamais d'URL publique. La consommer via
                       POST /me/verification/submit."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from auth import get_current_user
from config import get_settings
from storage import save_document, save_photo

router = APIRouter(prefix="/uploads", tags=["Uploads"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@router.post("")
async def upload_file(
    file: UploadFile,
    kind: Literal["photo", "document"] = Form("photo"),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Type de fichier non autorisé (image uniquement)")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"Fichier trop volumineux (max {settings.max_upload_bytes // (1024*1024)} Mo)")

    if kind == "photo":
        url = await save_photo(content, file.content_type)
        return {"kind": "photo", "url": url}

    key = await save_document(content, file.content_type)
    return {"kind": "document", "key": key}
