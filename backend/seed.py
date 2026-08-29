"""Données de démarrage — formules d'abonnement par défaut (prix en XOF,
placeholders à ajuster depuis l'admin une fois le marché confirmé)."""
from __future__ import annotations

from db import db
from models import SubscriptionPlan

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
