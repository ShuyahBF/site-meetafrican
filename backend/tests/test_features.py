"""Tests de bout en bout des fonctionnalités : profil détaillé, recherche
avancée, fil vidéo "Moments" (façon TikTok) et chat temps réel (en train
d'écrire, accusés de lecture, non lus)."""

import subprocess
import time
from functools import lru_cache

from video_processing import ffmpeg_exe


@lru_cache(maxsize=None)
def make_mp4(seconds: int = 2) -> bytes:
    """Vraie petite vidéo MP4 (mire de test + son) générée par ffmpeg."""
    import tempfile
    from pathlib import Path

    out = Path(tempfile.mkdtemp()) / f"test{seconds}.mp4"
    subprocess.run([
        ffmpeg_exe(), "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc=size=240x426:rate=15",
        "-f", "lavfi", "-i", "sine=frequency=440",
        "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out),
    ], check=True, capture_output=True)
    return out.read_bytes()


def wait_processed(client, headers, owner_id, video_id, timeout=60):
    """Attend la fin du traitement en tâche de fond (compression + flou)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        mine = client.get(f"/api/users/{owner_id}/videos", headers=headers).json()
        video = next((v for v in mine if v["id"] == video_id), None)
        if video and video["status"] != "processing":
            return video
        time.sleep(0.3)
    raise AssertionError("traitement vidéo trop long")


def _swipe_like(client, headers, target_id):
    return client.post("/api/swipe", json={"target_user_id": target_id, "action": "like"}, headers=headers).json()


# ---------------------------------------------------------------------------
# Profil & recherche
# ---------------------------------------------------------------------------

def test_profile_update_and_options(client, make_user):
    _, h, _ = make_user(gender="homme")
    opts = client.get("/api/profile-options").json()
    assert "Musique" in opts["interests"]

    r = client.put("/api/me/profile", json={
        "bio": "  Passionné de musique  ", "city": "Ouagadougou", "country": "Burkina Faso",
        "interests": ["Musique", "Cuisine", "Musique"], "relationship_goal": "mariage",
    }, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["bio"] == "Passionné de musique"
    assert body["interests"] == ["Musique", "Cuisine"]  # dédoublonné
    assert body["relationship_goal"] == "mariage"

    # Centre d'intérêt hors liste -> refusé
    assert client.put("/api/me/profile", json={"interests": ["Inconnu"]}, headers=h).status_code == 422


def test_advanced_search_filters(client, make_user):
    _, viewer, _ = make_user(gender="homme")
    make_user(gender="femme", birthdate="2000-01-01", city="Dakar", country="Sénégal",
              interests=["Danse"], relationship_goal="serieuse")
    make_user(gender="femme", birthdate="1980-01-01", city="Abidjan", country="Côte d'Ivoire",
              interests=["Lecture"])

    r = client.get("/api/search", params={"city": "dak", "interests": "Danse"}, headers=viewer).json()
    assert r["total"] == 1 and r["results"][0]["city"] == "Dakar"

    # Tranche d'âge : 40-60 ans -> seulement la membre née en 1980
    r = client.get("/api/search", params={"age_min": 40, "age_max": 60, "country": "ivoire"}, headers=viewer).json()
    assert r["total"] == 1 and r["results"][0]["city"] == "Abidjan"

    # Genre opposé par défaut : aucun homme dans les résultats
    r = client.get("/api/search", headers=viewer).json()
    assert all(p["gender"] == "femme" for p in r["results"])


def test_public_profile_reflects_match(client, make_user):
    a_id, a, _ = make_user(gender="homme")
    b_id, b, _ = make_user(gender="femme")
    r = client.get(f"/api/users/{b_id}", headers=a).json()
    assert r["is_match"] is False and r["my_swipe"] is None

    _swipe_like(client, a, b_id)
    assert _swipe_like(client, b, a_id)["matched"] is True
    r = client.get(f"/api/users/{b_id}", headers=a).json()
    assert r["is_match"] is True and r["conversation_id"]


# ---------------------------------------------------------------------------
# Fil vidéo "Moments"
# ---------------------------------------------------------------------------

def _publish(client, headers, caption="Coucou #Abidjan #danse", duration="2", content=None):
    return client.post(
        "/api/videos",
        files={"file": ("clip.mp4", content or make_mp4(2), "video/mp4")},
        data={"caption": caption, "duration_seconds": duration},
        headers=headers,
    )


def _publish_ready(client, headers, owner_id, **kw):
    r = _publish(client, headers, **kw)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "processing"
    video = wait_processed(client, headers, owner_id, r.json()["id"])
    assert video["status"] == "published", video
    return video


def test_only_verified_members_can_publish(client, make_user):
    _, unverified, _ = make_user(gender="femme")
    assert _publish(client, unverified).status_code == 403

    owner_id, verified, _ = make_user(gender="femme", verified=True)
    video = _publish_ready(client, verified, owner_id)
    assert video["hashtags"] == ["abidjan", "danse"]
    assert video["poster_url"] and video["duration_seconds"] > 1
    assert "clear_key" not in video
    assert _publish(client, verified, duration="600").status_code == 400  # durée déclarée trop longue

    # Durée RÉELLE trop longue (déclarée courte) -> refus au traitement
    r = _publish(client, verified, duration="5", content=make_mp4(63))
    failed = wait_processed(client, verified, owner_id, r.json()["id"])
    assert failed["status"] == "failed" and "trop longue" in failed["failure_reason"]


def test_video_blurred_for_all_clear_only_for_accepted_verified(client, make_user):
    owner_id, owner, _ = make_user(gender="femme", verified=True)
    video = _publish_ready(client, owner, owner_id)
    vid = video["id"]
    # L'auteure voit sa vidéo en clair (URL privée temporaire)
    assert video["is_clear"] is True and "/api/private-files/" in video["url"]

    # Membre NON vérifié : version floutée, impossible de demander l'accès
    _, stranger, _ = make_user(gender="homme")
    seen = client.get(f"/api/videos/{vid}", headers=stranger).json()
    assert seen["is_clear"] is False and seen["url"] == video["blurred_url"]
    assert "private-files" not in seen["url"] and "clear_key" not in seen
    assert client.post(f"/api/users/{owner_id}/video-access", headers=stranger).status_code == 403

    # Membre vérifié : flouté tant que l'auteure n'a pas accepté
    viewer_id, viewer, _ = make_user(gender="homme", verified=True)
    assert client.get(f"/api/videos/{vid}", headers=viewer).json()["is_clear"] is False
    assert client.post(f"/api/users/{owner_id}/video-access", headers=viewer).json()["status"] == "pending"
    assert client.get(f"/api/videos/{vid}", headers=viewer).json()["access"] == "pending"
    assert client.get("/api/conversations/unread-count", headers=owner).json()["video_requests"] == 1

    [req] = client.get("/api/me/video-access/requests", headers=owner).json()
    assert req["requester"]["id"] == viewer_id
    client.post(f"/api/me/video-access/requests/{req['id']}", json={"accept": True}, headers=owner)
    now = client.get(f"/api/videos/{vid}", headers=viewer).json()
    assert now["is_clear"] is True and "/api/private-files/" in now["url"]
    assert client.get(f"/api/users/{owner_id}", headers=viewer).json()["video_access"] == "granted"

    # Révocation -> retour au flou, et pas de relance possible
    client.post(f"/api/me/video-access/requests/{req['id']}", json={"accept": False}, headers=owner)
    assert client.get(f"/api/videos/{vid}", headers=viewer).json()["is_clear"] is False
    assert client.post(f"/api/users/{owner_id}/video-access", headers=viewer).status_code == 403

    # Un match vaut acceptation (membre vérifié)
    matched_id, matched, _ = make_user(gender="homme", verified=True)
    _swipe_like(client, matched, owner_id)
    assert _swipe_like(client, owner, matched_id)["matched"] is True
    assert client.get(f"/api/videos/{vid}", headers=matched).json()["is_clear"] is True


def test_feed_like_comment_view_report(client, make_user):
    author_id, author, _ = make_user(gender="femme", verified=True, country="Mali")
    _, viewer, _ = make_user(gender="homme", country="Mali")
    video_id = _publish_ready(client, author, author_id, caption="Bamako by night #bamako")["id"]

    feed = client.get("/api/videos/feed", headers=viewer).json()
    item = next(v for v in feed["items"] if v["id"] == video_id)
    assert item["author"]["is_verified"] is True and item["liked_by_me"] is False
    assert item["is_clear"] is False  # visible de tous, mais floutée

    # Filtre par hashtag et onglet "Près de moi"
    assert any(v["id"] == video_id for v in client.get("/api/videos/feed", params={"tag": "bamako"}, headers=viewer).json()["items"])
    assert any(v["id"] == video_id for v in client.get("/api/videos/feed", params={"tab": "pres-de-moi"}, headers=viewer).json()["items"])

    # J'aime idempotent (double-tap répété)
    client.post(f"/api/videos/{video_id}/like", params={"like": True}, headers=viewer)
    r = client.post(f"/api/videos/{video_id}/like", params={"like": True}, headers=viewer).json()
    assert r["likes_count"] == 1
    r = client.post(f"/api/videos/{video_id}/like", params={"like": False}, headers=viewer).json()
    assert r["likes_count"] == 0

    # Vue unique par membre
    client.post(f"/api/videos/{video_id}/view", headers=viewer)
    client.post(f"/api/videos/{video_id}/view", headers=viewer)
    assert client.get(f"/api/videos/{video_id}", headers=viewer).json()["views_count"] == 1

    # Commentaires
    c = client.post(f"/api/videos/{video_id}/comments", json={"text": "Trop beau 🔥"}, headers=viewer).json()
    comments = client.get(f"/api/videos/{video_id}/comments", headers=author).json()
    assert comments[0]["text"] == "Trop beau 🔥"
    # L'auteur de la vidéo peut supprimer un commentaire reçu
    assert client.delete(f"/api/videos/{video_id}/comments/{c['id']}", headers=author).status_code == 200

    # 3 signalements distincts -> retrait automatique du fil
    for _ in range(3):
        _, reporter, _ = make_user(gender="homme")
        assert client.post(f"/api/videos/{video_id}/report", json={"reason": "spam"}, headers=reporter).status_code == 201
    assert client.get(f"/api/videos/{video_id}", headers=viewer).status_code == 404


# ---------------------------------------------------------------------------
# Chat temps réel
# ---------------------------------------------------------------------------

def test_chat_typing_read_receipts_and_unread(client, make_user):
    a_id, a, a_token = make_user(gender="homme")
    b_id, b, b_token = make_user(gender="femme")
    _swipe_like(client, a, b_id)
    _swipe_like(client, b, a_id)
    conv_id = client.get(f"/api/users/{b_id}", headers=a).json()["conversation_id"]

    with client.websocket_connect(f"/api/ws/conversations/{conv_id}?token={a_token}") as ws_a:
        assert ws_a.receive_json()["type"] == "presence"
        with client.websocket_connect(f"/api/ws/conversations/{conv_id}?token={b_token}") as ws_b:
            assert set(ws_b.receive_json()["data"]["user_ids"]) == {a_id, b_id}
            ws_a.receive_json()  # présence mise à jour côté A

            # "En train d'écrire" : relayé à B uniquement
            ws_a.send_json({"type": "typing"})
            assert ws_b.receive_json() == {"type": "typing", "data": {"user_id": a_id}}

            # Message de A -> reçu par les deux
            ws_a.send_json({"type": "message", "text": "Salut 👋"})
            assert ws_a.receive_json()["data"]["text"] == "Salut 👋"
            assert ws_b.receive_json()["data"]["read_at"] is None

            assert client.get("/api/conversations/unread-count", headers=b).json()["unread"] == 1
            convs = client.get("/api/conversations", headers=b).json()
            assert next(c for c in convs if c["conversation_id"] == conv_id)["unread_count"] == 1

            # B lit -> A reçoit l'accusé de lecture
            ws_b.send_json({"type": "read"})
            event = ws_a.receive_json()
            assert event["type"] == "read" and event["data"]["reader_id"] == b_id
            assert client.get("/api/conversations/unread-count", headers=b).json()["unread"] == 0
