"""Connexion MongoDB (Motor) avec préfixage automatique des collections.

Le cluster Atlas est partagé avec d'autres bases/projets. Pour garantir
qu'aucune collection de MeetAfrican n'entre en collision avec des données
existantes, tout accès passe par `db.<nom>` où `<nom>` est automatiquement
préfixé (`maf_<nom>`) — impossible d'oublier le préfixe par erreur.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from config import get_settings


class PrefixedDatabase:
    def __init__(self, database: AsyncIOMotorDatabase, prefix: str):
        self._database = database
        self._prefix = prefix

    def __getattr__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]

    def __getitem__(self, name: str) -> AsyncIOMotorCollection:
        return self._database[f"{self._prefix}{name}"]


def _make_client(mongo_url: str):
    # MONGO_URL=mongomock:// -> base en mémoire (mongomock-motor), pratique
    # pour développer/tester sans connexion réseau à Atlas. Ne jamais utiliser
    # en production : les données ne persistent pas entre redémarrages.
    if mongo_url.startswith("mongomock://"):
        from mongomock_motor import AsyncMongoMockClient

        return AsyncMongoMockClient()
    from motor.motor_asyncio import AsyncIOMotorClient

    return AsyncIOMotorClient(mongo_url)


_settings = get_settings()
_client = _make_client(_settings.mongo_url)
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
    await db.swipes.create_index([("user_id", 1), ("target_user_id", 1)], unique=True)
    await db.conversations.create_index("match_id", unique=True)
    await db.identity_verifications.create_index("user_id")
    await db.vidal_api_cache.create_index("key", unique=True)
    await db.vidal_api_cache.create_index("expires_at", expireAfterSeconds=0)
    await db.vidal_api_quota.create_index("day", unique=True)
