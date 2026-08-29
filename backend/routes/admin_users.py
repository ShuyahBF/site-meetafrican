"""Gestion des comptes utilisateurs côté back-office — au-delà des files de
modération : recherche, vue détaillée, activation/désactivation, changement
de rôle.

Le changement de rôle est réservé aux comptes admin (pas modérateur) : un
modérateur ne doit pas pouvoir se promouvoir lui-même ni promouvoir
quelqu'un d'autre — c'est une action à risque d'escalade de privilèges."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_admin, get_current_super_admin
from db import db
from models import Rating, Report, Role, UserAdminView, to_user_admin_view

router = APIRouter(prefix="/admin/users", tags=["Administration — Comptes"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserListResult(BaseModel):
    items: List[UserAdminView]
    total: int
    page: int
    page_size: int


@router.get("", response_model=UserListResult)
async def list_users(
    search: Optional[str] = Query(None, description="Recherche par nom, email ou téléphone"),
    role: Optional[Literal["user", "moderator", "admin"]] = None,
    is_active: Optional[bool] = None,
    verification_status: Optional[Literal["unverified", "pending", "verified", "rejected"]] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(get_current_admin),
):
    query: dict = {}
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
        ]
    if role:
        query["role"] = role
    if is_active is not None:
        query["is_active"] = is_active
    if verification_status:
        query["verification_status"] = verification_status

    total = await db.users.count_documents(query)
    skip = (page - 1) * page_size
    docs = await db.users.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return UserListResult(items=[to_user_admin_view(d) for d in docs], total=total, page=page, page_size=page_size)


@router.get("/{user_id}")
async def get_user_detail(user_id: str, _: dict = Depends(get_current_admin)):
    doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Compte introuvable")

    ratings = await db.ratings.find({"rated_user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    reports = await db.reports.find({"reported_user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    subscription = await db.subscriptions.find_one(
        {"user_id": user_id, "status": "active"}, {"_id": 0}, sort=[("created_at", -1)]
    )
    scores = [r["score"] for r in ratings]

    return {
        "user": to_user_admin_view(doc),
        "photos": doc.get("photos", []),
        "rating_average": round(sum(scores) / len(scores), 2) if scores else None,
        "rating_count": len(scores),
        "reports": [Report(**r) for r in reports],
        "active_subscription": subscription,
    }


class StatusUpdate(BaseModel):
    is_active: bool
    reason: Optional[str] = None


@router.put("/{user_id}/status", response_model=UserAdminView)
async def update_user_status(user_id: str, payload: StatusUpdate, admin: dict = Depends(get_current_admin)):
    if user_id == admin["id"] and not payload.is_active:
        raise HTTPException(status_code=400, detail="Impossible de désactiver son propre compte")
    doc = await db.users.find_one({"id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Compte introuvable")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": payload.is_active, "updated_at": _now()}},
    )
    doc["is_active"] = payload.is_active
    return to_user_admin_view(doc)


class RoleUpdate(BaseModel):
    role: Literal["user", "moderator", "admin"]


@router.put("/{user_id}/role", response_model=UserAdminView)
async def update_user_role(user_id: str, payload: RoleUpdate, admin: dict = Depends(get_current_super_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Impossible de changer son propre rôle")
    doc = await db.users.find_one({"id": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Compte introuvable")

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"role": payload.role, "updated_at": _now()}},
    )
    doc["role"] = payload.role
    return to_user_admin_view(doc)
