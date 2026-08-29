"""Modération de contenu et vérification d'identité par IA (Claude vision).

Utilisé pour deux besoins distincts, chacun avec son propre prompt système
paramétrable par l'admin (voir models.ModerationSettings) :
  - vérification des pièces d'identité soumises à l'inscription / mise à jour
    de profil ;
  - modération des photos ajoutées à l'album de profil.

Dans les deux cas, la décision de l'IA est un des trois statuts
{approved, rejected, needs_review} — "needs_review" déclenche une escalade
vers la revue humaine plutôt que de laisser l'IA trancher seule en cas de
doute. La vérification automatique peut être désactivée globalement par
l'admin (ModerationSettings.ai_auto_enabled=False) : dans ce cas tout passe
directement en revue humaine, sans appel IA.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional

import httpx
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from config import get_settings

logger = logging.getLogger("meetafrican.ai_moderation")


class ModerationResult(BaseModel):
    decision: str  # approved | rejected | needs_review
    reason: str


async def _load_image_base64(image_url: str) -> tuple[str, str]:
    """Retourne (base64_data, media_type) pour une image locale (/api/files/...)
    ou distante (http/https)."""
    settings = get_settings()
    if image_url.startswith("http://") or image_url.startswith("https://"):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(image_url)
            r.raise_for_status()
            content = r.content
            media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]
    else:
        # Chemin local servi via /api/files/<nom> — on lit directement le disque.
        filename = image_url.rsplit("/", 1)[-1]
        path = Path(settings.uploads_dir) / filename
        content = path.read_bytes()
        media_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return base64.b64encode(content).decode("ascii"), media_type


def _parse_decision(raw_text: str) -> ModerationResult:
    try:
        data = json.loads(raw_text.strip())
        decision = data.get("decision")
        if decision not in ("approved", "rejected", "needs_review"):
            raise ValueError(f"decision inattendue: {decision}")
        return ModerationResult(decision=decision, reason=str(data.get("reason", ""))[:500])
    except Exception:
        # Réponse IA non exploitable -> on ne devine jamais, on escalade.
        logger.warning("Réponse IA de modération non parsable, escalade en revue humaine: %r", raw_text[:300])
        return ModerationResult(decision="needs_review", reason="Réponse IA non exploitable — revue humaine requise")


async def analyze_image(image_url: str, system_prompt: str) -> ModerationResult:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return ModerationResult(decision="needs_review", reason="Clé API IA non configurée — revue humaine requise")

    try:
        b64_data, media_type = await _load_image_base64(image_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossible de charger l'image pour modération: %s", exc)
        return ModerationResult(decision="needs_review", reason="Image illisible — revue humaine requise")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model=settings.ai_moderation_model,
            max_tokens=300,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                    {"type": "text", "text": "Analyse cette image selon les critères du prompt système et réponds en JSON."},
                ],
            }],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Erreur d'appel IA de modération: %s", exc)
        return ModerationResult(decision="needs_review", reason="Erreur IA — revue humaine requise")

    text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return _parse_decision("\n".join(text_blocks))
