"""Client pour l'API REST VIDAL Sécurisation (https://api.vidal.fr).

Un seul environnement réel pour ce compte (pas de sandbox VIDAL distincte) :
toutes les requêtes tapent directement l'API de production, avec un cache
Mongo (TTL configurable, `vidal_api_cache`) pour épargner le quota sur des
recherches répétées, et un compteur journalier (`vidal_api_quota`) qui
bloque avant de dépasser l'abonnement VIDAL plutôt que de laisser l'API
elle-même renvoyer une erreur de dépassement.

Sortie VIDAL en XML ATOM uniquement (pas de JSON — manuel d'intégration
MI_APIREST REV_03, section « Formats de retour »).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException

from config import get_settings
from db import db

ATOM_NS = "http://www.w3.org/2005/Atom"
VIDAL_NS = "http://api.vidal.net/-/spec/vidal-api/1.0/"
_NS = {"a": ATOM_NS, "vidal": VIDAL_NS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_key(path: str, params: Dict[str, Any]) -> str:
    # app_id/app_key exclus de la clé : ce sont des identifiants de compte,
    # pas des paramètres de la requête — les inclure casserait le cache si
    # on change un jour de couple app_id/app_key sans que la réponse change.
    raw = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _get_cached(cache_key: str) -> Optional[str]:
    doc = await db.vidal_api_cache.find_one({"key": cache_key})
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if expires_at is None:
        return None
    # MongoDB stocke les dates en UTC mais les renvoie "naive" (BSON n'a pas
    # de notion de fuseau) — on les requalifie en UTC avant de comparer à
    # _now(), sinon Python refuse de comparer naive/aware.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        return None
    return doc["xml"]


async def _set_cache(cache_key: str, xml_text: str, path: str) -> None:
    settings = get_settings()
    if settings.vidal_cache_ttl_hours <= 0:
        return
    expires_at = _now() + timedelta(hours=settings.vidal_cache_ttl_hours)
    await db.vidal_api_cache.update_one(
        {"key": cache_key},
        {"$set": {
            "key": cache_key, "path": path, "xml": xml_text,
            "cached_at": _now(), "expires_at": expires_at,
        }},
        upsert=True,
    )


async def _check_and_increment_quota() -> None:
    """Bloque AVANT l'appel si le quota du jour est déjà atteint — on ne
    veut jamais découvrir un dépassement d'abonnement via une erreur VIDAL
    en pleine navigation d'un médecin."""
    settings = get_settings()
    if settings.vidal_quota_per_day <= 0:
        return
    day_key = _now().strftime("%Y-%m-%d")
    doc = await db.vidal_api_quota.find_one({"day": day_key})
    if doc and doc.get("count", 0) >= settings.vidal_quota_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Quota VIDAL journalier atteint ({settings.vidal_quota_per_day} requêtes/jour).",
        )
    await db.vidal_api_quota.update_one(
        {"day": day_key}, {"$inc": {"count": 1}}, upsert=True,
    )


async def vidal_get(path: str, params: Optional[Dict[str, Any]] = None, use_cache: bool = True) -> str:
    """GET https://api.vidal.fr/rest/api{path} avec app_id/app_key ajoutés
    automatiquement. Passe par le cache Mongo sauf use_cache=False (utile
    pour un diagnostic où on veut forcer un vrai appel). Retourne le corps
    XML ATOM brut ; lève HTTPException sur erreur VIDAL, quota dépassé,
    timeout ou identifiants manquants."""
    settings = get_settings()
    if not settings.vidal_app_id or not settings.vidal_app_key:
        raise HTTPException(status_code=503, detail="VIDAL non configuré (app_id/app_key manquants côté serveur)")

    params = dict(params or {})
    cache_key = _cache_key(path, params)
    if use_cache:
        cached = await _get_cached(cache_key)
        if cached is not None:
            return cached

    await _check_and_increment_quota()

    query = {**params, "app_id": settings.vidal_app_id, "app_key": settings.vidal_app_key}
    url = f"{settings.vidal_base_url.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=settings.vidal_timeout_seconds) as client:
            r = await client.get(url, params=query)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Délai dépassé lors de l'appel à VIDAL")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur réseau vers VIDAL : {str(exc)[:200]}") from exc

    # Codes documentés dans le manuel d'intégration (section « Codes d'erreur »).
    if r.status_code == 401:
        raise HTTPException(status_code=502, detail="Identifiants VIDAL refusés (401) — vérifier app_id/app_key")
    if r.status_code == 403:
        raise HTTPException(status_code=502, detail="Accès VIDAL interdit (403) pour cette ressource")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Ressource VIDAL introuvable")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Erreur VIDAL {r.status_code} : {r.text[:300]}")

    xml_text = r.text
    if use_cache:
        await _set_cache(cache_key, xml_text, path)
    return xml_text


def parse_products_search(xml_text: str) -> List[Dict[str, Any]]:
    """Parse le flux Atom de GET /products?q=... en liste de dicts simples,
    prêts à être renvoyés en JSON au frontend (voir routes/vidal.py)."""
    root = ElementTree.fromstring(xml_text)
    results = []
    for entry in root.findall("a:entry", _NS):
        def vtext(tag: str) -> Optional[str]:
            el = entry.find(f"vidal:{tag}", _NS)
            return el.text if el is not None else None

        def vattr(tag: str, attr: str) -> Optional[str]:
            el = entry.find(f"vidal:{tag}", _NS)
            return el.get(attr) if el is not None else None

        results.append({
            "id": vtext("id"),
            "name": vtext("name"),
            "market_status": vattr("marketStatus", "name"),
            "best_doc_type": vattr("bestDocType", "name"),
            "without_prescription": vtext("withoutPrescription") == "true",
            "active_principles": vtext("activePrinciples"),
        })
    return results
