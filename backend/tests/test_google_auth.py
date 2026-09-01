"""Tests Emergent-managed Google Auth (POST /api/auth/session, /api/auth/logout)
+ regressions du flux JWT local.

Deux familles de tests :
1. TestGoogleAuthLive  -> appels HTTP réels sur le preview public (chemins
   d'erreur : header manquant, session_id invalide, /me non authentifié).
2. TestGoogleAuthMocked -> tests in-process (ASGITransport) avec
   routes.auth_google._fetch_session_data monkeypatché, pour le happy path
   sans jamais appeler https://demobackend.emergentagent.com.

Pas de pytest-asyncio dans cet env -> asyncio.run().
"""
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing from env and /app/frontend/.env")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


def _client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def api():
    return _client()


@pytest.fixture(scope="session")
def admin_credentials():
    path = Path("/app/memory/test_credentials.md")
    if not path.exists():
        pytest.skip("Missing /app/memory/test_credentials.md")
    content = path.read_text(encoding="utf-8")
    email = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    password = re.search(r'(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)', content)
    if not email or not password:
        pytest.skip("No email/password in test_credentials.md")
    return {"identifier": email.group(1), "password": password.group(1)}


# --------------------------------------------------------------------------
# 1) Regressions auth locale (JWT) — live preview
# --------------------------------------------------------------------------
class TestLocalAuthRegression:
    def test_admin_login_returns_jwt_and_admin_role(self, api, admin_credentials):
        r = api.post(f"{API}/auth/login", json=admin_credentials)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("access_token"), str) and data["access_token"]
        assert data["user"]["role"] == "admin"

    def test_me_with_local_jwt_bearer(self, api, admin_credentials):
        token = api.post(f"{API}/auth/login", json=admin_credentials).json()["access_token"]
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["role"] == "admin"
        assert "password_hash" not in me
        assert "_id" not in me
        assert "needs_profile_completion" in me

    def test_register_still_works(self, api):
        payload = {
            "full_name": "TEST GoogleAuthReg",
            "email": f"test_{uuid.uuid4().hex[:10]}@example.com",
            "password": "TestPass#2026",
            "gender": "femme",
            "birthdate": "1994-04-04",
        }
        r = api.post(f"{API}/auth/register", json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["user"]["full_name"] == payload["full_name"]
        token = data["access_token"]
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["id"] == data["user"]["id"]

    def test_plans_still_seeded(self, api):
        r = api.get(f"{API}/subscriptions/plans")
        assert r.status_code == 200, r.text
        plans = r.json()
        assert len(plans) == 3
        assert {p["code"] for p in plans} == {"1_semaine", "1_mois", "12_mois"}

    def test_admin_route_gated_for_standard_user(self, api):
        payload = {
            "full_name": "TEST Gate",
            "email": f"test_{uuid.uuid4().hex[:10]}@example.com",
            "password": "TestPass#2026",
            "gender": "homme",
            "birthdate": "1993-03-03",
        }
        token = api.post(f"{API}/auth/register", json=payload).json()["access_token"]
        r = requests.get(
            f"{API}/admin/settings/referral-points",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403, r.text

    def test_admin_route_allowed_for_admin(self, api, admin_credentials):
        token = api.post(f"{API}/auth/login", json=admin_credentials).json()["access_token"]
        r = requests.get(
            f"{API}/admin/settings/referral-points",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text


# --------------------------------------------------------------------------
# 2) Google auth — chemins d'erreur live
# --------------------------------------------------------------------------
class TestGoogleAuthLive:
    def test_session_without_header_400(self, api):
        r = api.post(f"{API}/auth/session")
        assert r.status_code == 400, r.text
        assert "X-Session-ID" in r.json().get("detail", "")

    def test_session_invalid_id_401(self, api):
        r = api.post(f"{API}/auth/session", headers={"X-Session-ID": f"fake-{uuid.uuid4().hex}"})
        assert r.status_code == 401, r.text

    def test_logout_without_anything_returns_ok(self, api):
        r = api.post(f"{API}/auth/logout")
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

    def test_me_without_auth_401(self, api):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_session_cookie_401(self):
        s = _client()
        s.cookies.set("session_token", "not-a-real-token")
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_bearer_401(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
        assert r.status_code == 401


# --------------------------------------------------------------------------
# 3) Google auth happy path — in-process, Emergent /session-data mocké
# --------------------------------------------------------------------------
FAKE_PROFILE = {
    "id": "g_1",
    "email": "gtest@example.com",
    "name": "G Test",
    "picture": None,
    "session_token": "stk_test",
}


def _run_mocked(coro_factory):
    import httpx
    from routes import auth_google as ag
    from server import app

    async def fake_fetch(session_id: str):
        return ag.EmergentSessionData(**FAKE_PROFILE)

    original = ag._fetch_session_data
    ag._fetch_session_data = fake_fetch

    async def main():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            return await coro_factory(client, ag)

    try:
        return asyncio.run(main())
    finally:
        ag._fetch_session_data = original


class TestGoogleAuthMocked:
    def test_exchange_sets_cookie_creates_user_and_session(self):
        async def scenario(client, ag):
            from db import db
            r = await client.post("/api/auth/session", headers={"X-Session-ID": "sid-1"})
            assert r.status_code == 200, r.text
            user = r.json()["user"]
            assert user["full_name"] == "G Test"
            assert user["needs_profile_completion"] is True

            set_cookie = r.headers.get("set-cookie", "")
            assert "session_token=stk_test" in set_cookie
            assert "HttpOnly" in set_cookie
            assert "Secure" in set_cookie
            assert "samesite=none" in set_cookie.lower()

            sessions = await db.sessions.find({"session_token": "stk_test"}, {"_id": 0}).to_list(10)
            assert len(sessions) == 1
            assert sessions[0]["user_id"] == user["id"]

            users = await db.users.find({"google_sub": "g_1"}, {"_id": 0}).to_list(10)
            assert len(users) == 1
            assert users[0]["password_hash"] is None
            assert users[0]["needs_profile_completion"] is True
            assert users[0]["email"] == "gtest@example.com"
            return user["id"]

        _run_mocked(scenario)

    def test_me_via_cookie_and_via_bearer_session_token(self):
        async def scenario(client, ag):
            r = await client.post("/api/auth/session", headers={"X-Session-ID": "sid-1"})
            assert r.status_code == 200
            uid = r.json()["user"]["id"]

            # cookie stocké automatiquement par le client httpx
            me_cookie = await client.get("/api/auth/me")
            assert me_cookie.status_code == 200, me_cookie.text
            assert me_cookie.json()["id"] == uid

            # bearer session_token (pas un JWT)
            me_bearer = await client.get(
                "/api/auth/me",
                headers={"Authorization": "Bearer stk_test", "Cookie": ""},
            )
            assert me_bearer.status_code == 200, me_bearer.text
            assert me_bearer.json()["id"] == uid

        _run_mocked(scenario)

    def test_logout_deletes_session_and_me_becomes_401(self):
        async def scenario(client, ag):
            from db import db
            await client.post("/api/auth/session", headers={"X-Session-ID": "sid-1"})
            out = await client.post("/api/auth/logout")
            assert out.status_code == 200
            assert out.json() == {"ok": True}
            left = await db.sessions.find({"session_token": "stk_test"}, {"_id": 0}).to_list(10)
            assert left == []

            me = await client.get("/api/auth/me", headers={"Cookie": "session_token=stk_test"})
            assert me.status_code == 401

        _run_mocked(scenario)

    def test_second_exchange_same_google_sub_no_duplicate_user(self):
        async def scenario(client, ag):
            from db import db
            r1 = await client.post("/api/auth/session", headers={"X-Session-ID": "sid-1"})
            r2 = await client.post("/api/auth/session", headers={"X-Session-ID": "sid-2"})
            assert r1.status_code == 200 and r2.status_code == 200, r2.text
            assert r1.json()["user"]["id"] == r2.json()["user"]["id"]
            users = await db.users.find({"google_sub": "g_1"}, {"_id": 0}).to_list(10)
            assert len(users) == 1

        _run_mocked(scenario)

    def test_session_missing_header_400_inprocess(self):
        async def scenario(client, ag):
            r = await client.post("/api/auth/session")
            assert r.status_code == 400
            assert r.json()["detail"] == "Header X-Session-ID manquant"

        _run_mocked(scenario)
