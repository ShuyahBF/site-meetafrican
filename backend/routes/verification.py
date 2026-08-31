"""Vérification d'identité — soumission d'une pièce d'identité à la création
du compte ou à toute resoumission ultérieure.

Le compte reste `pending` (non confirmé) tant qu'une pièce valide n'a pas été
approuvée. L'IA peut trancher automatiquement (activable/désactivable par
l'admin) ; en cas de doute ou si l'IA est désactivée, la demande passe en
revue humaine (modérateur/admin).

La pièce d'identité elle-même n'est JAMAIS exposée via une URL publique
permanente : on ne stocke que sa clé d'objet privée, et une URL d'accès
temporaire est générée à la demande (analyse IA au moment de la soumission,
affichage en revue admin)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_moderation import analyze_image
from auth import get_current_admin, get_current_user
from db import db
from models import (
    DEFAULT_ID_VERIFICATION_PROMPT,
    IdentityVerification,
    ModerationSettings,
    VerificationStatus,
)
from storage import presigned_document_url

router = APIRouter(tags=["Vérification d'identité"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _moderation_settings() -> ModerationSettings:
    doc = await db.settings.find_one({"id": "global_moderation"}, {"_id": 0})
    return ModerationSettings(**doc) if doc else ModerationSettings()


class VerificationSubmit(BaseModel):
    document_key: str


@router.post("/me/verification/submit", response_model=IdentityVerification, status_code=201)
async def submit_verification(payload: VerificationSubmit, user: dict = Depends(get_current_user)):
    settings = await _moderation_settings()
    verification = IdentityVerification(user_id=user["id"], document_key=payload.document_key)

    if settings.ai_auto_enabled:
        view_url = await presigned_document_url(payload.document_key)
        result = await analyze_image(view_url, settings.id_verification_prompt or DEFAULT_ID_VERIFICATION_PROMPT)
        verification.ai_decision = result.decision
        verification.ai_reason = result.reason
        if result.decision == "approved":
            verification.status = VerificationStatus.verified
            verification.reviewed_at = _now()
        elif result.decision == "rejected":
            verification.status = VerificationStatus.rejected
            verification.reviewed_at = _now()
        # "needs_review" -> reste VerificationStatus.pending, en attente d'un humain

    await db.identity_verifications.insert_one(verification.model_dump(mode="json"))

    new_user_status = (
        verification.status if verification.status != VerificationStatus.unverified else VerificationStatus.pending
    )
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"verification_status": new_user_status.value, "updated_at": _now()}},
    )
    return verification


@router.get("/me/verification", response_model=List[IdentityVerification])
async def my_verifications(user: dict = Depends(get_current_user)):
    items = await db.identity_verifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return items


@router.get("/admin/verification/pending")
async def pending_verifications(_: dict = Depends(get_current_admin)):
    items = await db.identity_verifications.find(
        {"status": VerificationStatus.pending.value}, {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    for item in items:
        item["document_view_url"] = await presigned_document_url(item["document_key"])
    return items


@router.post("/admin/verification/{verification_id}/review")
async def review_verification(verification_id: str, approve: bool, admin: dict = Depends(get_current_admin)):
    record = await db.identity_verifications.find_one({"id": verification_id})
    if not record:
        raise HTTPException(status_code=404, detail="Vérification introuvable")

    new_status = VerificationStatus.verified if approve else VerificationStatus.rejected
    await db.identity_verifications.update_one(
        {"id": verification_id},
        {"$set": {"status": new_status.value, "reviewed_by": admin["id"], "reviewed_at": _now()}},
    )
    await db.users.update_one(
        {"id": record["user_id"]},
        {"$set": {"verification_status": new_status.value, "updated_at": _now()}},
    )
    return {"ok": True, "status": new_status.value}


@router.get("/admin/settings/moderation", response_model=ModerationSettings)
async def get_moderation_settings(_: dict = Depends(get_current_admin)):
    return await _moderation_settings()


@router.put("/admin/settings/moderation", response_model=ModerationSettings)
async def update_moderation_settings(payload: ModerationSettings, _: dict = Depends(get_current_admin)):
    doc = payload.model_dump()
    doc["id"] = "global_moderation"
    await db.settings.update_one({"id": "global_moderation"}, {"$set": doc}, upsert=True)
    return payload
