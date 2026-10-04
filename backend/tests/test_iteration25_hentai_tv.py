"""
Iteration 25 — Hentai RoSub + Seriale TV verticals (backend).

Covers:
- /api/hentai-series + /api/hentai-seasons CRUD
- /api/tv-series + /api/tv-seasons CRUD
- Slug uniqueness, 404 handling, cascade delete
- Default /api/videos and /api/videos/popular filter out is_hentai and is_tv
- PATCH /api/videos derives hentai_series_id / tv_series_id from the season_id
- PATCH /api/videos with invalid *_season_id -> 400
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PW = "Admin123!"


# ─── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def reg():
    r = {
        "hentai_series_ids": [],
        "hentai_season_ids": [],
        "tv_series_ids": [],
        "tv_season_ids": [],
        "video_ids": [],
    }
    yield r
    client = MongoClient(MONGO_URL)
    d = client[DB_NAME]
    if r["hentai_series_ids"]:
        d.hentai_series.delete_many({"id": {"$in": r["hentai_series_ids"]}})
    if r["hentai_season_ids"]:
        d.hentai_seasons.delete_many({"id": {"$in": r["hentai_season_ids"]}})
    if r["tv_series_ids"]:
        d.tv_series.delete_many({"id": {"$in": r["tv_series_ids"]}})
    if r["tv_season_ids"]:
        d.tv_seasons.delete_many({"id": {"$in": r["tv_season_ids"]}})
    if r["video_ids"]:
        d.videos.delete_many({"id": {"$in": r["video_ids"]}})


# ─── Hentai series + seasons CRUD ─────────────────────────────────────────
class TestHentaiSeries:
    def test_list_public(self):
        r = requests.get(f"{API}/hentai-series", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_series(self, H, reg):
        name = f"TEST_H_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/hentai-series", json={"name": name, "description": "d"}, headers=H, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name
        assert d["slug"]
        reg["hentai_series_ids"].append(d["id"])

    def test_slug_conflict(self, H, reg):
        name = f"TEST_H_{uuid.uuid4().hex[:6]}"
        r1 = requests.post(f"{API}/hentai-series", json={"name": name}, headers=H, timeout=15)
        assert r1.status_code == 200
        sid = r1.json()["id"]
        reg["hentai_series_ids"].append(sid)
        slug = r1.json()["slug"]
        r2 = requests.post(f"{API}/hentai-series", json={"name": name + "x", "slug": slug}, headers=H, timeout=15)
        assert r2.status_code == 400

    def test_get_by_id_and_slug(self, H, reg):
        name = f"TEST_H_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/hentai-series", json={"name": name}, headers=H, timeout=15)
        sid = r.json()["id"]
        slug = r.json()["slug"]
        reg["hentai_series_ids"].append(sid)
        for key in [sid, slug]:
            g = requests.get(f"{API}/hentai-series/{key}", timeout=15)
            assert g.status_code == 200
            assert g.json()["id"] == sid

    def test_patch_and_delete(self, H, reg):
        name = f"TEST_H_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/hentai-series", json={"name": name}, headers=H, timeout=15)
        sid = r.json()["id"]
        p = requests.patch(f"{API}/hentai-series/{sid}", json={"description": "updated"}, headers=H, timeout=15)
        assert p.status_code == 200
        assert p.json()["description"] == "updated"
        d = requests.delete(f"{API}/hentai-series/{sid}", headers=H, timeout=15)
        assert d.status_code == 200
        g = requests.get(f"{API}/hentai-series/{sid}", timeout=15)
        assert g.status_code == 404


class TestHentaiSeasons:
    def _mk_series(self, H, reg):
        r = requests.post(
            f"{API}/hentai-series",
            json={"name": f"TEST_H_{uuid.uuid4().hex[:6]}"},
            headers=H, timeout=15,
        )
        reg["hentai_series_ids"].append(r.json()["id"])
        return r.json()

    def test_season_crud(self, H, reg):
        s = self._mk_series(H, reg)
        sid = s["id"]
        # create season
        r = requests.post(
            f"{API}/hentai-series/{sid}/seasons",
            json={"name": "S1", "season_number": 1},
            headers=H, timeout=15,
        )
        assert r.status_code == 200, r.text
        se = r.json()
        reg["hentai_season_ids"].append(se["id"])
        assert se["series_id"] == sid

        # list public (active)
        lst = requests.get(f"{API}/hentai-series/{sid}/seasons", timeout=15)
        assert lst.status_code == 200
        assert any(x["id"] == se["id"] for x in lst.json())

        # get by id
        g = requests.get(f"{API}/hentai-seasons/{se['id']}", timeout=15)
        assert g.status_code == 200

        # patch
        p = requests.patch(f"{API}/hentai-seasons/{se['id']}", json={"description": "desc"}, headers=H, timeout=15)
        assert p.status_code == 200

        # delete
        d = requests.delete(f"{API}/hentai-seasons/{se['id']}", headers=H, timeout=15)
        assert d.status_code == 200

    def test_cascade_delete_series_removes_seasons(self, H, reg, db):
        s = self._mk_series(H, reg)
        sid = s["id"]
        r = requests.post(
            f"{API}/hentai-series/{sid}/seasons",
            json={"name": "S1", "season_number": 1},
            headers=H, timeout=15,
        )
        season_id = r.json()["id"]
        # delete series
        d = requests.delete(f"{API}/hentai-series/{sid}", headers=H, timeout=15)
        assert d.status_code == 200
        # season gone
        assert db.hentai_seasons.find_one({"id": season_id}) is None
        # pop registry so teardown doesn't error
        reg["hentai_series_ids"].remove(sid)


# ─── TV series + seasons CRUD (parity) ────────────────────────────────────
class TestTvSeries:
    def test_list_public(self):
        r = requests.get(f"{API}/tv-series", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_full_crud(self, H, reg):
        name = f"TEST_TV_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/tv-series", json={"name": name}, headers=H, timeout=15)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        reg["tv_series_ids"].append(sid)

        # season
        rs = requests.post(
            f"{API}/tv-series/{sid}/seasons",
            json={"name": "S1", "season_number": 1},
            headers=H, timeout=15,
        )
        assert rs.status_code == 200, rs.text
        season_id = rs.json()["id"]
        reg["tv_season_ids"].append(season_id)

        # list seasons
        lst = requests.get(f"{API}/tv-series/{sid}/seasons", timeout=15)
        assert lst.status_code == 200
        assert any(x["id"] == season_id for x in lst.json())

        # patch season
        p = requests.patch(f"{API}/tv-seasons/{season_id}", json={"description": "d"}, headers=H, timeout=15)
        assert p.status_code == 200

        # patch series
        p2 = requests.patch(f"{API}/tv-series/{sid}", json={"description": "upd"}, headers=H, timeout=15)
        assert p2.status_code == 200

        # delete series cascades
        d = requests.delete(f"{API}/tv-series/{sid}", headers=H, timeout=15)
        assert d.status_code == 200
        reg["tv_series_ids"].remove(sid)


# ─── Default lists filter out hentai + tv ────────────────────────────────
class TestVideoListingFilters:
    def test_default_videos_excludes_hentai_and_tv(self, db):
        # Insert two synthetic ready videos directly
        hid = f"TEST_h_{uuid.uuid4().hex[:8]}"
        tid = f"TEST_t_{uuid.uuid4().hex[:8]}"
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        docs = []
        for vid, flag in [(hid, "is_hentai"), (tid, "is_tv")]:
            d = {
                "id": vid, "title": vid, "slug": vid,
                "uploader_id": "x", "uploader_username": "x",
                "status": "ready", "access_tier": "free",
                "is_short": False, "is_anime": False,
                "is_hentai": False, "is_tv": False, "is_film_rosub": False,
                flag: True,
                "created_at": now, "updated_at": now, "views": 0, "likes": 0, "dislikes": 0,
                "duration_sec": 0, "renditions": [], "subtitles": [], "tags": [],
            }
            docs.append(d)
        db.videos.insert_many(docs)
        try:
            r = requests.get(f"{API}/videos?limit=200", timeout=15)
            assert r.status_code == 200
            j = r.json()
            items = j["items"] if isinstance(j, dict) and "items" in j else j
            ids = [x["id"] for x in items]
            assert hid not in ids
            assert tid not in ids

            r2 = requests.get(f"{API}/videos?section=popular&limit=200", timeout=15)
            assert r2.status_code == 200
            j2 = r2.json()
            items2 = j2["items"] if isinstance(j2, dict) and "items" in j2 else j2
            ids2 = [x["id"] for x in items2]
            assert hid not in ids2
            assert tid not in ids2
        finally:
            db.videos.delete_many({"id": {"$in": [hid, tid]}})


# ─── PATCH video with hentai/tv season derives series_id ──────────────────
class TestPatchVideoDerivation:
    def test_patch_invalid_season(self, H):
        # Need some existing video to patch — use any ready video, or create a stub as admin.
        r = requests.get(f"{API}/videos?limit=1", timeout=15)
        j = r.json()
        items = j["items"] if isinstance(j, dict) and "items" in j else j
        if not items:
            pytest.skip("no videos available")
        vid = items[0]["id"]
        bad = requests.patch(
            f"{API}/videos/{vid}",
            json={"hentai_season_id": "nonexistent_" + uuid.uuid4().hex},
            headers=H, timeout=15,
        )
        assert bad.status_code == 400
        bad2 = requests.patch(
            f"{API}/videos/{vid}",
            json={"tv_season_id": "nonexistent_" + uuid.uuid4().hex},
            headers=H, timeout=15,
        )
        assert bad2.status_code == 400

    def test_patch_valid_season_sets_series(self, H, reg, db):
        # Create a hentai series + season
        s = requests.post(f"{API}/hentai-series", json={"name": f"TEST_H_{uuid.uuid4().hex[:6]}"}, headers=H, timeout=15).json()
        reg["hentai_series_ids"].append(s["id"])
        se = requests.post(
            f"{API}/hentai-series/{s['id']}/seasons",
            json={"name": "S1", "season_number": 1},
            headers=H, timeout=15,
        ).json()
        reg["hentai_season_ids"].append(se["id"])

        # Create a synthetic video doc owned by admin
        import datetime
        admin = db.users.find_one({"email": ADMIN_EMAIL})
        now = datetime.datetime.now(datetime.timezone.utc)
        vid = f"TEST_v_{uuid.uuid4().hex[:8]}"
        db.videos.insert_one({
            "id": vid, "title": "TEST patch", "slug": vid,
            "uploader_id": admin["id"], "uploader_username": admin.get("username") or "admin",
            "status": "ready", "access_tier": "free",
            "is_short": False, "is_anime": False, "is_hentai": False, "is_tv": False, "is_film_rosub": False,
            "created_at": now, "updated_at": now,
            "views": 0, "likes": 0, "dislikes": 0, "duration_sec": 0,
            "renditions": [], "subtitles": [], "tags": [],
        })
        reg["video_ids"].append(vid)

        p = requests.patch(
            f"{API}/videos/{vid}",
            json={"hentai_season_id": se["id"]},
            headers=H, timeout=15,
        )
        assert p.status_code == 200, p.text
        doc = db.videos.find_one({"id": vid}, {"_id": 0})
        assert doc["hentai_season_id"] == se["id"]
        assert doc["hentai_series_id"] == s["id"]
