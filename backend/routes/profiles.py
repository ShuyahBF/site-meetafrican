"""Profil détaillé, profil public et recherche avancée.

  - PUT  /me/profile       : édition de son propre profil (maquette 11 "Mon
                             profil" : bio, ville/pays, centres d'intérêt,
                             type de relation, enfants, profession).
  - GET  /profile-options  : listes fermées utilisées par les formulaires
                             (centres d'intérêt, types de relation…).
  - GET  /users/{id}       : fiche publique d'un autre membre (depuis le fil
                             vidéo, la recherche ou un match).
  - GET  /search           : recherche avancée multi-critères (maquette 10).

Les photos des autres membres suivent la même règle que la découverte :
visage masqué sans abonnement actif (cf. routes/matching.py).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user
from db import db
from models import (
    INTERESTS,
    ONLINE_THRESHOLD_SECONDS,
    ChildrenStatus,
    RelationshipGoal,
    UserPublic,
    VerificationStatus,
    to_user_public,
)
from routes.matching import _mask_photos_for_viewer, _opposite, _with_likes_received

router = APIRouter(tags=["Profils & recherche"])

# Libellés français affichés par le frontend — centralisés ici pour que
# l'API et l'interface parlent exactement la même langue.
RELATIONSHIP_GOAL_LABELS = {
    RelationshipGoal.serieuse.value: "Relation sérieuse",
    RelationshipGoal.mariage.value: "Mariage",
    RelationshipGoal.amitie.value: "Amitié / rencontres",
    RelationshipGoal.a_voir.value: "Je ne sais pas encore",
}
CHILDREN_LABELS = {
    ChildrenStatus.sans_enfant.value: "N'a pas d'enfants",
    ChildrenStatus.a_des_enfants.value: "A des enfants",
    ChildrenStatus.en_veut.value: "N'en a pas, en veut",
    ChildrenStatus.n_en_veut_pas.value: "N'en a pas, n'en veut pas",
}

# Âges extrêmes acceptés par les filtres (l'inscription impose 18 ans min.).
MIN_AGE, MAX_AGE = 18, 99


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Édition de son propre profil
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    """Tous les champs sont optionnels : seuls ceux envoyés sont modifiés."""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=80)
    country: Optional[str] = Field(None, max_length=80)
    profession: Optional[str] = Field(None, max_length=80)
    interests: Optional[List[str]] = Field(None, max_length=10)
    relationship_goal: Optional[RelationshipGoal] = None
    children: Optional[ChildrenStatus] = None

    @field_validator("interests")
    @classmethod
    def _known_interests_only(cls, v):
        """Refuse tout centre d'intérêt hors de la liste fermée INTERESTS
        (sinon la recherche par centre d'intérêt ne les retrouverait pas)."""
        if v is None:
            return v
        unknown = [i for i in v if i not in INTERESTS]
        if unknown:
            raise ValueError(f"Centres d'intérêt inconnus : {', '.join(unknown)}")
        # Dédoublonne en gardant l'ordre choisi par l'utilisateur.
        return list(dict.fromkeys(v))

    @field_validator("full_name", "bio", "city", "country", "profession", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


@router.get("/profile-options")
async def profile_options():
    """Listes de valeurs pour les formulaires (profil, recherche) — publique,
    sans authentification, comme /appearance."""
    return {
        "interests": INTERESTS,
        "relationship_goals": [{"value": k, "label": v} for k, v in RELATIONSHIP_GOAL_LABELS.items()],
        "children": [{"value": k, "label": v} for k, v in CHILDREN_LABELS.items()],
        "age_range": {"min": MIN_AGE, "max": MAX_AGE},
    }


@router.put("/me/profile", response_model=UserPublic)
async def update_my_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    # exclude_unset : un champ absent de la requête n'est pas touché ; un
    # champ envoyé explicitement à null/"" est bien effacé.
    changes = payload.model_dump(mode="json", exclude_unset=True)
    if "full_name" in changes and not changes["full_name"]:
        raise HTTPException(status_code=400, detail="Le nom ne peut pas être vide")
    for key in ("bio", "city", "country", "profession"):
        if key in changes and changes[key] == "":
            changes[key] = None
    if changes:
        changes["updated_at"] = _now()
        await db.users.update_one({"id": user["id"]}, {"$set": changes})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return to_user_public(fresh)


# ---------------------------------------------------------------------------
# Fiche publique d'un membre
# ---------------------------------------------------------------------------

@router.get("/users/{user_id}")
async def public_profile(user_id: str, viewer: dict = Depends(get_current_user)):
    """Fiche d'un autre membre + état de la relation avec le visiteur
    (déjà liké ? match ? conversation ouverte ?), pour que la page puisse
    proposer la bonne action (J'aime / Envoyer un message)."""
    doc = await db.users.find_one({"id": user_id, "is_active": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    profile = to_user_public(doc)
    [profile] = await _with_likes_received([profile])
    if user_id != viewer["id"]:
        [profile] = await _mask_photos_for_viewer([profile], viewer["id"])

    my_swipe = await db.swipes.find_one({"user_id": viewer["id"], "target_user_id": user_id}, {"_id": 0})
    user_a, user_b = sorted([viewer["id"], user_id])
    match = await db.matches.find_one({"user_a": user_a, "user_b": user_b}, {"_id": 0})
    conversation = (
        await db.conversations.find_one({"match_id": match["id"]}, {"_id": 0}) if match else None
    )
    videos_count = await db.videos.count_documents({"user_id": user_id, "status": "published"})

    return {
        "profile": profile,
        "is_me": user_id == viewer["id"],
        "my_swipe": my_swipe["action"] if my_swipe else None,
        "is_match": bool(match),
        "conversation_id": conversation["id"] if conversation else None,
        "videos_count": videos_count,
    }


# ---------------------------------------------------------------------------
# Recherche avancée (maquette 10)
# ---------------------------------------------------------------------------

def _birthdate_bounds(age_min: int, age_max: int) -> dict:
    """Traduit une tranche d'âge en bornes sur la date de naissance (stockée
    en chaîne ISO "AAAA-MM-JJ", donc comparable lexicographiquement) :
      âge >= age_min  <=>  né au plus tard il y a age_min ans ;
      âge <= age_max  <=>  né strictement après il y a (age_max + 1) ans."""
    today = date.today()

    def years_ago(n: int) -> str:
        try:
            return today.replace(year=today.year - n).isoformat()
        except ValueError:  # 29 février -> 28 février
            return today.replace(year=today.year - n, day=28).isoformat()

    return {"$lte": years_ago(age_min), "$gt": years_ago(age_max + 1)}


def _contains_ci(value: str) -> dict:
    """Filtre "contient", insensible à la casse, sur une saisie libre (ville,
    pays) — échappée pour qu'un caractère spécial ne casse pas la regex."""
    return {"$regex": re.escape(value.strip()), "$options": "i"}


@router.get("/search")
async def search_profiles(
    age_min: int = Query(MIN_AGE, ge=MIN_AGE, le=MAX_AGE),
    age_max: int = Query(MAX_AGE, ge=MIN_AGE, le=MAX_AGE),
    gender: Optional[str] = Query(None, pattern="^(homme|femme)$"),
    country: Optional[str] = Query(None, max_length=80),
    city: Optional[str] = Query(None, max_length=80),
    relationship_goal: Optional[RelationshipGoal] = None,
    children: Optional[ChildrenStatus] = None,
    interests: Optional[str] = Query(None, description="Liste séparée par des virgules"),
    verified_only: bool = False,
    online_only: bool = False,
    with_video_only: bool = False,
    limit: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    """Renvoie {total, results}. `total` alimente le compteur "X profils
    correspondent à vos critères" affiché avant de voir les résultats."""
    if age_min > age_max:
        age_min, age_max = age_max, age_min

    query: dict = {
        "id": {"$ne": user["id"]},
        "is_active": True,
        # Par défaut, genre opposé (même logique que la découverte).
        "gender": gender or _opposite(user["gender"]),
        "birthdate": _birthdate_bounds(age_min, age_max),
        # Les comptes du back-office n'apparaissent jamais dans la recherche.
        "role": {"$nin": ["admin", "moderator"]},
    }
    if country:
        query["country"] = _contains_ci(country)
    if city:
        query["city"] = _contains_ci(city)
    if relationship_goal:
        query["relationship_goal"] = relationship_goal.value
    if children:
        query["children"] = children.value
    if interests:
        wanted = [i.strip() for i in interests.split(",") if i.strip() in INTERESTS]
        if wanted:
            # Au moins UN centre d'intérêt en commun (comme les puces de la
            # maquette : plus on en coche, plus on élargit).
            query["interests"] = {"$in": wanted}
    if verified_only:
        query["verification_status"] = VerificationStatus.verified.value
    if online_only:
        # Même seuil que models.ONLINE_THRESHOLD_SECONDS (5 minutes), exprimé
        # en borne sur last_seen_at (chaîne ISO UTC, comparable telle quelle).
        threshold = datetime.now(timezone.utc) - timedelta(seconds=ONLINE_THRESHOLD_SECONDS)
        query["last_seen_at"] = {"$gte": threshold.isoformat()}
    if with_video_only:
        authors = await db.videos.distinct("user_id", {"status": "published"})
        query["id"] = {"$ne": user["id"], "$in": authors}

    total = await db.users.count_documents(query)
    # Les membres actifs récemment d'abord : plus de chances d'une réponse.
    docs = (
        await db.users.find(query, {"_id": 0})
        .sort("last_seen_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    profiles = [to_user_public(d) for d in docs]
    profiles = await _with_likes_received(profiles)
    profiles = await _mask_photos_for_viewer(profiles, user["id"])
    return {"total": total, "results": profiles}
