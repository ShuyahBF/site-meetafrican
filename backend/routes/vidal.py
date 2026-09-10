"""Proxy backend vers l'API REST VIDAL Sécurisation (api.vidal.fr).

Vrais appels, credentials réels côté serveur uniquement (jamais exposés au
navigateur — l'API VIDAL s'authentifie par app_id/app_key en paramètres de
requête, qui fuiraient instantanément si un appel direct était fait depuis
le JavaScript de la page /secure). Protégé par un secret partagé
(VIDAL_PROXY_SECRET) car /secure est une route cachée mais sans vrai login :
sans ce garde-fou, n'importe qui tombant sur l'URL pourrait épuiser le
quota VIDAL réel.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from config import get_settings
from db import db
from vidal_client import parse_product_detail, parse_products_search, vidal_get
from vidal_sync import get_sync_config, has_cached_referentiel, run_referentiel_sync, update_sync_config

router = APIRouter(prefix="/vidal", tags=["VIDAL Sécurisation"])

# Hôtes VIDAL publics autorisés pour /documents/proxy — jamais un proxy ouvert :
# seuls ces domaines connus, vus dans les URLs renvoyées par /product/{id}/detail.
_ALLOWED_DOCUMENT_HOSTS = {"api.vidal.fr", "document-rcp.vidal.fr"}


def _require_proxy_secret(x_vidal_proxy_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = (settings.vidal_proxy_secret or "").strip()
    if not expected or x_vidal_proxy_secret != expected:
        raise HTTPException(status_code=403, detail="Accès VIDAL refusé (secret manquant ou invalide)")


def _cache_doc_to_result(doc: dict) -> dict:
    return {
        "id": doc.get("product_id"),
        "name": doc.get("name"),
        "market_status": doc.get("market_status"),
        "best_doc_type": doc.get("best_doc_type"),
        "without_prescription": doc.get("without_prescription"),
        "active_principles": doc.get("active_principles"),
    }


@router.get("/products/search", dependencies=[Depends(_require_proxy_secret)])
async def search_products(q: str = Query(..., min_length=2, max_length=100)):
    """Recherche de produit par libellé. Deux sources possibles, pilotées par
    la config admin (voir /vidal/admin/sync-config) :
    - "cache" : recherche dans vidal_cache_referentiel_produits (pas d'appel
      VIDAL, donc pas d'aller-retour réseau à chaque frappe) — seulement si
      une synchronisation a déjà eu lieu au moins une fois, sinon repli
      automatique sur le temps réel pour ne jamais renvoyer une liste vide
      faute de cache peuplé.
    - "temps_reel" (par défaut) : GET /rest/api/products?q=... comme avant.
    Une fois un produit sélectionné, /products/{id}/detail reste TOUJOURS
    en temps réel, quel que soit le mode — seule la recherche est concernée."""
    config = await get_sync_config()
    if config.get("mode") == "cache" and await has_cached_referentiel():
        cursor = db.vidal_cache_referentiel_produits.find(
            {"name": {"$regex": re.escape(q), "$options": "i"}}
        ).limit(25)
        results = [_cache_doc_to_result(doc) async for doc in cursor]
        return {"query": q, "results": results, "source": "cache"}

    xml_text = await vidal_get("/products", {"q": q})
    return {"query": q, "results": parse_products_search(xml_text), "source": "temps_reel"}


@router.get("/products/{product_id}/detail", dependencies=[Depends(_require_proxy_secret)])
async def product_detail(product_id: str):
    """Voies d'administration et documents disponibles pour un produit — un
    seul appel VIDAL agrégé (GET /product/{id}?aggregate=ROUTE&aggregate=DOCUMENTS),
    confirmé par test réel. Alimente le card 2 de Fiche produit VIDAL et les
    listes déroulantes de voie de Sécurisation."""
    xml_text = await vidal_get(f"/product/{product_id}", {"aggregate": ["ROUTE", "DOCUMENTS"]})
    return parse_product_detail(xml_text)


@router.get("/documents/proxy", dependencies=[Depends(_require_proxy_secret)])
async def proxy_document(url: str = Query(..., min_length=1)):
    """Relaye un document VIDAL public (PDF notamment) depuis notre propre origine.

    Certains documents (RCP sur document-rcp.vidal.fr) renvoient un en-tête
    X-Frame-Options: SAMEORIGIN — confirmé par test réel — qui empêche de les
    charger en iframe directement depuis leur URL VIDAL. Ce sont des URLs
    publiques (aucun app_id/app_key requis, donc aucun quota consommé ici) ;
    on les relaie simplement pour qu'elles s'affichent dans la page plutôt
    que de forcer un lien externe. Liste d'hôtes limitée pour ne jamais
    devenir un proxy ouvert vers un domaine arbitraire."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in _ALLOWED_DOCUMENT_HOSTS:
        raise HTTPException(status_code=400, detail="URL de document non autorisée")

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(url)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Délai dépassé en récupérant le document VIDAL")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Erreur en récupérant le document : {str(exc)[:200]}") from exc

    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Document VIDAL introuvable ({r.status_code})")

    return Response(content=r.content, media_type=r.headers.get("content-type", "application/octet-stream"))


# --- Administration du cache référentiel produits ---------------------------
# Fréquence de synchronisation et mode recherche (cache/temps réel)
# paramétrables par l'admin, déclenchement manuel possible, journalisation
# systématique (type fixe "sync_refer") — voir vidal_sync.py pour la logique.

class SyncConfigUpdate(BaseModel):
    mode: str | None = Field(None, description="temps_reel | cache")
    frequency_days: int | None = Field(None, ge=0, le=365)


@router.get("/admin/sync-config", dependencies=[Depends(_require_proxy_secret)])
async def get_sync_config_route():
    return await get_sync_config()


@router.put("/admin/sync-config", dependencies=[Depends(_require_proxy_secret)])
async def update_sync_config_route(payload: SyncConfigUpdate):
    try:
        return await update_sync_config(mode=payload.mode, frequency_days=payload.frequency_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/sync-now", dependencies=[Depends(_require_proxy_secret)])
async def trigger_sync_now(background_tasks: BackgroundTasks):
    """Synchronisation manuelle — lancée en tâche de fond (le parcours complet
    du référentiel, ~628 appels VIDAL, prend quelques minutes) : la requête
    HTTP répond immédiatement, le résultat est consultable ensuite via
    /admin/sync-log."""
    config = await get_sync_config()
    if config.get("sync_in_progress"):
        return {"status": "already_running"}
    # FastAPI détecte que run_referentiel_sync est une coroutine et l'exécute
    # sur la même boucle asyncio après la réponse — ne jamais appeler la
    # fonction ici (elle serait exécutée immédiatement au lieu d'être différée).
    background_tasks.add_task(run_referentiel_sync, triggered_by="manuel")
    return {"status": "started"}


@router.get("/admin/sync-log", dependencies=[Depends(_require_proxy_secret)])
async def get_sync_log(limit: int = Query(20, ge=1, le=100)):
    cursor = db.vidal_sync_log.find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    return {"entries": [entry async for entry in cursor]}
