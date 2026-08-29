"""Routes /api/auth — inscription, connexion, profil courant."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from auth import create_access_token, get_current_user, hash_password, verify_password
from db import db
from models import Token, User, UserLogin, UserPublic, UserRegister

router = APIRouter(prefix="/auth", tags=["Auth"])

MIN_AGE_YEARS = 18


def _age_years(birthdate: str) -> int:
    d = date.fromisoformat(birthdate)
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _to_public(user: dict) -> UserPublic:
    return UserPublic(**{k: v for k, v in user.items() if k in UserPublic.model_fields})


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    if not payload.email and not payload.phone:
        raise HTTPException(status_code=400, detail="Email ou téléphone requis")
    try:
        if _age_years(payload.birthdate) < MIN_AGE_YEARS:
            raise HTTPException(status_code=400, detail="Inscription réservée aux 18 ans et plus")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date de naissance invalide")

    existing_query = []
    if payload.email:
        existing_query.append({"email": payload.email})
    if payload.phone:
        existing_query.append({"phone": payload.phone})
    if existing_query and await db.users.find_one({"$or": existing_query}):
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email/téléphone")

    referred_by: Optional[str] = None
    if payload.referral_code:
        referrer = await db.users.find_one({"referral_code": payload.referral_code}, {"_id": 0, "id": 1})
        if referrer:
            referred_by = referrer["id"]

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        gender=payload.gender,
        birthdate=payload.birthdate,
        referred_by=referred_by,
    )
    doc = user.model_dump(mode="json")
    await db.users.insert_one(doc.copy())
    token = create_access_token(user.id)
    return Token(access_token=token, user=_to_public(doc))


@router.post("/login", response_model=Token)
async def login(payload: UserLogin):
    user = await db.users.find_one(
        {"$or": [{"email": payload.identifier}, {"phone": payload.identifier}]},
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Compte désactivé")
    user.pop("_id", None)
    token = create_access_token(user["id"])
    return Token(access_token=token, user=_to_public(user))


@router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return _to_public(user)
