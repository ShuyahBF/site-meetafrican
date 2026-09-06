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
    # Version floutée + bandeau de marque, servie à la place de `url` aux
    # visiteurs sans abonnement actif (voir routes/matching.py). Générée en
    # même temps que le filigrane sur `url`, au moment de l'approbation —
    # absente tant que la photo n'est pas encore approuvée.
    masked_url: Optional[str] = None
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
    points: int = 0
    wallet_balance_xof: int = 0
    avg_response_seconds: Optional[float] = None
    response_count: int = 0
    referral_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    referred_by: Optional[str] = None
    is_active: bool = True
    last_seen_at: Optional[str] = None
    hearts_received: int = 0
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


def user_insert_doc(user: User) -> dict:
    """Sérialise un User pour insertion Mongo, en retirant email/phone quand
    ils valent None. email et phone ont un index unique "sparse" (db.py) :
    un sparse index n'exclut que les documents où la clé est absente, pas
    ceux où elle vaut explicitement null — model_dump() sérialise pourtant
    les champs Optional non fournis en null explicite. Sans ce retrait, le
    deuxième utilisateur créé sans téléphone (ou sans email) entre en
    collision sur {phone: null} (E11000 DuplicateKeyError) au lieu d'être
    accepté."""
    doc = user.model_dump(mode="json")
    if doc.get("email") is None:
        doc.pop("email", None)
    if doc.get("phone") is None:
        doc.pop("phone", None)
    return doc


# Un profil est considéré "en ligne" si sa dernière activité authentifiée
# remonte à moins de 5 minutes (voir auth.py:get_current_user, qui met à
# jour last_seen_at sur chaque requête, avec un throttle à 60s pour éviter
# une écriture Mongo à chaque appel).
ONLINE_THRESHOLD_SECONDS = 300


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
    last_seen_at: Optional[str] = None
    is_online: bool = False
    hearts_received: int = 0
    # Rempli séparément par l'appelant (nécessite une requête d'agrégation,
    # non disponible depuis le seul document utilisateur) — 0 par défaut.
    likes_received: int = 0
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


def _is_online(last_seen_at: Optional[str]) -> bool:
    if not last_seen_at:
        return False
    try:
        seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - seen).total_seconds() < ONLINE_THRESHOLD_SECONDS


def to_user_public(doc: dict) -> "UserPublic":
    data = {k: v for k, v in doc.items() if k in UserPublic.model_fields}
    data["age"] = _age_from_birthdate(doc.get("birthdate"))
    data["is_online"] = _is_online(doc.get("last_seen_at"))
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
# Portefeuille, cadeaux, points, coups de cœur — interactions entre profils
# ---------------------------------------------------------------------------

class WalletTransaction(BaseModel):
    """Historique du portefeuille — chaque mouvement de solde, quelle que
    soit sa nature, pour un relevé complet côté utilisateur."""
    id: str = Field(default_factory=_uuid)
    user_id: str
    kind: str  # "recharge" | "gift_sent" | "gift_received"
    amount_xof: int  # positif = crédit, négatif = débit
    related_user_id: Optional[str] = None  # expéditeur/destinataire du cadeau
    description: str
    payment_id: Optional[str] = None  # deposit_id PawaPay pour une recharge
    created_at: str = Field(default_factory=_now)


class Gift(BaseModel):
    """Catalogue de cadeaux payants, gérable par l'admin."""
    id: str = Field(default_factory=_uuid)
    code: str  # "roses", "chocolat"...
    name: str
    emoji: str = "🎁"
    price_xof: int
    active: bool = True


class GiftSent(BaseModel):
    id: str = Field(default_factory=_uuid)
    sender_id: str
    recipient_id: str
    gift_id: str
    gift_name: str
    price_xof: int
    message: Optional[str] = Field(None, max_length=200)
    created_at: str = Field(default_factory=_now)


class PointsTransfer(BaseModel):
    id: str = Field(default_factory=_uuid)
    sender_id: str
    recipient_id: str
    amount: int
    created_at: str = Field(default_factory=_now)


class HeartSent(BaseModel):
    """"Coup de cœur" — geste gratuit, symbolique, sans impact sur le solde
    de qui que ce soit (voir models.User.hearts_received)."""
    id: str = Field(default_factory=_uuid)
    sender_id: str
    recipient_id: str
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Parrainage social (points)
# ---------------------------------------------------------------------------

class ReferralPointsSettings(BaseModel):
    """Barème paramétrable par l'admin — points gagnés par plateforme de
    partage, et limite sur l'économie de points en général (transfert d'un
    profil à un autre, voir routes/interactions.py)."""
    id: str = "global"
    points_whatsapp: int = 5
    points_facebook: int = 5
    points_instagram: int = 5
    points_tiktok: int = 5
    max_shares_per_day: int = 3
    max_points_per_transfer: int = 50


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
    "Tu es un agent de vérification d'identité pour bAuthentik, un site de "
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
    "Tu es un modérateur de contenu pour bAuthentik, un site de rencontre "
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


class SiteAppearance(BaseModel):
    """Visuels de l'interface publique, modifiables par l'admin sans
    redéploiement — pour pouvoir rafraîchir le "look" périodiquement.
    hero_image_url vide/absent -> le frontend retombe sur son image par
    défaut embarquée dans le build."""
    id: str = "global"
    hero_image_url: Optional[str] = None


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
