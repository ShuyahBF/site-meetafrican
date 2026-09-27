"""Vidéos courtes — le fil vertical "Moments", façon TikTok.

Ce qui rend TikTok addictif et intuitif, et qu'on reprend ici :
  - un fil plein écran qu'on fait défiler d'un geste, sans rien choisir :
    l'algorithme "Pour toi" propose (mélange popularité + fraîcheur, et
    relègue en fin de liste ce qu'on a déjà vu) ;
  - des onglets simples : "Pour toi", "Près de moi" (même pays), "Mes
    matchs" (les vidéos des personnes avec qui on a matché) ;
  - des #hashtags cliquables qui filtrent le fil ;
  - des interactions en un geste : J'aime (double-tap), commentaires,
    partage, cadeaux — et, spécifique à un site de rencontre, "Ça me plaît"
    qui envoie un like au PROFIL et peut déclencher un match.

Authenticité : seuls les membres à l'identité VÉRIFIÉE peuvent publier
(la vérification par pièce d'identité existe déjà, cf. routes/verification.py).
Pas de modération a priori (comme TikTok) mais un signalement en un clic :
au-delà de AUTO_HIDE_REPORTS signalements, la vidéo est retirée
automatiquement en attendant la décision d'un modérateur.

Visibilité (règle de l'administrateur du site) :
  - chaque vidéo est visible par TOUS, mais ENTIÈREMENT FLOUTÉE (flou
    appliqué côté serveur dans les pixels, cf. video_processing.py) ;
  - la version CLAIRE n'est servie qu'aux membres à l'identité VÉRIFIÉE
    que l'auteur a ACCEPTÉS : soit par un match (like réciproque), soit en
    acceptant leur demande "Voir en clair" (routes /video-access ci-dessous) ;
  - l'auteur voit toujours ses propres vidéos en clair, les modérateurs aussi.
La version claire vit dans le stockage PRIVÉ : son lien n'est jamais
renvoyé à un membre non autorisé, et l'URL donnée aux autorisés expire.
"""
from __future__ import annotations

import asyncio
import math
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_admin, get_current_user
from config import get_settings
from db import db
from models import (
    Video,
    VideoAccessRequest,
    VideoAccessStatus,
    VideoComment,
    VideoStatus,
    VerificationStatus,
    _age_from_birthdate,
    _is_online,
)
from activity import current_ip
from storage import presigned_document_url, save_photo, save_private_media, save_public_media
from video_processing import VideoProcessingError, process_video

router = APIRouter(tags=["Vidéos (Moments)"])

ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}

# Nombre de signalements distincts à partir duquel une vidéo est retirée
# automatiquement du fil (un modérateur peut la rétablir depuis /admin).
AUTO_HIDE_REPORTS = 3

# Taille de la réserve de vidéos récentes sur laquelle l'algorithme "Pour
# toi" calcule son classement (suffisant tant que le site démarre ; à
# remplacer par un score précalculé en tâche de fond si le volume explose).
FOR_YOU_POOL = 300

HASHTAG_RE = re.compile(r"#([\wÀ-ÿ]{2,30})", re.UNICODE)

# Durée de vie des URL temporaires de la version claire : assez longue pour
# regarder et faire défiler le fil, courte pour qu'un lien partagé à un
# tiers cesse vite de fonctionner.
CLEAR_URL_TTL_SECONDS = 2 * 3600

# Champs internes jamais renvoyés tels quels par l'API.
_PRIVATE_FIELDS = ("clear_key", "ip")


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def extract_hashtags(caption: str) -> List[str]:
    """"Soirée #Abidjan #danse #Danse" -> ["abidjan", "danse"] (minuscules,
    dédoublonnés, ordre d'apparition conservé, 10 max)."""
    tags = [t.lower() for t in HASHTAG_RE.findall(caption or "")]
    return list(dict.fromkeys(tags))[:10]


def _for_you_score(video: dict, seen: bool) -> float:
    """Score "Pour toi" : l'engagement (J'aime, commentaires, vues) divisé
    par l'âge de la vidéo (formule "gravité" à la Hacker News) — une vidéo
    récente qui plaît remonte vite, puis redescend doucement. Les vidéos
    déjà vues sont fortement pénalisées pour que le fil reste neuf."""
    try:
        created = datetime.fromisoformat(video["created_at"])
        age_hours = max((_now_dt() - created).total_seconds() / 3600, 0)
    except (KeyError, ValueError):
        age_hours = 48
    engagement = (
        1
        + video.get("likes_count", 0) * 3
        + video.get("comments_count", 0) * 4
        + math.log1p(video.get("views_count", 0))
    )
    score = engagement / math.pow(age_hours + 2, 1.3)
    return score * (0.05 if seen else 1.0)


async def _author_cards(user_ids: List[str]) -> dict:
    """Infos auteur affichées en surimpression sur chaque vidéo (nom, âge,
    ville, badge vérifié, pastille en ligne, photo principale)."""
    docs = await db.users.find({"id": {"$in": list(set(user_ids))}}, {"_id": 0}).to_list(len(user_ids) or 1)
    cards = {}
    for d in docs:
        approved = [p for p in d.get("photos", []) if p.get("status") == "approved"]
        primary = next((p for p in approved if p.get("is_primary")), approved[0] if approved else None)
        cards[d["id"]] = {
            "id": d["id"],
            "full_name": d["full_name"],
            "age": _age_from_birthdate(d.get("birthdate")),
            "gender": d.get("gender"),
            "city": d.get("city"),
            "country": d.get("country"),
            "is_verified": d.get("verification_status") == VerificationStatus.verified.value,
            "is_online": _is_online(d.get("last_seen_at")),
            "is_test_data": bool(d.get("is_test_data")),
            # Miniature ronde de l'avatar : version masquée si elle existe
            # (même règle que les photos du profil : visage visible en clair
            # seulement dans la fiche, pour les abonnés).
            "avatar_url": (primary.get("masked_url") or primary.get("url")) if primary else None,
        }
    return cards


async def _clear_access_owner_ids(viewer: dict, owner_ids: List[str]) -> tuple[set, dict]:
    """Parmi `owner_ids`, les auteurs dont `viewer` peut voir les vidéos EN
    CLAIR, et l'état de ses demandes d'accès ({owner_id: statut}).

    Règle : le visiteur doit avoir une identité VÉRIFIÉE et être accepté par
    l'auteur — par un match, ou par une demande "Voir en clair" acceptée.
    L'auteur lui-même et les modérateurs voient toujours en clair."""
    owner_ids = list(set(owner_ids))
    requests = await db.video_access_requests.find(
        {"requester_id": viewer["id"], "owner_id": {"$in": owner_ids}}, {"_id": 0}
    ).to_list(len(owner_ids) or 1)
    request_status = {r["owner_id"]: r["status"] for r in requests}

    allowed = {viewer["id"]} & set(owner_ids)
    if viewer.get("role") in ("admin", "moderator"):
        return set(owner_ids), request_status
    if viewer.get("verification_status") != VerificationStatus.verified.value:
        return allowed, request_status

    allowed |= {oid for oid, st in request_status.items() if st == VideoAccessStatus.accepted.value}
    matches = await db.matches.find(
        {"$or": [
            {"user_a": viewer["id"], "user_b": {"$in": owner_ids}},
            {"user_b": viewer["id"], "user_a": {"$in": owner_ids}},
        ]},
        {"_id": 0},
    ).to_list(len(owner_ids) or 1)
    allowed |= {m["user_b"] if m["user_a"] == viewer["id"] else m["user_a"] for m in matches}
    return allowed, request_status


async def _decorate(videos: List[dict], viewer: dict) -> List[dict]:
    """Prépare les vidéos pour l'affichage : auteur, "déjà aimée ?", "profil
    déjà liké ?", et surtout la bonne VERSION de la vidéo :
      - `url` = URL temporaire de la version claire si le visiteur y a droit,
        sinon l'URL de la version floutée ;
      - `is_clear` et `access` ("granted" | "pending" | "refused" | "none")
        pilotent le cadenas et le bouton "Voir en clair" de l'interface.
    La clé privée de la version claire n'est jamais renvoyée."""
    if not videos:
        return []
    viewer_id = viewer["id"]
    ids = [v["id"] for v in videos]
    author_ids = [v["user_id"] for v in videos]
    liked = set(await db.video_likes.distinct("video_id", {"user_id": viewer_id, "video_id": {"$in": ids}}))
    profile_liked = set(await db.swipes.distinct(
        "target_user_id", {"user_id": viewer_id, "action": "like", "target_user_id": {"$in": author_ids}}
    ))
    allowed, request_status = await _clear_access_owner_ids(viewer, author_ids)
    authors = await _author_cards(author_ids)
    out = []
    for v in videos:
        author = authors.get(v["user_id"])
        if not author:
            continue  # auteur supprimé/désactivé entre-temps
        is_clear = v["user_id"] in allowed and bool(v.get("clear_key"))
        url = await presigned_document_url(v["clear_key"], CLEAR_URL_TTL_SECONDS) if is_clear else v.get("blurred_url")
        if v.get("status") == VideoStatus.published.value and not url:
            continue  # vidéo incomplète : jamais servie
        public = {k: val for k, val in v.items() if k not in _PRIVATE_FIELDS}
        out.append({
            **public,
            "url": url,
            "is_clear": is_clear,
            "access": "granted" if v["user_id"] in allowed else request_status.get(v["user_id"], "none"),
            "author": author,
            "liked_by_me": v["id"] in liked,
            "author_liked_by_me": v["user_id"] in profile_liked,
            "is_mine": v["user_id"] == viewer_id,
        })
    return out


async def _get_published_or_404(video_id: str) -> dict:
    video = await db.videos.find_one({"id": video_id, "status": VideoStatus.published.value}, {"_id": 0})
    if not video:
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    return video


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

@router.post("/videos", status_code=201)
async def publish_video(
    file: UploadFile = File(...),
    caption: str = Form("", max_length=300),
    duration_seconds: Optional[float] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Publie une vidéo courte. Réservé aux profils à l'identité vérifiée :
    c'est la garantie "africains authentiques" du fil."""
    settings = get_settings()
    if user.get("verification_status") != VerificationStatus.verified.value:
        raise HTTPException(
            status_code=403,
            detail="Vérifiez votre identité (Profil > Vérification) pour publier des vidéos",
        )
    if file.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(status_code=400, detail="Format non pris en charge (MP4, WebM ou MOV)")
    if duration_seconds is not None and duration_seconds > settings.max_video_duration_seconds + 1:
        raise HTTPException(
            status_code=400,
            detail=f"Vidéo trop longue ({settings.max_video_duration_seconds} secondes maximum)",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(content) > settings.max_video_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Vidéo trop volumineuse (max {settings.max_video_upload_bytes // (1024 * 1024)} Mo)",
        )

    caption = (caption or "").strip()
    video = Video(user_id=user["id"], caption=caption, hashtags=extract_hashtags(caption), ip=current_ip())
    await db.videos.insert_one(video.model_dump(mode="json"))

    # Fichier brut sur disque temporaire, puis compression + floutage en
    # TÂCHE DE FOND (plusieurs secondes) : la réponse part tout de suite, la
    # vidéo apparaît "En traitement" dans "Mes Moments" puis dans le fil.
    suffix = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}[file.content_type]
    with tempfile.NamedTemporaryFile(prefix="maf-upload-", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
    task = asyncio.create_task(_process_in_background(video.id, Path(tmp.name)))
    _BACKGROUND_TASKS.add(task)  # garde une référence (sinon la tâche peut être ramassée)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    [decorated] = await _decorate([video.model_dump(mode="json")], user)
    return decorated


_BACKGROUND_TASKS: set = set()


async def _process_in_background(video_id: str, source: Path) -> None:
    """Produit version claire (privée), version floutée et vignette
    (publiques), puis publie la vidéo — ou la marque en échec avec un
    message lisible. Le fichier brut est toujours supprimé à la fin."""
    settings = get_settings()
    try:
        result = await asyncio.to_thread(process_video, source, settings.max_video_duration_seconds)
        clear_key = await save_private_media(result.clear_mp4, "video/mp4")
        blurred_url = await save_public_media(result.blurred_mp4, "video/mp4")
        poster_url = await save_photo(result.poster_jpg, "image/jpeg")
        await db.videos.update_one({"id": video_id}, {"$set": {
            "clear_key": clear_key,
            "blurred_url": blurred_url,
            "poster_url": poster_url,
            "duration_seconds": result.duration_seconds,
            "status": VideoStatus.published.value,
            "created_at": _now(),  # "publiée à" = fin du traitement
        }})
    except VideoProcessingError as exc:
        await db.videos.update_one({"id": video_id}, {"$set": {"status": VideoStatus.failed.value, "failure_reason": str(exc)}})
    except Exception as exc:  # noqa: BLE001 — jamais laisser une vidéo bloquée "en traitement"
        print(f"[videos] traitement de {video_id} en échec : {exc!r}")
        await db.videos.update_one({"id": video_id}, {"$set": {
            "status": VideoStatus.failed.value, "failure_reason": "Erreur technique pendant le traitement",
        }})
    finally:
        source.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Fil
# ---------------------------------------------------------------------------

@router.get("/videos/feed")
async def video_feed(
    tab: Literal["pour-toi", "pres-de-moi", "matchs"] = "pour-toi",
    tag: Optional[str] = Query(None, max_length=30),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=30),
    user: dict = Depends(get_current_user),
):
    """Fil paginé (skip/limit, le frontend charge la page suivante quand on
    approche de la fin — défilement infini)."""
    query: dict = {"status": VideoStatus.published.value, "user_id": {"$ne": user["id"]}}

    if tag:
        query["hashtags"] = tag.lower().lstrip("#")

    if tab == "matchs":
        matches = await db.matches.find(
            {"$or": [{"user_a": user["id"]}, {"user_b": user["id"]}]}, {"_id": 0}
        ).to_list(500)
        partner_ids = [m["user_b"] if m["user_a"] == user["id"] else m["user_a"] for m in matches]
        query["user_id"] = {"$in": partner_ids}
    else:
        # "Pour toi" et "Près de moi" : profils du genre recherché, actifs.
        wanted_gender = "femme" if user.get("gender") == "homme" else "homme"
        author_query: dict = {"gender": wanted_gender, "is_active": True}
        if tab == "pres-de-moi":
            if not user.get("country"):
                return {"items": [], "has_more": False, "hint": "Renseignez votre pays dans votre profil"}
            author_query["country"] = {"$regex": f"^{re.escape(user['country'])}$", "$options": "i"}
        author_ids = await db.users.distinct("id", author_query)
        query["user_id"] = {"$in": author_ids}

    if tab == "pour-toi" and not tag:
        # Classement "Pour toi" calculé sur les vidéos récentes.
        pool = await db.videos.find(query, {"_id": 0}).sort("created_at", -1).limit(FOR_YOU_POOL).to_list(FOR_YOU_POOL)
        seen = set(await db.video_views.distinct(
            "video_id", {"user_id": user["id"], "video_id": {"$in": [v["id"] for v in pool]}}
        ))
        pool.sort(key=lambda v: _for_you_score(v, v["id"] in seen), reverse=True)
        page = pool[skip: skip + limit]
        has_more = skip + limit < len(pool)
    else:
        page = (
            await db.videos.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit + 1).to_list(limit + 1)
        )
        has_more = len(page) > limit
        page = page[:limit]

    return {"items": await _decorate(page, user), "has_more": has_more}


@router.get("/videos/trending-tags")
async def trending_tags(user: dict = Depends(get_current_user)):
    """Hashtags les plus utilisés sur les 200 dernières vidéos — suggestions
    cliquables en tête du fil, comme la page "Découvrir" de TikTok."""
    recent = await db.videos.find(
        {"status": VideoStatus.published.value}, {"_id": 0, "hashtags": 1}
    ).sort("created_at", -1).limit(200).to_list(200)
    counts: dict = {}
    for v in recent:
        for t in v.get("hashtags", []):
            counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:12]
    return [{"tag": t, "count": c} for t, c in top]


@router.get("/users/{user_id}/videos")
async def user_videos(user_id: str, viewer: dict = Depends(get_current_user)):
    """Grille des vidéos d'un membre (sa fiche profil, ou "Mes Moments").
    L'auteur voit aussi ses vidéos en traitement ou en échec."""
    statuses = [VideoStatus.published.value]
    if user_id == viewer["id"]:
        statuses += [VideoStatus.processing.value, VideoStatus.failed.value]
    items = await db.videos.find(
        {"user_id": user_id, "status": {"$in": statuses}}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return await _decorate(items, viewer)


@router.get("/videos/{video_id}")
async def get_video(video_id: str, user: dict = Depends(get_current_user)):
    """Une vidéo seule — cible des liens de partage (/moments/<id>)."""
    video = await _get_published_or_404(video_id)
    [decorated] = await _decorate([video], user) or [None]
    if not decorated:
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    return decorated


# ---------------------------------------------------------------------------
# Interactions : vue, J'aime, commentaires, signalement
# ---------------------------------------------------------------------------

@router.post("/videos/{video_id}/view")
async def record_view(video_id: str, user: dict = Depends(get_current_user)):
    """Compte une vue unique par membre (appelé après ~2 s de lecture)."""
    await _get_published_or_404(video_id)
    result = await db.video_views.update_one(
        {"video_id": video_id, "user_id": user["id"]},
        {"$setOnInsert": {"video_id": video_id, "user_id": user["id"], "created_at": _now()}},
        upsert=True,
    )
    if result.upserted_id is not None:
        await db.videos.update_one({"id": video_id}, {"$inc": {"views_count": 1}})
    return {"ok": True}


@router.post("/videos/{video_id}/like")
async def toggle_like(video_id: str, like: bool = True, user: dict = Depends(get_current_user)):
    """J'aime / Je n'aime plus (idempotent : `like=true` deux fois de suite
    — typiquement un double-tap répété — ne compte qu'une fois)."""
    await _get_published_or_404(video_id)
    key = {"video_id": video_id, "user_id": user["id"]}
    if like:
        result = await db.video_likes.update_one(
            key, {"$setOnInsert": {**key, "created_at": _now()}}, upsert=True
        )
        if result.upserted_id is not None:
            await db.videos.update_one({"id": video_id}, {"$inc": {"likes_count": 1}})
    else:
        result = await db.video_likes.delete_one(key)
        if result.deleted_count:
            await db.videos.update_one({"id": video_id}, {"$inc": {"likes_count": -1}})
    video = await db.videos.find_one({"id": video_id}, {"_id": 0, "likes_count": 1})
    return {"liked": like, "likes_count": max(video.get("likes_count", 0), 0)}


@router.get("/videos/{video_id}/comments")
async def list_comments(video_id: str, user: dict = Depends(get_current_user)):
    await _get_published_or_404(video_id)
    comments = await db.video_comments.find({"video_id": video_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    authors = await _author_cards([c["user_id"] for c in comments])
    return [
        {**{k: v for k, v in c.items() if k != "ip"}, "author": authors.get(c["user_id"]), "is_mine": c["user_id"] == user["id"]}
        for c in comments if c["user_id"] in authors
    ]


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


@router.post("/videos/{video_id}/comments", status_code=201)
async def add_comment(video_id: str, payload: CommentCreate, user: dict = Depends(get_current_user)):
    await _get_published_or_404(video_id)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Commentaire vide")
    comment = VideoComment(video_id=video_id, user_id=user["id"], text=text)
    await db.video_comments.insert_one({**comment.model_dump(mode="json"), "ip": current_ip()})
    await db.videos.update_one({"id": video_id}, {"$inc": {"comments_count": 1}})
    authors = await _author_cards([user["id"]])
    return {**comment.model_dump(mode="json"), "author": authors.get(user["id"]), "is_mine": True}


@router.delete("/videos/{video_id}/comments/{comment_id}")
async def delete_comment(video_id: str, comment_id: str, user: dict = Depends(get_current_user)):
    """Supprimable par son auteur, par l'auteur de la vidéo ou par un
    modérateur."""
    comment = await db.video_comments.find_one({"id": comment_id, "video_id": video_id}, {"_id": 0})
    if not comment:
        raise HTTPException(status_code=404, detail="Commentaire introuvable")
    video = await db.videos.find_one({"id": video_id}, {"_id": 0, "user_id": 1})
    allowed = (
        comment["user_id"] == user["id"]
        or (video and video["user_id"] == user["id"])
        or user.get("role") in ("admin", "moderator")
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Action non autorisée")
    await db.video_comments.delete_one({"id": comment_id})
    await db.videos.update_one({"id": video_id}, {"$inc": {"comments_count": -1}})
    return {"ok": True}


class VideoReportCreate(BaseModel):
    reason: Literal["faux_profil", "contenu_choquant", "harcelement", "spam", "autre"]


@router.post("/videos/{video_id}/report", status_code=201)
async def report_video(video_id: str, payload: VideoReportCreate, user: dict = Depends(get_current_user)):
    """Un signalement par membre et par vidéo. Au-delà de AUTO_HIDE_REPORTS,
    la vidéo sort du fil en attendant un modérateur."""
    video = await _get_published_or_404(video_id)
    if video["user_id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Impossible de signaler sa propre vidéo")
    key = {"video_id": video_id, "user_id": user["id"]}
    result = await db.video_reports.update_one(
        key, {"$setOnInsert": {**key, "reason": payload.reason, "created_at": _now()}}, upsert=True
    )
    if result.upserted_id is not None:
        await db.videos.update_one({"id": video_id}, {"$inc": {"reports_count": 1}})
        if video.get("reports_count", 0) + 1 >= AUTO_HIDE_REPORTS:
            await db.videos.update_one(
                {"id": video_id},
                {"$set": {"status": VideoStatus.removed.value, "removed_reason": "Signalements multiples (auto)"}},
            )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Back-office
# ---------------------------------------------------------------------------

@router.get("/admin/videos")
async def admin_list_videos(
    status: Literal["all", "published", "removed", "reported"] = "reported",
    _: dict = Depends(get_current_admin),
):
    if status == "reported":
        query: dict = {"reports_count": {"$gt": 0}}
    elif status == "all":
        query = {}
    else:
        query = {"status": status}
    items = await db.videos.find(query, {"_id": 0}).sort(
        [("reports_count", -1), ("created_at", -1)]
    ).to_list(200)
    authors = await _author_cards([v["user_id"] for v in items])
    for v in items:
        v["author"] = authors.get(v["user_id"])
        v["report_reasons"] = await db.video_reports.distinct("reason", {"video_id": v["id"]})
        # Les modérateurs jugent sur la version claire.
        clear_key = v.pop("clear_key", None)
        v["url"] = await presigned_document_url(clear_key, CLEAR_URL_TTL_SECONDS) if clear_key else v.get("blurred_url")
    return items


class VideoModeration(BaseModel):
    action: Literal["remove", "restore"]
    reason: Optional[str] = Field(None, max_length=200)


@router.post("/admin/videos/{video_id}/moderate")
async def moderate_video(video_id: str, payload: VideoModeration, _: dict = Depends(get_current_admin)):
    video = await db.videos.find_one({"id": video_id}, {"_id": 0, "id": 1})
    if not video:
        raise HTTPException(status_code=404, detail="Vidéo introuvable")
    if payload.action == "remove":
        update = {"status": VideoStatus.removed.value, "removed_reason": payload.reason or "Retirée par la modération"}
    else:
        # Rétablir = la vidéo repart de zéro côté signalements (sinon le
        # prochain signalement la retirerait de nouveau immédiatement).
        update = {"status": VideoStatus.published.value, "removed_reason": None, "reports_count": 0}
        await db.video_reports.delete_many({"video_id": video_id})
    await db.videos.update_one({"id": video_id}, {"$set": update})
    return {"ok": True, "status": update["status"]}


# ---------------------------------------------------------------------------
# Accès à la version claire : demandes "Voir en clair"
# ---------------------------------------------------------------------------

@router.post("/users/{owner_id}/video-access", status_code=201)
async def request_clear_access(owner_id: str, user: dict = Depends(get_current_user)):
    """Demande à `owner_id` l'autorisation de voir ses vidéos en clair.
    Réservé aux identités vérifiées (sinon l'autorisation ne servirait à rien)."""
    if owner_id == user["id"]:
        raise HTTPException(status_code=400, detail="Vous voyez déjà vos propres vidéos en clair")
    if user.get("verification_status") != VerificationStatus.verified.value:
        raise HTTPException(status_code=403, detail="Vérifiez d'abord votre identité pour demander à voir en clair")
    owner = await db.users.find_one({"id": owner_id, "is_active": True}, {"_id": 0, "id": 1})
    if not owner:
        raise HTTPException(status_code=404, detail="Profil introuvable")

    existing = await db.video_access_requests.find_one({"owner_id": owner_id, "requester_id": user["id"]}, {"_id": 0})
    if existing:
        if existing["status"] == VideoAccessStatus.refused.value:
            # Un refus reste un refus : pas de relance possible (anti-harcèlement).
            raise HTTPException(status_code=403, detail="Ce membre a refusé votre demande")
        return {"status": existing["status"]}
    req = VideoAccessRequest(owner_id=owner_id, requester_id=user["id"])
    await db.video_access_requests.insert_one(req.model_dump(mode="json"))
    return {"status": req.status.value}


@router.get("/me/video-access/requests")
async def my_incoming_requests(user: dict = Depends(get_current_user)):
    """Demandes reçues en attente + membres déjà autorisés (pour pouvoir
    révoquer)."""
    items = await db.video_access_requests.find(
        {"owner_id": user["id"], "status": {"$in": [VideoAccessStatus.pending.value, VideoAccessStatus.accepted.value]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    cards = await _author_cards([r["requester_id"] for r in items])
    return [{**r, "requester": cards[r["requester_id"]]} for r in items if r["requester_id"] in cards]


class AccessDecision(BaseModel):
    accept: bool


@router.post("/me/video-access/requests/{request_id}")
async def decide_request(request_id: str, payload: AccessDecision, user: dict = Depends(get_current_user)):
    """Accepter / refuser une demande — ou révoquer (accept=false) un accès
    déjà accordé."""
    req = await db.video_access_requests.find_one({"id": request_id, "owner_id": user["id"]}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    status = VideoAccessStatus.accepted if payload.accept else VideoAccessStatus.refused
    await db.video_access_requests.update_one(
        {"id": request_id}, {"$set": {"status": status.value, "decided_at": _now()}}
    )
    return {"ok": True, "status": status.value}
