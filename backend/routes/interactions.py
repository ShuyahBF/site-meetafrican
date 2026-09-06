"""Interactions entre profils au-delà du swipe : coup de cœur (geste
gratuit), transfert réel de points, portefeuille prépayé et cadeaux payants.

La recharge du portefeuille (paiement réel) vit dans payments_pawapay.py, à
côté du reste de l'intégration PawaPay — ce module ne fait que dépenser un
solde déjà crédité."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_admin, get_current_user
from db import db
from models import Gift, GiftSent, HeartSent, PointsTransfer, ReferralPointsSettings, WalletTransaction

router = APIRouter(tags=["Interactions"])


async def _points_settings() -> ReferralPointsSettings:
    doc = await db.settings.find_one({"id": "global_referral_points"}, {"_id": 0})
    return ReferralPointsSettings(**doc) if doc else ReferralPointsSettings()


async def _get_target(target_user_id: str, user_id: str) -> dict:
    if target_user_id == user_id:
        raise HTTPException(status_code=400, detail="Action invalide sur son propre profil")
    target = await db.users.find_one({"id": target_user_id}, {"_id": 0, "id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return target


# ---------------------------------------------------------------------------
# Coup de cœur — gratuit, symbolique
# ---------------------------------------------------------------------------

@router.post("/users/{target_user_id}/heart", status_code=201)
async def send_heart(target_user_id: str, user: dict = Depends(get_current_user)):
    await _get_target(target_user_id, user["id"])
    heart = HeartSent(sender_id=user["id"], recipient_id=target_user_id)
    await db.hearts_sent.insert_one(heart.model_dump(mode="json"))
    await db.users.update_one({"id": target_user_id}, {"$inc": {"hearts_received": 1}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Transfert réel de points
# ---------------------------------------------------------------------------

class PointsTransferCreate(BaseModel):
    amount: int = Field(..., gt=0)


@router.post("/users/{target_user_id}/points", status_code=201)
async def send_points(target_user_id: str, payload: PointsTransferCreate, user: dict = Depends(get_current_user)):
    await _get_target(target_user_id, user["id"])
    settings = await _points_settings()
    if payload.amount > settings.max_points_per_transfer:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.max_points_per_transfer} points par envoi",
        )
    if payload.amount > user.get("points", 0):
        raise HTTPException(status_code=400, detail="Solde de points insuffisant")

    # Débit conditionnel atomique : évite un double envoi concurrent de
    # vider le solde en dessous de zéro (deux requêtes simultanées passant
    # toutes les deux le contrôle ci-dessus avant que l'une ne débite).
    result = await db.users.update_one(
        {"id": user["id"], "points": {"$gte": payload.amount}},
        {"$inc": {"points": -payload.amount}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Solde de points insuffisant")

    await db.users.update_one({"id": target_user_id}, {"$inc": {"points": payload.amount}})
    transfer = PointsTransfer(sender_id=user["id"], recipient_id=target_user_id, amount=payload.amount)
    await db.points_transfers.insert_one(transfer.model_dump(mode="json"))
    return {"ok": True, "amount": payload.amount}


# ---------------------------------------------------------------------------
# Portefeuille — solde et historique (la recharge est dans payments_pawapay.py)
# ---------------------------------------------------------------------------

@router.get("/me/wallet")
async def my_wallet(user: dict = Depends(get_current_user)):
    history = await db.wallet_transactions.find(
        {"user_id": user["id"]}, {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"balance_xof": user.get("wallet_balance_xof", 0), "history": history}


# ---------------------------------------------------------------------------
# Cadeaux payants — catalogue public + envoi depuis le portefeuille
# ---------------------------------------------------------------------------

@router.get("/gifts", response_model=List[Gift])
async def list_gifts():
    return await db.gifts.find({"active": True}, {"_id": 0}).sort("price_xof", 1).to_list(100)


@router.post("/admin/gifts", response_model=Gift, status_code=201)
async def create_gift(payload: Gift, _: dict = Depends(get_current_admin)):
    await db.gifts.insert_one(payload.model_dump())
    return payload


@router.put("/admin/gifts/{gift_id}", response_model=Gift)
async def update_gift(gift_id: str, payload: Gift, _: dict = Depends(get_current_admin)):
    if not await db.gifts.find_one({"id": gift_id}):
        raise HTTPException(status_code=404, detail="Cadeau introuvable")
    doc = payload.model_dump()
    doc["id"] = gift_id
    await db.gifts.update_one({"id": gift_id}, {"$set": doc})
    return doc


class GiftSendPayload(BaseModel):
    message: Optional[str] = Field(None, max_length=200)


@router.post("/users/{target_user_id}/gifts/{gift_id}", response_model=GiftSent, status_code=201)
async def send_gift(
    target_user_id: str, gift_id: str, payload: GiftSendPayload, user: dict = Depends(get_current_user),
):
    await _get_target(target_user_id, user["id"])
    gift = await db.gifts.find_one({"id": gift_id, "active": True}, {"_id": 0})
    if not gift:
        raise HTTPException(status_code=404, detail="Cadeau introuvable")

    result = await db.users.update_one(
        {"id": user["id"], "wallet_balance_xof": {"$gte": gift["price_xof"]}},
        {"$inc": {"wallet_balance_xof": -gift["price_xof"]}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Solde du portefeuille insuffisant")

    sent = GiftSent(
        sender_id=user["id"], recipient_id=target_user_id,
        gift_id=gift["id"], gift_name=gift["name"], price_xof=gift["price_xof"],
        message=payload.message,
    )
    await db.gifts_sent.insert_one(sent.model_dump(mode="json"))

    debit = WalletTransaction(
        user_id=user["id"], kind="gift_sent", amount_xof=-gift["price_xof"],
        related_user_id=target_user_id, description=f"Cadeau envoyé : {gift['name']}",
    )
    await db.wallet_transactions.insert_one(debit.model_dump(mode="json"))
    return sent
