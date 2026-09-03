"""
Iteration 21 tests:
- Admin stats returns total_vip_users, updates on grant/revoke VIP.
- GET /api/videos?kind=video excludes shorts (regression: kind=short returns only shorts).
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def db():
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO not configured")
    return MongoClient(MONGO_URL)[DB_NAME]


# ---------- VIP stat card ----------

class TestAdminStatsVip:
    def test_stats_has_total_vip_users_field(self, admin_headers):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total_vip_users" in data, f"missing total_vip_users field. keys={list(data.keys())}"
        assert isinstance(data["total_vip_users"], int)

    def test_stats_matches_db_count(self, admin_headers, db):
        r = requests.get(f"{API}/admin/stats", headers=admin_headers)
        assert r.status_code == 200
        stat_val = r.json()["total_vip_users"]
        db_val = db.users.count_documents({"is_vip": True})
        assert stat_val == db_val, f"stat={stat_val}, db={db_val}"

    def test_grant_revoke_updates_stat(self, admin_headers, db):
        # Create test user
        email = f"TEST_vipstat_{uuid.uuid4().hex[:8]}@example.com"
        rr = requests.post(f"{API}/auth/register",
                           json={"email": email, "password": "Test1234!",
                                 "username": f"tvs{uuid.uuid4().hex[:6]}"}, timeout=15)
        assert rr.status_code in (200, 201), rr.text
        tok = rr.json().get("token") or requests.post(
            f"{API}/auth/login", json={"email": email, "password": "Test1234!"}).json()["token"]
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
        uid = me["id"]

        try:
            before = requests.get(f"{API}/admin/stats", headers=admin_headers).json()["total_vip_users"]

            gr = requests.post(f"{API}/admin/users/{uid}/grant-vip",
                               headers=admin_headers, json={"duration_days": 30})
            assert gr.status_code == 200, gr.text

            after_grant = requests.get(f"{API}/admin/stats", headers=admin_headers).json()["total_vip_users"]
            assert after_grant == before + 1, f"before={before}, after_grant={after_grant}"

            rv = requests.post(f"{API}/admin/users/{uid}/revoke-vip", headers=admin_headers)
            assert rv.status_code == 200, rv.text

            after_revoke = requests.get(f"{API}/admin/stats", headers=admin_headers).json()["total_vip_users"]
            assert after_revoke == before, f"before={before}, after_revoke={after_revoke}"
        finally:
            db.users.delete_one({"id": uid})


# ---------- Videos kind filter (shorts exclusion regression) ----------

class TestVideosKindFilter:
    seeded_ids = []

    @pytest.fixture(autouse=True, scope="class")
    def _seed(self, request):
        db_ = request.getfixturevalue("db")
        base = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "renditions": [{"quality": "720p", "url": "https://example.com/v.m3u8", "size_bytes": 0}],
            "duration_seconds": 30,
            "thumbnail_url": "https://example.com/t.jpg",
            "views": 0, "likes": [], "dislikes": [], "tags": [],
            "category": "test", "uploader_id": "system", "status": "ready",
            "access_tier": "free", "description": "",
        }
        long_id = f"TEST_long_{uuid.uuid4().hex[:8]}"
        short_id = f"TEST_short_{uuid.uuid4().hex[:8]}"
        db_.videos.insert_one({**base, "id": long_id, "title": "TEST_LONG_VID", "is_short": False})
        db_.videos.insert_one({**base, "id": short_id, "title": "TEST_SHORT_VID",
                               "is_short": True, "shorts_category": "xxx"})
        TestVideosKindFilter.seeded_ids = [long_id, short_id]
        yield
        for vid in TestVideosKindFilter.seeded_ids:
            db_.videos.delete_one({"id": vid})

    def _fetch(self, section):
        r = requests.get(f"{API}/videos", params={"kind": "video", "section": section, "limit": 200})
        assert r.status_code == 200, r.text
        return r.json()

    def test_kind_video_latest_no_shorts(self):
        data = self._fetch("latest")
        items = data.get("items", data) if isinstance(data, dict) else data
        for it in items:
            assert it.get("is_short") is not True, f"short leaked into kind=video latest: {it.get('id')} {it.get('title')}"

    def test_kind_video_popular_no_shorts(self):
        data = self._fetch("popular")
        items = data.get("items", data) if isinstance(data, dict) else data
        for it in items:
            assert it.get("is_short") is not True, f"short leaked into kind=video popular: {it.get('id')}"

    def test_kind_video_random_no_shorts(self):
        data = self._fetch("random")
        items = data.get("items", data) if isinstance(data, dict) else data
        for it in items:
            assert it.get("is_short") is not True, f"short leaked into kind=video random: {it.get('id')}"

    def test_kind_short_returns_only_shorts(self):
        r = requests.get(f"{API}/videos", params={"kind": "short", "section": "latest", "limit": 200})
        assert r.status_code == 200
        data = r.json()
        items = data.get("items", data) if isinstance(data, dict) else data
        assert len(items) > 0, "expected at least the seeded short"
        for it in items:
            assert it.get("is_short") is True, f"non-short returned in kind=short: {it.get('id')}"
        # our seeded short should appear
        ids = [it.get("id") for it in items]
        assert TestVideosKindFilter.seeded_ids[1] in ids
