"""Onglet « Usage » du back-office (lot 47) — voir blocages_acces.py pour les règles.

Super-administrateur UNIQUEMENT (rôle « admin » ; 403 pour les modérateurs et les membres) :
  - GET  /api/admin/usage/connexions          : historique des connexions (50 par page,
                                                plus récentes en haut ; filtres q, du, au,
                                                abonnement, etat) ;
  - GET  /api/admin/usage/presence?sids=a,b   : pastilles de présence (rafraîchies toutes les
                                                30 s par le site, en requête de FOND : ne compte
                                                pas comme une activité de l'administrateur) ;
  - GET  /api/admin/usage/blocages            : blocages en cours ;
  - POST /api/admin/usage/blocages            : bloquer une IP (ce compte / tous) ou un compte ;
  - POST /api/admin/usage/blocages/{id}/lever : lever un blocage ;
  - POST /api/admin/usage/autoriser           : lever tous les blocages d'une IP ou d'un compte ;
  - GET  /api/admin/usage/journal             : journal des actions (qui, quand, quoi) ;
  - GET/PUT /api/admin/usage/contact          : contact affiché sur la page de blocage.
Public (sans connexion) :
  - GET  /api/acces-suspendu/contact          : contact affiché sur la page « Accès
                                                momentanément suspendu ».
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

import abonnement_grace
import blocages_acces as service
from auth import get_current_super_admin
from db import db

admin = APIRouter(prefix="/admin/usage", tags=["Usage (super-administrateur)"])
public = APIRouter(tags=["Accès suspendu"])

PAR_PAGE = 50

LIBELLES_ABONNEMENT = {"aucun": "Aucun", "actif": "Actif", "grace": "Période de grâce", "expire": "Expiré"}


class Blocage(BaseModel):
    """Demande de blocage envoyée par l'onglet « Usage »."""
    type: Literal["ip", "compte"]
    ip: Optional[str] = Field(None, max_length=64)
    user_id: Optional[str] = Field(None, max_length=64)
    tous_comptes: bool = True              # IP : bloquée pour tous les comptes (case cochée par défaut)
    libelle: Optional[str] = Field(None, max_length=120)  # nom facultatif du site (ex. « Cybercafé X »)
    motif: Optional[str] = Field(None, max_length=300)


class Autorisation(BaseModel):
    type: Literal["ip", "compte"]
    ip: Optional[str] = Field(None, max_length=64)
    user_id: Optional[str] = Field(None, max_length=64)


class Contact(BaseModel):
    email: Optional[str] = Field(None, max_length=200)
    whatsapp: Optional[str] = Field(None, max_length=40)


# ---------------------------------------------------------------------------
# Historique des connexions
# ---------------------------------------------------------------------------
async def _abonnement(user_id: str, user: dict, formules: dict) -> dict:
    """État lisible de l'abonnement : formule + actif / grâce / expiré / aucun."""
    etat = await abonnement_grace.etat(user_id, user)
    statut = etat.get("statut", "aucun")
    libelle = LIBELLES_ABONNEMENT.get(statut, statut)
    if statut == "grace" and etat.get("jours_grace_restants"):
        libelle = f"Période de grâce ({etat['jours_grace_restants']} j)"
    return {"statut": statut, "libelle": libelle, "formule": formules.get(etat.get("plan_id")),
            "echeance": etat.get("echeance")}


@admin.get("/connexions")
async def connexions(
    q: str = Query("", max_length=100),
    du: str = Query("", max_length=10),
    au: str = Query("", max_length=10),
    abonnement: str = Query("", max_length=10),
    etat: str = Query("", max_length=10),
    page: int = Query(1, ge=1, le=10_000),
    _: dict = Depends(get_current_super_admin),
):
    # --- 1. Filtre MongoDB (période, état, recherche compte / IP) ---
    filtre: dict = {}
    debut, fin = service.debut_periode(du or None), service.debut_periode(au or None, fin=True)
    if debut or fin:
        filtre["date"] = {k: v for k, v in (("$gte", debut), ("$lt", fin)) if v}
    if etat in ("reussie", "refusee"):
        filtre["etat"] = etat
    if q.strip():
        motif = {"$regex": re.escape(q.strip()), "$options": "i"}
        ids = await db.users.distinct("id", {"$or": [{"full_name": motif}, {"email": motif}, {"phone": motif}]})
        filtre["$or"] = [{"ip": motif}, {"identifiant": motif}, {"user_id": {"$in": ids}}]
    # État de l'abonnement : calculé (pas stocké) -> on retient les comptes qui conviennent
    if abonnement in LIBELLES_ABONNEMENT:
        retenus = []
        for uid in await db.connexions_journal.distinct("user_id", filtre):
            if uid and (await abonnement_grace.etat(uid))["statut"] == abonnement:
                retenus.append(uid)
        filtre["user_id"] = {"$in": retenus}

    # --- 2. Page demandée (50 lignes, plus récentes en haut) ---
    total = await db.connexions_journal.count_documents(filtre)
    lignes = await db.connexions_journal.find(filtre, {"_id": 0}).sort("date", -1) \
        .skip((page - 1) * PAR_PAGE).limit(PAR_PAGE).to_list(PAR_PAGE)

    # --- 3. Compléments : comptes, abonnements, blocages, présence ---
    uids = list({l["user_id"] for l in lignes if l.get("user_id")})
    comptes = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": uids}},
        {"_id": 0, "id": 1, "full_name": 1, "email": 1, "phone": 1, "role": 1, "grace_jours": 1}).to_list(len(uids) or 1)}
    formules = {p["id"]: p.get("name") for p in await db.subscription_plans.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(200)}
    abonnements = {uid: await _abonnement(uid, comptes.get(uid) or {}, formules) for uid in uids}
    blocages = await service.blocages_actifs(cache=False)
    presence = await service.presence_sessions([l.get("sid") for l in lignes if l.get("sid")])

    items = []
    for l in lignes:
        uid = l.get("user_id")
        compte = comptes.get(uid)
        items.append({
            "id": l["id"], "date": l["date"], "ip": l.get("ip"), "etat": l.get("etat"), "motif": l.get("motif"),
            "methode": l.get("methode"), "methode_libelle": service.METHODES.get(l.get("methode"), l.get("methode")),
            "appareil": l.get("appareil"), "sid": l.get("sid"), "identifiant": l.get("identifiant"),
            "compte": {"id": compte["id"], "nom": compte.get("full_name"),
                       "identifiant": compte.get("email") or compte.get("phone"),
                       "super_admin": compte.get("role") == "admin"} if compte else None,
            "abonnement": abonnements.get(uid) or {"statut": "aucun", "libelle": "—", "formule": None},
            "ip_etat": service.etat_ip(blocages, uid, l.get("ip")),
            "compte_bloque": service.compte_bloque(blocages, uid) if uid else False,
            "presence": presence.get(l.get("sid")) or service.couleur_presence(None),
        })
    return {"items": items, "total": total, "page": page, "par_page": PAR_PAGE,
            "pages": max(1, -(-total // PAR_PAGE))}


@admin.get("/presence")
async def presence(sids: str = Query("", max_length=20_000), _: dict = Depends(get_current_super_admin)):
    """Pastilles de présence d'une liste de sessions (identifiants séparés par des virgules)."""
    return {"presence": await service.presence_sessions([s.strip() for s in sids.split(",") if s.strip()])}


# ---------------------------------------------------------------------------
# Blocages
# ---------------------------------------------------------------------------
@admin.get("/blocages")
async def blocages_en_cours(_: dict = Depends(get_current_super_admin)):
    liste = await db.blocages.find({"actif": True}, {"_id": 0}).sort("cree_le", -1).to_list(1000)
    return {"blocages": liste}


@admin.post("/blocages")
async def creer_blocage(data: Blocage, adm: dict = Depends(get_current_super_admin)):
    return await service.bloquer(adm, type_=data.type, ip=data.ip, user_id=data.user_id,
                                 tous_comptes=data.tous_comptes, libelle=data.libelle, motif=data.motif)


@admin.post("/blocages/{blocage_id}/lever")
async def lever_blocage(blocage_id: str, adm: dict = Depends(get_current_super_admin)):
    return await service.lever(adm, blocage_id)


@admin.post("/autoriser")
async def autoriser(data: Autorisation, adm: dict = Depends(get_current_super_admin)):
    n = await service.autoriser(adm, type_=data.type, ip=data.ip, user_id=data.user_id)
    return {"ok": True, "leves": n}


@admin.get("/journal")
async def journal_actions(_: dict = Depends(get_current_super_admin)):
    return {"actions": await db.blocages_journal.find({}, {"_id": 0}).sort("date", -1).to_list(100)}


@admin.get("/contact")
async def lire_contact(_: dict = Depends(get_current_super_admin)):
    return await service.lire_contact()


@admin.put("/contact")
async def regler_contact(data: Contact, adm: dict = Depends(get_current_super_admin)):
    return await service.regler_contact(adm, data.email, data.whatsapp)


@public.get("/acces-suspendu/contact")
async def contact_public():
    """Contact de la plateforme pour la page « Accès momentanément suspendu »
    (vide = le site affiche le contact officiel des pages légales)."""
    return await service.lire_contact()
