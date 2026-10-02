"""Traçabilité : adresse IP des visiteurs et journal d'activité.

Demande de l'administrateur du site : chaque action (inscription,
connexion, abonnement, paiement, publication, message, J'aime…) doit
enregistrer l'adresse IP de son auteur, consultable dans le back-office.

Trois mécanismes complémentaires :
  1. `ActivityLogMiddleware` : journalise AUTOMATIQUEMENT toute requête qui
     modifie quelque chose (POST/PUT/PATCH/DELETE sur /api) — qui, quoi,
     depuis quelle IP, avec quel résultat — dans la collection
     `activity_log`. Aucune route ne peut être oubliée.
  2. `current_ip()` : IP de la requête en cours, disponible partout (via une
     ContextVar posée par le middleware) pour l'inscrire directement sur
     les documents importants (compte, abonnement, paiement, vidéo…).
  3. `log_activity()` : journalisation explicite des actions qui ne passent
     pas par une requête HTTP classique (messages envoyés par WebSocket,
     connexion réussie avec l'identité du membre…).

Données personnelles : une adresse IP en est une. Le journal est purgé
automatiquement après ACTIVITY_RETENTION_DAYS (index TTL, cf. db.py) et
n'est lisible que par les administrateurs/modérateurs.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from auth import decode_access_token
from db import db

# Durée de conservation du journal d'activité (purge automatique).
ACTIVITY_RETENTION_DAYS = 365

_current_ip: ContextVar[Optional[str]] = ContextVar("current_ip", default=None)

# Libellés lisibles des actions, par motif de chemin (le premier qui
# correspond gagne). Les chemins non listés gardent "MÉTHODE /chemin".
_ACTION_LABELS = [
    (r"^POST /api/auth/register$", "Inscription"),
    (r"^POST /api/auth/login$", "Tentative de connexion"),
    (r"^PUT /api/me/profile$", "Modification du profil"),
    (r"^POST /api/me/photos$", "Ajout d'une photo"),
    (r"^DELETE /api/me/photos/", "Suppression d'une photo"),
    (r"^POST /api/me/verification/submit$", "Envoi de pièce d'identité"),
    (r"^POST /api/uploads$", "Envoi de fichier"),
    (r"^POST /api/subscriptions/subscribe$", "Souscription à un abonnement"),
    (r"^POST /api/subscriptions/payment-proof$", "Preuve de paiement envoyée"),
    (r"^POST /api/payments/pawapay/payment-page$", "Paiement d'abonnement (Mobile Money)"),
    (r"^POST /api/payments/pawapay/wallet-recharge$", "Recharge du portefeuille"),
    (r"^POST /api/payments/pawapay/webhooks/", "Confirmation PawaPay (webhook)"),
    (r"^POST /api/videos$", "Publication d'une vidéo"),
    (r"^DELETE /api/videos/[^/]+$", "Suppression d'une vidéo"),
    (r"^POST /api/videos/[^/]+/like$", "J'aime sur une vidéo"),
    (r"^POST /api/videos/[^/]+/comments$", "Commentaire sur une vidéo"),
    (r"^DELETE /api/videos/[^/]+/comments/", "Suppression d'un commentaire"),
    (r"^POST /api/videos/[^/]+/report$", "Signalement d'une vidéo"),
    (r"^POST /api/videos/[^/]+/view$", "Vue d'une vidéo"),
    (r"^POST /api/users/[^/]+/video-access$", "Demande « Voir en clair »"),
    (r"^POST /api/me/video-access/requests/", "Réponse à une demande « Voir en clair »"),
    (r"^POST /api/swipe$", "Swipe (J'aime / Passer un profil)"),
    (r"^POST /api/swipe/undo$", "Annulation d'un swipe"),
    (r"^POST /api/conversations/[^/]+/messages$", "Message envoyé"),
    (r"^POST /api/conversations/[^/]+/read$", "Messages lus"),
    (r"^POST /api/users/[^/]+/heart$", "Coup de cœur envoyé"),
    (r"^POST /api/users/[^/]+/points$", "Transfert de points"),
    (r"^POST /api/users/[^/]+/gifts/", "Cadeau envoyé"),
    (r"^POST /api/me/ratings$", "Notation d'un membre"),
    (r"^POST /api/me/reports$", "Signalement d'un membre"),
    (r"^POST /api/me/referrals/share$", "Partage du lien de parrainage"),
    (r"^POST /api/stats/visit$", "Visite du site"),
    (r"^(POST|PUT|DELETE) /api/admin/", "Action d'administration"),
    (r"^POST /api/plateforme/transfert/export$", "Export complet des données"),
    (r"^POST /api/plateforme/transfert/import$", "Import complet des données"),
    (r"^POST /api/plateforme/transfert/restauration-initiale$", "Restauration initiale des données"),
    (r"^POST /api/plateforme/deconnexion-generale", "Maintenance / déconnexion de tous les utilisateurs"),
]
_COMPILED_LABELS = [(re.compile(p), label) for p, label in _ACTION_LABELS]

# Requêtes qui ne sont PAS journalisées : très fréquentes et sans enjeu
# (compter chaque vue ou chaque accusé de lecture noierait le journal).
_SKIPPED = re.compile(r"^POST /api/(videos/[^/]+/view|conversations/[^/]+/read)$")


def action_label(method: str, path: str) -> str:
    key = f"{method} {path}"
    for pattern, label in _COMPILED_LABELS:
        if pattern.search(key):
            return label
    return key


def ip_from_headers(headers: dict, fallback: Optional[str] = None) -> Optional[str]:
    """IP réelle du visiteur. Derrière le proxy de Render, l'adresse vue
    par le serveur est celle du proxy : la vraie est la PREMIÈRE entrée de
    l'en-tête X-Forwarded-For (les suivantes sont les proxys traversés)."""
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real = headers.get("x-real-ip")
    return real.strip() if real else fallback


def current_ip() -> Optional[str]:
    """IP de la requête HTTP en cours (None hors requête)."""
    return _current_ip.get()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


async def log_activity(
    user_id: Optional[str],
    action: str,
    ip: Optional[str],
    *,
    method: Optional[str] = None,
    path: Optional[str] = None,
    status_code: Optional[int] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Ajoute une ligne au journal d'activité. Ne lève jamais d'exception :
    un échec de journalisation ne doit pas faire échouer l'action du membre."""
    now = _now_dt()
    try:
        await db.activity_log.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "action": action,
            "ip": ip,
            "method": method,
            "path": path,
            "status_code": status_code,
            "user_agent": (user_agent or "")[:300] or None,
            "details": details or None,
            "created_at": now.isoformat(),
            # Champ date "natif" : sert à la purge automatique (index TTL).
            "created_at_dt": now,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[activity] journalisation impossible : {exc!r}")


class ActivityLogMiddleware:
    """Middleware ASGI (pas BaseHTTPMiddleware : il ne doit pas perturber
    les WebSockets du chat). Pose l'IP courante pour toute requête HTTP et
    journalise celles qui modifient des données."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        client = scope.get("client")
        ip = ip_from_headers(headers, client[0] if client else None)
        token = _current_ip.set(ip)

        method = scope.get("method", "GET")
        path = scope.get("path", "")
        should_log = (
            method in ("POST", "PUT", "PATCH", "DELETE")
            and path.startswith("/api/")
            and not _SKIPPED.search(f"{method} {path}")
        )
        status_holder = {"code": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _current_ip.reset(token)
            if should_log:
                auth = headers.get("authorization", "")
                user_id = decode_access_token(auth[7:]) if auth.lower().startswith("bearer ") else None
                # En tâche de fond : la réponse est déjà partie.
                asyncio.create_task(log_activity(
                    user_id,
                    action_label(method, path),
                    ip,
                    method=method,
                    path=path,
                    status_code=status_holder["code"],
                    user_agent=headers.get("user-agent"),
                ))
