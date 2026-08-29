"""Connexion MongoDB (Motor) avec préfixage automatique des collections.

Le cluster Atlas est partagé avec d'autres bases/projets. Pour garantir
qu'aucune collection de MeetAfrican n'entre en collision avec des données
existantes, tout accès passe par `db.<nom>` où `<nom>` est automatiquement
préfixé (`maf_<nom>`) — impossible d'oublier le préfixe par erreur.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from config import get_settings


class PrefixedDatabase:
    def __init__(self, database: AsyncIOMotorDatabase, prefix: str):
        self._database = database
        self._prefix = prefix

    def __getattr__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]

    def __getitem__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]


_settings = get_settings()
_client = AsyncIOMotorClient(_settings.mongo_url)
_raw_db = _client[_settings.mongo_db_name]

db = PrefixedDatabase(_raw_db, _settings.mongo_collection_prefix)


async def ensure_indexes() -> None:
    await db.users.create_index("email", unique=True, sparse=True)
    await db.users.create_index("phone", unique=True, sparse=True)
    await db.payments.create_index("deposit_id", unique=True)
    await db.payment_links.create_index("slug", unique=True)
    await db.subscriptions.create_index("user_id")
    await db.matches.create_index([("user_a", 1), ("user_b", 1)], unique=True)
    await db.messages.create_index("conversation_id")
    await db.reports.create_index("reported_user_id")
    await db.ratings.create_index([("rated_user_id", 1), ("rater_user_id", 1)], unique=True)
    await db.referral_shares.create_index("user_id")
