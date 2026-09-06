"""Données de démarrage — formules d'abonnement par défaut (prix en XOF,
placeholders à ajuster depuis l'admin une fois le marché confirmé) et
bootstrap du premier compte admin."""
from __future__ import annotations

from datetime import datetime, timezone

from auth import hash_password
from config import get_settings
from db import db
from models import Gender, Gift, Role, SubscriptionPlan, User, user_insert_doc

DEFAULT_PLANS = [
    SubscriptionPlan(
        code="1_semaine",
        name="1 Semaine",
        duration_days=7,
        price_xof=5000,
        features=["Accès illimité au chat", "Voir toutes les photos", "Filtres de recherche avancée"],
    ),
    SubscriptionPlan(
        code="1_mois",
        name="1 Mois",
        duration_days=30,
        price_xof=12000,
        features=[
            "Accès illimité au chat", "Voir toutes les photos",
            "Filtres de recherche avancée", "Voir qui a visité votre profil",
        ],
        badge="Populaire",
    ),
    SubscriptionPlan(
        code="12_mois",
        name="12 Mois",
        duration_days=365,
        price_xof=55000,
        savings_pct=62,
        features=[
            "Accès illimité au chat", "Voir toutes les photos",
            "Filtres de recherche avancée", "Voir qui a visité votre profil",
            "Navigation sans publicité",
        ],
        featured=True,
        badge="Meilleure offre",
    ),
]


async def seed_default_plans() -> None:
    for plan in DEFAULT_PLANS:
        existing = await db.subscription_plans.find_one({"code": plan.code})
        if not existing:
            await db.subscription_plans.insert_one(plan.model_dump())


DEFAULT_GIFTS = [
    Gift(code="rose", name="Rose", emoji="🌹", price_xof=500),
    Gift(code="bouquet", name="Bouquet de fleurs", emoji="💐", price_xof=2000),
    Gift(code="chocolat", name="Boîte de chocolats", emoji="🍫", price_xof=1500),
    Gift(code="cadeau", name="Cadeau surprise", emoji="🎁", price_xof=3000),
    Gift(code="diamant", name="Diamant", emoji="💎", price_xof=10000),
]


async def seed_default_gifts() -> None:
    for gift in DEFAULT_GIFTS:
        existing = await db.gifts.find_one({"code": gift.code})
        if not existing:
            await db.gifts.insert_one(gift.model_dump())


async def ensure_admin_user() -> None:
    """Crée ou promeut le compte admin défini par ADMIN_BOOTSTRAP_EMAIL /
    ADMIN_BOOTSTRAP_PASSWORD. Sans ces variables, ne fait rien — le
    back-office reste inaccessible tant qu'aucun admin n'existe."""
    settings = get_settings()
    if not settings.admin_bootstrap_email or not settings.admin_bootstrap_password:
        return

    existing = await db.users.find_one({"email": settings.admin_bootstrap_email})
    if existing:
        if existing.get("role") != Role.admin.value:
            await db.users.update_one({"id": existing["id"]}, {"$set": {"role": Role.admin.value}})
        return

    admin = User(
        full_name="Administrateur bAuthentik",
        email=settings.admin_bootstrap_email,
        password_hash=hash_password(settings.admin_bootstrap_password),
        gender=Gender.homme,
        birthdate="1990-01-01",
        role=Role.admin,
        verification_status="verified",
    )
    await db.users.insert_one(user_insert_doc(admin))
