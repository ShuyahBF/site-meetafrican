# Emergent Auth Testing Playbook — MeetAfrican

## Step 1: Manually create a test session (in-memory mongomock — need to hit the backend endpoint that inserts)
Because MeetAfrican uses `mongomock://` in the preview env, we cannot use `mongosh`. Instead:
- Insert a test user + session via a small python script executed inside the backend container, OR
- Use the real OAuth flow with a Google test account.

Preferred: real OAuth flow.

## Step 2: Test Backend API
```bash
API_URL="https://meetafrican-phase.preview.emergentagent.com"

# Bearer fallback (also supports cookie via credentials:include)
curl -X GET "$API_URL/api/auth/me" -H "Authorization: Bearer <SESSION_TOKEN>"

# Session exchange (backend calls Emergent /session-data internally)
curl -X POST "$API_URL/api/auth/session" \
  -H "X-Session-ID: <SESSION_ID_FROM_URL_FRAGMENT>" \
  -c /tmp/cookies.txt

# Cookie-based me
curl -X GET "$API_URL/api/auth/me" -b /tmp/cookies.txt

# Logout
curl -X POST "$API_URL/api/auth/logout" -b /tmp/cookies.txt
```

## Step 3: Browser Testing
Playwright:
```python
await page.context.add_cookies([{
    "name": "session_token",
    "value": "<SESSION_TOKEN>",
    "domain": "meetafrican-phase.preview.emergentagent.com",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto("https://meetafrican-phase.preview.emergentagent.com/decouverte")
```

## Checklist
- [ ] `maf_users` document has `id` (uuid) and `email` fields
- [ ] `maf_sessions` document has `session_token`, `user_id` (matches user.id), `expires_at`
- [ ] All queries use `{"_id": 0}` projection
- [ ] `/api/auth/me` accepts BOTH `session_token` cookie AND `Authorization: Bearer <token>` (JWT or session_token)
- [ ] Frontend detects `session_id=` in `useLocation().hash` (not `window.location.hash`)
- [ ] `AuthContext` skips `/auth/me` check when hash contains `session_id=`
- [ ] After callback, user lands on `/decouverte` (member) or `/admin` (admin)
- [ ] Google users can access the app; `needs_profile_completion=true` flag is exposed on `/auth/me` for future onboarding step
- [ ] Existing local login (email/phone + password) still works unchanged

## Success Indicators
✅ `/api/auth/me` returns user data (both cookie and Bearer paths)
✅ `/decouverte` loads without redirect after OAuth callback
✅ Local login continues to work in parallel

## Test Identities (Google Auth)
- Any Google account can log in during Phase 1 (no allowlist).
- First-time Google users are auto-created in `maf_users` with `role=user`, `verification_status=unverified`, `needs_profile_completion=true`, default gender/birthdate. Password_hash is null (they cannot log in via password).
- Track linked test emails here as they are used.
