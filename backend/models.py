"""Modèles Pydantic partagés (utilisateurs, profils, abonnements, paiements)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


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

    @field_validator("email", "phone", "referral_code", mode="before")
    @classmethod
    def _blank_optional_to_none(cls, v):
        """Les champs optionnels du formulaire d'inscription arrivent en ''
        (pas omis) quand l'utilisateur les laisse vides — à traiter comme
        "non fourni", pas comme une valeur invalide."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


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
    password_hash: Optional[str] = None  # None pour les comptes Google (pas de mot de passe local)
    gender: Gender
    birthdate: str
    bio: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = None
    country: Optional[str] = None
    photos: List[Photo] = Field(default_factory=list)
    role: Role = Role.user
    verification_status: VerificationStatus = VerificationStatus.unverified
    points: int = 0
    avg_response_seconds: Optional[float] = None
    response_count: int = 0
    referral_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    referred_by: Optional[str] = None
    is_active: bool = True
    # Auth externe (Emergent-managed Google) — populé si le compte a été créé
    # via OAuth Google. `needs_profile_completion` invite à compléter genre/
    # date de naissance/téléphone lors du premier login.
    google_sub: Optional[str] = None
    avatar_url: Optional[str] = None
    needs_profile_completion: bool = False
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class UserSession(BaseModel):
    """Session bearer/cookie émise après login Google (Emergent Auth).
    Distinct du JWT local (auth par mot de passe) : les deux coexistent."""
    id: str = Field(default_factory=_uuid)
    user_id: str
    session_token: str
    expires_at: str  # ISO datetime UTC
    created_at: str = Field(default_factory=_now)


class UserPublic(BaseModel):
    """Vue exposée à l'API — jamais de password_hash, ni de date de
    naissance exacte (seulement l'âge calculé)."""
    id: str
    full_name: str
    age: Optional[int] = None
    gender: Gender
    bio: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    photos: List[Photo] = Field(default_factory=list)
    role: Role = Role.user
    verification_status: VerificationStatus
    points: int
    referral_code: str
    avg_response_seconds: Optional[float] = None
    avatar_url: Optional[str] = None
    needs_profile_completion: bool = False
    created_at: str


def _age_from_birthdate(birthdate: Optional[str]) -> Optional[int]:
    if not birthdate:
        return None
    try:
        from datetime import date
        d = date.fromisoformat(birthdate)
        today = date.today()
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except ValueError:
        return None


def to_user_public(doc: dict) -> "UserPublic":
    data = {k: v for k, v in doc.items() if k in UserPublic.model_fields}
    data["age"] = _age_from_birthdate(doc.get("birthdate"))
    return UserPublic(**data)


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
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Vérification d'identité & modération photo par IA
# ---------------------------------------------------------------------------

class AiDecision(str, Enum):
    approved = "approved"
    rejected = "rejected"
    needs_review = "needs_review"  # IA incertaine -> escalade humaine


DEFAULT_ID_VERIFICATION_PROMPT = (
    "Tu es un agent de vérification d'identité pour MeetAfrican, un site de "
    "rencontre. On te montre la photo d'une pièce d'identité (carte "
    "nationale, passeport, permis) soumise par un utilisateur lors de son "
    "inscription ou d'une mise à jour de profil.\n\n"
    "Évalue uniquement :\n"
    "1. S'agit-il bien d'une pièce d'identité officielle lisible (pas une "
    "photo floue, tronquée, un écran filmé, un document manifestement "
    "trafiqué, ou une image sans rapport) ?\n"
    "2. Le document semble-t-il authentique et cohérent (pas de signe "
    "évident de montage/falsification) ?\n\n"
    "Ne tente PAS de vérifier l'identité réelle de la personne (pas de "
    "comparaison biométrique) — évalue seulement la validité apparente du "
    "document. En cas de doute, réponds needs_review plutôt que de deviner.\n\n"
    "Réponds STRICTEMENT en JSON, rien d'autre : "
    '{"decision": "approved"|"rejected"|"needs_review", "reason": "<courte explication en français>"}'
)

DEFAULT_PHOTO_MODERATION_PROMPT = (
    "Tu es un modérateur de contenu pour MeetAfrican, un site de rencontre "
    "africain. On te montre une photo qu'un utilisateur veut ajouter à son "
    "album de profil.\n\n"
    "Rejette (rejected) les photos qui contiennent : nudité ou contenu "
    "sexuel explicite, violence, symboles haineux, mineurs, informations de "
    "contact (numéro de téléphone/réseaux sociaux affichés sur l'image), "
    "publicité manifeste, ou qui sont clairement une image volée/stock/"
    "célébrité plutôt qu'une photo personnelle.\n"
    "Approuve (approved) les photos de personnes correctes, habillées, "
    "conformes à un usage de profil de rencontre.\n"
    "Si tu n'es pas sûr (photo ambiguë, de groupe, de dos, artistique...), "
    "réponds needs_review pour une revue humaine plutôt que de deviner.\n\n"
    "Réponds STRICTEMENT en JSON, rien d'autre : "
    '{"decision": "approved"|"rejected"|"needs_review", "reason": "<courte explication en français>"}'
)


class ModerationSettings(BaseModel):
    """Prompts système modifiables par l'admin, et interrupteur global de la
    vérification automatique par IA (désactivable -> tout passe en revue
    humaine)."""
    id: str = "global"
    ai_auto_enabled: bool = True
    id_verification_prompt: str = DEFAULT_ID_VERIFICATION_PROMPT
    photo_moderation_prompt: str = DEFAULT_PHOTO_MODERATION_PROMPT


class IdentityVerification(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str
    document_key: str  # clé d'objet privée — jamais une URL publique
    status: VerificationStatus = VerificationStatus.pending
    ai_decision: Optional[AiDecision] = None
    ai_reason: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class SwipeAction(str, Enum):
    like = "like"
    pass_ = "pass"


class Swipe(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str
    target_user_id: str
    action: SwipeAction
    created_at: str = Field(default_factory=_now)


class Match(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_a: str
    user_b: str
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class Conversation(BaseModel):
    id: str = Field(default_factory=_uuid)
    match_id: str
    user_a: str
    user_b: str
    last_message_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class Message(BaseModel):
    id: str = Field(default_factory=_uuid)
    conversation_id: str
    sender_id: str
    text: str = Field(..., min_length=1, max_length=2000)
    created_at: str = Field(default_factory=_now)
