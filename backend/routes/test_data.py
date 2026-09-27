"""Données de test (back-office) : génération et purge.

Demande de l'administrateur : peupler le site d'une centaine de comptes
fictifs (hommes/femmes, profils variés, photos, vidéos, matchs,
conversations…) pour le tester, en MARQUANT tout ce qui est généré, afin de
pouvoir tout supprimer le jour venu.

Marquage : chaque document créé porte `is_test_data: True` ; chaque fichier
envoyé au stockage (photos, vidéos, vignettes) est inventorié dans la
collection `test_media`. Les profils de test affichent un badge « Test »
dans l'interface et ne sont jamais comptés dans les compteurs publics.

Purge : supprime tous les documents marqués, les fichiers inventoriés, ET
les traces laissées par de vrais membres sur ces profils (J'aime, matchs,
conversations, commentaires, demandes d'accès…) pour ne rien laisser
pointer vers un compte disparu. Les opérations financières réelles
(cadeaux payés, transferts de points) ne sont jamais supprimées.

Les deux opérations tournent en tâche de fond (plusieurs minutes pour les
vidéos) ; leur avancement est lisible via GET /admin/test-data.
"""
from __future__ import annotations

import asyncio
import io
import random
import subprocess
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_admin, hash_password
from db import db
from image_processing import FONT_PATH, apply_face_mask, apply_watermark
from routes.videos import extract_hashtags
from storage import delete_private_media, delete_public_media, save_photo, save_private_media, save_public_media
from video_processing import ffmpeg_exe, process_video

router = APIRouter(prefix="/admin/test-data", tags=["Données de test"])

# Identifiants communs à tous les comptes de test (affichés dans l'admin
# pour pouvoir se connecter "dans la peau" d'un membre de test).
TEST_PASSWORD = "TestBeAuthentik2026!"
TEST_EMAIL_DOMAIN = "test.beauthentik.net"
TEST_IP = "test"
JOB_ID = "test_data_job"

MALE_NAMES = ["Kofi", "Moussa", "Ibrahim", "Yao", "Kwame", "Amadou", "Seydou", "Koffi", "Didier", "Olivier",
              "Mamadou", "Cheikh", "Emmanuel", "Serge", "Ousmane", "Abdoulaye", "Patrick", "Jean-Marc", "Issa", "Boris"]
FEMALE_NAMES = ["Aïcha", "Fatou", "Mariam", "Awa", "Grace", "Nadia", "Aminata", "Salimata", "Adjoa", "Esther",
                "Rokia", "Mireille", "Fanta", "Clarisse", "Djeneba", "Prisca", "Kadiatou", "Ruth", "Estelle", "Binta"]
LAST_NAMES = ["Traoré", "Diop", "Ouédraogo", "Mensah", "Kouassi", "Koné", "Diallo", "Sawadogo", "Ndiaye", "Coulibaly",
              "Kaboré", "Bamba", "Yeo", "Sanogo", "Touré", "Mbaye", "Boateng", "Zongo", "Keïta", "Camara"]
CITIES = [("Ouagadougou", "Burkina Faso"), ("Bobo-Dioulasso", "Burkina Faso"), ("Abidjan", "Côte d'Ivoire"),
          ("Bouaké", "Côte d'Ivoire"), ("Dakar", "Sénégal"), ("Thiès", "Sénégal"), ("Bamako", "Mali"),
          ("Accra", "Ghana"), ("Lomé", "Togo"), ("Cotonou", "Bénin"), ("Niamey", "Niger"), ("Douala", "Cameroun"),
          ("Yaoundé", "Cameroun"), ("Libreville", "Gabon"), ("Paris", "France"), ("Lyon", "France"),
          ("Bruxelles", "Belgique"), ("Montréal", "Canada")]
INTERESTS = ["Sport", "Cinéma", "Voyages", "Musique", "Art", "Cuisine", "Photographie", "Danse", "Lecture", "Mode",
             "Foi", "Entrepreneuriat", "Nature", "Jeux vidéo"]
GOALS = ["serieuse", "mariage", "amitie", "a_voir"]
CHILDREN = ["sans_enfant", "a_des_enfants", "en_veut", "n_en_veut_pas"]
PROFESSIONS = ["Infirmière", "Enseignant", "Commerçante", "Ingénieur", "Comptable", "Étudiante", "Juriste",
               "Développeur", "Photographe", "Entrepreneure", "Médecin", "Coiffeuse", "Chauffeur", "Architecte"]
BIOS = [
    "J'aime rire, voyager et les bonnes conversations. Ici pour du sérieux 💫",
    "Passionné de musique et de cuisine du pays. Je cherche une belle complicité.",
    "Simple, souriante et croyante. La famille avant tout 🙏🏾",
    "Entrepreneur le jour, danseur le week-end 💃🏾 Et toi ?",
    "Amoureuse des voyages et des couchers de soleil 🌅",
    "Calme, posé, j'aime la lecture et les longues balades.",
    "Toujours partant pour un bon maquis entre amis 😄",
]
CAPTIONS = [
    "Dimanche en famille ☀️ #famille #weekend", "Mon plat préféré 🍲 #cuisine", "Soirée danse 💃🏾 #danse #afrobeat",
    "Balade au marché #{city}", "Coucher de soleil 🌅 #love", "Petit moment de sport 💪🏾 #sport",
    "Nouvelle coiffure, vous validez ? #mode", "Au boulot avec le sourire 😄 #travail", "Musique du soir 🎶 #musique",
]
MESSAGES = [
    "Coucou 😊", "Salut, comment tu vas ?", "Bien et toi ?", "J'ai vu ton Moment, trop joli 🔥",
    "Merci 😄 tu es d'où exactement ?", "On pourrait se voir un de ces jours ?", "Avec plaisir !",
    "Tu fais quoi ce week-end ?", "Rien de prévu, et toi ?", "👋🏾", "Haha 😂", "Bonne soirée 🌙",
]
COLORS = [((244, 37, 106), (255, 122, 69)), ((139, 92, 246), (244, 37, 106)), ((16, 185, 129), (14, 165, 233)),
          ((245, 158, 11), (239, 68, 68)), ((14, 165, 233), (139, 92, 246)), ((30, 41, 59), (244, 37, 106))]


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


async def _set_job(**fields) -> None:
    await db.settings.update_one({"id": JOB_ID}, {"$set": {"id": JOB_ID, **fields}}, upsert=True)


async def _job() -> dict:
    return await db.settings.find_one({"id": JOB_ID}, {"_id": 0}) or {"status": "idle"}


# ---------------------------------------------------------------------------
# Génération des médias (fonctions bloquantes -> asyncio.to_thread)
# ---------------------------------------------------------------------------

def _portrait_jpeg(name: str, colors) -> bytes:
    """Portrait fictif : dégradé, silhouette, initiale et bandeau "TEST"."""
    from PIL import Image, ImageDraw, ImageFont

    c1, c2 = colors
    img = Image.new("RGB", (600, 800))
    draw = ImageDraw.Draw(img)
    for y in range(800):
        t = y / 800
        draw.line([(0, y), (600, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    draw.ellipse([200, 180, 400, 380], fill=(255, 255, 255))
    draw.pieslice([120, 400, 480, 900], 180, 360, fill=(255, 255, 255))
    draw.text((300, 280), name[0], fill=c1, font=ImageFont.truetype(str(FONT_PATH), 120), anchor="mm")
    draw.rounded_rectangle([230, 40, 370, 96], 18, fill=(0, 0, 0))
    draw.text((300, 68), "TEST", fill=(255, 255, 255), font=ImageFont.truetype(str(FONT_PATH), 34), anchor="mm")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _photo_variants(name: str, colors):
    raw = _portrait_jpeg(name, colors)
    return apply_watermark(raw), apply_face_mask(raw)


def _test_video(label: str, colors) -> Path:
    """Petite vidéo verticale (6 s) : fond en dégradé animé + texte, avec
    un son. Le texte est dessiné par Pillow puis superposé (le ffmpeg
    embarqué n'a pas le filtre drawtext)."""
    from PIL import Image, ImageDraw, ImageFont

    tmp = Path(tempfile.mkdtemp(prefix="maf-test-"))
    overlay = Image.new("RGBA", (360, 640), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text((180, 320), label, font=ImageFont.truetype(str(FONT_PATH), 28), fill="white", anchor="mm")
    draw.rounded_rectangle((130, 40, 230, 80), 12, fill=(0, 0, 0, 120))
    draw.text((180, 60), "TEST", font=ImageFont.truetype(str(FONT_PATH), 22), fill="white", anchor="mm")
    overlay.save(tmp / "overlay.png")
    c0 = "0x%02x%02x%02x" % colors[0]
    c1 = "0x%02x%02x%02x" % colors[1]
    out = tmp / "video.mp4"
    subprocess.run([
        ffmpeg_exe(), "-hide_banner", "-y",
        "-f", "lavfi", "-i", f"gradients=s=360x640:c0={c0}:c1={c1}:speed=0.02:d=6",
        "-loop", "1", "-i", str(tmp / "overlay.png"),
        "-f", "lavfi", "-i", f"sine=frequency={random.choice([262, 330, 392, 440])}:d=6",
        "-filter_complex", "[0][1]overlay=0:0:shortest=1",
        "-t", "6", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out),
    ], check=True, capture_output=True, timeout=120)
    return out


async def _remember_media(kind: str, ref: str) -> None:
    """Inventorie un fichier de test pour la purge (kind: public | private)."""
    await db.test_media.insert_one({"id": _uuid(), "kind": kind, "ref": ref, "is_test_data": True, "created_at": _iso(_now_dt())})


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

async def _generate(count: int, videos: int) -> None:
    rng = random.Random()
    now = _now_dt()
    summary = {"users": 0, "videos": 0, "swipes": 0, "matches": 0, "messages": 0, "comments": 0, "access_requests": 0}
    try:
        await _set_job(status="running", step="Création des comptes", progress=0, total=count, error=None,
                       started_at=_iso(now), finished_at=None, summary=summary)
        password_hash = hash_password(TEST_PASSWORD)  # un seul hachage (lent) pour tous
        batch = uuid.uuid4().hex[:6]
        users: List[dict] = []

        for i in range(count):
            gender = "homme" if i % 2 == 0 else "femme"
            first = rng.choice(MALE_NAMES if gender == "homme" else FEMALE_NAMES)
            last = rng.choice(LAST_NAMES)
            city, country = rng.choice(CITIES)
            age = rng.randint(20, 45)
            birth = date.today().replace(year=date.today().year - age) - timedelta(days=rng.randint(0, 360))
            colors = rng.choice(COLORS)
            watermarked, masked = await asyncio.to_thread(_photo_variants, first, colors)
            url, masked_url = await save_photo(watermarked, "image/jpeg"), await save_photo(masked, "image/jpeg")
            await _remember_media("public", url)
            await _remember_media("public", masked_url)
            minutes_ago = rng.choice([1, 2, 3, 30, 90, 300, 1440, 4000])
            user = {
                "id": _uuid(),
                "full_name": f"{first} {last}",
                "email": f"test.{first.lower().replace('ï', 'i').replace('é', 'e')}.{batch}{i}@{TEST_EMAIL_DOMAIN}",
                "password_hash": password_hash,
                "gender": gender,
                "birthdate": birth.isoformat(),
                "bio": rng.choice(BIOS),
                "city": city,
                "country": country,
                "interests": rng.sample(INTERESTS, rng.randint(2, 5)),
                "relationship_goal": rng.choice(GOALS),
                "children": rng.choice(CHILDREN),
                "profession": rng.choice(PROFESSIONS),
                "photos": [{"id": _uuid(), "url": url, "masked_url": masked_url, "status": "approved",
                            "is_primary": True, "moderation_notes": "Donnée de test", "moderated_at": _iso(now),
                            "created_at": _iso(now)}],
                "role": "user",
                "verification_status": "verified" if rng.random() < 0.65 else rng.choice(["unverified", "pending"]),
                "points": rng.randint(0, 200),
                "wallet_balance_xof": 0,
                "avg_response_seconds": rng.choice([None, 60, 240, 1200, 7200]),
                "response_count": rng.randint(0, 30),
                "referral_code": uuid.uuid4().hex[:8],
                "referred_by": None,
                "is_active": True,
                "last_seen_at": _iso(now - timedelta(minutes=minutes_ago)),
                "hearts_received": rng.randint(0, 25),
                "registration_ip": TEST_IP,
                "last_login_ip": TEST_IP,
                "created_at": _iso(now - timedelta(days=rng.randint(0, 60))),
                "updated_at": _iso(now),
                "is_test_data": True,
            }
            await db.users.insert_one(dict(user))
            users.append(user)
            summary["users"] += 1
            if i % 5 == 0:
                await _set_job(progress=i + 1, summary=summary)

        men = [u for u in users if u["gender"] == "homme"]
        women = [u for u in users if u["gender"] == "femme"]

        # --- Vidéos (identités vérifiées uniquement, comme pour un vrai membre)
        verified = [u for u in users if u["verification_status"] == "verified"]
        authors = rng.sample(verified, min(videos, len(verified)))
        await _set_job(step="Création des vidéos (compression + flou)", progress=0, total=len(authors))
        video_docs = []
        for n, author in enumerate(authors):
            first = author["full_name"].split(" ")[0]
            source = await asyncio.to_thread(_test_video, f"{first} · {author['city']}", rng.choice(COLORS))
            try:
                result = await asyncio.to_thread(process_video, source, 60)
            finally:
                source.unlink(missing_ok=True)
            clear_key = await save_private_media(result.clear_mp4, "video/mp4")
            blurred_url = await save_public_media(result.blurred_mp4, "video/mp4")
            poster_url = await save_photo(result.poster_jpg, "image/jpeg")
            await _remember_media("private", clear_key)
            await _remember_media("public", blurred_url)
            await _remember_media("public", poster_url)
            caption = rng.choice(CAPTIONS).replace("{city}", author["city"].lower().replace(" ", "").replace("-", ""))
            video = {
                "id": _uuid(), "user_id": author["id"], "caption": caption, "hashtags": extract_hashtags(caption),
                "clear_key": clear_key, "blurred_url": blurred_url, "poster_url": poster_url,
                "duration_seconds": result.duration_seconds, "status": "published", "failure_reason": None,
                "likes_count": 0, "comments_count": 0, "views_count": 0, "reports_count": 0, "removed_reason": None,
                "ip": TEST_IP, "created_at": _iso(now - timedelta(hours=rng.randint(1, 240))), "is_test_data": True,
            }
            await db.videos.insert_one(dict(video))
            video_docs.append(video)
            summary["videos"] += 1
            await _set_job(progress=n + 1, summary=summary)

        # --- Swipes (J'aime / Passer) et matchs réciproques
        await _set_job(step="Swipes, matchs et conversations", progress=0, total=1)
        likes = set()
        for u in users:
            others = women if u["gender"] == "homme" else men
            for target in rng.sample(others, min(len(others), rng.randint(6, 14))):
                action = "like" if rng.random() < 0.7 else "pass"
                await db.swipes.insert_one({"id": _uuid(), "user_id": u["id"], "target_user_id": target["id"],
                                            "action": action, "created_at": _iso(now - timedelta(hours=rng.randint(1, 300))),
                                            "is_test_data": True})
                summary["swipes"] += 1
                if action == "like":
                    likes.add((u["id"], target["id"]))
        pairs = {tuple(sorted(p)) for p in likes if (p[1], p[0]) in likes}
        by_id = {u["id"]: u for u in users}
        for a, b in pairs:
            match_id, conv_id = _uuid(), _uuid()
            created = now - timedelta(hours=rng.randint(1, 200))
            await db.matches.insert_one({"id": match_id, "user_a": a, "user_b": b, "created_at": _iso(created), "is_test_data": True})
            last_at = created
            if rng.random() < 0.75:  # la plupart des matchs ont une conversation commencée
                for k in range(rng.randint(2, 8)):
                    last_at = created + timedelta(minutes=5 * (k + 1))
                    sender = a if k % 2 == 0 else b
                    unread = k >= 4 and rng.random() < 0.5
                    await db.messages.insert_one({"id": _uuid(), "conversation_id": conv_id, "sender_id": sender,
                                                  "text": rng.choice(MESSAGES), "created_at": _iso(last_at),
                                                  "read_at": None if unread else _iso(last_at + timedelta(minutes=1)),
                                                  "is_test_data": True})
                    summary["messages"] += 1
            await db.conversations.insert_one({"id": conv_id, "match_id": match_id, "user_a": a, "user_b": b,
                                               "last_message_at": _iso(last_at), "created_at": _iso(created),
                                               "is_test_data": True})
            summary["matches"] += 1

        # --- Interactions sur les vidéos : vues, J'aime, commentaires
        comment_texts = ["Trop beau 🔥", "Magnifique 😍", "👏🏾👏🏾", "Tu es où exactement ?", "J'adore !", "💯"]
        for video in video_docs:
            viewers = rng.sample(users, rng.randint(5, min(40, len(users))))
            likers = viewers[: rng.randint(0, len(viewers))]
            commenters = rng.sample(viewers, rng.randint(0, min(4, len(viewers))))
            for v in viewers:
                await db.video_views.insert_one({"video_id": video["id"], "user_id": v["id"], "created_at": _iso(now), "is_test_data": True})
            for liker in likers:
                await db.video_likes.insert_one({"video_id": video["id"], "user_id": liker["id"], "created_at": _iso(now), "is_test_data": True})
            for c in commenters:
                await db.video_comments.insert_one({"id": _uuid(), "video_id": video["id"], "user_id": c["id"],
                                                    "text": rng.choice(comment_texts), "ip": TEST_IP,
                                                    "created_at": _iso(now - timedelta(minutes=rng.randint(1, 3000))),
                                                    "is_test_data": True})
                summary["comments"] += 1
            await db.videos.update_one({"id": video["id"]}, {"$set": {
                "views_count": len(viewers), "likes_count": len(likers), "comments_count": len(commenters)}})

        # --- Demandes "Voir en clair" (acceptées / en attente)
        verified_ids = [u["id"] for u in verified]
        for video in video_docs[: max(1, len(video_docs) // 2)]:
            for requester_id in rng.sample(verified_ids, min(2, len(verified_ids))):
                if requester_id == video["user_id"]:
                    continue
                exists = await db.video_access_requests.find_one({"owner_id": video["user_id"], "requester_id": requester_id})
                if exists:
                    continue
                await db.video_access_requests.insert_one({
                    "id": _uuid(), "owner_id": video["user_id"], "requester_id": requester_id,
                    "status": rng.choice(["pending", "accepted"]), "created_at": _iso(now), "decided_at": None,
                    "is_test_data": True})
                summary["access_requests"] += 1

        await _set_job(status="done", step="Terminé", progress=1, total=1, finished_at=_iso(_now_dt()), summary=summary)
    except Exception as exc:  # noqa: BLE001
        print(f"[test_data] génération interrompue : {exc!r}")
        await _set_job(status="failed", error=str(exc)[:300], finished_at=_iso(_now_dt()), summary=summary)


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------

async def _purge() -> None:
    summary: dict = {}
    try:
        await _set_job(status="purging", step="Suppression des données de test", error=None, started_at=_iso(_now_dt()))
        user_ids = await db.users.distinct("id", {"is_test_data": True})
        video_ids = await db.videos.distinct("id", {"$or": [{"is_test_data": True}, {"user_id": {"$in": user_ids}}]})
        conv_ids = await db.conversations.distinct("id", {"$or": [
            {"is_test_data": True}, {"user_a": {"$in": user_ids}}, {"user_b": {"$in": user_ids}}]})

        # 1) Fichiers inventoriés (photos, vidéos, vignettes)
        media = await db.test_media.find({}, {"_id": 0}).to_list(100000)
        for item in media:
            try:
                if item["kind"] == "private":
                    await delete_private_media(item["ref"])
                else:
                    await delete_public_media(item["ref"])
            except Exception as exc:  # noqa: BLE001 — un fichier déjà absent ne bloque pas la purge
                print(f"[test_data] fichier non supprimé {item['ref']} : {exc!r}")
        summary["files"] = len(media)

        # 2) Documents marqués + traces laissées par de vrais membres
        mark = {"is_test_data": True}
        plan = {
            "messages": {"$or": [mark, {"conversation_id": {"$in": conv_ids}}, {"sender_id": {"$in": user_ids}}]},
            "conversations": {"id": {"$in": conv_ids}},
            "matches": {"$or": [mark, {"user_a": {"$in": user_ids}}, {"user_b": {"$in": user_ids}}]},
            "swipes": {"$or": [mark, {"user_id": {"$in": user_ids}}, {"target_user_id": {"$in": user_ids}}]},
            "video_likes": {"$or": [mark, {"video_id": {"$in": video_ids}}, {"user_id": {"$in": user_ids}}]},
            "video_views": {"$or": [mark, {"video_id": {"$in": video_ids}}, {"user_id": {"$in": user_ids}}]},
            "video_comments": {"$or": [mark, {"video_id": {"$in": video_ids}}, {"user_id": {"$in": user_ids}}]},
            "video_reports": {"$or": [{"video_id": {"$in": video_ids}}, {"user_id": {"$in": user_ids}}]},
            "video_access_requests": {"$or": [mark, {"owner_id": {"$in": user_ids}}, {"requester_id": {"$in": user_ids}}]},
            "hearts_sent": {"$or": [{"sender_id": {"$in": user_ids}}, {"recipient_id": {"$in": user_ids}}]},
            "ratings": {"$or": [{"rated_user_id": {"$in": user_ids}}, {"rater_user_id": {"$in": user_ids}}]},
            "reports": {"$or": [{"reported_user_id": {"$in": user_ids}}, {"reporter_user_id": {"$in": user_ids}}]},
            "activity_log": {"user_id": {"$in": user_ids}},
            "videos": {"id": {"$in": video_ids}},
            "users": {"id": {"$in": user_ids}},
            "test_media": {},
        }
        for collection, query in plan.items():
            result = await db[collection].delete_many(query)
            summary[collection] = result.deleted_count
        await _set_job(status="purged", step="Données de test supprimées", finished_at=_iso(_now_dt()), summary=summary)
    except Exception as exc:  # noqa: BLE001
        print(f"[test_data] purge interrompue : {exc!r}")
        await _set_job(status="failed", error=str(exc)[:300], finished_at=_iso(_now_dt()), summary=summary)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

_BACKGROUND: set = set()


def _launch(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


@router.get("")
async def test_data_status(_: dict = Depends(get_current_admin)):
    """Avancement de la dernière opération + inventaire actuel + identifiants."""
    sample = await db.users.find({"is_test_data": True}, {"_id": 0, "email": 1, "full_name": 1, "gender": 1}).limit(6).to_list(6)
    return {
        "job": await _job(),
        "counts": {
            "users": await db.users.count_documents({"is_test_data": True}),
            "videos": await db.videos.count_documents({"is_test_data": True}),
            "matches": await db.matches.count_documents({"is_test_data": True}),
            "messages": await db.messages.count_documents({"is_test_data": True}),
        },
        "credentials": {"password": TEST_PASSWORD, "sample_accounts": sample},
    }


class GenerateRequest(BaseModel):
    count: int = Field(100, ge=2, le=300)
    videos: int = Field(30, ge=0, le=100)


@router.post("/generate", status_code=202)
async def generate_test_data(payload: GenerateRequest, _: dict = Depends(get_current_admin)):
    job = await _job()
    if job.get("status") in ("running", "purging"):
        raise HTTPException(status_code=409, detail="Une opération sur les données de test est déjà en cours")
    _launch(_generate(payload.count, payload.videos))
    return {"ok": True, "status": "running"}


@router.delete("", status_code=202)
async def purge_test_data(_: dict = Depends(get_current_admin)):
    job = await _job()
    if job.get("status") in ("running", "purging"):
        raise HTTPException(status_code=409, detail="Une opération sur les données de test est déjà en cours")
    _launch(_purge())
    return {"ok": True, "status": "purging"}
