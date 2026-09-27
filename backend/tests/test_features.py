"""Tests de bout en bout des fonctionnalités : profil détaillé, recherche
avancée, fil vidéo "Moments" (façon TikTok) et chat temps réel (en train
d'écrire, accusés de lecture, non lus)."""

FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1024  # contenu factice


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

def _publish(client, headers, caption="Coucou #Abidjan #danse", duration="12"):
    return client.post(
        "/api/videos",
        files={"file": ("clip.mp4", FAKE_MP4, "video/mp4")},
        data={"caption": caption, "duration_seconds": duration},
        headers=headers,
    )


def test_only_verified_members_can_publish(client, make_user):
    _, unverified, _ = make_user(gender="femme")
    assert _publish(client, unverified).status_code == 403

    _, verified, _ = make_user(gender="femme", verified=True)
    r = _publish(client, verified)
    assert r.status_code == 201, r.text
    assert r.json()["hashtags"] == ["abidjan", "danse"]
    assert _publish(client, verified, duration="600").status_code == 400  # trop longue


def test_feed_like_comment_view_report(client, make_user):
    author_id, author, _ = make_user(gender="femme", verified=True, country="Mali")
    _, viewer, _ = make_user(gender="homme", country="Mali")
    video_id = _publish(client, author, caption="Bamako by night #bamako").json()["id"]

    feed = client.get("/api/videos/feed", headers=viewer).json()
    item = next(v for v in feed["items"] if v["id"] == video_id)
    assert item["author"]["is_verified"] is True and item["liked_by_me"] is False

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
