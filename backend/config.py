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

    # CORS — une ou plusieurs origines séparées par des virgules (utile pour
    # accepter à la fois l'URL Render (*.onrender.com) et un domaine custom
    # une fois branché, sans devoir choisir entre les deux).
    frontend_origin: str = "http://localhost:5173"

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]

    # PawaPay (ported from ShuyahBF/Emergent, Site-SawaliSmartSystems)
    pawapay_environment: str = "sandbox"  # sandbox | production
    pawapay_api_token_sandbox: Optional[str] = None
    pawapay_api_token_production: Optional[str] = None
    pawapay_callback_secret: Optional[str] = None
    pawapay_default_country: str = "BFA"

    # Object storage (photos, pièces d'identité)
    # storage_backend="local" : disque local, pratique en dev/test, jamais en
    # production (perdu à chaque redéploiement). storage_backend="r2" :
    # Cloudflare R2 (compatible S3) — voir backend/storage.py.
    storage_backend: str = "local"  # local | r2
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 Mo

    # Mode local uniquement
    uploads_dir: str = "./uploads"
    public_base_url: str = "http://localhost:8000"

    # Mode R2 uniquement — Cloudflare dashboard > R2 > Manage API Tokens
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_photos: str = "meetafrican-photos"       # bucket PUBLIC (album profil)
    r2_bucket_documents: str = "meetafrican-documents"  # bucket PRIVÉ (pièces d'identité)
    # URL publique du bucket photos (domaine personnalisé Cloudflare, ou
    # l'URL r2.dev fournie par Cloudflare pour les tests).
    r2_public_photos_base_url: Optional[str] = None
    r2_presigned_url_ttl_seconds: int = 600

    # IA de modération / vérification (Claude, via l'API Anthropic)
    anthropic_api_key: Optional[str] = None
    ai_moderation_model: str = "claude-sonnet-5"

    # Bootstrap du premier compte admin (back-office) — optionnel : si défini,
    # le compte est créé/promu admin au démarrage. À retirer du .env une fois
    # le compte créé, ou à changer pour promouvoir quelqu'un d'autre.
    admin_bootstrap_email: Optional[str] = None
    admin_bootstrap_password: Optional[str] = None

    # VIDAL Sécurisation (api.vidal.fr) — un seul couple app_id/app_key réel
    # fourni par l'utilisateur. Décision explicite (10/09/2026) : pas de
    # distinction sandbox/production côté VIDAL pour ce compte, on tape
    # toujours l'API réelle pour être sûr des retours à jour (l'API a pu
    # évoluer depuis la rédaction du manuel d'intégration MI_APIREST REV_03).
    vidal_base_url: str = "https://api.vidal.fr/rest/api"
    vidal_app_id: Optional[str] = None
    vidal_app_key: Optional[str] = None
    vidal_timeout_seconds: int = 12
    vidal_cache_ttl_hours: int = 168  # 168h = 7 jours, cf. manuel : contenu peu volatil
    vidal_quota_per_day: int = 200  # 0 = illimité
    # Secret partagé exigé sur les routes /api/vidal/* : la page /secure qui
    # les appelle n'a pas de vrai login (c'est un prototype, route cachée
    # mais pas authentifiée) — sans ce garde-fou, quiconque tombe sur l'URL
    # cachée pourrait épuiser le quota VIDAL réel.
    vidal_proxy_secret: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
