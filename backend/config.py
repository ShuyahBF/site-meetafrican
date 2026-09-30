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

    # CORS — une ou plusieurs origines séparées par des virgules, le domaine
    # officiel EN PREMIER (il sert aussi d'URL publique dans les liens envoyés
    # aux membres et pour le retour des paiements), ex. en production :
    # FRONTEND_ORIGIN=https://beauthentik.net,https://www.beauthentik.net
    frontend_origin: str = "http://localhost:5173"

    @property
    def frontend_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origin.split(",") if o.strip()]

    @property
    def public_site_url(self) -> str:
        """URL publique "principale" du site (liens envoyés aux membres :
        parrainage…) = la PREMIÈRE origine de FRONTEND_ORIGIN. Mettre donc le
        domaine officiel en tête, ex.
        FRONTEND_ORIGIN=https://beauthentik.net,https://www.beauthentik.net"""
        origins = self.frontend_origins
        return origins[0].rstrip("/") if origins else "http://localhost:5173"

    # TikTok Login Kit (« Continuer avec TikTok ») : app créée sur developers.tiktok.com.
    # Client key / secret : variables d'environnement Render uniquement (jamais dans Git).
    tiktok_client_key: Optional[str] = None
    tiktok_client_secret: Optional[str] = None
    # Adresse de retour déclarée dans le portail TikTok
    # (défaut : <PUBLIC_BASE_URL>/api/auth/tiktok/callback, ex. https://api.beauthentik.net/api/auth/tiktok/callback)
    tiktok_redirect_uri: Optional[str] = None

    # PawaPay (ported from ShuyahBF/Emergent, Site-SawaliSmartSystems)
    pawapay_environment: str = "sandbox"  # sandbox | production
    pawapay_api_token_sandbox: Optional[str] = None
    pawapay_api_token_production: Optional[str] = None
    pawapay_callback_secret: Optional[str] = None
    pawapay_default_country: str = "BFA"

    # Vérification des numéros par code OTP (voir otp_senders.py)
    # WhatsApp Cloud API (Meta) — mêmes identifiants que sawalismartsystems.com
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_otp_template: Optional[str] = None  # modèle Meta, 1 variable = le code
    whatsapp_otp_template_lang: str = "fr"
    # Orange SMS API (OAuth2 client_credentials, https://developer.orange.com)
    orange_sms_client_id: Optional[str] = None
    orange_sms_client_secret: Optional[str] = None
    orange_sms_sender_msisdn: Optional[str] = None  # numéro émetteur enregistré chez Orange, ex. +22600000000
    orange_sms_sender_name: Optional[str] = None  # nom d'émetteur optionnel (si activé par Orange)
    # OVH SMS (https://api.ovh.com) — secours / numéros hors Burkina
    ovh_sms_endpoint: str = "ovh-eu"  # ovh-eu | ovh-ca
    ovh_sms_application_key: Optional[str] = None
    ovh_sms_application_secret: Optional[str] = None
    ovh_sms_consumer_key: Optional[str] = None
    ovh_sms_service_name: Optional[str] = None  # ex. sms-ab12345-1
    ovh_sms_sender: Optional[str] = None  # expéditeur déclaré chez OVH, ex. beAuthentik
    # Indicatif ajouté aux numéros saisis sans indicatif (8 chiffres au Burkina Faso)
    default_phone_country_code: str = "226"

    # Object storage (photos, pièces d'identité)
    # storage_backend="local" : disque local, pratique en dev/test, jamais en
    # production (perdu à chaque redéploiement). storage_backend="r2" :
    # Cloudflare R2 (compatible S3) — voir backend/storage.py.
    storage_backend: str = "local"  # local | r2
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 Mo (photos, pièces d'identité)
    # Vidéos courtes du fil "Moments" : taille et durée maximales. La durée
    # est contrôlée côté navigateur (lecture des métadonnées avant envoi) et
    # re-vérifiée sur la valeur déclarée côté serveur.
    max_video_upload_bytes: int = 50 * 1024 * 1024  # 50 Mo
    max_video_duration_seconds: int = 60
    # Vidéo de présentation des Moments sur la page d'accueil (envoyée par
    # l'admin) : volontairement plus légère que les Moments des membres,
    # car elle est proposée à tous les visiteurs de la page publique.
    max_home_video_upload_bytes: int = 20 * 1024 * 1024  # 20 Mo

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
    # Mot de passe admin oublié : passer à true le temps d'UN redéploiement
    # pour que le compte ADMIN_BOOTSTRAP_EMAIL reprenne le mot de passe
    # ADMIN_BOOTSTRAP_PASSWORD, puis remettre à false.
    admin_bootstrap_reset_password: bool = False

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
