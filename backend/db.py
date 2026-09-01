"""Connexion MongoDB (Motor) avec préfixage automatique des collections.

Le cluster Atlas est partagé avec d'autres bases/projets. Pour garantir
qu'aucune collection de MeetAfrican n'entre en collision avec des données
existantes, tout accès passe par `db.<nom>` où `<nom>` est automatiquement
préfixé (`maf_<nom>`) — impossible d'oublier le préfixe par erreur.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure, PyMongoError

from config import get_settings

logger = logging.getLogger(__name__)


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


async def _safe_create_index(collection, keys, **kwargs) -> None:
    """Crée un index en avalant les erreurs de permission (cluster Atlas
    partagé où l'utilisateur DB n'a pas le privilège createIndex). Les
    contraintes d'unicité restent appliquées côté applicatif (find_one avant
    insert) : perdre les index n'empêche pas l'app de fonctionner."""
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        # code 13 = Unauthorized ; on log et on continue (l'app doit démarrer
        # même si l'utilisateur DB n'a que readWrite sans createIndex).
        logger.warning(
            "Skipping index on %s (%s): %s",
            getattr(collection, "name", "?"), keys, exc,
        )
    except PyMongoError as exc:
        logger.warning(
            "Failed to create index on %s (%s): %s",
            getattr(collection, "name", "?"), keys, exc,
        )


async def ensure_indexes() -> None:
    await _safe_create_index(db.users, "email", unique=True, sparse=True)
    await _safe_create_index(db.users, "phone", unique=True, sparse=True)
    await _safe_create_index(db.payments, "deposit_id", unique=True)
    await _safe_create_index(db.payment_links, "slug", unique=True)
    await _safe_create_index(db.subscriptions, "user_id")
    await _safe_create_index(db.matches, [("user_a", 1), ("user_b", 1)], unique=True)
    await _safe_create_index(db.messages, "conversation_id")
    await _safe_create_index(db.reports, "reported_user_id")
    await _safe_create_index(db.ratings, [("rated_user_id", 1), ("rater_user_id", 1)], unique=True)
    await _safe_create_index(db.referral_shares, "user_id")
    await _safe_create_index(db.swipes, [("user_id", 1), ("target_user_id", 1)], unique=True)
    await _safe_create_index(db.conversations, "match_id", unique=True)
    await _safe_create_index(db.identity_verifications, "user_id")
