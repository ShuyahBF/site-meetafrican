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

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from config import get_settings
from vidal_client import parse_products_search, vidal_get

router = APIRouter(prefix="/vidal", tags=["VIDAL Sécurisation"])


def _require_proxy_secret(x_vidal_proxy_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = (settings.vidal_proxy_secret or "").strip()
    if not expected or x_vidal_proxy_secret != expected:
        raise HTTPException(status_code=403, detail="Accès VIDAL refusé (secret manquant ou invalide)")


@router.get("/products/search", dependencies=[Depends(_require_proxy_secret)])
async def search_products(q: str = Query(..., min_length=2, max_length=100)):
    """Recherche de produit par libellé — GET /rest/api/products?q=...
    Utilisé pour remplacer le typeahead simulé de /secure (Sécurisation,
    Posologie, Fiche produit) par de vrais résultats VIDAL."""
    xml_text = await vidal_get("/products", {"q": q})
    return {"query": q, "results": parse_products_search(xml_text)}
