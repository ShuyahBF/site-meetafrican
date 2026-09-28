"""Journal HORODATÉ de toutes les soumissions et vérifications.

Chaque étape (soumission d'une photo ou d'une pièce d'identité, décision de
l'IA, contrôle automatique des visages, décision d'un modérateur, envoi et
validation d'un code OTP…) est enregistrée avec :
  - la date et l'heure exactes (UTC) ;
  - le type de vérification (photo, document, phone, whatsapp) ;
  - l'action et son auteur (membre, ia, systeme, moderateur) ;
  - l'adresse IP de la requête et des détails utiles.
Consultable par l'équipe dans Admin > Vérifications (journal).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from activity import current_ip
from db import db


async def log_verification(
    kind: str,
    action: str,
    user_id: str,
    *,
    actor: str = "membre",
    actor_id: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """Enregistre un événement et renvoie son horodatage ISO (UTC)."""
    now = datetime.now(timezone.utc)
    await db.verification_events.insert_one({
        "id": str(uuid.uuid4()),
        "at": now.isoformat(),
        "kind": kind,          # photo | document | phone | whatsapp
        "action": action,      # submitted, ai_approved, auto_rejected_faces, human_approved…
        "user_id": user_id,    # membre concerné
        "actor": actor,        # membre | ia | systeme | moderateur
        "actor_id": actor_id,  # id du modérateur, le cas échéant
        "target_id": target_id,  # photo, dossier… concerné
        "details": details or {},
        "ip": current_ip(),
    })
    return now.isoformat()
