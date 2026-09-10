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


async def vidal_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
    bypass_quota: bool = False,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """GET https://api.vidal.fr/rest/api{path} avec app_id/app_key ajoutés
    automatiquement. Passe par le cache Mongo sauf use_cache=False (utile
    pour un diagnostic où on veut forcer un vrai appel). Retourne le corps
    XML ATOM brut ; lève HTTPException sur erreur VIDAL, quota dépassé,
    timeout ou identifiants manquants.

    bypass_quota=True : réservé aux opérations internes/admin (ex. la
    synchronisation complète du référentiel produits, ~628 appels) — le
    quota journalier existe pour éviter les abus d'utilisateurs finaux,
    pas pour brider une opération explicitement déclenchée par l'admin.

    client : réutiliser un httpx.AsyncClient existant (connexion TLS gardée
    ouverte entre appels) plutôt que d'en ouvrir un nouveau à chaque fois —
    essentiel pour un enchaînement de nombreux appels (ex. les 628 appels
    d'une synchronisation complète du référentiel, voir vidal_sync.py) :
    testé en réel, sans réutilisation la synchronisation complète prend
    ~16 minutes essentiellement en négociations TLS répétées."""
    settings = get_settings()
    if not settings.vidal_app_id or not settings.vidal_app_key:
        raise HTTPException(status_code=503, detail="VIDAL non configuré (app_id/app_key manquants côté serveur)")

    params = dict(params or {})
    cache_key = _cache_key(path, params)
    if use_cache:
        cached = await _get_cached(cache_key)
        if cached is not None:
            return cached

    if not bypass_quota:
        await _check_and_increment_quota()

    query = {**params, "app_id": settings.vidal_app_id, "app_key": settings.vidal_app_key}
    url = f"{settings.vidal_base_url.rstrip('/')}{path}"
    try:
        if client is not None:
            r = await client.get(url, params=query)
        else:
            async with httpx.AsyncClient(timeout=settings.vidal_timeout_seconds) as one_shot_client:
                r = await one_shot_client.get(url, params=query)
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


OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"


def parse_products_search_page(xml_text: str) -> tuple[List[Dict[str, Any]], int]:
    """Comme parse_products_search, mais renvoie aussi le nombre total de
    résultats (balise opensearch:totalResults) — nécessaire pour paginer
    jusqu'au bout lors de la synchronisation complète du référentiel
    (vidal_sync.py), sans deviner combien de pages il reste à parcourir."""
    root = ElementTree.fromstring(xml_text)
    total_el = root.find(f"{{{OPENSEARCH_NS}}}totalResults")
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    return parse_products_search(xml_text), total


def parse_product_detail(xml_text: str) -> Dict[str, Any]:
    """Parse le flux Atom de GET /product/{id}?aggregate=ROUTE&aggregate=DOCUMENTS
    (un seul appel VIDAL renvoie le produit, ses voies d'administration ET ses
    documents disponibles — confirmé par test réel, pas par supposition sur le
    manuel). Chaque <entry> porte vidal:categories="PRODUCT|ROUTE|DOCUMENT" ;
    on les répartit selon cet attribut plutôt que de deviner leur ordre."""
    root = ElementTree.fromstring(xml_text)
    categories_attr = f"{{{VIDAL_NS}}}categories"
    name: Optional[str] = None
    routes: List[Dict[str, Any]] = []
    documents: Dict[str, Dict[str, Any]] = {}  # dédupliqué par item_type (garde la 1ère occurrence = la plus récente)

    for entry in root.findall("a:entry", _NS):
        category = entry.get(categories_attr)

        if category == "PRODUCT":
            name_el = entry.find("vidal:name", _NS)
            name = name_el.text if name_el is not None else None

        elif category == "ROUTE":
            id_el = entry.find("vidal:id", _NS)
            name_el = entry.find("vidal:name", _NS)
            routes.append({
                "id": id_el.text if id_el is not None else None,
                "name": name_el.text if name_el is not None else None,
            })

        elif category == "DOCUMENT":
            item_type_el = entry.find("vidal:itemType", _NS)
            item_type = (item_type_el.get("name") if item_type_el is not None else None) or (
                item_type_el.text if item_type_el is not None else None
            )
            if not item_type or item_type in documents:
                continue  # on ne garde que la 1ère occurrence (la plus récente) par type
            title_el = entry.find("a:title", _NS)
            doc_url = None
            for link in entry.findall("a:link", _NS):
                if link.get("rel") == "related" and link.get("type") == "application/xhtml+xml":
                    doc_url = link.get("href")
                    break
            documents[item_type] = {
                "item_type": item_type,
                "title": title_el.text if title_el is not None else None,
                "url": doc_url,
                # HTML public directement affichable en iframe (confirmé par test réel :
                # api.vidal.fr/data/mono/... répond sans auth, sans X-Frame-Options) — le
                # reste (PDF sur document-rcp.vidal.fr notamment) doit s'ouvrir en lien externe.
                "is_html": bool(doc_url and doc_url.lower().endswith((".html", ".htm"))),
            }

    return {"name": name, "routes": routes, "documents": list(documents.values())}
