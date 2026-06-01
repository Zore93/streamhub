"""Iteration 3 backend tests:
- Admin grant-pro / revoke-pro (durations + auth)
- Public /api/site/player-config + PATCH /api/admin/settings (allow_video_download)
- Subtitle .vtt upload (regression: no SameFileError) and .srt auto-convert
- Migration JSON output validation
- Smoke tests on existing endpoints
"""
import os
import io
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"
OWNER_EMAIL = "owner@streamhub.io"
OWNER_PASS = "Owner@2026!"
MIGRATE_DIR = Path("/app/deploy/migrate/out")


def auth(tok): return {"Authorization": f"Bearer {tok}"}


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j["access_token"]


@pytest.fixture(scope="session")
def admin_tok():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def owner_tok():
    return _login(OWNER_EMAIL, OWNER_PASS)


@pytest.fixture(scope="session")
def regular_user(admin_tok):
    """Create a non-admin user via signup; return (id, email, token)."""
    email = f"TEST_iter3_{uuid.uuid4().hex[:8]}@example.com"
    pw = "Passw0rd!Test"
    r = requests.post(f"{API}/auth/register", json={"email": email, "username": f"TESTu{uuid.uuid4().hex[:6]}", "password": pw}, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("token") or j.get("access_token") or _login(email, pw)
    # Resolve user id via /auth/me
    me = requests.get(f"{API}/auth/me", headers=auth(tok), timeout=10)
    assert me.status_code == 200, me.text
    uid = me.json()["id"]
    yield {"id": uid, "email": email, "token": tok}
    # cleanup
    try:
        requests.delete(f"{API}/admin/users/{uid}", headers=auth(admin_tok), timeout=10)
    except Exception:
        pass


# ============ GRANT/REVOKE PRO ============
class TestGrantRevokePro:
    def _get_user(self, admin_tok, uid):
        r = requests.get(f"{API}/admin/users?q=", headers=auth(admin_tok), timeout=10)
        assert r.status_code == 200, r.text
        for u in r.json():
            if u["id"] == uid:
                return u
        return None

    @pytest.mark.parametrize("duration,days", [("1day", 1), ("1week", 7), ("1month", 30)])
    def test_grant_pro_durations(self, admin_tok, regular_user, duration, days):
        uid = regular_user["id"]
        before = datetime.now(timezone.utc)
        r = requests.post(f"{API}/admin/users/{uid}/grant-pro",
                          headers=auth(admin_tok), json={"duration": duration}, timeout=10)
        assert r.status_code == 200, r.text
        exp_str = r.json()["pro_expires_at"]
        assert exp_str and exp_str != "permanent"
        exp = datetime.fromisoformat(exp_str)
        delta = exp - before
        # within 5 minute window of expected
        assert timedelta(days=days) - timedelta(minutes=5) < delta < timedelta(days=days) + timedelta(minutes=5), \
            f"expected ~{days}d, got {delta}"
        u = self._get_user(admin_tok, uid)
        assert u and u["is_pro"] is True
        assert u["pro_expires_at"] == exp_str

    def test_grant_pro_permanent(self, admin_tok, regular_user):
        uid = regular_user["id"]
        r = requests.post(f"{API}/admin/users/{uid}/grant-pro",
                          headers=auth(admin_tok), json={"duration": "permanent"}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["pro_expires_at"] == "permanent"
        u = self._get_user(admin_tok, uid)
        assert u["is_pro"] is True
        assert u["pro_expires_at"] == "permanent"

    def test_grant_pro_custom(self, admin_tok, regular_user):
        uid = regular_user["id"]
        before = datetime.now(timezone.utc)
        r = requests.post(f"{API}/admin/users/{uid}/grant-pro",
                          headers=auth(admin_tok),
                          json={"duration": "custom", "custom_days": 45}, timeout=10)
        assert r.status_code == 200, r.text
        exp = datetime.fromisoformat(r.json()["pro_expires_at"])
        delta = exp - before
        assert timedelta(days=45) - timedelta(minutes=5) < delta < timedelta(days=45) + timedelta(minutes=5)

    def test_grant_pro_invalid_duration(self, admin_tok, regular_user):
        r = requests.post(f"{API}/admin/users/{regular_user['id']}/grant-pro",
                          headers=auth(admin_tok), json={"duration": "forever"}, timeout=10)
        assert r.status_code == 400, r.text

    def test_grant_pro_requires_admin(self, regular_user):
        r = requests.post(f"{API}/admin/users/{regular_user['id']}/grant-pro",
                          headers=auth(regular_user["token"]),
                          json={"duration": "1day"}, timeout=10)
        assert r.status_code == 403, f"expected 403 for non-admin, got {r.status_code} {r.text}"

    def test_revoke_pro(self, admin_tok, regular_user):
        uid = regular_user["id"]
        # First grant
        requests.post(f"{API}/admin/users/{uid}/grant-pro",
                      headers=auth(admin_tok), json={"duration": "1week"}, timeout=10)
        # Revoke
        r = requests.post(f"{API}/admin/users/{uid}/revoke-pro", headers=auth(admin_tok), timeout=10)
        assert r.status_code == 200, r.text
        u = self._get_user(admin_tok, uid)
        assert u["is_pro"] is False
        assert u["pro_expires_at"] in (None, "")

    def test_revoke_pro_requires_admin(self, regular_user):
        r = requests.post(f"{API}/admin/users/{regular_user['id']}/revoke-pro",
                          headers=auth(regular_user["token"]), timeout=10)
        assert r.status_code == 403


# ============ PLAYER CONFIG ============
class TestPlayerConfig:
    def test_default_player_config(self, admin_tok):
        # Reset to false first
        requests.patch(f"{API}/admin/settings", headers=auth(admin_tok),
                       json={"allow_video_download": False}, timeout=10)
        r = requests.get(f"{API}/site/player-config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "allow_video_download" in data
        assert data["allow_video_download"] is False

    def test_toggle_allow_download(self, admin_tok):
        # set true
        r = requests.patch(f"{API}/admin/settings", headers=auth(admin_tok),
                           json={"allow_video_download": True}, timeout=10)
        assert r.status_code == 200, r.text
        # confirm persisted via public endpoint
        r2 = requests.get(f"{API}/site/player-config", timeout=10)
        assert r2.json()["allow_video_download"] is True
        # reset
        requests.patch(f"{API}/admin/settings", headers=auth(admin_tok),
                       json={"allow_video_download": False}, timeout=10)
        r3 = requests.get(f"{API}/site/player-config", timeout=10)
        assert r3.json()["allow_video_download"] is False

    def test_player_config_public(self):
        # no auth needed
        r = requests.get(f"{API}/site/player-config", timeout=10)
        assert r.status_code == 200


# ============ SUBTITLES ============
class TestSubtitles:
    @pytest.fixture(scope="class")
    def video_id(self, admin_tok):
        # find an existing video (we use any with status=ready owned by admin or any since admin can edit all)
        r = requests.get(f"{API}/videos?section=latest&limit=1", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("items", []) if isinstance(body, dict) else body
        if not items:
            pytest.skip("no videos available to attach subtitle")
        return items[0]["id"]

    def test_vtt_upload_no_samefile(self, admin_tok, video_id):
        vtt_content = b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello vtt test\n"
        files = {"file": ("test.vtt", io.BytesIO(vtt_content), "text/vtt")}
        data = {"language": "en", "label": "TEST VTT"}
        r = requests.post(f"{API}/videos/{video_id}/subtitles",
                          headers=auth(admin_tok), files=files, data=data, timeout=30)
        assert r.status_code == 200, f"vtt upload failed: {r.status_code} {r.text}"
        sub = r.json()
        assert sub["format"] == "vtt", f"format={sub.get('format')}"
        # Bug check: rel_orig should be None per fix intent (but code overrides it)
        # Track sub id for cleanup
        TestSubtitles._vtt_sub_id = sub["id"]
        TestSubtitles._vtt_original_url = sub.get("original_url")

    def test_vtt_rel_orig_is_none(self):
        # As per spec: rel_orig should be null in DB for .vtt
        assert TestSubtitles._vtt_original_url in (None, ""), \
            f"BUG: .vtt upload should have rel_orig=None but got {TestSubtitles._vtt_original_url!r}"

    def test_srt_upload_converts(self, admin_tok, video_id):
        srt = b"1\n00:00:00,000 --> 00:00:02,000\nHello SRT test\n\n2\n00:00:03,000 --> 00:00:05,000\nSecond line\n"
        files = {"file": ("test.srt", io.BytesIO(srt), "text/plain")}
        data = {"language": "fr", "label": "TEST SRT"}
        r = requests.post(f"{API}/videos/{video_id}/subtitles",
                          headers=auth(admin_tok), files=files, data=data, timeout=60)
        assert r.status_code == 200, f"srt upload failed: {r.status_code} {r.text}"
        sub = r.json()
        assert sub["format"] == "srt"
        assert sub.get("original_url"), "srt upload must have original_url set"
        TestSubtitles._srt_sub_id = sub["id"]

    def test_cleanup_subs(self, admin_tok, video_id):
        for attr in ("_vtt_sub_id", "_srt_sub_id"):
            sid = getattr(TestSubtitles, attr, None)
            if sid:
                requests.delete(f"{API}/videos/{video_id}/subtitles/{sid}",
                                headers=auth(admin_tok), timeout=10)


# ============ MIGRATION OUTPUT ============
class TestMigrationOutput:
    def _jl(self, p):
        return [json.loads(l) for l in open(p) if l.strip()]

    def test_files_exist(self):
        for f in ("users.json", "videos.json", "categories.json", "legacy_id_maps.json"):
            assert (MIGRATE_DIR / f).exists(), f"missing {f}"

    def test_counts(self):
        m = json.load(open(MIGRATE_DIR / "legacy_id_maps.json"))
        c = m.get("counts", {})
        assert c.get("users") == 2544, f"users count={c.get('users')}"
        assert c.get("categories") == 19
        assert c.get("videos") == 1420
        assert c.get("skipped_rows") == 0

    def test_users_schema(self):
        users = self._jl(MIGRATE_DIR / "users.json")
        assert len(users) == 2544
        u = users[0]
        required = ["id", "email", "password_hash", "role", "is_pro", "pro_expires_at"]
        for k in required:
            assert k in u, f"user missing {k}"
        assert u["password_hash"].startswith("$2b$"), f"pwh prefix={u['password_hash'][:6]}"
        assert u["role"] in ("user", "admin")
        assert isinstance(u["is_pro"], bool)

    def test_videos_schema(self):
        videos = self._jl(MIGRATE_DIR / "videos.json")
        assert len(videos) == 1420
        v = videos[0]
        for k in ["id", "title", "renditions", "category_id", "uploader_id", "status"]:
            assert k in v, f"video missing {k}"
        assert v["status"] == "ready"
        assert isinstance(v["renditions"], list)
        assert len(v["renditions"]) >= 1

    def test_categories_count(self):
        cats = self._jl(MIGRATE_DIR / "categories.json")
        assert len(cats) == 19


# ============ SMOKE: EXISTING ENDPOINTS ============
class TestSmoke:
    def test_admin_login(self, admin_tok):
        assert admin_tok

    def test_owner_login(self, owner_tok):
        assert owner_tok

    def test_admin_stats(self, admin_tok):
        r = requests.get(f"{API}/admin/stats", headers=auth(admin_tok), timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_videos", "total_users"):
            assert k in d

    def test_categories(self):
        r = requests.get(f"{API}/categories", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_videos_latest(self):
        r = requests.get(f"{API}/videos?section=latest", timeout=10)
        assert r.status_code == 200
