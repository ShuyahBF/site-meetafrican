"""Notation entre comptes et signalement de faux profils / abus."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_admin, get_current_user
from db import db
from models import Rating, Report

router = APIRouter(tags=["Notation & Signalement"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Notation
# ---------------------------------------------------------------------------

class RatingCreate(BaseModel):
    rated_user_id: str
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=300)


@router.post("/me/ratings", response_model=Rating, status_code=201)
async def rate_user(payload: RatingCreate, user: dict = Depends(get_current_user)):
    if payload.rated_user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Impossible de se noter soi-même")
    target = await db.users.find_one({"id": payload.rated_user_id}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    rating = Rating(rated_user_id=payload.rated_user_id, rater_user_id=user["id"], score=payload.score, comment=payload.comment)
    await db.ratings.update_one(
        {"rated_user_id": payload.rated_user_id, "rater_user_id": user["id"]},
        {"$set": rating.model_dump(mode="json")},
        upsert=True,
    )
    return rating


@router.get("/users/{user_id}/rating-summary")
async def rating_summary(user_id: str):
    ratings = await db.ratings.find({"rated_user_id": user_id}, {"_id": 0, "score": 1}).to_list(10000)
    if not ratings:
        return {"average": None, "count": 0}
    scores = [r["score"] for r in ratings]
    return {"average": round(sum(scores) / len(scores), 2), "count": len(scores)}


# ---------------------------------------------------------------------------
# Signalement
# ---------------------------------------------------------------------------

class ReportCreate(BaseModel):
    reported_user_id: str
    reason: Literal["fake_profile", "abus", "autre"]
    details: Optional[str] = Field(None, max_length=500)


@router.post("/me/reports", response_model=Report, status_code=201)
async def report_user(payload: ReportCreate, user: dict = Depends(get_current_user)):
    if payload.reported_user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Impossible de se signaler soi-même")
    target = await db.users.find_one({"id": payload.reported_user_id}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    report = Report(
        reported_user_id=payload.reported_user_id,
        reporter_user_id=user["id"],
        reason=payload.reason,
        details=payload.details,
    )
    await db.reports.insert_one(report.model_dump(mode="json"))
    return report


@router.get("/admin/reports", response_model=List[Report])
async def list_reports(status: str = "open", _: dict = Depends(get_current_admin)):
    query = {} if status == "all" else {"status": status}
    items = await db.reports.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


class ReportReview(BaseModel):
    status: Literal["reviewed", "dismissed"]
    deactivate_reported_user: bool = False


@router.post("/admin/reports/{report_id}/review")
async def review_report(report_id: str, payload: ReportReview, admin: dict = Depends(get_current_admin)):
    report = await db.reports.find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Signalement introuvable")

    await db.reports.update_one(
        {"id": report_id},
        {"$set": {"status": payload.status, "reviewed_by": admin["id"], "reviewed_at": _now()}},
    )
    if payload.deactivate_reported_user:
        await db.users.update_one({"id": report["reported_user_id"]}, {"$set": {"is_active": False, "updated_at": _now()}})
    return {"ok": True, "status": payload.status}
