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

import secrets

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from activity import current_ip
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


def _return_url(payload_url: Optional[str], page: str, deposit_id: str) -> str:
    """Adresse où PawaPay renvoie le client après paiement : toujours une page
    du SITE PUBLIC (https://beauthentik.net/...), jamais le serveur d'API.

    Une adresse fournie par le navigateur n'est acceptée que si elle pointe
    vers l'un des domaines autorisés (FRONTEND_ORIGIN) — sinon n'importe qui
    pourrait fabriquer un lien de paiement qui redirige vers un site
    frauduleux. La page d'arrivée affiche l'état du paiement (?paiement=)."""
    s = get_settings()
    if payload_url and any(payload_url.startswith(origin.rstrip("/") + "/") for origin in s.frontend_origins):
        return payload_url
    return f"{s.public_site_url}/{page}?paiement={deposit_id}"


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
    return_url = _return_url(payload.return_url, "abonnement", deposit_id)

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
        "ip": current_ip(),  # IP du payeur (suivi admin)
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
    branche purpose=="wallet_recharge" dans _apply_verified_status ci-dessous."""
    s = get_settings()
    token = _active_token()
    if not token:
        raise HTTPException(status_code=503, detail="PawaPay non configuré (clé API manquante)")

    country = (payload.country or s.pawapay_default_country).upper()
    deposit_id = _uuid()
    return_url = _return_url(payload.return_url, "portefeuille", deposit_id)

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
        "ip": current_ip(),  # IP du payeur (suivi admin)
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
    """État d'un paiement. `refresh=true` (page de retour après paiement) :
    interroge PawaPay et APPLIQUE le résultat (activation de l'abonnement,
    crédit du portefeuille) — utile si la notification (webhook) de
    PawaPay tarde ou se perd."""
    payment = await db.payments.find_one({"deposit_id": deposit_id}, {"_id": 0})
    if not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    if payment["user_id"] != user["id"] and user.get("role") not in ("admin", "moderator"):
        raise HTTPException(status_code=403, detail="Accès refusé")
    if not refresh or payment["status"] in ("completed", "failed"):
        return payment

    entry = await _fetch_deposit(deposit_id)
    if entry:
        await _apply_verified_status(payment, entry)
    return await db.payments.find_one({"deposit_id": deposit_id}, {"_id": 0})


def _extract_deposit(body: Any) -> Optional[Dict[str, Any]]:
    """Réponse de GET /v2/deposits/{id} -> objet dépôt. Tolère les formats
    connus : {"status": "FOUND", "data": {...}}, {"data": [...]}, [...] ou
    l'objet dépôt directement."""
    if isinstance(body, list):
        return body[0] if body else None
    if isinstance(body, dict):
        inner = body.get("data")
        if isinstance(inner, list):
            return inner[0] if inner else None
        if isinstance(inner, dict):
            return inner
        if body.get("depositId"):
            return body
    return None


async def _fetch_deposit(deposit_id: str) -> Optional[Dict[str, Any]]:
    """Statut FAISANT FOI d'un dépôt, demandé directement à PawaPay (avec
    notre jeton API). None si PawaPay est injoignable ou ne connaît pas le
    dépôt."""
    token = _active_token()
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{_base_url()}/v2/deposits/{deposit_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code >= 400:
            return None
        return _extract_deposit(r.json())
    except (httpx.HTTPError, ValueError):
        return None


def _deposit_amount(entry: Dict[str, Any]) -> Optional[float]:
    """Montant du dépôt tel que connu de PawaPay (plusieurs noms selon la
    version de l'API)."""
    for key in ("amount", "depositedAmount", "requestedAmount"):
        if entry.get(key) not in (None, ""):
            try:
                return float(entry[key])
            except (TypeError, ValueError):
                return None
    details = entry.get("amountDetails") or {}
    try:
        return float(details["amount"]) if details.get("amount") not in (None, "") else None
    except (TypeError, ValueError):
        return None


async def _apply_verified_status(payment: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """Applique le statut VÉRIFIÉ auprès de PawaPay, une seule fois :
    - COMPLETED : contrôle du montant, puis activation de l'abonnement ou
      crédit du portefeuille ;
    - FAILED / REJECTED : paiement en échec ;
    - autre (en cours) : simple mise à jour de l'état brut.
    Point d'entrée UNIQUE (webhook et page de retour) : l'activation ne
    peut donc ni être oubliée, ni être faite deux fois."""
    deposit_id = payment["deposit_id"]
    status_raw = (entry.get("status") or "").upper()
    status_map = {"COMPLETED": "completed", "FAILED": "failed", "REJECTED": "failed"}
    new_status = status_map.get(status_raw)

    update: Dict[str, Any] = {"api_status": status_raw or None, "updated_at": _now()}
    message = _readable(entry.get("failureReason") or entry.get("rejectionReason"))
    if message:
        update["api_message"] = message

    if new_status == "completed":
        paid = _deposit_amount(entry)
        if paid is not None and abs(paid - float(payment["amount"])) > 0.01:
            # Montant différent de celui demandé : on n'active rien, un
            # humain doit regarder (visible dans l'admin Paiements).
            update.update({"status": "amount_mismatch", "api_message": f"Montant reçu {paid} ≠ montant attendu {payment['amount']}"})
            await db.payments.update_one({"deposit_id": deposit_id}, {"$set": update})
            return {"ok": False, "reason": "montant incohérent"}

    if not new_status:
        await db.payments.update_one({"deposit_id": deposit_id}, {"$set": update})
        return {"ok": True, "applied": False}

    # Passage atomique vers l'état final : si deux notifications arrivent en
    # même temps, une seule "gagne" et applique les effets.
    update["status"] = new_status
    result = await db.payments.update_one(
        {"deposit_id": deposit_id, "status": {"$nin": ["completed", "failed"]}}, {"$set": update}
    )
    if not result.modified_count:
        return {"ok": True, "applied": False}  # déjà traité (idempotence)

    if new_status == "completed" and payment.get("subscription_id"):
        subscription = await db.subscriptions.find_one({"id": payment["subscription_id"]})
        if subscription:
            plan = await db.subscription_plans.find_one({"id": subscription["plan_id"]})
            duration_days = (plan or {}).get("duration_days", 30)
            from datetime import timedelta
            expires_at = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
            await db.subscriptions.update_one(
                {"id": subscription["id"]},
                {"$set": {"status": "active", "started_at": _now(), "expires_at": expires_at, "payment_id": deposit_id}},
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
    """Notification de PawaPay. Le secret dans l'URL filtre les appels, mais
    on ne fait JAMAIS confiance au contenu reçu : le statut est redemandé à
    PawaPay avant d'activer quoi que ce soit (une notification forgée par
    quelqu'un qui connaîtrait le secret n'a donc aucun effet)."""
    s = get_settings()
    expected = (s.pawapay_callback_secret or "").strip()
    if not expected or not secrets.compare_digest(secret, expected):
        raise HTTPException(status_code=403, detail="secret de callback invalide")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="payload invalide")

    deposit_id = payload.get("depositId") or payload.get("deposit_id")
    if not deposit_id:
        return {"ok": False, "reason": "depositId manquant"}
    payment = await db.payments.find_one({"deposit_id": deposit_id}, {"_id": 0})
    if not payment:
        await db.webhook_logs.insert_one({
            "id": _uuid(), "topic": "pawapay_orphan", "payload": payload, "created_at": _now(),
        })
        return {"ok": False, "reason": "paiement inconnu (orphelin loggé)"}

    entry = await _fetch_deposit(deposit_id)
    if not entry:
        # PawaPay injoignable : erreur 503 pour que PawaPay renvoie la
        # notification plus tard (la page de retour peut aussi rattraper).
        raise HTTPException(status_code=503, detail="vérification PawaPay impossible, réessayer")
    return await _apply_verified_status(payment, entry)


# ---------------------------------------------------------------------------
# Rapprochement automatique (sans callback)
# ---------------------------------------------------------------------------
# Le compte PawaPay est partagé avec sawalismartsystems.com : son unique URL
# de callback pointe vers Sawali, beAuthentik ne reçoit donc pas les
# notifications. On interroge nous-mêmes PawaPay, à intervalle régulier,
# pour chaque paiement encore en attente : l'abonnement est activé (ou le
# portefeuille crédité) même si le membre ne revient jamais sur le site.

RECONCILE_INTERVAL_SECONDS = 60      # fréquence de la vérification
RECONCILE_MAX_AGE_HOURS = 48         # au-delà, un paiement en attente est abandonné


async def reconcile_pending_payments() -> int:
    """Une passe de rapprochement. Renvoie le nombre de paiements finalisés
    (payés ou en échec) pendant cette passe."""
    from datetime import timedelta
    oldest = (datetime.now(timezone.utc) - timedelta(hours=RECONCILE_MAX_AGE_HOURS)).isoformat()
    pending = await db.payments.find(
        # "pending" = le membre a été redirigé vers la page de paiement PawaPay
        {"status": "pending", "created_at": {"$gte": oldest}}, {"_id": 0}
    ).to_list(200)
    finalized = 0
    for payment in pending:
        entry = await _fetch_deposit(payment["deposit_id"])
        if not entry:
            continue  # PawaPay injoignable ou dépôt pas encore créé : prochaine passe
        result = await _apply_verified_status(payment, entry)
        if result.get("applied"):
            finalized += 1
    return finalized


async def reconcile_loop() -> None:
    """Boucle de fond démarrée au lancement du serveur (server.py). Une
    erreur ponctuelle ne doit jamais arrêter la boucle."""
    import asyncio
    import logging
    logger = logging.getLogger(__name__)
    while True:
        try:
            if _active_token():
                await reconcile_pending_payments()
        except Exception:  # noqa: BLE001
            logger.exception("Erreur pendant le rapprochement des paiements PawaPay")
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
