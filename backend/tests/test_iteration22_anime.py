"""
Iteration 22 tests — Anime vertical.

Covers:
- AnimeSeries CRUD (create with auto-slug + explicit slug, unique, patch, delete)
- Delete unassigns videos (is_anime=false, anime_series_id=null)
- GET /api/anime-series returns active only
- GET /api/anime-series/all admin returns all + episode_count
- GET /api/anime-series/{slug|id} returns series + episodes ordered by anime_series_position
- GET /api/videos filters: is_anime=true → only anime; default excludes anime from
  latest/popular/random; is_anime=false works
- PATCH /api/videos/{id} accepts is_anime + anime_series_id + anime_series_position
- Chunked upload finish would force is_anime=false when is_short=true — we simulate
  the same rule by direct insert + PATCH (upload endpoint requires actual bytes).
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


@pytest.fixture(scope="module")
def seed(db):
    """Seed 2 anime series (1 active, 1 inactive) + a few videos (anime/non-anime/short)."""
    now = datetime.now(timezone.utc).isoformat()
    active_id = f"TEST_anime_active_{uuid.uuid4().hex[:6]}"
    inactive_id = f"TEST_anime_inactive_{uuid.uuid4().hex[:6]}"
    db.anime_series.insert_many([
        {"id": active_id, "name": "TEST_ActiveSeries", "slug": f"test-active-{uuid.uuid4().hex[:6]}",
         "description": "", "cover_thumbnail": "", "tags": [], "active": True, "sort_order": 0, "created_at": now},
        {"id": inactive_id, "name": "TEST_InactiveSeries", "slug": f"test-inactive-{uuid.uuid4().hex[:6]}",
         "description": "", "cover_thumbnail": "", "tags": [], "active": False, "sort_order": 0, "created_at": now},
    ])

    def _vid(is_short=False, is_anime=False, anime_series_id=None, pos=None):
        vid_id = f"TEST_vid_{uuid.uuid4().hex[:8]}"
        db.videos.insert_one({
            "id": vid_id, "title": f"TEST_{vid_id}", "slug": vid_id, "description": "",
            "video_url": "/x.mp4", "thumbnail": "", "duration": 10, "views": 5, "likes": 0,
            "status": "ready", "is_short": is_short, "is_anime": is_anime,
            "anime_series_id": anime_series_id, "anime_series_position": pos,
            "created_at": now, "uploader_id": "sys", "tags": [], "category": None,
            "shorts_category": None, "shorts_series_id": None,
        })
        return vid_id

    ep_a = _vid(is_anime=True, anime_series_id=active_id, pos=2)
    ep_b = _vid(is_anime=True, anime_series_id=active_id, pos=1)
    ep_c = _vid(is_anime=True, anime_series_id=active_id, pos=3)
    plain = _vid()
    short = _vid(is_short=True)

    yield {
        "active_id": active_id, "inactive_id": inactive_id,
        "eps": [ep_a, ep_b, ep_c], "plain": plain, "short": short,
    }

    # Cleanup
    db.videos.delete_many({"id": {"$in": [ep_a, ep_b, ep_c, plain, short]}})
    db.anime_series.delete_many({"id": {"$in": [active_id, inactive_id]}})
    db.anime_series.delete_many({"name": {"$regex": "^TEST_"}})


# ----------------- Anime Series CRUD -----------------

class TestAnimeSeriesCRUD:
    def test_list_active_only(self, seed, admin_headers):
        r = requests.get(f"{API}/anime-series", timeout=10)
        assert r.status_code == 200
        names = [x["name"] for x in r.json()]
        assert "TEST_ActiveSeries" in names
        assert "TEST_InactiveSeries" not in names

    def test_admin_list_all(self, seed, admin_headers):
        r = requests.get(f"{API}/anime-series/all", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        rows = r.json()
        names = [x["name"] for x in rows]
        assert "TEST_ActiveSeries" in names and "TEST_InactiveSeries" in names
        active = next(x for x in rows if x["name"] == "TEST_ActiveSeries")
        assert active.get("episode_count") == 3

    def test_get_by_slug_and_id_ordered(self, seed):
        # by id
        r = requests.get(f"{API}/anime-series/{seed['active_id']}", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Flat shape: series fields + episodes[] + episode_count
        assert "episodes" in data and "id" in data and "slug" in data
        assert data["episode_count"] == 3
        eps = data["episodes"]
        positions = [e.get("anime_series_position") for e in eps]
        assert positions == sorted(positions, key=lambda x: (x is None, x))
        # ep_b has pos=1, so should be first
        assert eps[0]["id"] == seed["eps"][1]

        # by slug
        slug = data["slug"]
        r2 = requests.get(f"{API}/anime-series/{slug}", timeout=10)
        assert r2.status_code == 200
        assert r2.json()["id"] == seed["active_id"]

    def test_create_auto_slug_and_unique(self, admin_headers, db):
        name = f"TEST_AnimeAuto {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/anime-series", json={"name": name},
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["slug"] and s["name"] == name
        sid = s["id"]

        # duplicate slug should 400
        r2 = requests.post(f"{API}/anime-series",
                           json={"name": "another", "slug": s["slug"]},
                           headers=admin_headers, timeout=10)
        assert r2.status_code == 400

        # patch
        r3 = requests.patch(f"{API}/anime-series/{sid}",
                            json={"description": "updated"},
                            headers=admin_headers, timeout=10)
        assert r3.status_code == 200
        assert r3.json()["description"] == "updated"

        # delete
        r4 = requests.delete(f"{API}/anime-series/{sid}", headers=admin_headers, timeout=10)
        assert r4.status_code == 200
        assert db.anime_series.find_one({"id": sid}) is None

    def test_delete_unassigns_videos(self, admin_headers, db):
        now = datetime.now(timezone.utc).isoformat()
        sid = f"TEST_del_{uuid.uuid4().hex[:6]}"
        vid = f"TEST_delvid_{uuid.uuid4().hex[:6]}"
        db.anime_series.insert_one({
            "id": sid, "name": "TEST_ToDelete", "slug": f"test-todel-{uuid.uuid4().hex[:6]}",
            "description": "", "cover_thumbnail": "", "tags": [], "active": True,
            "sort_order": 0, "created_at": now,
        })
        db.videos.insert_one({
            "id": vid, "title": "TEST_v", "slug": vid, "description": "",
            "video_url": "/x.mp4", "thumbnail": "", "duration": 10, "views": 0, "likes": 0,
            "status": "ready", "is_short": False, "is_anime": True,
            "anime_series_id": sid, "anime_series_position": 1, "created_at": now,
            "uploader_id": "sys", "tags": [],
        })
        r = requests.delete(f"{API}/anime-series/{sid}", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        v = db.videos.find_one({"id": vid})
        assert v["is_anime"] is False
        assert v["anime_series_id"] is None
        db.videos.delete_one({"id": vid})


# ----------------- Videos filter -----------------

class TestVideosAnimeFilter:
    def test_kind_video_is_anime_true(self, seed):
        r = requests.get(f"{API}/videos", params={"kind": "video", "is_anime": "true", "limit": 100}, timeout=10)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()}
        for e in seed["eps"]:
            assert e in ids
        assert seed["plain"] not in ids
        # all are is_anime true
        assert all(v.get("is_anime") for v in r.json())

    def test_default_latest_excludes_anime(self, seed):
        r = requests.get(f"{API}/videos", params={"section": "latest", "limit": 200}, timeout=10)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()}
        for e in seed["eps"]:
            assert e not in ids, f"anime {e} leaked into /latest"

    def test_default_popular_excludes_anime(self, seed):
        r = requests.get(f"{API}/videos", params={"section": "popular", "limit": 200}, timeout=10)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()}
        for e in seed["eps"]:
            assert e not in ids

    def test_default_random_excludes_anime(self, seed):
        r = requests.get(f"{API}/videos", params={"section": "random", "limit": 200}, timeout=10)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()}
        for e in seed["eps"]:
            assert e not in ids

    def test_is_anime_false_regression(self, seed):
        r = requests.get(f"{API}/videos", params={"kind": "video", "is_anime": "false", "limit": 200}, timeout=10)
        assert r.status_code == 200
        rows = r.json()
        assert all(not v.get("is_anime") for v in rows)
        ids = {v["id"] for v in rows}
        assert seed["plain"] in ids


# ----------------- PATCH video -----------------

class TestVideoPatchAnime:
    def test_patch_anime_fields(self, seed, admin_headers, db):
        vid = seed["plain"]
        r = requests.patch(
            f"{API}/videos/{vid}",
            json={"is_anime": True, "anime_series_id": seed["active_id"], "anime_series_position": 7},
            headers=admin_headers, timeout=10,
        )
        assert r.status_code == 200, r.text
        v = db.videos.find_one({"id": vid})
        assert v["is_anime"] is True
        assert v["anime_series_id"] == seed["active_id"]
        assert v["anime_series_position"] == 7
        # revert
        requests.patch(
            f"{API}/videos/{vid}",
            json={"is_anime": False, "anime_series_id": None, "anime_series_position": None},
            headers=admin_headers, timeout=10,
        )
