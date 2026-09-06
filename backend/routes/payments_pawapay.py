"""PawaPay — encaissement (deposit) via la Hosted Payment Page.

Porté et adapté depuis ShuyahBF/Emergent (branche Site-SawaliSmartSystems,
backend/server.py). Mêmes principes de fiabilité que l'original :
  - le paiement est persisté EN BASE avant l'appel à PawaPay (on ne perd
    jamais un depositId, même en cas d'erreur réseau) ;
  - un webhook idempotent, protégé par un secret, applique le statut final ;
  - un endpoint de polling permet de rafraîchir le statut depuis PawaPay
    si le webhook n'est pas encore arrivé ;
  - Orange/Moov/Telecel (BFA) sont sélectionnés par le client sur la page
    hébergée PawaPay — le site n'a jamais à collecter de PIN/OTP.

Docs PawaPay v2 : https://docs.pawapay.io/v2/api-reference/deposits
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from config import get_settings
from db import db

router = APIRouter(prefix="/payments/pawapay", tags=["Paiements — PawaPay"])

PAWAPAY_HOSTS = {
    "sandbox": "https://api.sandbox.pawapay.io",
    "production": "https://api.pawapay.io",
}

_CURRENCY_BY_COUNTRY = {
    "BFA": "XOF", "BEN": "XOF", "CIV": "XOF", "GNB": "XOF",
    "MLI": "XOF", "NER": "XOF", "SEN": "XOF", "TGO": "XOF",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _currency_for_country(country: str) -> str:
    return _CURRENCY_BY_COUNTRY.get((country or "BFA").upper(), "XOF")


def _active_token() -> Optional[str]:
    s = get_settings()
    if s.pawapay_environment == "production":
        return s.pawapay_api_token_production
    return s.pawapay_api_token_sandbox


def _base_url() -> str:
    s = get_settings()
    return PAWAPAY_HOSTS.get(s.pawapay_environment, PAWAPAY_HOSTS["sandbox"])


def _readable(field: Any) -> Optional[str]:
    """PawaPay renvoie failureReason/rejectionReason comme des objets
    {failureCode, failureMessage}. On les rend imprimables pour le front."""
    if field is None:
        return None
    if isinstance(field, str):
        return field
    if isinstance(field, dict):
        msg = field.get("failureMessage") or field.get("rejectionMessage")
        code = field.get("failureCode") or field.get("rejectionCode")
        if msg and code:
            return f"{code} — {msg}"
        return msg or code
    return str(field)[:300]


class PaymentPageCreate(BaseModel):
    subscription_id: str
    amount_xof: int = Field(..., gt=0)
    country: Optional[str] = None
    msisdn: Optional[str] = None
    return_url: Optional[str] = Field(None, max_length=500)


@router.post("/payment-page")
async def create_payment_page(
    payload: PaymentPageCreate, request: Request, user: dict = Depends(get_current_user)
):
    s = get_settings()
    token = _active_token()
    if not token:
        raise HTTPException(status_code=503, detail="PawaPay non configuré (clé API manquante)")

    subscription = await db.subscriptions.find_one({"id": payload.subscription_id, "user_id": user["id"]})
    if not subscription:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")

    country = (payload.country or s.pawapay_default_country).upper()
    deposit_id = _uuid()
    origin = (payload.return_url or str(request.base_url)).rstrip("/")
    return_url = payload.return_url or f"{origin}/abonnement/retour?depositId={deposit_id}"

    body: Dict[str, Any] = {
        "depositId": deposit_id,
        "returnUrl": return_url,
        "country": country,
        "amountDetails": {
            "amount": str(payload.amount_xof),
            "currency": _currency_for_country(country),
        },
    }
    msisdn_digits = "".join(ch for ch in (payload.msisdn or "") if ch.isdigit())
    if msisdn_digits:
        body["phoneNumber"] = msisdn_digits

    payment_doc = {
        "id": _uuid(),
        "deposit_id": deposit_id,
        "user_id": user["id"],
        "subscription_id": subscription["id"],
        "purpose": "subscription",
        "amount": payload.amount_xof,
        "currency": _currency_for_country(country),
        "country": country,
        "environment": s.pawapay_environment,
        "flow": "payment_page",
        "status": "initiated",
        "api_status": None,
        "api_message": None,
        "return_url": return_url,
        "redirect_url": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    # Persisté AVANT l'appel PawaPay (best-practice) : on ne perd jamais le depositId.
    await db.payments.insert_one(payment_doc.copy())

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{_base_url()}/v2/paymentpage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            try:
                api_resp = r.json()
            except Exception:
                api_resp = {"raw": r.text[:500]}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Délai dépassé lors de l'appel à PawaPay")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur PawaPay : {str(exc)[:200]}") from exc

    redirect_url = (api_resp or {}).get("redirectUrl")
    if not redirect_url:
        await db.payments.update_one(
            {"deposit_id": deposit_id},
            {"$set": {
                "status": "failed",
                "api_status": "PAYMENT_PAGE_REJECTED",
                "api_message": _readable(api_resp.get("failureReason") or api_resp.get("message") or api_resp),
                "updated_at": _now(),
            }},
        )
        raise HTTPException(
            status_code=502,
            detail=_readable(api_resp.get("failureReason") or api_resp.get("message")) or "PawaPay n'a pas renvoyé de lien de paiement.",
        )

    await db.payments.update_one(
        {"deposit_id": deposit_id},
        {"$set": {"status": "pending", "redirect_url": redirect_url, "updated_at": _now()}},
    )
    await db.subscriptions.update_one(
        {"id": subscription["id"]},
        {"$set": {"payment_id": deposit_id}},
    )
    return {"deposit_id": deposit_id, "redirect_url": redirect_url}


class WalletRechargeCreate(BaseModel):
    amount_xof: int = Field(..., gt=0)
    country: Optional[str] = None
    msisdn: Optional[str] = None
    return_url: Optional[str] = Field(None, max_length=500)


@router.post("/wallet-recharge")
async def create_wallet_recharge(
    payload: WalletRechargeCreate, request: Request, user: dict = Depends(get_current_user)
):
    """Même mécanique que /payment-page (abonnement), mais crédite le
    portefeuille de l'utilisateur au lieu d'activer un abonnement — voir la
    branche purpose=="wallet_recharge" dans _apply_webhook ci-dessous."""
    s = get_settings()
    token = _active_token()
    if not token:
        raise HTTPException(status_code=503, detail="PawaPay non configuré (clé API manquante)")

    country = (payload.country or s.pawapay_default_country).upper()
    deposit_id = _uuid()
    origin = (payload.return_url or str(request.base_url)).rstrip("/")
    return_url = payload.return_url or f"{origin}/portefeuille/retour?depositId={deposit_id}"

    body: Dict[str, Any] = {
        "depositId": deposit_id,
        "returnUrl": return_url,
        "country": country,
        "amountDetails": {
            "amount": str(payload.amount_xof),
            "currency": _currency_for_country(country),
        },
    }
    msisdn_digits = "".join(ch for ch in (payload.msisdn or "") if ch.isdigit())
    if msisdn_digits:
        body["phoneNumber"] = msisdn_digits

    payment_doc = {
        "id": _uuid(),
        "deposit_id": deposit_id,
        "user_id": user["id"],
        "subscription_id": None,
        "purpose": "wallet_recharge",
        "amount": payload.amount_xof,
        "currency": _currency_for_country(country),
        "country": country,
        "environment": s.pawapay_environment,
        "flow": "payment_page",
        "status": "initiated",
        "api_status": None,
        "api_message": None,
        "return_url": return_url,
        "redirect_url": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.payments.insert_one(payment_doc.copy())

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{_base_url()}/v2/paymentpage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=body,
            )
            try:
                api_resp = r.json()
            except Exception:
                api_resp = {"raw": r.text[:500]}
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Délai dépassé lors de l'appel à PawaPay")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur PawaPay : {str(exc)[:200]}") from exc

    redirect_url = (api_resp or {}).get("redirectUrl")
    if not redirect_url:
        await db.payments.update_one(
            {"deposit_id": deposit_id},
            {"$set": {
                "status": "failed",
                "api_status": "PAYMENT_PAGE_REJECTED",
                "api_message": _readable(api_resp.get("failureReason") or api_resp.get("message") or api_resp),
                "updated_at": _now(),
            }},
        )
        raise HTTPException(
            status_code=502,
            detail=_readable(api_resp.get("failureReason") or api_resp.get("message")) or "PawaPay n'a pas renvoyé de lien de paiement.",
        )

    await db.payments.update_one(
        {"deposit_id": deposit_id},
        {"$set": {"status": "pending", "redirect_url": redirect_url, "updated_at": _now()}},
    )
    return {"deposit_id": deposit_id, "redirect_url": redirect_url}


@router.get("/{deposit_id}")
async def get_payment_status(
    deposit_id: str, refresh: bool = False, user: dict = Depends(get_current_user)
):
    payment = await db.payments.find_one({"deposit_id": deposit_id}, {"_id": 0})
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    if payment["user_id"] != user["id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not refresh or payment["status"] in ("completed", "failed"):
        return payment

    token = _active_token()
    if not token:
        return payment
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{_base_url()}/v2/deposits/{deposit_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = r.json() if r.status_code < 500 else {}
    except httpx.HTTPError:
        return payment  # on laisse tel quel, le webhook ou un prochain refresh rattrapera

    entries = data if isinstance(data, list) else data.get("data") or [data]
    entry = entries[0] if entries else {}
    api_status = (entry or {}).get("status")
    update: Dict[str, Any] = {"updated_at": _now()}
    if api_status:
        update["status"] = api_status.lower()
        update["api_status"] = api_status
    fr = (entry or {}).get("failureReason")
    if fr:
        update["api_message"] = _readable(fr)
    await db.payments.update_one({"deposit_id": deposit_id}, {"$set": update})
    payment.update(update)
    return payment


async def _apply_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    deposit_id = payload.get("depositId") or payload.get("deposit_id")
    if not deposit_id:
        return {"ok": False, "reason": "depositId manquant"}
    payment = await db.payments.find_one({"deposit_id": deposit_id}, {"_id": 0})
    if not payment:
        await db.webhook_logs.insert_one({
            "id": _uuid(), "topic": "pawapay_orphan", "payload": payload, "created_at": _now(),
        })
        return {"ok": False, "reason": "paiement inconnu (orphelin loggé)"}

    status_raw = (payload.get("status") or "").upper()
    status_map = {"COMPLETED": "completed", "FAILED": "failed", "REJECTED": "failed"}
    new_status = status_map.get(status_raw, payment["status"])

    # Idempotence : rien à faire si déjà appliqué
    if payment["status"] == new_status:
        return {"ok": True, "applied": False}

    update = {
        "status": new_status,
        "api_status": status_raw,
        "api_message": _readable(payload.get("failureReason") or payload.get("rejectionReason")),
        "updated_at": _now(),
    }
    await db.payments.update_one({"deposit_id": deposit_id}, {"$set": update})

    if new_status == "completed" and payment.get("subscription_id"):
        subscription = await db.subscriptions.find_one({"id": payment["subscription_id"]})
        if subscription:
            plan = await db.subscription_plans.find_one({"id": subscription["plan_id"]})
            duration_days = (plan or {}).get("duration_days", 30)
            from datetime import timedelta
            expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
            await db.subscriptions.update_one(
                {"id": subscription["id"]},
                {"$set": {"status": "active", "started_at": _now(), "expires_at": expires_at}},
            )
    elif new_status == "completed" and payment.get("purpose") == "wallet_recharge":
        from models import WalletTransaction
        await db.users.update_one(
            {"id": payment["user_id"]}, {"$inc": {"wallet_balance_xof": payment["amount"]}},
        )
        tx = WalletTransaction(
            user_id=payment["user_id"], kind="recharge", amount_xof=payment["amount"],
            description=f"Recharge {payment['amount']} {payment['currency']}",
            payment_id=deposit_id,
        )
        await db.wallet_transactions.insert_one(tx.model_dump(mode="json"))
    return {"ok": True, "applied": True}


@router.post("/webhooks/deposits/{secret}", include_in_schema=False)
async def webhook_deposits(secret: str, request: Request):
    s = get_settings()
    expected = (s.pawapay_callback_secret or "").strip()
    if not expected or secret != expected:
        raise HTTPException(status_code=403, detail="secret de callback invalide")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="payload invalide")
    return await _apply_webhook(payload)
