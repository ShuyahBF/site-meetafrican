"""Backend regression tests — MeetAfrican Phase 1.

Couvre: health, auth (register/login/me), subscriptions/plans, photos+moderation,
matching (discover/swipe/matches), chat (conversations/messages), admin RBAC,
ratings, reports, referrals, payments PawaPay (mode non configuré).
"""
import os
import re
import uuid
from datetime import date
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from the process environment and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def api():
    return _client()


@pytest.fixture(scope="session")
def admin_credentials():
    credentials_path = Path("/app/memory/test_credentials.md")
    if not credentials_path.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = credentials_path.read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    password = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not password:
        pytest.skip("No email/password found in test_credentials.md")
    return {"identifier": email.group(1), "password": password.group(1)}


def _register(api, gender="homme", birthdate="1995-05-05", **extra):
    payload = {
        "full_name": "TEST User",
        "email": f"test_{uuid.uuid4().hex[:10]}@example.com",
        "password": "TestPass#2026",
        "gender": gender,
        "birthdate": birthdate,
    }
    payload.update(extra)
    r = api.post(f"{API}/auth/register", json=payload)
    return payload, r


def _auth(token):
    s = _client()
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def admin_token(api, admin_credentials):
    r = api.post(f"{API}/auth/login", json=admin_credentials)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    data = r.json()
    assert data["user"]["role"] == "admin", f"admin role expected, got {data['user'].get('role')}"
    return data["access_token"]


@pytest.fixture(scope="session")
def admin_client(admin_token):
    return _auth(admin_token)


@pytest.fixture(scope="session")
def male_user(api):
    payload, r = _register(api, gender="homme")
    assert r.status_code == 201, r.text[:300]
    d = r.json()
    return {"payload": payload, "token": d["access_token"], "id": d["user"]["id"],
            "client": _auth(d["access_token"])}


@pytest.fixture(scope="session")
def female_user(api):
    payload, r = _register(api, gender="femme")
    assert r.status_code == 201, r.text[:300]
    d = r.json()
    return {"payload": payload, "token": d["access_token"], "id": d["user"]["id"],
            "client": _auth(d["access_token"])}


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

class TestHealth:
    def test_health(self, api):
        r = api.get(f"{API}/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

class TestAuth:
    def test_register_returns_jwt_and_profile(self, api):
        payload, r = _register(api)
        assert r.status_code == 201, r.text[:300]
        d = r.json()
        assert isinstance(d.get("access_token"), str) and len(d["access_token"]) > 20
        assert d.get("token_type") in ("bearer", "Bearer")
        u = d["user"]
        assert u["full_name"] == payload["full_name"]
        assert u["gender"] == payload["gender"]
        assert u["role"] == "user"
        assert "password_hash" not in u
        assert "_id" not in u

        # /me with the fresh token must return the same profile
        me = _auth(d["access_token"]).get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json()["id"] == u["id"]
        assert me.json()["full_name"] == payload["full_name"]

    def test_register_minor_rejected(self, api):
        minor_bd = date.today().replace(year=date.today().year - 17).isoformat()
        _, r = _register(api, birthdate=minor_bd)
        assert r.status_code == 400, f"expected 400 for minor, got {r.status_code}: {r.text[:200]}"
        assert "18" in r.json()["detail"]

    def test_register_invalid_birthdate(self, api):
        _, r = _register(api, birthdate="not-a-date")
        assert r.status_code == 400, r.text[:200]

    def test_register_duplicate_email_conflict(self, api, male_user):
        r = api.post(f"{API}/auth/register", json=male_user["payload"])
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text[:200]}"

    def test_register_requires_email_or_phone(self, api):
        r = api.post(f"{API}/auth/register", json={
            "full_name": "TEST NoContact", "password": "TestPass#2026",
            "gender": "homme", "birthdate": "1990-01-01",
        })
        assert r.status_code == 400, r.text[:200]

    def test_register_short_password_422(self, api):
        _, r = _register(api, password="short")
        assert r.status_code == 422, r.text[:200]

    def test_login_with_email_identifier(self, api, male_user):
        r = api.post(f"{API}/auth/login", json={
            "identifier": male_user["payload"]["email"],
            "password": male_user["payload"]["password"],
        })
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["user"]["id"] == male_user["id"]
        assert isinstance(d["access_token"], str)

    def test_login_with_phone_identifier(self, api):
        phone = f"+2266{uuid.uuid4().int % 10**7:07d}"
        payload, r = _register(api, phone=phone, email=None)
        assert r.status_code == 201, r.text[:300]
        uid = r.json()["user"]["id"]
        r2 = api.post(f"{API}/auth/login", json={"identifier": phone, "password": payload["password"]})
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json()["user"]["id"] == uid

    def test_register_gender_autre_not_supported(self, api):
        """Spec demandait gender 'autre' — le modèle Gender ne l'accepte pas."""
        _, r = _register(api, gender="autre")
        assert r.status_code == 422, r.status_code

    def test_login_wrong_password_401(self, api, male_user):
        r = api.post(f"{API}/auth/login", json={
            "identifier": male_user["payload"]["email"], "password": "WrongPass#2026"})
        assert r.status_code == 401

    def test_login_unknown_identifier_401(self, api):
        r = api.post(f"{API}/auth/login", json={
            "identifier": "nobody_here@example.com", "password": "WrongPass#2026"})
        assert r.status_code == 401

    def test_admin_login_role(self, api, admin_credentials):
        r = api.post(f"{API}/auth/login", json=admin_credentials)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["user"]["role"] == "admin"
        assert r.json()["user"]["verification_status"] == "verified"

    def test_me_requires_token(self, api):
        r = api.get(f"{API}/auth/me")
        assert r.status_code in (401, 403), r.status_code

    def test_me_invalid_token(self):
        r = _auth("garbage.token.value").get(f"{API}/auth/me")
        assert r.status_code == 401


# --------------------------------------------------------------------------
# Subscriptions
# --------------------------------------------------------------------------

class TestSubscriptions:
    def test_plans_seeded(self, api):
        r = api.get(f"{API}/subscriptions/plans")
        assert r.status_code == 200
        plans = r.json()
        codes = {p["code"] for p in plans}
        assert {"1_semaine", "1_mois", "12_mois"} <= codes, codes
        for p in plans:
            assert p["active"] is True
            assert isinstance(p["price_xof"], int) and p["price_xof"] > 0
            assert "_id" not in p
        durations = [p["duration_days"] for p in plans]
        assert durations == sorted(durations), "plans should be sorted by duration"

    def test_my_subscription_default_none(self, male_user):
        r = male_user["client"].get(f"{API}/subscriptions/me")
        assert r.status_code == 200
        assert r.json()["status"] == "none"

    def test_subscribe_and_payment_proof_flow(self, api, male_user):
        plans = api.get(f"{API}/subscriptions/plans").json()
        plan = plans[0]
        r = male_user["client"].post(f"{API}/subscriptions/subscribe", json={"plan_id": plan["id"]})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["plan"]["code"] == plan["code"]
        sub_id = d["subscription_id"]

        proof = male_user["client"].post(f"{API}/subscriptions/payment-proof", json={
            "subscription_id": sub_id, "screenshot_url": "https://example.test/proof.png"})
        assert proof.status_code == 201, proof.text[:300]
        assert proof.json()["status"] == "pending"

    def test_subscribe_unknown_plan_404(self, male_user):
        r = male_user["client"].post(f"{API}/subscriptions/subscribe", json={"plan_id": "does-not-exist"})
        assert r.status_code == 404

    def test_pending_proofs_forbidden_for_user(self, male_user):
        r = male_user["client"].get(f"{API}/subscriptions/payment-proofs/pending")
        assert r.status_code == 403

    def test_pending_proofs_allowed_for_admin(self, admin_client):
        r = admin_client.get(f"{API}/subscriptions/payment-proofs/pending")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_approves_proof_activates_subscription(self, api, admin_client):
        payload, reg = _register(api, gender="femme")
        client = _auth(reg.json()["access_token"])
        plan = api.get(f"{API}/subscriptions/plans").json()[1]
        sub_id = client.post(f"{API}/subscriptions/subscribe",
                             json={"plan_id": plan["id"]}).json()["subscription_id"]
        proof = client.post(f"{API}/subscriptions/payment-proof", json={
            "subscription_id": sub_id, "screenshot_url": "https://example.com/p.png"})
        assert proof.status_code == 201, proof.text[:300]
        proof_id = proof.json()["id"]

        rev = admin_client.post(f"{API}/subscriptions/payment-proofs/{proof_id}/review",
                                params={"approve": True})
        assert rev.status_code == 200, rev.text[:300]
        assert rev.json()["status"] == "approved"

        mine = client.get(f"{API}/subscriptions/me")
        assert mine.status_code == 200
        d = mine.json()
        assert d.get("status") == "active", f"subscription not activated after proof approval: {d}"
        assert d["plan_id"] == plan["id"]
        assert d.get("expires_at")


# --------------------------------------------------------------------------
# Photos + moderation queue (admin)
# --------------------------------------------------------------------------

class TestPhotosModeration:
    def test_add_photo_goes_to_review_then_admin_approves(self, male_user, admin_client):
        r = male_user["client"].post(f"{API}/me/photos", json={
            "url": "https://example.test/photo-m.jpg", "is_primary": True})
        assert r.status_code == 201, r.text[:300]
        photo = r.json()
        # AI key non configurée -> escalade revue humaine
        assert photo["status"] == "needs_review", photo
        photo_id = photo["id"]

        pending = admin_client.get(f"{API}/admin/photos/pending")
        assert pending.status_code == 200, pending.text[:300]
        assert any(p["id"] == photo_id for p in pending.json()), "photo missing from pending queue"

        review = admin_client.post(
            f"{API}/admin/photos/{male_user['id']}/{photo_id}/review", params={"approve": True})
        assert review.status_code == 200, review.text[:300]
        assert review.json()["status"] == "approved"

        me = male_user["client"].get(f"{API}/auth/me").json()
        assert any(p["id"] == photo_id and p["status"] == "approved" for p in me["photos"]), me["photos"]

    def test_pending_photos_forbidden_for_user(self, male_user):
        r = male_user["client"].get(f"{API}/admin/photos/pending")
        assert r.status_code == 403

    def test_delete_unknown_photo_404(self, male_user):
        r = male_user["client"].delete(f"{API}/me/photos/{uuid.uuid4()}")
        assert r.status_code == 404, (
            "BUG: delete_photo uses modified_count but always $set updated_at, "
            f"so a missing photo returns {r.status_code} instead of 404")

    def test_delete_existing_photo_removes_it(self, male_user):
        add = male_user["client"].post(f"{API}/me/photos", json={
            "url": "https://example.com/photo-to-delete.jpg"})
        assert add.status_code == 201, add.text[:300]
        pid = add.json()["id"]
        d = male_user["client"].delete(f"{API}/me/photos/{pid}")
        assert d.status_code == 200, d.text[:300]
        me = male_user["client"].get(f"{API}/auth/me").json()
        assert pid not in [p["id"] for p in me["photos"]], "photo not removed"


# --------------------------------------------------------------------------
# Matching / discover / swipe
# --------------------------------------------------------------------------

class TestMatching:
    def test_discover_requires_auth(self, api):
        r = api.get(f"{API}/discover")
        assert r.status_code in (401, 403)

    def test_discover_returns_opposite_gender_with_approved_photo(
        self, male_user, female_user, admin_client
    ):
        # female needs an approved photo to be discoverable
        p = female_user["client"].post(f"{API}/me/photos", json={
            "url": "https://example.test/photo-f.jpg", "is_primary": True})
        assert p.status_code == 201, p.text[:300]
        pid = p.json()["id"]
        rev = admin_client.post(
            f"{API}/admin/photos/{female_user['id']}/{pid}/review", params={"approve": True})
        assert rev.status_code == 200, rev.text[:300]

        r = male_user["client"].get(f"{API}/discover")
        assert r.status_code == 200, r.text[:300]
        profiles = r.json()
        assert isinstance(profiles, list)
        ids = [u["id"] for u in profiles]
        assert female_user["id"] in ids, f"female profile not discoverable: {ids}"
        for u in profiles:
            assert u["gender"] == "femme"
            assert u["id"] != male_user["id"]
            assert "password_hash" not in u

    def test_swipe_self_400(self, male_user):
        r = male_user["client"].post(f"{API}/swipe", json={
            "target_user_id": male_user["id"], "action": "like"})
        assert r.status_code == 400

    def test_swipe_unknown_target_404(self, male_user):
        r = male_user["client"].post(f"{API}/swipe", json={
            "target_user_id": str(uuid.uuid4()), "action": "like"})
        assert r.status_code == 404

    def test_swipe_invalid_action_422(self, male_user, female_user):
        r = male_user["client"].post(f"{API}/swipe", json={
            "target_user_id": female_user["id"], "action": "right"})
        assert r.status_code == 422

    def test_mutual_like_creates_match_and_conversation(self, male_user, female_user):
        r1 = male_user["client"].post(f"{API}/swipe", json={
            "target_user_id": female_user["id"], "action": "like"})
        assert r1.status_code == 200, r1.text[:300]
        assert r1.json()["matched"] is False, "no reciprocal like yet"

        r2 = female_user["client"].post(f"{API}/swipe", json={
            "target_user_id": male_user["id"], "action": "like"})
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["matched"] is True, d
        assert d["match_id"]

        m = male_user["client"].get(f"{API}/matches")
        assert m.status_code == 200, m.text[:300]
        matches = m.json()
        assert any(x["match_id"] == d["match_id"] for x in matches), matches
        entry = next(x for x in matches if x["match_id"] == d["match_id"])
        assert entry["other_user"]["id"] == female_user["id"]
        assert entry["conversation_id"], "conversation should be created on match"

    def test_discover_excludes_already_swiped(self, male_user, female_user):
        r = male_user["client"].get(f"{API}/discover")
        assert r.status_code == 200
        assert female_user["id"] not in [u["id"] for u in r.json()], "swiped profile still in discover"


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------

class TestChat:
    def test_conversation_messaging_flow(self, male_user, female_user):
        # dépend du match créé dans TestMatching
        convs = male_user["client"].get(f"{API}/conversations")
        assert convs.status_code == 200, convs.text[:300]
        items = convs.json()
        assert items, "no conversation found after mutual match"
        conv = next(c for c in items if c["other_user"]["id"] == female_user["id"])
        cid = conv["conversation_id"]

        send = male_user["client"].post(f"{API}/conversations/{cid}/messages",
                                       json={"text": "TEST bonjour"})
        assert send.status_code == 201, send.text[:300]
        assert send.json()["text"] == "TEST bonjour"
        assert send.json()["sender_id"] == male_user["id"]

        reply = female_user["client"].post(f"{API}/conversations/{cid}/messages",
                                          json={"text": "TEST salut"})
        assert reply.status_code == 201, reply.text[:300]

        msgs = female_user["client"].get(f"{API}/conversations/{cid}/messages")
        assert msgs.status_code == 200
        texts = [m["text"] for m in msgs.json()]
        assert texts[-2:] == ["TEST bonjour", "TEST salut"], texts

        # persistance côté liste de conversations
        listed = female_user["client"].get(f"{API}/conversations").json()
        target = next(c for c in listed if c["conversation_id"] == cid)
        assert target["last_message"]["text"] == "TEST salut"

    def test_messages_forbidden_for_outsider(self, male_user, female_user, api):
        convs = male_user["client"].get(f"{API}/conversations").json()
        cid = convs[0]["conversation_id"]
        _, r = _register(api, gender="homme")
        outsider = _auth(r.json()["access_token"])
        resp = outsider.get(f"{API}/conversations/{cid}/messages")
        assert resp.status_code == 403, resp.status_code

    def test_unknown_conversation_404(self, male_user):
        r = male_user["client"].get(f"{API}/conversations/{uuid.uuid4()}/messages")
        assert r.status_code == 404

    def test_empty_message_rejected(self, male_user):
        cid = male_user["client"].get(f"{API}/conversations").json()[0]["conversation_id"]
        r = male_user["client"].post(f"{API}/conversations/{cid}/messages", json={"text": ""})
        assert r.status_code == 422


# --------------------------------------------------------------------------
# Admin RBAC & settings
# --------------------------------------------------------------------------

ADMIN_GET_ENDPOINTS = [
    "/admin/settings/referral-points",
    "/admin/subscription-plans",
    "/admin/reports",
    "/admin/photos/pending",
    "/admin/verification/pending",
    "/admin/settings/moderation",
]


class TestAdmin:
    @pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
    def test_admin_get_200(self, admin_client, path):
        r = admin_client.get(f"{API}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
    def test_admin_get_403_for_standard_user(self, male_user, path):
        r = male_user["client"].get(f"{API}{path}")
        assert r.status_code == 403, f"{path} -> {r.status_code}"

    @pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
    def test_admin_get_401_without_token(self, api, path):
        r = api.get(f"{API}{path}")
        assert r.status_code in (401, 403), f"{path} -> {r.status_code}"

    def test_update_referral_points_persists(self, admin_client):
        original = admin_client.get(f"{API}/admin/settings/referral-points").json()
        new = dict(original)
        new["points_whatsapp"] = 7
        r = admin_client.put(f"{API}/admin/settings/referral-points", json=new)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["points_whatsapp"] == 7
        again = admin_client.get(f"{API}/admin/settings/referral-points")
        assert again.json()["points_whatsapp"] == 7
        # restore
        admin_client.put(f"{API}/admin/settings/referral-points", json=original)

    def test_create_and_update_plan(self, admin_client):
        code = f"TEST_{uuid.uuid4().hex[:6]}"
        payload = {"code": code, "name": "TEST Plan", "duration_days": 3, "price_xof": 999,
                   "features": ["TEST"], "active": False}
        r = admin_client.post(f"{API}/admin/subscription-plans", json=payload)
        assert r.status_code == 201, r.text[:300]
        plan = r.json()
        assert plan["code"] == code and plan["price_xof"] == 999

        upd = dict(plan)
        upd["price_xof"] = 1500
        r2 = admin_client.put(f"{API}/admin/subscription-plans/{plan['id']}", json=upd)
        assert r2.status_code == 200, r2.text[:300]
        assert r2.json()["price_xof"] == 1500

        all_plans = admin_client.get(f"{API}/admin/subscription-plans").json()
        stored = next(p for p in all_plans if p["id"] == plan["id"])
        assert stored["price_xof"] == 1500
        # inactive plan must not leak into public list
        public = requests.get(f"{API}/subscriptions/plans").json()
        assert plan["id"] not in [p["id"] for p in public]

    def test_update_unknown_plan_404(self, admin_client):
        payload = {"code": "TEST_X", "name": "X", "duration_days": 1, "price_xof": 1}
        r = admin_client.put(f"{API}/admin/subscription-plans/{uuid.uuid4()}", json=payload)
        assert r.status_code == 404

    def test_moderation_settings_toggle_persists(self, admin_client):
        original = admin_client.get(f"{API}/admin/settings/moderation").json()
        new = dict(original)
        new["ai_auto_enabled"] = False
        r = admin_client.put(f"{API}/admin/settings/moderation", json=new)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["ai_auto_enabled"] is False
        assert admin_client.get(f"{API}/admin/settings/moderation").json()["ai_auto_enabled"] is False
        admin_client.put(f"{API}/admin/settings/moderation", json=original)
        assert admin_client.get(f"{API}/admin/settings/moderation").json()["ai_auto_enabled"] is True


# --------------------------------------------------------------------------
# Ratings & reports
# --------------------------------------------------------------------------

class TestRatings:
    def test_rate_user_and_summary(self, male_user, female_user):
        r = male_user["client"].post(f"{API}/me/ratings", json={
            "rated_user_id": female_user["id"], "score": 4, "comment": "TEST ok"})
        assert r.status_code == 201, r.text[:300]
        assert r.json()["score"] == 4

        s = requests.get(f"{API}/users/{female_user['id']}/rating-summary")
        assert s.status_code == 200
        assert s.json() == {"average": 4.0, "count": 1}

        # upsert: re-rating replaces the previous score
        r2 = male_user["client"].post(f"{API}/me/ratings", json={
            "rated_user_id": female_user["id"], "score": 2})
        assert r2.status_code == 201
        s2 = requests.get(f"{API}/users/{female_user['id']}/rating-summary").json()
        assert s2 == {"average": 2.0, "count": 1}, s2

    def test_rate_self_400(self, male_user):
        r = male_user["client"].post(f"{API}/me/ratings", json={
            "rated_user_id": male_user["id"], "score": 5})
        assert r.status_code == 400

    def test_rate_unknown_user_404(self, male_user):
        r = male_user["client"].post(f"{API}/me/ratings", json={
            "rated_user_id": str(uuid.uuid4()), "score": 5})
        assert r.status_code == 404

    def test_rating_score_out_of_range_422(self, male_user, female_user):
        r = male_user["client"].post(f"{API}/me/ratings", json={
            "rated_user_id": female_user["id"], "score": 9})
        assert r.status_code == 422

    def test_summary_no_ratings(self, api, male_user):
        r = api.get(f"{API}/users/{male_user['id']}/rating-summary")
        assert r.status_code == 200
        assert r.json() == {"average": None, "count": 0}

    def test_report_flow_and_admin_review(self, api, male_user, admin_client):
        victim_payload, reg = _register(api, gender="femme")
        victim_email = victim_payload["email"]
        victim_id = reg.json()["user"]["id"]
        r = male_user["client"].post(f"{API}/me/reports", json={
            "reported_user_id": victim_id, "reason": "fake_profile", "details": "TEST details"})
        assert r.status_code == 201, r.text[:300]
        report_id = r.json()["id"]
        assert r.json()["status"] == "open"

        open_reports = admin_client.get(f"{API}/admin/reports").json()
        assert any(x["id"] == report_id for x in open_reports)

        rev = admin_client.post(f"{API}/admin/reports/{report_id}/review", json={
            "status": "reviewed", "deactivate_reported_user": True})
        assert rev.status_code == 200, rev.text[:300]
        assert rev.json()["status"] == "reviewed"

        still_open = admin_client.get(f"{API}/admin/reports").json()
        assert report_id not in [x["id"] for x in still_open]
        all_reports = admin_client.get(f"{API}/admin/reports", params={"status": "all"}).json()
        assert report_id in [x["id"] for x in all_reports]

        # deactivated account can no longer log in
        login = api.post(f"{API}/auth/login", json={
            "identifier": victim_email, "password": "TestPass#2026"})
        assert login.status_code == 403, login.status_code

    def test_report_self_400(self, male_user):
        r = male_user["client"].post(f"{API}/me/reports", json={
            "reported_user_id": male_user["id"], "reason": "abus"})
        assert r.status_code == 400

    def test_review_unknown_report_404(self, admin_client):
        r = admin_client.post(f"{API}/admin/reports/{uuid.uuid4()}/review", json={"status": "dismissed"})
        assert r.status_code == 404


# --------------------------------------------------------------------------
# Referrals
# --------------------------------------------------------------------------

class TestReferrals:
    def test_my_referrals_and_share_points(self, male_user):
        r = male_user["client"].get(f"{API}/me/referrals")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["referral_code"]
        assert d["referral_code"] in d["referral_link"]
        points_before = d["points"]

        s = male_user["client"].post(f"{API}/me/referrals/share", json={"platform": "whatsapp"})
        assert s.status_code == 201, s.text[:300]
        awarded = s.json()["points_awarded"]
        assert awarded > 0

        after = male_user["client"].get(f"{API}/me/referrals").json()
        assert after["points"] == points_before + awarded, after
        assert len(after["history"]) >= 1

    def test_share_invalid_platform_422(self, male_user):
        r = male_user["client"].post(f"{API}/me/referrals/share", json={"platform": "linkedin"})
        assert r.status_code == 422

    def test_referral_code_links_new_signup(self, api, male_user):
        code = male_user["client"].get(f"{API}/me/referrals").json()["referral_code"]
        _, r = _register(api, gender="femme", referral_code=code)
        assert r.status_code == 201, r.text[:300]
        assert r.json()["user"]["id"]

    def test_referrals_requires_auth(self, api):
        r = api.get(f"{API}/me/referrals")
        assert r.status_code in (401, 403)


# --------------------------------------------------------------------------
# Verification (identity) — mode local, sans IA
# --------------------------------------------------------------------------

class TestVerification:
    def test_submit_verification_pending_then_admin_approves(self, api, male_user, admin_client):
        r = male_user["client"].post(f"{API}/me/verification/submit", json={
            "document_key": "TEST_doc_key.jpg"})
        assert r.status_code == 201, r.text[:300]
        d = r.json()
        assert d["status"] == "pending", d
        vid = d["id"]

        mine = male_user["client"].get(f"{API}/me/verification")
        assert mine.status_code == 200
        assert any(x["id"] == vid for x in mine.json())

        pending = admin_client.get(f"{API}/admin/verification/pending")
        assert pending.status_code == 200, pending.text[:300]
        assert any(x["id"] == vid for x in pending.json())

        rev = admin_client.post(f"{API}/admin/verification/{vid}/review", params={"approve": True})
        assert rev.status_code == 200, rev.text[:300]
        assert rev.json()["status"] == "verified"
        assert male_user["client"].get(f"{API}/auth/me").json()["verification_status"] == "verified"

    def test_review_unknown_verification_404(self, admin_client):
        r = admin_client.post(f"{API}/admin/verification/{uuid.uuid4()}/review", params={"approve": True})
        assert r.status_code == 404


# --------------------------------------------------------------------------
# Payments — PawaPay non configuré (doit échouer proprement, pas en 500)
# --------------------------------------------------------------------------

class TestPayments:
    def test_payment_page_unconfigured_returns_503(self, api, male_user):
        plan = api.get(f"{API}/subscriptions/plans").json()[0]
        sub = male_user["client"].post(f"{API}/subscriptions/subscribe",
                                      json={"plan_id": plan["id"]}).json()
        r = male_user["client"].post(f"{API}/payments/pawapay/payment-page", json={
            "subscription_id": sub["subscription_id"], "amount_xof": plan["price_xof"]})
        assert r.status_code == 503, f"expected 503 clean error, got {r.status_code}: {r.text[:300]}"
        assert "PawaPay" in r.json()["detail"]

    def test_payment_page_requires_auth(self, api):
        r = api.post(f"{API}/payments/pawapay/payment-page", json={
            "subscription_id": "x", "amount_xof": 100})
        assert r.status_code in (401, 403)

    def test_payment_status_unknown_404(self, male_user):
        r = male_user["client"].get(f"{API}/payments/pawapay/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_webhook_rejects_bad_secret(self, api):
        r = api.post(f"{API}/payments/pawapay/webhooks/deposits/wrong-secret",
                     json={"depositId": "x", "status": "COMPLETED"})
        assert r.status_code == 403, r.status_code


# --------------------------------------------------------------------------
# Uploads (mode local)
# --------------------------------------------------------------------------

class TestUploads:
    def test_upload_requires_auth(self, api):
        r = api.post(f"{API}/uploads")
        assert r.status_code in (401, 403, 422)

    def test_upload_rejects_non_image(self, male_user):
        s = requests.Session()
        s.headers.update({"Authorization": male_user["client"].headers["Authorization"]})
        r = s.post(f"{API}/uploads",
                   files={"file": ("test.txt", b"hello", "text/plain")},
                   data={"kind": "photo"})
        assert r.status_code == 400, f"{r.status_code}: {r.text[:200]}"

    def test_upload_photo_local_returns_url(self, male_user):
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082")
        s = requests.Session()
        s.headers.update({"Authorization": male_user["client"].headers["Authorization"]})
        r = s.post(f"{API}/uploads",
                   files={"file": ("test.png", png, "image/png")},
                   data={"kind": "photo"})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        d = r.json()
        assert d["kind"] == "photo" and d["url"]
