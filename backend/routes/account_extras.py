"""Réglages du compte et historique des visites.

  - GET/PUT /me/settings : notes vocales (envoyer/recevoir), transcription
    écrite des notes vocales, Mode Invisible (14 jours, sur droit), son des
    nouveaux messages (activé / mode silencieux, volume, choix du son).
  - GET  /me/mode-invisible        : état du Mode Invisible (fin, droits, prix du bonus) ;
  - POST /me/mode-invisible/bonus  : acheter le bonus avec le portefeuille (active 14 jours) ;
  - GET/PUT /admin/mode-invisible  : prix du bonus (super-administrateur seulement).
  - GET /me/visitors     : qui a consulté mon profil et regardé mes Moments
    (horodaté). Les visiteurs en mode invisible et l'équipe n'y figurent pas.
  - record_profile_visit : appelé à l'ouverture d'une fiche profil.

Mode invisible : le membre n'apparaît plus "en ligne" (ni "vu il y a…"),
et ses propres visites ne sont pas montrées aux profils qu'il consulte.
Droits, durée et bonus : voir mode_invisible.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import mode_invisible
from activity import current_ip, log_activity
from auth import get_current_super_admin, get_current_user
from db import db
from models import WalletTransaction

router = APIRouter(tags=["Réglages & visites"])

# Sons proposés pour le bip des nouveaux messages (générés dans le navigateur,
# voir frontend/src/lib/bipMessage.js) : identifiant -> libellé
SONS_MESSAGES = {"carillon": "Carillon", "goutte": "Goutte", "bip": "Bip court"}

# Réglages par défaut d'un compte (stockés dans users.settings)
DEFAULT_SETTINGS = {
    "voice_notes": True,          # envoyer et recevoir des notes vocales
    "voice_transcription": True,  # transcrire mes notes / voir les transcriptions
    "invisible_mode": False,      # masquer ma présence et mes visites (14 jours, sur droit)
    "son_messages": True,         # bip à l'arrivée d'un nouveau message (False = mode silencieux)
    "son_volume": 70,             # volume du bip, de 0 à 100
    "son_type": "carillon",       # son choisi (clé de SONS_MESSAGES)
}
_STAFF = ("admin", "moderator")


def user_settings(user: dict) -> dict:
    """Réglages complets du membre (valeurs par défaut pour ce qui n'a jamais été
    réglé). Le Mode Invisible est renvoyé tel qu'il s'applique MAINTENANT :
    éteint si sa date de fin (14 jours) est dépassée."""
    valeurs = {**DEFAULT_SETTINGS, **(user.get("settings") or {})}
    valeurs["invisible_mode"] = mode_invisible.est_actif(user)
    valeurs["invisible_mode_expire_le"] = valeurs.get("invisible_mode_expire_le") if valeurs["invisible_mode"] else None
    if valeurs.get("son_type") not in SONS_MESSAGES:
        valeurs["son_type"] = DEFAULT_SETTINGS["son_type"]
    return valeurs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _reponse_reglages(user_id: str) -> dict:
    """Réglages relus en base + état détaillé du Mode Invisible (coupé s'il a expiré)."""
    frais = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0}) or {"id": user_id}
    frais = await mode_invisible.couper_si_expire(frais)
    return {**user_settings(frais), "sons_disponibles": SONS_MESSAGES,
            "mode_invisible": await mode_invisible.etat_membre(frais)}


@router.get("/me/settings")
async def get_settings_(user: dict = Depends(get_current_user)):
    return await _reponse_reglages(user["id"])


class SettingsUpdate(BaseModel):
    voice_notes: Optional[bool] = None
    voice_transcription: Optional[bool] = None
    invisible_mode: Optional[bool] = None
    son_messages: Optional[bool] = None
    son_volume: Optional[int] = Field(None, ge=0, le=100)
    son_type: Optional[Literal["carillon", "goutte", "bip"]] = None


@router.put("/me/settings")
async def update_settings(payload: SettingsUpdate, user: dict = Depends(get_current_user)):
    valeurs = payload.model_dump(exclude_none=True)
    invisible = valeurs.pop("invisible_mode", None)
    changes = {f"settings.{k}": v for k, v in valeurs.items()}
    update: dict = {}
    if invisible is True:
        # Activation : le serveur vérifie le droit (bonus payé ou formule) ; 403 sinon.
        # La date de fin (14 jours) est enregistrée et contrôlée à chaque lecture.
        changes["settings.invisible_mode"] = True
        changes["settings.invisible_mode_expire_le"] = await mode_invisible.date_fin_activation(user)
        # Passage en invisible : on efface immédiatement la trace "vu il y a…"
        update["$unset"] = {"last_seen_at": ""}
    elif invisible is False:
        changes["settings.invisible_mode"] = False
        changes["settings.invisible_mode_expire_le"] = None
    if changes:
        update["$set"] = changes
    if update:
        await db.users.update_one({"id": user["id"]}, update)
    return await _reponse_reglages(user["id"])


# ---------------------------------------------------------------------------
# Mode Invisible : état, achat du bonus, prix (super-administrateur)
# ---------------------------------------------------------------------------
@router.get("/me/mode-invisible")
async def etat_mode_invisible(user: dict = Depends(get_current_user)):
    return await mode_invisible.etat_membre(await mode_invisible.couper_si_expire(user))


@router.post("/me/mode-invisible/bonus")
async def acheter_bonus(user: dict = Depends(get_current_user)):
    """Achat du bonus Mode Invisible avec le portefeuille (solde en XOF) : le
    montant est débité, le mode est activé aussitôt pour 14 jours."""
    prix = await mode_invisible.prix_bonus()
    if prix is None:
        raise HTTPException(400, "Achat du bonus indisponible : son prix n'a pas encore été fixé par beAuthentik.")
    if mode_invisible.bonus_actif(user):
        raise HTTPException(400, "Vous avez déjà un bonus Mode Invisible en cours.")
    # Débit atomique : seulement si le solde suffit (même règle que les cadeaux)
    debit = await db.users.update_one(
        {"id": user["id"], "wallet_balance_xof": {"$gte": prix}},
        {"$inc": {"wallet_balance_xof": -prix}},
    )
    if debit.modified_count == 0:
        raise HTTPException(400, f"Solde du portefeuille insuffisant : le bonus coûte {prix} XOF. "
                                 "Rechargez votre portefeuille.")
    fin = (mode_invisible.maintenant() + timedelta(days=mode_invisible.DUREE_JOURS)).isoformat()
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"mode_invisible_bonus_jusqu_au": fin, "settings.invisible_mode": True,
                  "settings.invisible_mode_expire_le": fin},
         "$unset": {"last_seen_at": ""}},
    )
    # Ligne du relevé du portefeuille
    ligne = WalletTransaction(user_id=user["id"], kind="bonus_mode_invisible", amount_xof=-prix,
                              description=f"Bonus Mode Invisible ({mode_invisible.DUREE_JOURS} jours)")
    await db.wallet_transactions.insert_one(ligne.model_dump(mode="json"))
    await log_activity(user["id"], "Bonus Mode Invisible acheté", current_ip(), details={"prix_xof": prix, "fin": fin})
    return await _reponse_reglages(user["id"])


class PrixBonus(BaseModel):
    prix_bonus_xof: Optional[int] = None  # None = achat indisponible


@router.get("/admin/mode-invisible")
async def lire_prix_bonus(_: dict = Depends(get_current_super_admin)):
    return await mode_invisible.reglage_admin()


@router.put("/admin/mode-invisible")
async def modifier_prix_bonus(payload: PrixBonus, adm: dict = Depends(get_current_super_admin)):
    reglage = await mode_invisible.regler_prix(payload.prix_bonus_xof, adm)
    await log_activity(adm["id"], "Prix du bonus Mode Invisible modifié", current_ip(),
                       details={"prix_bonus_xof": payload.prix_bonus_xof})
    return reglage


async def record_profile_visit(visitor: dict, target_id: str) -> None:
    """Une visite par visiteur, par profil et par jour (compteur + dernière date)."""
    if visitor["id"] == target_id or visitor.get("role") in _STAFF:
        return
    now = _now()
    await db.profile_visits.update_one(
        {"visitor_id": visitor["id"], "target_id": target_id, "day": now[:10]},
        {"$set": {"last_at": now, "invisible": mode_invisible.est_actif(visitor)},
         "$setOnInsert": {"first_at": now}, "$inc": {"count": 1}},
        upsert=True,
    )


async def _cards(ids) -> dict:
    ids = [i for i in set(ids) if i]
    docs = await db.users.find(
        {"id": {"$in": ids}, "role": {"$nin": list(_STAFF)}, "is_active": True},
        {"_id": 0, "id": 1, "full_name": 1, "city": 1, "photos": 1, "verification_status": 1, "is_test_data": 1,
         "settings": 1},
    ).to_list(len(ids) or 1)
    out = {}
    for d in docs:
        approved = [p for p in d.get("photos", []) if p.get("status") == "approved"]
        primary = next((p for p in approved if p.get("is_primary")), approved[0] if approved else None)
        out[d["id"]] = {
            "id": d["id"], "full_name": d["full_name"], "city": d.get("city"),
            "is_verified": d.get("verification_status") == "verified", "is_test_data": bool(d.get("is_test_data")),
            "avatar_url": (primary.get("masked_url") or primary.get("url")) if primary else None,
        }
    return out


@router.get("/me/visitors")
async def my_visitors(user: dict = Depends(get_current_user)):
    """Historique horodaté : visites de mon profil et vues de mes Moments."""
    visits = await db.profile_visits.find(
        {"target_id": user["id"], "invisible": {"$ne": True}}, {"_id": 0}
    ).sort("last_at", -1).to_list(300)
    my_videos = await db.videos.find({"user_id": user["id"]}, {"_id": 0, "id": 1, "caption": 1, "poster_url": 1}).to_list(500)
    videos_by_id = {v["id"]: v for v in my_videos}
    views = await db.video_views.find(
        {"video_id": {"$in": list(videos_by_id)}, "user_id": {"$ne": user["id"]}, "invisible": {"$ne": True}}, {"_id": 0}
    ).to_list(1000)
    views.sort(key=lambda v: v.get("created_at") or v.get("viewed_at") or "", reverse=True)
    cards = await _cards([v["visitor_id"] for v in visits] + [v["user_id"] for v in views])

    profile_items = [
        {"visitor": cards[v["visitor_id"]], "at": v["last_at"], "count": v.get("count", 1)}
        for v in visits if v["visitor_id"] in cards
    ]
    moment_items = [
        {"viewer": cards[v["user_id"]], "at": v.get("created_at") or v.get("viewed_at"),
         "video": videos_by_id.get(v["video_id"])}
        for v in views if v["user_id"] in cards
    ]
    return {"profile_visits": profile_items[:200], "moment_views": moment_items[:200]}
