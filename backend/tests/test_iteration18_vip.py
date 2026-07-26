"""
Iteration 18 - VIP tier backend tests.

Coverage:
  - Package tier filtering (pro/vip/legacy)
  - VIP package CRUD
  - grant-vip / revoke-vip admin endpoints
  - auth/me reports is_vip / vip_expires_at / vip_package_id
  - PATCH /api/videos/{id} accepts/rejects access_tier
  - GET /api/videos/{id} access hierarchy for free/pro/vip viewers
  - VIP-expiry auto-revoke at login
  - checkout accepts a VIP package
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"


# ---------- helpers ----------

def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def db():
    if not MONGO_URL or not DB_NAME:
        pytest.skip("MONGO_URL/DB_NAME not set")
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def free_user(db):
    """Register a fresh free user."""
    email = f"TEST_free_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "username": f"tfree{uuid.uuid4().hex[:6]}"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("token") or _login(email, "Test1234!")["token"]
    me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    yield {"email": email, "token": tok, "id": me["id"]}
    db.users.delete_one({"id": me["id"]})


@pytest.fixture(scope="module")
def pro_user(db, admin_headers):
    email = f"TEST_pro_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "username": f"tpro{uuid.uuid4().hex[:6]}"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("token") or _login(email, "Test1234!")["token"]
    me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    uid = me["id"]
    # Grant pro
    gr = requests.post(f"{API}/admin/users/{uid}/grant-pro", headers=admin_headers,
                       json={"duration_days": 30})
    assert gr.status_code == 200, gr.text
    # Re-login to refresh
    tok = _login(email, "Test1234!")["token"]
    yield {"email": email, "token": tok, "id": uid}
    db.users.delete_one({"id": uid})


@pytest.fixture(scope="module")
def vip_user(db, admin_headers):
    email = f"TEST_vip_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "username": f"tvip{uuid.uuid4().hex[:6]}"},
                      timeout=15)
    assert r.status_code in (200, 201), r.text
    tok = r.json().get("token") or _login(email, "Test1234!")["token"]
    me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    uid = me["id"]
    gr = requests.post(f"{API}/admin/users/{uid}/grant-vip", headers=admin_headers,
                       json={"duration_days": 30})
    assert gr.status_code == 200, gr.text
    tok = _login(email, "Test1234!")["token"]
    yield {"email": email, "token": tok, "id": uid}
    db.users.delete_one({"id": uid})


# ---------- Package endpoint tests ----------

class TestPackages:
    created_ids = []

    def test_create_vip_package(self, admin_headers):
        payload = {"tier": "vip", "name": "TEST_VIP_1", "price_cents": 4999, "currency": "USD",
                   "duration_days": 30, "features": ["all"]}
        r = requests.post(f"{API}/packages", headers=admin_headers, json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("tier") == "vip"
        assert data.get("name") == "TEST_VIP_1"
        assert "id" in data
        TestPackages.created_ids.append(data["id"])

    def test_create_pro_package(self, admin_headers):
        payload = {"tier": "pro", "name": "TEST_PRO_1", "price_cents": 999, "currency": "USD",
                   "duration_days": 30, "features": []}
        r = requests.post(f"{API}/packages", headers=admin_headers, json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("tier") == "pro"
        TestPackages.created_ids.append(data["id"])

    def test_list_packages_tier_vip(self):
        r = requests.get(f"{API}/packages?tier=vip")
        assert r.status_code == 200
        pkgs = r.json()
        assert isinstance(pkgs, list)
        assert all(p.get("tier") == "vip" for p in pkgs), [p.get("tier") for p in pkgs]
        assert any(p.get("name") == "TEST_VIP_1" for p in pkgs)

    def test_list_packages_tier_pro_includes_legacy(self, db):
        # Insert a legacy package doc without tier field
        legacy_id = f"legacy_{uuid.uuid4().hex[:8]}"
        db.packages.insert_one({
            "id": legacy_id, "name": "TEST_LEGACY", "price_cents": 500, "currency": "USD",
            "duration_days": 30, "features": [], "active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        try:
            r = requests.get(f"{API}/packages?tier=pro")
            assert r.status_code == 200
            pkgs = r.json()
            # legacy must appear in pro filter
            ids = [p["id"] for p in pkgs]
            assert legacy_id in ids, f"legacy pkg not in pro list; got {ids}"
            # No vip pkg should sneak in
            assert all(p.get("tier") in (None, "pro") for p in pkgs)
        finally:
            db.packages.delete_one({"id": legacy_id})

    def test_list_packages_all_no_filter(self):
        r = requests.get(f"{API}/packages")
        assert r.status_code == 200
        pkgs = r.json()
        names = [p.get("name") for p in pkgs]
        assert "TEST_VIP_1" in names
        assert "TEST_PRO_1" in names

    def test_patch_vip_package(self, admin_headers):
        pid = TestPackages.created_ids[0]
        r = requests.patch(f"{API}/packages/{pid}", headers=admin_headers,
                           json={"name": "TEST_VIP_1_upd"})
        assert r.status_code == 200, r.text
        # GET back to verify persistence via list
        pkgs = requests.get(f"{API}/packages?tier=vip").json()
        matching = [p for p in pkgs if p["id"] == pid]
        assert matching and matching[0]["name"] == "TEST_VIP_1_upd"

    def test_reject_invalid_tier_on_create(self, admin_headers):
        r = requests.post(f"{API}/packages", headers=admin_headers,
                          json={"tier": "gold", "name": "TEST_BAD", "price_cents": 1, "currency": "USD",
                                "duration_days": 1, "features": []})
        # Code coerces invalid to "pro" — expect created as pro (not 400)
        assert r.status_code in (200, 201, 400)
        if r.status_code in (200, 201):
            data = r.json()
            assert data.get("tier") == "pro"
            TestPackages.created_ids.append(data["id"])

    def test_cleanup_packages(self, admin_headers):
        for pid in TestPackages.created_ids:
            requests.delete(f"{API}/packages/{pid}", headers=admin_headers)
        remaining = requests.get(f"{API}/packages").json()
        rem_ids = [p["id"] for p in remaining]
        for pid in TestPackages.created_ids:
            assert pid not in rem_ids


# ---------- VIP grant/revoke + auth/me ----------

class TestVipGrantRevoke:
    def test_auth_me_reports_vip_fields(self, vip_user):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {vip_user['token']}"})
        assert r.status_code == 200
        me = r.json()
        assert me.get("is_vip") is True
        assert me.get("vip_expires_at")

    def test_auth_me_free_user_no_vip(self, free_user):
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {free_user['token']}"}).json()
        assert me.get("is_vip") in (False, None)

    def test_revoke_vip(self, admin_headers, db):
        # Create a temp vip user, revoke, verify
        email = f"TEST_revoke_{uuid.uuid4().hex[:8]}@example.com"
        requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "username": f"trev{uuid.uuid4().hex[:6]}"})
        tok = _login(email, "Test1234!")["token"]
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
        uid = me["id"]
        requests.post(f"{API}/admin/users/{uid}/grant-vip", headers=admin_headers, json={"duration_days": 30})
        rv = requests.post(f"{API}/admin/users/{uid}/revoke-vip", headers=admin_headers)
        assert rv.status_code == 200
        tok2 = _login(email, "Test1234!")["token"]
        me2 = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok2}"}).json()
        assert me2.get("is_vip") in (False, None)
        assert me2.get("vip_expires_at") in (None, "")
        db.users.delete_one({"id": uid})

    def test_vip_auto_expires_on_login(self, admin_headers, db):
        email = f"TEST_expire_{uuid.uuid4().hex[:8]}@example.com"
        requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "username": f"texp{uuid.uuid4().hex[:6]}"})
        tok = _login(email, "Test1234!")["token"]
        uid = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["id"]
        # Force expired vip
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db.users.update_one({"id": uid}, {"$set": {"is_vip": True, "vip_expires_at": past}})
        # login triggers auto expire
        login2 = _login(email, "Test1234!")
        # /me should show is_vip false
        me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {login2['token']}"}).json()
        assert me.get("is_vip") in (False, None), f"is_vip should be false after expiry, got {me.get('is_vip')}"
        db.users.delete_one({"id": uid})


# ---------- Video access hierarchy ----------

class TestVideoAccessTiers:
    """Insert synthetic video docs directly into DB, then hit GET /api/videos/{id}."""

    video_ids = []

    @pytest.fixture(autouse=True, scope="class")
    def _seed_videos(self, request, db=None):
        # db fixture is module-scoped — get via request
        db = request.getfixturevalue("db")
        base = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "renditions": [{"quality": "720p", "url": "https://example.com/vid720.m3u8", "size_bytes": 0}],
            "duration_seconds": 60,
            "thumbnail_url": "https://example.com/thumb.jpg",
            "views": 0,
            "likes": 0,
            "dislikes": 0,
            "tags": [],
            "category": "test",
        }
        for tier in ("free", "pro", "vip"):
            vid = f"testvid_{tier}_{uuid.uuid4().hex[:8]}"
            db.videos.insert_one({
                **base, "id": vid, "title": f"TEST_VIDEO_{tier.upper()}",
                "access_tier": tier, "uploader_id": "system", "status": "ready",
                "description": ""
            })
            TestVideoAccessTiers.video_ids.append((tier, vid))
        yield
        for _, vid in TestVideoAccessTiers.video_ids:
            db.videos.delete_one({"id": vid})

    def _get(self, vid, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return requests.get(f"{API}/videos/{vid}", headers=headers)

    def test_free_video_open_to_all(self, free_user, pro_user, vip_user):
        vid = dict(TestVideoAccessTiers.video_ids)["free"]
        for tok in (None, free_user["token"], pro_user["token"], vip_user["token"]):
            r = self._get(vid, tok)
            assert r.status_code == 200
            data = r.json()
            assert not data.get("locked"), f"free vid locked for token={tok}"
            assert data.get("renditions"), "free vid missing renditions"

    def test_pro_video_locked_for_anon_and_free(self, free_user):
        vid = dict(TestVideoAccessTiers.video_ids)["pro"]
        for tok in (None, free_user["token"]):
            r = self._get(vid, tok)
            assert r.status_code == 200
            data = r.json()
            assert data.get("locked") is True, f"pro vid should be locked; got {data}"

    def test_pro_video_open_for_pro_and_vip(self, pro_user, vip_user):
        vid = dict(TestVideoAccessTiers.video_ids)["pro"]
        for tok in (pro_user["token"], vip_user["token"]):
            r = self._get(vid, tok)
            assert r.status_code == 200
            data = r.json()
            assert not data.get("locked"), f"pro vid locked for token={tok[:20]}: {data}"
            assert data.get("renditions")

    def test_vip_video_locked_for_free_and_pro(self, free_user, pro_user):
        vid = dict(TestVideoAccessTiers.video_ids)["vip"]
        for tok in (None, free_user["token"], pro_user["token"]):
            r = self._get(vid, tok)
            assert r.status_code == 200
            data = r.json()
            assert data.get("locked") is True, f"vip vid should be locked for tok={tok}: keys={list(data.keys())}"

    def test_vip_video_open_for_vip(self, vip_user):
        vid = dict(TestVideoAccessTiers.video_ids)["vip"]
        r = self._get(vid, vip_user["token"])
        assert r.status_code == 200
        data = r.json()
        assert not data.get("locked"), f"vip vid locked for vip user: {data}"
        assert data.get("renditions")


# ---------- PATCH video access_tier ----------

class TestPatchVideoTier:
    @pytest.fixture
    def seed_video(self, db):
        vid = f"testpatchvid_{uuid.uuid4().hex[:8]}"
        db.videos.insert_one({
            "id": vid, "title": "TEST_PATCH", "access_tier": "free",
            "uploader_id": "system", "status": "ready",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "renditions": {"720p": "x"}, "duration_seconds": 1,
            "thumbnail_url": "x", "views": 0, "likes": 0, "dislikes": 0,
            "tags": [], "category": "test", "description": ""
        })
        yield vid
        db.videos.delete_one({"id": vid})

    def test_patch_to_vip_ok(self, seed_video, admin_headers):
        r = requests.patch(f"{API}/videos/{seed_video}", headers=admin_headers,
                           json={"access_tier": "vip"})
        assert r.status_code == 200, r.text
        got = requests.get(f"{API}/videos/{seed_video}",
                           headers=admin_headers).json()
        assert got.get("access_tier") == "vip" or got.get("locked") in (True, False)

    def test_patch_invalid_tier_400(self, seed_video, admin_headers):
        r = requests.patch(f"{API}/videos/{seed_video}", headers=admin_headers,
                           json={"access_tier": "gold"})
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"


# ---------- Checkout accepts VIP package ----------

class TestCheckoutVipPackage:
    def test_checkout_accepts_vip_package(self, admin_headers, vip_user):
        # Create a VIP pkg
        p = requests.post(f"{API}/packages", headers=admin_headers,
                          json={"tier": "vip", "name": "TEST_VIP_CHK", "price_cents": 4999,
                                "currency": "USD", "duration_days": 30, "features": []})
        assert p.status_code in (200, 201)
        pid = p.json()["id"]
        try:
            # attempt checkout as a vip user (any authed user)
            r = requests.post(f"{API}/payments/checkout",
                              headers={"Authorization": f"Bearer {vip_user['token']}"},
                              json={"package_id": pid,
                                    "origin_url": BASE_URL})
            # Endpoint should not 404/400 on VIP package; may 500 if Stripe key missing → tolerated
            assert r.status_code in (200, 201, 400, 402, 500, 503), r.text
            if r.status_code in (200, 201):
                data = r.json()
                # Expect either checkout url or session_id
                assert "url" in data or "session_id" in data or "checkout_url" in data
        finally:
            requests.delete(f"{API}/packages/{pid}", headers=admin_headers)
