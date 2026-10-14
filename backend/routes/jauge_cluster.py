"""Lot 77 — GET /api/admin/atlas/jauge : occupation du cluster de production (administrateur principal uniquement).
Règles de calcul : jauge_cluster.py. Jamais d'adresse ni d'identifiant de connexion dans la réponse."""
from __future__ import annotations

from fastapi import APIRouter, Depends

import jauge_cluster
from auth import get_current_super_admin
from config import get_settings
from db import db

router = APIRouter(prefix="/admin/atlas", tags=["Administration"])


@router.get("/jauge")
async def jauge(forcer: bool = False, _: dict = Depends(get_current_super_admin)):
    """Taille occupée (Mo) et nombre de collections du cluster, avec couleur et pourcentage ;
    « forcer » ignore la mesure gardée en mémoire (10 min)."""
    # Le client Mongo est celui de la base de la plateforme (la base enveloppée par PrefixedDatabase)
    return await jauge_cluster.mesurer(db._database.client, get_settings().mongo_db_name, forcer)
