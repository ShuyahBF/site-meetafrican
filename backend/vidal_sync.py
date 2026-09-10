"""Synchronisation périodique du référentiel produits VIDAL vers un cache
Mongo local (`vidal_cache_referentiel_produits`), pour éviter un aller-retour
réseau vers api.vidal.fr à chaque frappe clavier dans le typeahead de
recherche produit.

Fonctionnement :
- `run_referentiel_sync()` parcourt TOUT le catalogue VIDAL (GET /products
  avec q vide, paginé 25/page — confirmé par test réel : 15 680 produits,
  soit ~628 appels) et upsert chaque produit dans le cache.
- C'est une opération admin/interne : elle contourne le quota journalier
  anti-abus (`bypass_quota=True` sur vidal_get) — ce quota protège contre
  des utilisateurs finaux qui abuseraient de la recherche, pas contre une
  synchronisation explicitement déclenchée par l'admin.
- Un job planifié (`sync_scheduler_loop`, lancé au démarrage du serveur)
  vérifie périodiquement si la fréquence configurée par l'admin est
  écoulée depuis la dernière synchronisation, et relance si besoin — sans
  dépendre d'un vrai service cron externe (pas nécessaire vu le volume,
  ~628 appels se font en quelques minutes).
- Chaque exécution (planifiée ou manuelle) est journalisée dans
  `vidal_sync_log` avec date/heure, résultats et le type fixe "sync_refer",
  comme demandé.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from config import get_settings
from db import db
from vidal_client import parse_products_search_page, vidal_get

logger = logging.getLogger("vidal_sync")

_CONFIG_ID = "singleton"
_PAGE_SIZE = 25
_SCHEDULER_CHECK_INTERVAL_SECONDS = 3600  # vérifie 1x/heure si une sync est due


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_sync_config() -> Dict[str, Any]:
    """Renvoie la config de synchronisation (créée avec des valeurs par
    défaut prudentes si absente) : mode "temps_reel" par défaut — on ne
    bascule jamais la recherche sur un cache vide sans que l'admin l'ait
    explicitement choisi et qu'une synchronisation ait déjà eu lieu."""
    doc = await db.vidal_sync_config.find_one({"id": _CONFIG_ID}, {"_id": 0})
    if doc:
        return doc
    default = {
        "id": _CONFIG_ID,
        "mode": "temps_reel",  # "temps_reel" | "cache"
        "frequency_days": 7,   # paramétrable par l'admin (ex. 7 = semaine, 30 = mois)
        "last_sync_at": None,
        "sync_in_progress": False,
        "updated_at": _now(),
    }
    await db.vidal_sync_config.update_one({"id": _CONFIG_ID}, {"$setOnInsert": default}, upsert=True)
    return default


async def update_sync_config(mode: Optional[str] = None, frequency_days: Optional[int] = None) -> Dict[str, Any]:
    if mode is not None and mode not in ("temps_reel", "cache"):
        raise ValueError("mode invalide (attendu : temps_reel | cache)")
    update: Dict[str, Any] = {"updated_at": _now()}
    if mode is not None:
        update["mode"] = mode
    if frequency_days is not None:
        update["frequency_days"] = max(0, int(frequency_days))
    await get_sync_config()  # garantit l'existence du doc avant le $set
    await db.vidal_sync_config.update_one({"id": _CONFIG_ID}, {"$set": update})
    return await get_sync_config()


async def has_cached_referentiel() -> bool:
    """Utilisé par la recherche pour ne jamais retomber sur un cache vide en
    mode "cache" faute de synchronisation initiale — repli automatique sur
    le temps réel plutôt qu'une liste de résultats vide et déroutante."""
    config = await get_sync_config()
    return config.get("last_sync_at") is not None


def _to_cache_doc(product: Dict[str, Any], synced_at: datetime) -> Dict[str, Any]:
    return {**product, "product_id": product["id"], "synced_at": synced_at}


async def run_referentiel_sync(triggered_by: str = "cron") -> Dict[str, Any]:
    """Parcourt tout le catalogue VIDAL et met à jour le cache. Toujours
    journalisé (succès, échec ou partiel), même si aucune ligne n'a pu être
    synchronisée — jamais d'exécution silencieuse."""
    config = await get_sync_config()
    if config.get("sync_in_progress"):
        logger.info("Synchronisation référentiel déjà en cours, run ignoré (%s)", triggered_by)
        return {"status": "skipped_already_running"}

    await db.vidal_sync_config.update_one({"id": _CONFIG_ID}, {"$set": {"sync_in_progress": True}})
    start = _now()
    page = 1
    total_expected: Optional[int] = None
    synced_count = 0
    api_calls = 0
    error_message: Optional[str] = None

    try:
        # Un seul client HTTP réutilisé pour les ~628 appels de la synchronisation
        # complète (connexion TLS gardée ouverte) — sans ça, chaque appel repayait
        # une négociation TLS complète : testé en réel, ~16 minutes sans réutilisation.
        timeout = get_settings().vidal_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                xml_text = await vidal_get(
                    "/products", {"q": "", "start-page": page, "page-size": _PAGE_SIZE},
                    use_cache=False, bypass_quota=True, client=client,
                )
                api_calls += 1
                results, total_results = parse_products_search_page(xml_text)
                if total_expected is None:
                    total_expected = total_results

                if not results:
                    break

                now = _now()
                for product in results:
                    if not product.get("id"):
                        continue
                    doc = _to_cache_doc(product, now)
                    await db.vidal_cache_referentiel_produits.update_one(
                        {"product_id": doc["product_id"]}, {"$set": doc}, upsert=True,
                    )
                    synced_count += 1

                if total_expected and synced_count >= total_expected:
                    break
                page += 1
    except Exception as exc:  # noqa: BLE001 — on journalise puis on relance, jamais d'échec silencieux
        error_message = str(exc)[:500]
        logger.exception("Erreur pendant la synchronisation du référentiel VIDAL")
    finally:
        await db.vidal_sync_config.update_one({"id": _CONFIG_ID}, {"$set": {"sync_in_progress": False}})

    finished = _now()
    duration_seconds = (finished - start).total_seconds()
    status = "error" if (error_message and synced_count == 0) else ("partial" if error_message else "success")
    result_summary = (
        f"{synced_count} produit(s) synchronisé(s) sur {total_expected or '?'} annoncés, "
        f"{api_calls} appel(s) API VIDAL, {duration_seconds:.0f}s"
        + (f" — erreur : {error_message}" if error_message else "")
    )

    log_entry = {
        "ts": start,
        "type": "sync_refer",
        "status": status,
        "result": result_summary,
        "products_synced": synced_count,
        "products_expected": total_expected,
        "api_calls": api_calls,
        "duration_seconds": round(duration_seconds, 1),
        "triggered_by": triggered_by,
        "error_message": error_message,
    }
    await db.vidal_sync_log.insert_one(log_entry.copy())

    if status != "error":
        await db.vidal_sync_config.update_one({"id": _CONFIG_ID}, {"$set": {"last_sync_at": start}})

    logger.info("Synchronisation référentiel VIDAL terminée : %s", result_summary)
    return log_entry


async def _maybe_run_scheduled_sync() -> None:
    config = await get_sync_config()
    frequency_days = config.get("frequency_days") or 0
    if frequency_days <= 0:
        return  # 0 = planification désactivée, seule la sync manuelle reste possible
    last_sync_at = config.get("last_sync_at")
    if last_sync_at is not None and last_sync_at.tzinfo is None:
        last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)
    due = last_sync_at is None or (_now() - last_sync_at) >= timedelta(days=frequency_days)
    if due:
        await run_referentiel_sync(triggered_by="cron")


async def sync_scheduler_loop() -> None:
    """Boucle de fond démarrée une fois au lancement du serveur (voir
    server.py). Pas de vrai service cron externe : le volume (~628 appels,
    quelques minutes) ne le justifie pas, et ça évite de dépendre d'un
    service Render supplémentaire pour une fréquence de toute façon
    reconfigurable dynamiquement par l'admin (pas figée au déploiement)."""
    while True:
        try:
            await _maybe_run_scheduled_sync()
        except Exception:  # noqa: BLE001 — la boucle ne doit jamais s'arrêter sur une erreur ponctuelle
            logger.exception("Erreur dans la boucle de planification de synchronisation VIDAL")
        await asyncio.sleep(_SCHEDULER_CHECK_INTERVAL_SECONDS)
