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
    author_id, author, _ = make_user(gender="femme", verified=True, country="Mali", city="Bamako")
    _, viewer, _ = make_user(gender="homme", country="Mali", city=" bamako ")
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


def test_referral_link_uses_first_public_origin(client, make_user, monkeypatch):
    """FRONTEND_ORIGIN peut lister plusieurs domaines : le lien de parrainage
    doit utiliser le premier, pas la liste entière."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "frontend_origin", "https://beauthentik.net, https://www.beauthentik.net")
    _, h, _ = make_user()
    link = client.get("/api/me/referrals", headers=h).json()["referral_link"]
    assert link.startswith("https://beauthentik.net/inscription?ref=")


def test_payment_return_url_always_on_public_site(monkeypatch):
    """Retour après paiement : toujours une page du site public, et une
    adresse fournie par le navigateur n'est acceptée que sur un domaine
    autorisé (pas de redirection vers un site tiers)."""
    from config import get_settings
    from routes.payments_pawapay import _return_url

    monkeypatch.setattr(get_settings(), "frontend_origin", "https://beauthentik.net,https://www.beauthentik.net")
    assert _return_url(None, "abonnement", "dep1") == "https://beauthentik.net/abonnement?paiement=dep1"
    assert _return_url("https://www.beauthentik.net/portefeuille?x=1", "portefeuille", "d") == "https://www.beauthentik.net/portefeuille?x=1"
    # Domaine étranger ou simple préfixe trompeur -> ignoré
    assert _return_url("https://evil.example/phish", "abonnement", "d2").startswith("https://beauthentik.net/")
    assert _return_url("https://beauthentik.net.evil.example/x", "abonnement", "d3").startswith("https://beauthentik.net/")


# ---------------------------------------------------------------------------
# Traçabilité IP, compteurs publics, données de test
# ---------------------------------------------------------------------------

def _admin_headers(client, make_user):
    from db import db

    admin_id, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "admin"}}))
    return headers


def test_every_action_records_client_ip(client, make_user):
    ip = "41.207.13.37"  # IP publique burkinabè fictive, telle que transmise par le proxy Render
    _, h, _ = make_user()
    xff = {**h, "X-Forwarded-For": f"{ip}, 10.0.0.1"}
    client.put("/api/me/profile", json={"city": "Ouagadougou"}, headers=xff)
    plan_id = client.get("/api/subscriptions/plans").json()[0]["id"]
    sub = client.post("/api/subscriptions/subscribe", json={"plan_id": plan_id}, headers=xff).json()

    import time
    time.sleep(0.3)  # journalisation en tâche de fond
    admin = _admin_headers(client, make_user)
    log = client.get("/api/admin/activity", params={"ip": ip}, headers=admin).json()
    actions = {i["action"] for i in log["items"]}
    assert {"Modification du profil", "Souscription à un abonnement"} <= actions
    assert all(i["user"] for i in log["items"])

    from db import db
    doc = client.portal.call(lambda: db.subscriptions.find_one({"id": sub["subscription_id"]}))
    assert doc["ip"] == ip

    # Connexion : IP de dernière connexion + ligne "Connexion réussie"
    email = client.get("/api/auth/me", headers=h).json()
    user_doc = client.portal.call(lambda: db.users.find_one({"id": email["id"]}))
    r = client.post("/api/auth/login", json={"identifier": user_doc["email"], "password": "motdepasse123"},
                    headers={"X-Forwarded-For": ip})
    assert r.status_code == 200
    user_doc = client.portal.call(lambda: db.users.find_one({"id": email["id"]}))
    assert user_doc["last_login_ip"] == ip
    summary = client.get(f"/api/admin/activity/user/{email['id']}", headers=admin).json()
    assert summary["ips"][0]["ip"] == ip

    # Réservé au back-office
    assert client.get("/api/admin/activity", headers=h).status_code == 403


def test_public_counters_and_visitor_ip(client, make_user):
    before = client.post("/api/stats/visit", headers={"X-Forwarded-For": "102.180.1.1"}).json()
    assert before["your_ip"] == "102.180.1.1"
    # Même IP le même jour : pas de double comptage ; autre IP : +1
    again = client.post("/api/stats/visit", headers={"X-Forwarded-For": "102.180.1.1"}).json()
    other = client.post("/api/stats/visit", headers={"X-Forwarded-For": "102.180.1.2"}).json()
    assert again["visits"] == before["visits"] and other["visits"] == before["visits"] + 1
    make_user(verified=True)
    after = client.get("/api/stats/public").json()
    assert after["registered"] == before["registered"] + 1 and after["verified"] == before["verified"] + 1


def test_test_data_generate_then_purge_everything(client, make_user):
    import time

    from db import db

    admin = _admin_headers(client, make_user)
    real_id, real, _ = make_user(gender="homme")
    counters_before = client.get("/api/stats/public").json()

    assert client.post("/api/admin/test-data/generate", json={"count": 12, "videos": 2}, headers=admin).status_code == 202
    for _ in range(300):
        status = client.get("/api/admin/test-data", headers=admin).json()
        if status["job"]["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert status["job"]["status"] == "done", status["job"]
    assert status["counts"]["users"] == 12 and status["counts"]["videos"] == 2

    # Les comptes de test ne sont jamais comptés publiquement
    assert client.get("/api/stats/public").json()["registered"] == counters_before["registered"]
    results = client.get("/api/search", params={"age_min": 18, "age_max": 99}, headers=real).json()["results"]
    # Lot 50 — l'information « profil de test » est réservée au back-office : jamais transmise aux membres
    assert results and not any(p["is_test_data"] for p in results)
    from db import db
    ids_test = {d["id"] for d in client.portal.call(lambda: db.users.find({"is_test_data": True}, {"_id": 0, "id": 1}).to_list(1000))}
    test_profile = next(p for p in results if p["id"] in ids_test)

    # On peut se connecter avec un compte de test (mot de passe commun)
    email = status["credentials"]["sample_accounts"][0]["email"]
    assert client.post("/api/auth/login", json={"identifier": email, "password": status["credentials"]["password"]}).status_code == 200

    # Un vrai membre interagit avec un profil de test -> trace à purger aussi
    client.post("/api/swipe", json={"target_user_id": test_profile["id"], "action": "like"}, headers=real)

    assert client.delete("/api/admin/test-data", headers=admin).status_code == 202
    for _ in range(300):
        job = client.get("/api/admin/test-data", headers=admin).json()
        if job["job"]["status"] in ("purged", "failed"):
            break
        time.sleep(0.2)
    assert job["job"]["status"] == "purged", job["job"]
    for coll in ("users", "videos", "swipes", "matches", "messages", "conversations", "video_likes", "test_media"):
        assert client.portal.call(lambda c=coll: db[c].count_documents({"is_test_data": True})) == 0, coll
    assert client.portal.call(lambda: db.swipes.count_documents({"target_user_id": test_profile["id"]})) == 0
    # Le vrai membre, lui, est intact
    assert client.portal.call(lambda: db.users.count_documents({"id": real_id})) == 1


def test_admin_password_reset_switch(client, monkeypatch):
    """ADMIN_BOOTSTRAP_RESET_PASSWORD=true : le compte admin reprend le mot
    de passe de ADMIN_BOOTSTRAP_PASSWORD au démarrage (mot de passe oublié)."""
    from config import get_settings
    from seed import ensure_admin_user

    s = get_settings()
    monkeypatch.setattr(s, "admin_bootstrap_email", "boss@beauthentik.net")
    monkeypatch.setattr(s, "admin_bootstrap_password", "Ancien-mdp-2026")
    client.portal.call(ensure_admin_user)
    ok = lambda pw: client.post("/api/auth/login", json={"identifier": "boss@beauthentik.net", "password": pw}).status_code
    assert ok("Ancien-mdp-2026") == 200

    monkeypatch.setattr(s, "admin_bootstrap_password", "Nouveau-mdp-2026")
    client.portal.call(ensure_admin_user)          # sans l'interrupteur : inchangé
    assert ok("Nouveau-mdp-2026") == 401
    monkeypatch.setattr(s, "admin_bootstrap_reset_password", True)
    client.portal.call(ensure_admin_user)          # avec : réinitialisé
    assert ok("Nouveau-mdp-2026") == 200


# ---------------------------------------------------------------------------
# Paiements PawaPay : notification vérifiée auprès de PawaPay
# ---------------------------------------------------------------------------

def _pending_subscription_payment(client, make_user, amount=5000):
    """Crée (directement en base) un abonnement en attente + son paiement."""
    import uuid

    from db import db

    user_id, headers, _ = make_user()
    plan = client.get("/api/subscriptions/plans").json()[0]
    sub = client.post("/api/subscriptions/subscribe", json={"plan_id": plan["id"]}, headers=headers).json()
    deposit_id = str(uuid.uuid4())
    client.portal.call(lambda: db.payments.insert_one({
        "id": str(uuid.uuid4()), "deposit_id": deposit_id, "user_id": user_id,
        "subscription_id": sub["subscription_id"], "purpose": "subscription", "amount": amount,
        "currency": "XOF", "status": "initiated",
    }))
    return deposit_id, sub["subscription_id"], headers


def test_webhook_is_verified_with_pawapay_before_activation(client, make_user, monkeypatch):
    from config import get_settings
    from db import db
    import routes.payments_pawapay as pp

    monkeypatch.setattr(get_settings(), "pawapay_callback_secret", "s3cret")
    deposit_id, sub_id, _ = _pending_subscription_payment(client, make_user)
    sub_status = lambda: client.portal.call(lambda: db.subscriptions.find_one({"id": sub_id}))["status"]
    hook = lambda: client.post(f"/api/payments/pawapay/webhooks/deposits/s3cret", json={"depositId": deposit_id, "status": "COMPLETED"})

    # Mauvais secret -> refusé
    assert client.post("/api/payments/pawapay/webhooks/deposits/faux", json={"depositId": deposit_id}).status_code == 403

    # Notification "COMPLETED" forgée alors que PawaPay dit "en cours" -> rien n'est activé
    async def processing(_):
        return {"depositId": deposit_id, "status": "PROCESSING"}
    monkeypatch.setattr(pp, "_fetch_deposit", processing)
    hook()
    assert sub_status() == "pending"

    # PawaPay injoignable -> 503 (PawaPay renverra la notification)
    async def unreachable(_):
        return None
    monkeypatch.setattr(pp, "_fetch_deposit", unreachable)
    assert hook().status_code == 503

    # Confirmé par PawaPay avec le bon montant -> activé, une seule fois
    # (réponse au format v2 de PawaPay, passée par le même extracteur que la prod)
    v2_response = {"status": "FOUND", "data": {"depositId": deposit_id, "status": "COMPLETED", "amount": "5000", "currency": "XOF"}}
    async def completed(_):
        return pp._extract_deposit(v2_response)
    monkeypatch.setattr(pp, "_fetch_deposit", completed)
    assert hook().json()["applied"] is True
    assert sub_status() == "active"
    assert hook().json()["applied"] is False  # idempotent


def test_payment_amount_mismatch_and_refresh_activation(client, make_user, monkeypatch):
    from db import db
    import routes.payments_pawapay as pp

    # Montant incohérent -> pas d'activation
    deposit_id, sub_id, headers = _pending_subscription_payment(client, make_user)
    async def wrong_amount(_):
        return {"depositId": deposit_id, "status": "COMPLETED", "amount": "100"}
    monkeypatch.setattr(pp, "_fetch_deposit", wrong_amount)
    r = client.get(f"/api/payments/pawapay/{deposit_id}", params={"refresh": True}, headers=headers).json()
    assert r["status"] == "amount_mismatch"
    assert client.portal.call(lambda: db.subscriptions.find_one({"id": sub_id}))["status"] == "pending"

    # Page de retour (refresh) sans webhook : l'abonnement est bien activé
    deposit_id, sub_id, headers = _pending_subscription_payment(client, make_user)
    async def ok(_):
        return {"depositId": deposit_id, "status": "COMPLETED", "amount": "5000"}
    monkeypatch.setattr(pp, "_fetch_deposit", ok)
    r = client.get(f"/api/payments/pawapay/{deposit_id}", params={"refresh": True}, headers=headers).json()
    assert r["status"] == "completed"
    assert client.portal.call(lambda: db.subscriptions.find_one({"id": sub_id}))["status"] == "active"


def test_reconcile_activates_pending_payment_without_callback(client, make_user, monkeypatch):
    """Compte PawaPay partagé (callback chez Sawali) : la passe de
    rapprochement active l'abonnement sans aucune notification reçue."""
    from datetime import datetime, timezone

    from db import db
    import routes.payments_pawapay as pp

    deposit_id, sub_id, _ = _pending_subscription_payment(client, make_user, amount=5000)
    # Paiement "pending" (membre redirigé vers PawaPay), créé à l'instant
    client.portal.call(lambda: db.payments.update_one(
        {"deposit_id": deposit_id},
        {"$set": {"status": "pending", "created_at": datetime.now(timezone.utc).isoformat()}},
    ))

    async def completed(_):
        return {"depositId": deposit_id, "status": "COMPLETED", "amount": "5000"}
    monkeypatch.setattr(pp, "_fetch_deposit", completed)

    assert client.portal.call(pp.reconcile_pending_payments) == 1
    assert client.portal.call(lambda: db.subscriptions.find_one({"id": sub_id}))["status"] == "active"
    # Passe suivante : plus rien en attente, rien n'est appliqué deux fois
    assert client.portal.call(pp.reconcile_pending_payments) == 0


def test_payment_page_shows_beauthentik_branding(client, make_user, monkeypatch):
    """La page PawaPay (compte partagé avec Sawali) affiche beAuthentik dans
    "reason" et dans le libellé SMS (customerMessage), en français."""
    import httpx

    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "pawapay_environment", "sandbox")
    monkeypatch.setattr(settings, "pawapay_api_token_sandbox", "tok")

    sent = {}

    async def fake_post(self, url, headers=None, json=None, **kw):
        sent.update(json)  # corps envoyé à PawaPay
        return httpx.Response(200, json={"redirectUrl": "https://pay.example/x"})
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    _, headers, _ = make_user()
    plan = client.get("/api/subscriptions/plans").json()[0]
    sub = client.post("/api/subscriptions/subscribe", json={"plan_id": plan["id"]}, headers=headers).json()
    r = client.post("/api/payments/pawapay/payment-page",
                    json={"subscription_id": sub["subscription_id"], "amount_xof": 5000}, headers=headers)
    assert r.status_code == 200, r.text
    assert sent["customerMessage"] == "beAuthentik"
    assert "beAuthentik" in sent["reason"] and len(sent["reason"]) <= 50
    assert sent["language"] == "FR"



def test_near_me_by_city_and_by_gps(client, make_user):
    """"Près de moi" : par ville (profil) ou par géolocalisation (obligatoire
    pour ce mode, distance arrondie, position jamais exposée)."""
    a_id, a, _ = make_user(gender="femme", verified=True, country="Burkina Faso", city="Ouagadougou")
    b_id, b, _ = make_user(gender="femme", verified=True, country="Burkina Faso", city="Bobo-Dioulasso")
    _, viewer, _ = make_user(gender="homme", country="Burkina Faso", city="Ouagadougou")
    va = _publish_ready(client, a, a_id, caption="Ouaga")["id"]
    vb = _publish_ready(client, b, b_id, caption="Bobo")["id"]
    feed = lambda near: client.get("/api/videos/feed", params={"tab": "pres-de-moi", "near": near}, headers=viewer).json()

    # Ville : seulement Ouagadougou
    ids = [v["id"] for v in feed("ville")["items"]]
    assert va in ids and vb not in ids

    # GPS : exigé tant que la position n'est pas partagée
    assert feed("gps")["location_required"] is True

    # Positions : A à ~5 km du visiteur, B à Bobo (~300 km, hors rayon)
    assert client.put("/api/me/location", json={"lat": 12.3714, "lng": -1.5197}, headers=viewer).status_code == 200
    client.put("/api/me/location", json={"lat": 12.41, "lng": -1.49}, headers=a)
    client.put("/api/me/location", json={"lat": 11.1771, "lng": -4.2979}, headers=b)
    items = feed("gps")["items"]
    assert [v["id"] for v in items] == [va]
    assert items[0]["distance_km"] in (5, 6)  # ~5,5 km entre positions arrondies
    assert "location" not in items[0]["author"]

    # Position arrondie à ~1 km en base, et effaçable
    from db import db
    doc = client.portal.call(lambda: db.users.find_one({"id": a_id}))
    assert doc["location"] == {"lat": 12.41, "lng": -1.49}
    client.delete("/api/me/location", headers=viewer)
    assert feed("gps")["location_required"] is True


def test_face_blur_falls_back_to_full_blur_without_face():
    """Sans visage détecté : repli sûr (photo entièrement floutée)."""
    import io

    import numpy as np
    from PIL import Image

    from face_blur import blur_faces_in_photo, detect_faces
    from image_processing import apply_face_mask

    blank = np.full((400, 300, 3), 200, np.uint8)
    assert detect_faces(blank) == []
    assert blur_faces_in_photo(blank) is None
    buf = io.BytesIO()
    Image.fromarray(blank).save(buf, "JPEG")
    masked = Image.open(io.BytesIO(apply_face_mask(buf.getvalue())))
    assert masked.size == (300, 400)


def test_moderators_team_and_staff_hidden(client, make_user):
    """L'admin désigne des modérateurs ; les comptes de l'équipe sont
    invisibles des membres (découverte, fiche profil)."""
    from db import db

    admin_id, admin, _ = make_user(gender="homme")
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "admin"}}))
    mod_id, mod, _ = make_user(gender="femme")
    _, member, _ = make_user(gender="homme")
    email = client.portal.call(lambda: db.users.find_one({"id": mod_id}))["email"]

    # Seul l'admin principal gère l'équipe
    assert client.post("/api/admin/team", json={"email": email}, headers=member).status_code == 403
    assert client.post("/api/admin/team", json={"email": email.upper()}, headers=admin).json()["role"] == "moderator"
    assert client.get("/api/admin/team", headers=mod).status_code == 403
    assert {u["id"] for u in client.get("/api/admin/team", headers=admin).json()} >= {admin_id, mod_id}

    # Invisible pour un membre : fiche 404, jamais dans la découverte
    assert client.get(f"/api/users/{mod_id}", headers=member).status_code == 404
    client.portal.call(lambda: db.users.update_one({"id": mod_id}, {"$set": {"photos": [{"id": "p", "url": "u", "status": "approved"}]}}))
    assert mod_id not in [p["id"] for p in client.get("/api/discover", headers=member).json()]

    # Retrait : redevient un membre normal
    assert client.delete(f"/api/admin/team/{mod_id}", headers=admin).status_code == 200
    assert client.get(f"/api/users/{mod_id}", headers=member).status_code == 200


def test_phone_and_whatsapp_otp_verification(client, make_user, monkeypatch):
    """Code OTP par WhatsApp / SMS : envoi, erreurs, validation, badges,
    anti-abus (délai entre envois) et unicité du numéro."""
    import routes.phone_verification as pv

    sent = {}

    async def fake_send(msisdn, code, *_primary):
        sent["msisdn"], sent["code"] = msisdn, code
        return True, None
    monkeypatch.setattr(pv, "send_whatsapp_code", fake_send)
    monkeypatch.setattr(pv, "send_sms_code", fake_send)

    user_id, headers, _ = make_user()
    other_id, other, _ = make_user()

    # Numéro local à 8 chiffres -> indicatif 226 ajouté
    r = client.post("/api/me/numbers/otp/request", json={"channel": "whatsapp", "number": "70 12 34 56"}, headers=headers)
    assert r.status_code == 200, r.text
    assert sent["msisdn"] == "22670123456"
    # Nouvel envoi immédiat refusé (délai de 60 s)
    assert client.post("/api/me/numbers/otp/request", json={"channel": "whatsapp", "number": "70123456"}, headers=headers).status_code == 429

    # Mauvais code : 400 (pas 401), puis bon code
    wrong = "000000" if sent["code"] != "000000" else "111111"
    assert client.post("/api/me/numbers/otp/verify", json={"channel": "whatsapp", "code": wrong}, headers=headers).status_code == 400
    r = client.post("/api/me/numbers/otp/verify", json={"channel": "whatsapp", "code": sent["code"]}, headers=headers)
    assert r.status_code == 200 and r.json()["whatsapp_verified"] is True
    numbers = client.get("/api/me/numbers", headers=headers).json()
    assert numbers["whatsapp"] == "+22670123456" and numbers["whatsapp_verified"] is True

    # Badge visible par les autres, jamais le numéro
    profile = client.get(f"/api/users/{user_id}", headers=other).json()
    assert "+22670123456" not in str(profile)

    # Le même numéro ne peut pas être vérifié sur un autre compte
    assert client.post("/api/me/numbers/otp/request", json={"channel": "whatsapp", "number": "+226 70 12 34 56"}, headers=other).status_code == 409

    # SMS : même parcours, numéro de téléphone vérifié
    client.post("/api/me/numbers/otp/request", json={"channel": "sms", "number": "+22676000000"}, headers=headers)
    assert client.post("/api/me/numbers/otp/verify", json={"channel": "sms", "code": sent["code"]}, headers=headers).json()["phone_verified"] is True


def test_group_photo_rejected_but_sent_to_human_review_with_timestamps(client, make_user, monkeypatch):
    """Plus de 2 visages : refus immédiat avec raison, mais revue humaine
    quand même ; chaque étape est horodatée dans le journal."""
    import routes.photos as ph
    from db import db

    async def three_faces(_url):
        return 3

    async def ai_must_not_run(*_a, **_k):
        raise AssertionError("l'IA ne doit pas être appelée")
    monkeypatch.setattr(ph, "_count_faces", three_faces)
    monkeypatch.setattr(ph, "analyze_image", ai_must_not_run)

    user_id, headers, _ = make_user()
    admin_id, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "moderator"}}))

    photo = client.post("/api/me/photos", json={"url": "https://example.com/groupe.jpg"}, headers=headers).json()
    assert photo["status"] == "rejected" and photo["faces_detected"] == 3
    assert "3 visages" in photo["rejection_reason"] and photo["pending_human_review"] is True
    assert photo["moderated_at"]

    # Dans la file de revue humaine
    queue = client.get("/api/admin/photos/pending", headers=admin).json()
    assert any(p["id"] == photo["id"] for p in queue)

    # Le modérateur confirme le refus : sort de la file, horodaté
    client.post(f"/api/admin/photos/{user_id}/{photo['id']}/review", params={"approve": False}, headers=admin)
    assert not any(p["id"] == photo["id"] for p in client.get("/api/admin/photos/pending", headers=admin).json())

    events = client.get("/api/admin/verification-events", params={"user_id": user_id, "kind": "photo"}, headers=admin).json()
    actions = [e["action"] for e in events["items"]]
    assert {"submitted", "faces_counted", "auto_rejected_faces", "human_rejected"} <= set(actions)
    assert all(e["at"] for e in events["items"])
    assert next(e for e in events["items"] if e["action"] == "human_rejected")["actor_id"] == admin_id


def test_sms_provider_order_and_fallback(monkeypatch):
    """SMS : Orange d'abord pour +226 (OVH en secours), OVH d'abord ailleurs."""
    import asyncio

    import otp_senders as o

    calls = []

    def fake(name, ok):
        async def _send(msisdn, code):
            calls.append(name)
            return ok
        return _send
    monkeypatch.setattr(o, "orange_configured", lambda: True)
    monkeypatch.setattr(o, "ovh_configured", lambda: True)
    monkeypatch.setattr(o, "_send_sms_orange", fake("orange", False))
    monkeypatch.setattr(o, "_send_sms_ovh", fake("ovh", True))

    assert asyncio.run(o.send_sms_code("22670123456", "123456")) == (True, None)
    assert calls == ["orange", "ovh"]  # Orange en échec -> OVH en secours
    calls.clear()
    asyncio.run(o.send_sms_code("33612345678", "123456"))
    assert calls == ["ovh"]


def _matched_pair(client, make_user):
    a_id, a, _ = make_user(gender="homme")
    b_id, b, _ = make_user(gender="femme")
    _swipe_like(client, a, b_id)
    _swipe_like(client, b, a_id)
    conv_id = client.get(f"/api/users/{b_id}", headers=a).json()["conversation_id"]
    return a_id, a, b_id, b, conv_id


def test_settings_invisible_mode_and_visitors(client, make_user):
    """Mode invisible : pas "en ligne", visites non montrées ; sinon
    l'historique horodaté "Qui a vu mon profil / mes Moments" est rempli."""
    target_id, target, _ = make_user(gender="femme", verified=True)
    visitor_id, visitor, _ = make_user(gender="homme")
    ghost_id, ghost, _ = make_user(gender="homme")

    assert client.get("/api/me/settings", headers=ghost).json()["invisible_mode"] is False
    # Droit au Mode Invisible (lot 45) : bonus valable, posé directement en base pour ce test
    from datetime import datetime, timedelta, timezone
    from db import db
    fin_bonus = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    client.portal.call(lambda: db.users.update_one({"id": ghost_id}, {"$set": {"mode_invisible_bonus_jusqu_au": fin_bonus}}))
    assert client.put("/api/me/settings", json={"invisible_mode": True}, headers=ghost).json()["invisible_mode"] is True

    client.get(f"/api/users/{target_id}", headers=visitor)
    client.get(f"/api/users/{target_id}", headers=ghost)
    video_id = _publish_ready(client, target, target_id, caption="Salut")["id"]
    client.post(f"/api/videos/{video_id}/view", headers=visitor)
    client.post(f"/api/videos/{video_id}/view", headers=ghost)

    history = client.get("/api/me/visitors", headers=target).json()
    assert [v["visitor"]["id"] for v in history["profile_visits"]] == [visitor_id]
    assert history["profile_visits"][0]["at"]
    assert [v["viewer"]["id"] for v in history["moment_views"]] == [visitor_id]

    # Le membre invisible n'apparaît jamais "en ligne"
    ghost_profile = client.get(f"/api/users/{ghost_id}", headers=visitor).json()["profile"]
    assert ghost_profile["is_online"] is False and ghost_profile["last_seen_at"] is None


def test_voice_notes_respect_settings(client, make_user):
    a_id, a, b_id, b, conv_id = _matched_pair(client, make_user)
    audio = ("note.webm", b"\x1aE\xdf\xa3fake-opus", "audio/webm")

    r = client.post(f"/api/conversations/{conv_id}/voice", files={"file": audio},
                    data={"duration": "4.2", "transcript": "On se voit samedi ?"}, headers=a)
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "voice" and r.json()["audio_url"] and r.json()["transcript"] == "On se voit samedi ?"

    # B désactive la transcription : il ne la voit plus
    client.put("/api/me/settings", json={"voice_transcription": False}, headers=b)
    msg = client.get(f"/api/conversations/{conv_id}/messages", headers=b).json()[-1]
    assert msg["kind"] == "voice" and msg["transcript"] is None and msg["audio_url"]

    # B refuse les notes vocales : A ne peut plus lui en envoyer
    client.put("/api/me/settings", json={"voice_notes": False}, headers=b)
    r = client.post(f"/api/conversations/{conv_id}/voice", files={"file": audio}, data={"duration": "2"}, headers=a)
    assert r.status_code == 403


def test_testimonials_and_support(client, make_user):
    from db import db

    user_id, user, _ = make_user()
    admin_id, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "moderator"}}))

    # Témoignage : invisible tant qu'il n'est pas approuvé
    t = client.post("/api/testimonials", json={"text": "J'ai rencontré quelqu'un de vrai ici, merci beAuthentik !", "rating": 5}, headers=user).json()
    assert t["status"] == "pending" and all(x["id"] != t["id"] for x in client.get("/api/testimonials").json())
    client.post(f"/api/admin/testimonials/{t['id']}/review", params={"approve": True}, headers=admin)
    public = client.get("/api/testimonials").json()
    assert any(x["id"] == t["id"] for x in public) and "user_id" not in public[0]

    # Support : ticket, réponse de l'équipe horodatée, clôture
    ticket = client.post("/api/support/tickets", json={"topic": "paiement", "subject": "Paiement non activé", "message": "J'ai payé mais rien."}, headers=user).json()
    assert any(x["id"] == ticket["id"] for x in client.get("/api/admin/support/tickets", headers=admin).json())
    reply = client.post(f"/api/support/tickets/{ticket['id']}/messages", json={"message": "C'est régularisé."}, headers=admin).json()
    assert reply["from_staff"] is True and reply["at"]
    mine = client.get("/api/me/support/tickets", headers=user).json()[0]
    assert mine["status"] == "answered" and mine["unread_by_member"] is True and len(mine["messages"]) == 2
    assert client.post(f"/api/admin/support/tickets/{ticket['id']}/close", headers=admin).status_code == 200


def test_me_suivre_live_tracking(client, make_user):
    """Suivi en temps réel : positions visibles du compte désigné et de
    l'équipe, pas des autres ; arrêt par le propriétaire."""
    from db import db

    owner_id, owner, _ = make_user()
    guardian_id, guardian, _ = make_user()
    _, stranger, _ = make_user()
    staff_id, staff, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": staff_id}, {"$set": {"role": "admin"}}))
    guardian_email = client.portal.call(lambda: db.users.find_one({"id": guardian_id}))["email"]

    s = client.post("/api/tracking/sessions", json={"guardian_email": guardian_email, "duration_minutes": 60,
                                                   "note": "Rendez-vous au maquis"}, headers=owner).json()
    assert s["status"] == "active" and s["guardian_id"] == guardian_id
    assert client.post(f"/api/tracking/sessions/{s['id']}/points", json={"lat": 12.3714, "lng": -1.5197, "accuracy": 15}, headers=owner).json()["ok"]
    # Un autre membre ne peut ni envoyer de position ni voir le suivi
    assert client.post(f"/api/tracking/sessions/{s['id']}/points", json={"lat": 0, "lng": 0}, headers=guardian).status_code == 404
    assert client.get(f"/api/tracking/sessions/{s['id']}", headers=stranger).status_code == 404

    seen = client.get(f"/api/tracking/sessions/{s['id']}", headers=guardian).json()
    assert seen["last_point"]["lat"] == 12.3714 and len(seen["points"]) == 1 and seen["points"][0]["at"]
    assert client.get("/api/tracking/me", headers=guardian).json()["watching"][0]["id"] == s["id"]
    assert any(x["id"] == s["id"] for x in client.get("/api/admin/tracking", headers=staff).json())

    assert client.post(f"/api/tracking/sessions/{s['id']}/stop", headers=owner).status_code == 200
    assert client.post(f"/api/tracking/sessions/{s['id']}/points", json={"lat": 12.4, "lng": -1.5}, headers=owner).status_code == 410


def test_sms_primary_provider_setting(client, make_user, monkeypatch):
    """L'admin choisit le fournisseur SMS principal ; l'autre part en repli."""
    import asyncio

    import otp_senders as o
    from db import db

    admin_id, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "admin"}}))
    _, member, _ = make_user()
    assert client.put("/api/admin/settings/sms", json={"primary": "ovh"}, headers=member).status_code == 403
    assert client.put("/api/admin/settings/sms", json={"primary": "ovh"}, headers=admin).json()["primary"] == "ovh"
    assert client.get("/api/admin/settings/sms", headers=admin).json()["primary"] == "ovh"

    calls = []

    def fake(name, ok):
        async def _send(msisdn, code):
            calls.append(name)
            return ok
        return _send
    monkeypatch.setattr(o, "orange_configured", lambda: True)
    monkeypatch.setattr(o, "ovh_configured", lambda: True)
    monkeypatch.setattr(o, "_send_sms_orange", fake("orange", True))
    monkeypatch.setattr(o, "_send_sms_ovh", fake("ovh", False))
    # OVH principal (même pour un +226), en échec -> Orange en repli
    assert asyncio.run(o.send_sms_code("22670123456", "123456", "ovh")) == (True, None)
    assert calls == ["ovh", "orange"]


def test_admin_timeline_and_member_file(client, make_user):
    """Chronologie admin (du plus récent au plus ancien, avec les noms) et
    fiche membre consultée en invisible."""
    from db import db

    admin_id, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": admin_id}, {"$set": {"role": "moderator"}}))
    member_id, member, _ = make_user(gender="femme")
    reporter_id, reporter, _ = make_user(gender="homme")
    client.post("/api/testimonials", json={"text": "Une expérience vraiment authentique, bravo !", "rating": 4}, headers=member)
    client.post("/api/me/reports", json={"reported_user_id": member_id, "reason": "fake_profile"}, headers=reporter)

    assert client.get("/api/admin/timeline", headers=member).status_code == 403
    items = client.get("/api/admin/timeline", headers=admin).json()["items"]
    dates = [i["at"] for i in items]
    assert dates == sorted(dates, reverse=True)
    types = {i["type"] for i in items}
    assert {"inscription", "temoignage", "signalement"} <= types
    report = next(i for i in items if i["type"] == "signalement")
    assert report["user"]["id"] == member_id and report["details"]["par"]  # noms résolus

    # Filtre par membre
    only = client.get("/api/admin/timeline", params={"user_id": member_id}, headers=admin).json()["items"]
    assert only and all(i["user_id"] == member_id for i in only)

    # Fiche membre : lecture seule, en invisible (aucune visite enregistrée)
    file = client.get(f"/api/admin/members/{member_id}", headers=admin).json()
    assert file["user"]["id"] == member_id and "password_hash" not in file["user"]
    assert file["reports_received"][0]["reporter_name"]
    client.get(f"/api/users/{member_id}", headers=admin)
    assert client.get("/api/me/visitors", headers=member).json()["profile_visits"] == []


# ---------------------------------------------------------------------------
# Page d'accueil : encart vidéo « Moments » paramétrable par l'admin
# ---------------------------------------------------------------------------

def test_moments_video_settings(client, make_user):
    admin = _admin_headers(client, make_user)
    _, member, _ = make_user()

    # Par défaut : aucune vidéo, encart désactivé (rien n'est affiché).
    public = client.get("/api/appearance").json()
    assert public["moments_video_url"] is None and public["moments_video_enabled"] is False

    # Envoi du fichier : réservé à l'admin, MP4/WebM uniquement.
    files = {"file": ("moment.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")}
    assert client.post("/api/admin/settings/appearance/moments-video", files=files, headers=member).status_code == 403
    bad = {"file": ("moment.mov", b"x", "video/quicktime")}
    assert client.post("/api/admin/settings/appearance/moments-video", files=bad, headers=admin).status_code == 400
    res = client.post("/api/admin/settings/appearance/moments-video", files=files, headers=admin)
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert url.endswith(".mp4")

    # Enregistrement du réglage puis lecture publique (sans authentification).
    current = client.get("/api/admin/settings/appearance", headers=admin).json()
    payload = {**current, "moments_video_url": url, "moments_video_poster_url": "", "moments_video_enabled": True}
    assert client.put("/api/admin/settings/appearance", json=payload, headers=admin).status_code == 200
    public = client.get("/api/appearance").json()
    assert public["moments_video_url"] == url
    assert public["moments_video_poster_url"] is None  # chaîne vide -> pas d'aperçu
    assert public["moments_video_enabled"] is True

    # Seules les adresses http(s) sont acceptées.
    evil = {**payload, "moments_video_url": "javascript:alert(1)"}
    assert client.put("/api/admin/settings/appearance", json=evil, headers=admin).status_code == 422

    # Remise à zéro pour ne pas influencer d'autres tests.
    reset = {**payload, "moments_video_url": None, "moments_video_enabled": False}
    assert client.put("/api/admin/settings/appearance", json=reset, headers=admin).status_code == 200
