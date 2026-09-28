"""Témoignages et support.

Témoignages : un membre raconte son expérience (ou sa rencontre). Chaque
témoignage est relu par l'équipe avant publication ; seuls les témoignages
approuvés sont visibles (page publique /temoignages).

Support : "Écrire au support" ouvre un ticket ; membre et équipe échangent
des messages horodatés jusqu'à la clôture du ticket.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_admin, get_current_user
from db import db

router = APIRouter(tags=["Témoignages & support"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Témoignages
# ---------------------------------------------------------------------------

class TestimonialCreate(BaseModel):
    text: str = Field(..., min_length=20, max_length=1200)
    rating: int = Field(5, ge=1, le=5)


@router.post("/testimonials", status_code=201)
async def create_testimonial(payload: TestimonialCreate, user: dict = Depends(get_current_user)):
    doc = {
        "id": _uuid(), "user_id": user["id"], "text": payload.text.strip(), "rating": payload.rating,
        # Affiché publiquement : prénom + ville seulement
        "author_name": user["full_name"].split(" ")[0], "author_city": user.get("city"),
        "status": "pending", "created_at": _now(), "reviewed_at": None, "reviewed_by": None,
        "is_test_data": bool(user.get("is_test_data")),
    }
    await db.testimonials.insert_one(dict(doc))
    return doc


@router.get("/testimonials")
async def public_testimonials(limit: int = Query(30, ge=1, le=100)):
    """Témoignages approuvés (public, sans connexion)."""
    return await db.testimonials.find(
        {"status": "approved"}, {"_id": 0, "user_id": 0, "reviewed_by": 0}
    ).sort("created_at", -1).to_list(limit)


@router.get("/me/testimonials")
async def my_testimonials(user: dict = Depends(get_current_user)):
    return await db.testimonials.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.get("/admin/testimonials")
async def admin_testimonials(status: str = "pending", _: dict = Depends(get_current_admin)):
    return await db.testimonials.find({"status": status}, {"_id": 0}).sort("created_at", 1).to_list(200)


@router.post("/admin/testimonials/{testimonial_id}/review")
async def review_testimonial(testimonial_id: str, approve: bool, admin: dict = Depends(get_current_admin)):
    result = await db.testimonials.update_one({"id": testimonial_id}, {"$set": {
        "status": "approved" if approve else "rejected", "reviewed_at": _now(), "reviewed_by": admin["id"],
    }})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Témoignage introuvable")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------

SupportTopic = Literal["compte", "paiement", "verification", "securite", "signalement", "autre"]


class TicketCreate(BaseModel):
    topic: SupportTopic = "autre"
    subject: str = Field(..., min_length=3, max_length=120)
    message: str = Field(..., min_length=5, max_length=3000)


class TicketReply(BaseModel):
    message: str = Field(..., min_length=1, max_length=3000)


def _msg(author: dict, text: str, from_staff: bool) -> dict:
    return {"id": _uuid(), "author_id": author["id"], "from_staff": from_staff,
            "author_name": "Support beAuthentik" if from_staff else author["full_name"],
            "text": text.strip(), "at": _now()}


@router.post("/support/tickets", status_code=201)
async def create_ticket(payload: TicketCreate, user: dict = Depends(get_current_user)):
    now = _now()
    ticket = {
        "id": _uuid(), "user_id": user["id"], "user_name": user["full_name"], "topic": payload.topic,
        "subject": payload.subject.strip(), "status": "open", "created_at": now, "updated_at": now,
        "closed_at": None, "messages": [_msg(user, payload.message, False)], "unread_by_member": False,
    }
    await db.support_tickets.insert_one(dict(ticket))
    return ticket


@router.get("/me/support/tickets")
async def my_tickets(user: dict = Depends(get_current_user)):
    return await db.support_tickets.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(50)


async def _ticket_for(ticket_id: str, user: dict) -> dict:
    ticket = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
    is_staff = user.get("role") in ("admin", "moderator")
    if not ticket or (ticket["user_id"] != user["id"] and not is_staff):
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return ticket


@router.post("/support/tickets/{ticket_id}/messages")
async def reply_ticket(ticket_id: str, payload: TicketReply, user: dict = Depends(get_current_user)):
    ticket = await _ticket_for(ticket_id, user)
    from_staff = user.get("role") in ("admin", "moderator") and ticket["user_id"] != user["id"]
    msg = _msg(user, payload.message, from_staff)
    await db.support_tickets.update_one({"id": ticket_id}, {
        "$push": {"messages": msg},
        # Un message du membre rouvre un ticket clos ; une réponse de l'équipe
        # est signalée au membre comme "nouvelle réponse".
        "$set": {"updated_at": msg["at"], "status": "answered" if from_staff else "open",
                 "unread_by_member": from_staff, "closed_at": None},
    })
    return msg


@router.post("/me/support/tickets/{ticket_id}/seen")
async def ticket_seen(ticket_id: str, user: dict = Depends(get_current_user)):
    await db.support_tickets.update_one({"id": ticket_id, "user_id": user["id"]}, {"$set": {"unread_by_member": False}})
    return {"ok": True}


@router.get("/admin/support/tickets")
async def admin_tickets(status: Optional[str] = "open", _: dict = Depends(get_current_admin)):
    query = {"status": status} if status else {}
    return await db.support_tickets.find(query, {"_id": 0}).sort("updated_at", 1).to_list(200)


@router.post("/admin/support/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, _: dict = Depends(get_current_admin)):
    now = _now()
    result = await db.support_tickets.update_one({"id": ticket_id}, {"$set": {"status": "closed", "closed_at": now, "updated_at": now}})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return {"ok": True}
