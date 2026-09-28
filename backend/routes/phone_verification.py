"""Vérification des numéros de téléphone (SMS) et WhatsApp par code OTP.

Parcours (page « Mon profil ») :
  1. GET  /me/numbers                 : mes numéros + canaux disponibles ;
  2. POST /me/numbers/otp/request     : envoi d'un code à 6 chiffres
                                        (WhatsApp ou SMS Orange) ;
  3. POST /me/numbers/otp/verify      : le membre saisit le code reçu ->
                                        numéro enregistré comme VÉRIFIÉ.

Sécurité :
  - le code n'est jamais stocké en clair (empreinte HMAC-SHA256) ;
  - validité 10 minutes (et purge automatique en base, index TTL) ;
  - 5 essais maximum par code, 60 s entre deux envois, 5 envois par heure ;
  - un numéro vérifié sur un compte ne peut pas l'être sur un autre.
Les autres membres voient seulement les badges « téléphone / WhatsApp
vérifié », jamais les numéros.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from auth import get_current_admin, get_current_super_admin, get_current_user
from config import get_settings
from db import db
from verification_log import log_verification
from otp_senders import (
    orange_configured, ovh_configured, send_sms_code, send_whatsapp_code, sms_configured, whatsapp_configured,
)

router = APIRouter(tags=["Vérification des numéros"])

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_HOUR = 5

Channel = Literal["sms", "whatsapp"]
# Nom du type de vérification dans le journal horodaté
_KIND = {"sms": "phone", "whatsapp": "whatsapp"}
# Champs du profil mis à jour selon le canal
_FIELDS = {
    "sms": ("phone", "phone_verified", "phone_verified_at"),
    "whatsapp": ("whatsapp", "whatsapp_verified", "whatsapp_verified_at"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_msisdn(raw: str) -> str:
    """Numéro -> chiffres avec indicatif (ex. "70 12 34 56" -> "22670123456")."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:  # numéro local burkinabè (8 chiffres) : indicatif par défaut
        digits = get_settings().default_phone_country_code + digits
    if not 10 <= len(digits) <= 15:
        raise HTTPException(status_code=400, detail="Numéro invalide : indiquez l'indicatif pays, ex. +226 70 12 34 56")
    return digits


def _hash(code: str, user_id: str) -> str:
    """Empreinte du code (jamais stocké en clair)."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


async def _number_taken(user_id: str, channel: str, msisdn: str) -> bool:
    """Numéro déjà utilisé par un AUTRE compte (vérifié, ou identifiant de connexion)."""
    field, verified_flag, _ = _FIELDS[channel]
    variants = [f"+{msisdn}", msisdn]
    query = {"id": {"$ne": user_id}, field: {"$in": variants}}
    if channel == "whatsapp":
        query[verified_flag] = True
    return await db.users.find_one(query, {"_id": 0, "id": 1}) is not None


async def sms_primary_provider() -> str:
    doc = await db.settings.find_one({"id": "sms"}, {"_id": 0}) or {}
    return doc.get("primary", "auto")


class SmsSettings(BaseModel):
    primary: Literal["auto", "orange", "ovh"] = "auto"


@router.get("/admin/settings/sms")
async def get_sms_settings(_: dict = Depends(get_current_admin)):
    return {"primary": await sms_primary_provider(),
            "configured": {"orange": orange_configured(), "ovh": ovh_configured()}}


@router.put("/admin/settings/sms")
async def update_sms_settings(payload: SmsSettings, _: dict = Depends(get_current_super_admin)):
    await db.settings.update_one({"id": "sms"}, {"$set": {"id": "sms", "primary": payload.primary}}, upsert=True)
    return {"primary": payload.primary, "configured": {"orange": orange_configured(), "ovh": ovh_configured()}}


@router.get("/me/numbers")
async def my_numbers(user: dict = Depends(get_current_user)):
    return {
        "phone": user.get("phone"),
        "phone_verified": bool(user.get("phone_verified")),
        "phone_verified_at": user.get("phone_verified_at"),
        "whatsapp": user.get("whatsapp"),
        "whatsapp_verified": bool(user.get("whatsapp_verified")),
        "whatsapp_verified_at": user.get("whatsapp_verified_at"),
        "channels": {"sms": sms_configured(), "whatsapp": whatsapp_configured()},
    }


class OtpRequest(BaseModel):
    channel: Channel
    number: str = Field(..., min_length=8, max_length=25)


@router.post("/me/numbers/otp/request")
async def request_code(payload: OtpRequest, user: dict = Depends(get_current_user)):
    msisdn = normalize_msisdn(payload.number)
    if await _number_taken(user["id"], payload.channel, msisdn):
        raise HTTPException(status_code=409, detail="Ce numéro est déjà utilisé par un autre compte")

    now = _now()
    current = await db.otp_codes.find_one({"user_id": user["id"], "channel": payload.channel}, {"_id": 0})
    window_start, sends = now, 0
    if current:
        last = datetime.fromisoformat(current["last_sent_at"])
        wait = RESEND_COOLDOWN_SECONDS - (now - last).total_seconds()
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Patientez {int(wait) + 1} s avant de redemander un code")
        start = datetime.fromisoformat(current["window_start"])
        if now - start < timedelta(hours=1):
            window_start, sends = start, current.get("sends", 0)
            if sends >= MAX_SENDS_PER_HOUR:
                raise HTTPException(status_code=429, detail="Trop de codes demandés : réessayez dans une heure")

    code = f"{secrets.randbelow(1_000_000):06d}"
    if payload.channel == "whatsapp":
        ok, error = await send_whatsapp_code(msisdn, code)
    else:
        # Fournisseur SMS principal choisi dans Admin > Paramètres (l'autre en repli)
        ok, error = await send_sms_code(msisdn, code, await sms_primary_provider())
    masked = f"+{msisdn[:5]}•••{msisdn[-2:]}"
    await log_verification(_KIND[payload.channel], "code_sent" if ok else "code_send_failed", user["id"],
                           actor="systeme", details={"number": masked, **({} if ok else {"error": error})})
    if not ok:
        raise HTTPException(status_code=502, detail=error)

    expires = now + timedelta(minutes=CODE_TTL_MINUTES)
    await db.otp_codes.update_one(
        {"user_id": user["id"], "channel": payload.channel},
        {"$set": {
            "user_id": user["id"], "channel": payload.channel, "msisdn": msisdn,
            "code_hash": _hash(code, user["id"]), "attempts": 0,
            "expires_at": expires.isoformat(),
            "expires_at_dt": expires,  # purge automatique (index TTL, db.py)
            "last_sent_at": now.isoformat(),
            "window_start": window_start.isoformat(), "sends": sends + 1,
        }},
        upsert=True,
    )
    return {"ok": True, "expires_in_minutes": CODE_TTL_MINUTES, "masked_number": masked}


class OtpVerify(BaseModel):
    channel: Channel
    code: str = Field(..., min_length=4, max_length=10)


@router.post("/me/numbers/otp/verify")
async def verify_code(payload: OtpVerify, user: dict = Depends(get_current_user)):
    otp = await db.otp_codes.find_one({"user_id": user["id"], "channel": payload.channel}, {"_id": 0})
    if not otp:
        raise HTTPException(status_code=404, detail="Aucun code en cours : demandez-en un nouveau")
    if _now() > datetime.fromisoformat(otp["expires_at"]):
        raise HTTPException(status_code=410, detail="Code expiré : demandez-en un nouveau")
    if otp.get("attempts", 0) >= MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Trop d'essais : demandez un nouveau code")
    if not hmac.compare_digest(otp["code_hash"], _hash(payload.code.strip(), user["id"])):
        await db.otp_codes.update_one({"user_id": user["id"], "channel": payload.channel}, {"$inc": {"attempts": 1}})
        await log_verification(_KIND[payload.channel], "code_wrong", user["id"])
        left = MAX_ATTEMPTS - otp.get("attempts", 0) - 1
        # 400 et non 401 : un 401 déconnecterait le membre côté interface.
        raise HTTPException(status_code=400, detail=f"Code incorrect ({left} essai(s) restant(s))")

    msisdn = otp["msisdn"]
    if await _number_taken(user["id"], payload.channel, msisdn):
        raise HTTPException(status_code=409, detail="Ce numéro est déjà utilisé par un autre compte")
    field, verified_flag, verified_at = _FIELDS[payload.channel]
    at = await log_verification(_KIND[payload.channel], "verified", user["id"],
                                details={"number": f"+{msisdn[:5]}•••{msisdn[-2:]}"})
    try:
        await db.users.update_one({"id": user["id"]}, {"$set": {
            field: f"+{msisdn}", verified_flag: True, verified_at: at,
        }})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Ce numéro est déjà utilisé par un autre compte")
    await db.otp_codes.delete_one({"user_id": user["id"], "channel": payload.channel})
    return {"ok": True, field: f"+{msisdn}", verified_flag: True}
