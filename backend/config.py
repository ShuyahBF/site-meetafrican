"""Configuration centralisée, lue depuis les variables d'environnement (.env).

Toutes les collections MongoDB du projet sont préfixées `maf_` (voir db.py)
pour cohabiter sans risque dans un cluster Atlas partagé avec d'autres bases.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db_name: str = "site_meetafrican"
    mongo_collection_prefix: str = "maf_"

    # Auth
    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 jours

    # CORS
    frontend_origin: str = "http://localhost:5173"

    # PawaPay (ported from ShuyahBF/Emergent, Site-SawaliSmartSystems)
    pawapay_environment: str = "sandbox"  # sandbox | production
    pawapay_api_token_sandbox: Optional[str] = None
    pawapay_api_token_production: Optional[str] = None
    pawapay_callback_secret: Optional[str] = None
    pawapay_default_country: str = "BFA"

    # Object storage (photos, pièces d'identité) — placeholder, à brancher plus tard
    uploads_dir: str = "./uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
