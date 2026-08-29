"""Modèles Pydantic partagés (utilisateurs, profils, abonnements, paiements)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Gender(str, Enum):
    homme = "homme"
    femme = "femme"


class VerificationStatus(str, Enum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class PhotoStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    needs_review = "needs_review"  # IA incertaine -> escalade humaine


class Role(str, Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


# ---------------------------------------------------------------------------
# Auth / Utilisateurs
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=8, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)
    gender: Gender
    birthdate: str  # ISO date — validé côté route (âge minimum)
    referral_code: Optional[str] = Field(None, max_length=20)


class UserLogin(BaseModel):
    identifier: str  # email ou téléphone
    password: str


class Photo(BaseModel):
    id: str = Field(default_factory=_uuid)
    url: str
    status: PhotoStatus = PhotoStatus.pending
    is_primary: bool = False
    moderation_notes: Optional[str] = None
    moderated_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class User(BaseModel):
    id: str = Field(default_factory=_uuid)
    full_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password_hash: str
    gender: Gender
    birthdate: str
    bio: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = None
    country: Optional[str] = None
    photos: List[Photo] = Field(default_factory=list)
    role: Role = Role.user
    verification_status: VerificationStatus = VerificationStatus.unverified
    verification_auto_enabled: bool = True  # activable/désactivable par l'admin
    points: int = 0
    referral_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    referred_by: Optional[str] = None
    is_active: bool = True
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class UserPublic(BaseModel):
    """Vue exposée à l'API — jamais de password_hash."""
    id: str
    full_name: str
    gender: Gender
    bio: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    photos: List[Photo] = Field(default_factory=list)
    verification_status: VerificationStatus
    points: int
    referral_code: str
    created_at: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---------------------------------------------------------------------------
# Abonnements / Paiements
# ---------------------------------------------------------------------------

class SubscriptionPlan(BaseModel):
    id: str = Field(default_factory=_uuid)
    code: str  # ex: "1_semaine", "1_mois", "12_mois"
    name: str
    duration_days: int
    price_xof: int
    savings_pct: Optional[int] = None
    features: List[str] = Field(default_factory=list)
    featured: bool = False
    badge: Optional[str] = None  # "Meilleure offre", "Populaire"...
    active: bool = True


class Subscription(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str
    plan_id: str
    status: str = "pending"  # pending | active | expired | cancelled
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    payment_id: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class PaymentProof(BaseModel):
    """Confirmation manuelle par capture d'écran, pour les moyens de paiement
    locaux non couverts par PawaPay."""
    id: str = Field(default_factory=_uuid)
    user_id: str
    plan_id: str
    screenshot_url: str
    status: str = "pending"  # pending | approved | rejected
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Parrainage social (points)
# ---------------------------------------------------------------------------

class ReferralPointsSettings(BaseModel):
    """Barème paramétrable par l'admin — points gagnés par plateforme de partage."""
    id: str = "global"
    points_whatsapp: int = 5
    points_facebook: int = 5
    points_instagram: int = 5
    points_tiktok: int = 5
    max_shares_per_day: int = 3


class ReferralShare(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str
    platform: str  # whatsapp | facebook | instagram | tiktok
    points_awarded: int
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Notation / Signalement
# ---------------------------------------------------------------------------

class Rating(BaseModel):
    id: str = Field(default_factory=_uuid)
    rated_user_id: str
    rater_user_id: str
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=300)
    created_at: str = Field(default_factory=_now)


class Report(BaseModel):
    id: str = Field(default_factory=_uuid)
    reported_user_id: str
    reporter_user_id: str
    reason: str  # "fake_profile" | "abus" | "autre"
    details: Optional[str] = Field(None, max_length=500)
    status: str = "open"  # open | reviewed | dismissed
    created_at: str = Field(default_factory=_now)
