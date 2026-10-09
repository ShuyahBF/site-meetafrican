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


class RelationshipGoal(str, Enum):
    """Type de relation recherchée (maquette 10 "Recherche avancée")."""
    serieuse = "serieuse"        # relation sérieuse
    mariage = "mariage"          # en vue d'un mariage
    amitie = "amitie"            # amitié / rencontres
    a_voir = "a_voir"            # pas encore décidé


class ChildrenStatus(str, Enum):
    """Situation vis-à-vis des enfants (maquette 10, rubrique "Style de vie")."""
    sans_enfant = "sans_enfant"            # n'a pas d'enfants
    a_des_enfants = "a_des_enfants"        # a des enfants
    en_veut = "en_veut"                    # n'en a pas mais en veut
    n_en_veut_pas = "n_en_veut_pas"        # n'en a pas et n'en veut pas


# Centres d'intérêt proposés (maquettes 10 et 11). Liste fermée : garantit
# que la recherche par centre d'intérêt retrouve bien les profils (pas de
# fautes de frappe / variantes libres).
INTERESTS = [
    "Sport", "Cinéma", "Voyages", "Musique", "Art", "Cuisine", "Photographie",
    "Danse", "Lecture", "Mode", "Foi", "Entrepreneuriat", "Nature", "Jeux vidéo",
]


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
    # Code de liaison TikTok (« Continuer avec TikTok » sans compte existant)
    tiktok_lien: Optional[str] = Field(None, max_length=64)

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
    # Code de liaison TikTok : lie le compte TikTok au compte existant à la connexion
    tiktok_lien: Optional[str] = Field(None, max_length=64)


class Photo(BaseModel):
    id: str = Field(default_factory=_uuid)
    url: str
    # Version masquée (bande des yeux au nez) servie à la place de `url` aux
    # visiteurs sans abonnement actif (voir routes/matching.py). Depuis le
    # 09/10/2026, produite dès l'envoi pour que le membre et l'administrateur
    # voient l'aperçu ; elle n'est servie aux autres qu'une fois la photo approuvée.
    masked_url: Optional[str] = None
    # Version de l'algorithme de masquage ayant produit masked_url (les
    # anciennes versions sont régénérées par media_migration.py).
    mask_version: Optional[str] = None
    status: PhotoStatus = PhotoStatus.pending
    is_primary: bool = False
    moderation_notes: Optional[str] = None
    moderated_at: Optional[str] = None
    # Horodatage et traçabilité de chaque étape (détail complet dans le
    # journal des vérifications, verification_log.py).
    faces_detected: Optional[int] = None      # nombre de visages trouvés par le détecteur
    ai_decision: Optional[str] = None
    ai_checked_at: Optional[str] = None
    rejection_reason: Optional[str] = None    # raison affichée au membre
    pending_human_review: bool = False        # refusée mais soumise quand même à un modérateur
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)  # = date de soumission


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
    # Profil détaillé (modifiable via PUT /me/profile, filtrable via /search)
    interests: List[str] = Field(default_factory=list)
    relationship_goal: Optional[RelationshipGoal] = None
    children: Optional[ChildrenStatus] = None
    profession: Optional[str] = None
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
    interests: List[str] = Field(default_factory=list)
    relationship_goal: Optional[RelationshipGoal] = None
    children: Optional[ChildrenStatus] = None
    profession: Optional[str] = None
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
    # Profil fictif généré pour tester le site (badge « Test » à l'écran).
    is_test_data: bool = False
    # Numéros confirmés par code OTP (badges) — jamais le numéro lui-même.
    phone_verified: bool = False
    whatsapp_verified: bool = False
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
    # Lot 50 — « profil de test » : information réservée au back-office
    # (super-administrateur). Jamais transmise aux membres.
    data["is_test_data"] = False
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
    # Case « Autorise le Mode Invisible » (réglée par le super-administrateur) :
    # les abonnés de cette formule peuvent activer le Mode Invisible sans acheter le bonus
    autorise_mode_invisible: bool = False


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
    kind: str  # "recharge" | "gift_sent" | "gift_received" | "bonus_mode_invisible"
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
    "Tu es un agent de vérification d'identité pour beAuthentik, un site de "
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
    "Tu es le modérateur des photos de profil de beAuthentik, un site de "
    "rencontre sérieux pour personnes africaines authentiques. Un membre "
    "vient de prendre ou de charger cette photo pour son profil.\n\n"
    "REJETTE (rejected) la photo si l'une de ces conditions est vraie :\n"
    "1. Aucun visage humain n'est clairement visible (paysage, objet, "
    "animal, dessin, mème, capture d'écran, texte, silhouette de dos, visage "
    "caché ou coupé).\n"
    "2. Nudité, même partielle : sexe, fesses, seins ou tétons visibles, "
    "sous-vêtements, lingerie, torse nu mis en scène, maillot de bain hors "
    "contexte de plage, personne déshabillée ou en serviette.\n"
    "3. Photo trop sexy ou provocante : pose suggestive, cadrage centré sur "
    "le décolleté, les fesses, l'entrejambe ou le corps plutôt que sur la "
    "personne, geste ou expression à caractère sexuel.\n"
    "4. Violence, arme, drogue, symbole haineux, contenu choquant.\n"
    "5. Personne qui semble mineure (moins de 18 ans), ou enfant au premier plan.\n"
    "6. Coordonnées affichées (téléphone, réseaux sociaux, QR code), "
    "publicité, logo commercial dominant.\n"
    "7. Image manifestement non personnelle : célébrité, photo de banque "
    "d'images, image générée par IA, filtre qui déforme fortement le visage.\n\n"
    "APPROUVE (approved) uniquement une photo nette d'une personne adulte, "
    "habillée correctement, dont le visage est visible, adaptée à un profil "
    "de rencontre respectueux.\n"
    "En cas de doute (photo de groupe, visage peu visible, tenue limite, "
    "qualité médiocre…), réponds needs_review : un modérateur humain "
    "tranchera. Ne devine jamais.\n\n"
    "Réponds STRICTEMENT en JSON, rien d'autre : "
    '{"decision": "approved"|"rejected"|"needs_review", "reason": "<courte explication en français>"}'
)

# Anciennes versions du prompt par défaut : si l'admin n'a pas personnalisé
# le prompt (valeur identique à une ancienne version), la nouvelle version
# s'applique automatiquement (voir routes/photos.py).
LEGACY_PHOTO_MODERATION_PROMPTS = (
    (
        "Tu es un modérateur de contenu pour beAuthentik, un site de rencontre "
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
    ),
)


class SiteAppearance(BaseModel):
    """Visuels de l'interface publique, modifiables par l'admin sans
    redéploiement — pour pouvoir rafraîchir le "look" périodiquement.
    hero_image_url vide/absent -> le frontend retombe sur son image par
    défaut embarquée dans le build."""
    id: str = "global"
    hero_image_url: Optional[str] = None
    # Encart vidéo « Moments » de la page d'accueil (à côté du texte de
    # présentation des Moments) : URL de la vidéo (fichier envoyé via
    # POST /admin/settings/appearance/moments-video ou URL externe), image
    # d'aperçu facultative, et interrupteur. Vidéo absente ou désactivée ->
    # rien n'est affiché sur la page d'accueil.
    moments_video_url: Optional[str] = Field(None, max_length=2000)
    moments_video_poster_url: Optional[str] = Field(None, max_length=2000)
    moments_video_enabled: bool = False

    @field_validator("moments_video_url", "moments_video_poster_url", mode="before")
    @classmethod
    def _check_media_url(cls, value):
        # Chaîne vide -> pas de média ; sinon seule une adresse http(s)
        # absolue est acceptée (évite les schémas exotiques type javascript:).
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        if not value.lower().startswith(("https://", "http://")):
            raise ValueError("L'adresse doit commencer par https:// (ou http://)")
        return value


class ModerationSettings(BaseModel):
    """Prompts système modifiables par l'admin, et interrupteur global de la
    vérification automatique par IA (désactivable -> tout passe en revue
    humaine)."""
    id: str = "global"
    ai_auto_enabled: bool = True
    # 09/10/2026 — « l'administrateur doit valider mon inscription et voir ma photo masquée » : toute nouvelle
    # photo attend la validation d'un administrateur, même quand l'IA la juge conforme (son avis est affiché).
    validation_admin_obligatoire: bool = True
    id_verification_prompt: str = DEFAULT_ID_VERIFICATION_PROMPT
    photo_moderation_prompt: str = DEFAULT_PHOTO_MODERATION_PROMPT

    @field_validator("photo_moderation_prompt", mode="before")
    @classmethod
    def _upgrade_legacy_prompt(cls, value):
        # Prompt jamais personnalisé par l'admin -> dernière version par défaut.
        return DEFAULT_PHOTO_MODERATION_PROMPT if value in LEGACY_PHOTO_MODERATION_PROMPTS else value


class IdentityVerification(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str
    document_key: str  # clé d'objet privée — jamais une URL publique
    status: VerificationStatus = VerificationStatus.pending
    ai_decision: Optional[AiDecision] = None
    ai_reason: Optional[str] = None
    ai_checked_at: Optional[str] = None  # horodatage de l'analyse IA
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=_now)  # = date de soumission


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
    # Note vocale (kind="voice") : fichier audio PRIVÉ, lu via une URL
    # temporaire (audio_url, générée à la lecture), + transcription écrite
    # facultative (faite dans le navigateur de l'expéditeur).
    kind: str = "text"  # text | voice
    audio_key: Optional[str] = None
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None
    transcript: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    # Accusé de lecture : date à laquelle le destinataire a vu le message
    # (None tant qu'il ne l'a pas lu). Mis à jour par l'événement WebSocket
    # "read" ou par POST /conversations/{id}/read — voir routes/chat.py.
    read_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Vidéos courtes — fil vertical façon TikTok ("Moments"), voir routes/videos.py
# ---------------------------------------------------------------------------

class VideoStatus(str, Enum):
    processing = "processing"  # compression + floutage en cours (invisible dans le fil)
    published = "published"    # visible dans le fil
    failed = "failed"          # traitement impossible (fichier illisible, trop long…)
    removed = "removed"        # retirée par la modération (reste en base, jamais servie)


class Video(BaseModel):
    """Vidéo courte. Deux versions sont produites au traitement (cf.
    video_processing.py) :
      - `blurred_url` : version entièrement floutée, PUBLIQUE, vue par tous ;
      - `clear_key`   : clé de la version claire dans le stockage PRIVÉ —
        jamais exposée telle quelle par l'API ; une URL temporaire est
        générée uniquement pour les membres autorisés (routes/videos.py)."""
    id: str = Field(default_factory=_uuid)
    user_id: str
    caption: str = Field("", max_length=300)
    # #hashtags extraits de la légende (en minuscules, sans le #) — rendent
    # les tags cliquables et filtrables dans le fil, comme sur TikTok.
    hashtags: List[str] = Field(default_factory=list)
    clear_key: Optional[str] = None
    blurred_url: Optional[str] = None
    poster_url: Optional[str] = None
    # Durée réelle mesurée par ffmpeg au traitement.
    duration_seconds: Optional[float] = None
    status: VideoStatus = VideoStatus.processing
    failure_reason: Optional[str] = None
    likes_count: int = 0
    comments_count: int = 0
    views_count: int = 0
    reports_count: int = 0
    removed_reason: Optional[str] = None
    # IP de publication (suivi admin — jamais renvoyée aux autres membres)
    ip: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class VideoAccessStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    refused = "refused"


class VideoAccessRequest(BaseModel):
    """Demande d'un membre VÉRIFIÉ (`requester_id`) pour voir en clair les
    vidéos d'un autre membre (`owner_id`). L'autorisation vaut pour toutes
    les vidéos de l'auteur, et reste révocable par lui."""
    id: str = Field(default_factory=_uuid)
    owner_id: str
    requester_id: str
    status: VideoAccessStatus = VideoAccessStatus.pending
    created_at: str = Field(default_factory=_now)
    decided_at: Optional[str] = None


class VideoComment(BaseModel):
    id: str = Field(default_factory=_uuid)
    video_id: str
    user_id: str
    text: str = Field(..., min_length=1, max_length=500)
    created_at: str = Field(default_factory=_now)
