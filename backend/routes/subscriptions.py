"""Routes /api/subscriptions — formules Premium, souscription, preuve de
paiement manuelle (pour les moyens de paiement locaux hors PawaPay)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from db import db
from models import PaymentProof, Subscription, SubscriptionPlan

router = APIRouter(prefix="/subscriptions", tags=["Abonnements"])


@router.get("/plans", response_model=List[SubscriptionPlan])
async def list_plans():
    plans = await db.subscription_plans.find({"active": True}, {"_id": 0}).sort("duration_days", 1).to_list(50)
    return plans


class SubscribeRequest(BaseModel):
    plan_id: str


@router.post("/subscribe")
async def subscribe(payload: SubscribeRequest, user: dict = Depends(get_current_user)):
    plan = await db.subscription_plans.find_one({"id": payload.plan_id, "active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="Formule introuvable")
    subscription = Subscription(user_id=user["id"], plan_id=plan["id"])
    doc = subscription.model_dump(mode="json")
    await db.subscriptions.insert_one(doc.copy())
    return {
        "subscription_id": subscription.id,
        "plan": {"code": plan["code"], "name": plan["name"], "price_xof": plan["price_xof"]},
        "next_step": "Appelez /api/payments/pawapay/payment-page avec ce subscription_id pour payer par Mobile Money, ou /api/subscriptions/payment-proof pour un paiement local avec capture d'écran.",
    }


@router.get("/me")
async def my_subscription(user: dict = Depends(get_current_user)):
    sub = await db.subscriptions.find_one(
        {"user_id": user["id"], "status": "active"}, {"_id": 0}, sort=[("created_at", -1)]
    )
    return sub or {"status": "none"}


class PaymentProofCreate(BaseModel):
    subscription_id: str
    screenshot_url: str = Field(..., max_length=1000)


@router.post("/payment-proof", response_model=PaymentProof, status_code=201)
async def submit_payment_proof(payload: PaymentProofCreate, user: dict = Depends(get_current_user)):
    subscription = await db.subscriptions.find_one({"id": payload.subscription_id, "user_id": user["id"]})
    if not subscription:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    proof = PaymentProof(
        user_id=user["id"],
        plan_id=subscription["plan_id"],
        screenshot_url=payload.screenshot_url,
    )
    await db.payment_proofs.insert_one(proof.model_dump(mode="json"))
    return proof


@router.get("/payment-proofs/pending", response_model=List[PaymentProof])
async def list_pending_proofs(user: dict = Depends(get_current_user)):
    """Réservé aux admins/modérateurs — file d'attente de validation manuelle."""
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    items = await db.payment_proofs.find({"status": "pending"}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return items


@router.post("/payment-proofs/{proof_id}/review")
async def review_payment_proof(proof_id: str, approve: bool, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    proof = await db.payment_proofs.find_one({"id": proof_id})
    if not proof:
        raise HTTPException(status_code=404, detail="Preuve introuvable")
    from datetime import datetime, timedelta, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    new_status = "approved" if approve else "rejected"
    await db.payment_proofs.update_one(
        {"id": proof_id},
        {"$set": {"status": new_status, "reviewed_by": user["id"], "reviewed_at": now_iso}},
    )
    if approve:
        subscription = await db.subscriptions.find_one({"user_id": proof["user_id"], "plan_id": proof["plan_id"]}, sort=[("created_at", -1)])
        plan = await db.subscription_plans.find_one({"id": proof["plan_id"]})
        if subscription and plan:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=plan.get("duration_days", 30))).isoformat()
            await db.subscriptions.update_one(
                {"id": subscription["id"]},
                {"$set": {"status": "active", "started_at": now_iso, "expires_at": expires_at}},
            )
    return {"ok": True, "status": new_status}
