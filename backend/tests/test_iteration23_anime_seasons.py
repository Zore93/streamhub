"""
Iteration 23 tests — Anime Seasons layer.

Covers:
- POST /api/anime-series creates a series
- POST /api/anime-series/{sid}/seasons: auto slug (s01, ova-1, movie-1, special-1) and auto title,
  season_type validation (falls back to season for unknown), unique-slug guard,
  auto position from count.
- GET /api/anime-series/{sid}/seasons (public, active-only)
- GET /api/anime-series/{sid}/seasons/all (admin, includes inactive)
- GET /api/anime-seasons/{id_or_slug} returns season + series + sorted episodes
- GET /api/anime-series/{series_slug}/seasons/{season_slug} — 404 if mismatched series
- PATCH /api/anime-seasons/{id}
- DELETE /api/anime-seasons/{id} blocked when episodes exist; allowed when empty
- DELETE /api/anime-series cascades seasons + detaches videos
- PATCH /api/videos/{id} with anime_season_id derives anime_series_id;
  invalid anime_season_id -> 400
- GET /api/anime-series/{k} includes `seasons` and `episodes` (legacy compat)
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
def series(admin_headers, db):
    """Create a fresh series via the API."""
    name = f"TEST_S23_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/anime-series",
                      headers=admin_headers,
                      json={"name": name, "description": "seed", "active": True},
                      timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    yield s
    # teardown — cascade delete removes seasons + detaches videos
    requests.delete(f"{API}/anime-series/{s['id']}", headers=admin_headers, timeout=15)
    # extra safety: remove test-created seasons if series delete somehow left orphans
    db.anime_seasons.delete_many({"series_id": s["id"]})


# ---------- Season creation ----------

def test_create_season_auto_slug_and_title(admin_headers, series):
    r = requests.post(f"{API}/anime-series/{series['id']}/seasons",
                      headers=admin_headers, json={"number": 1}, timeout=15)
    assert r.status_code == 200, r.text
    se = r.json()
    assert se["slug"] == "s01"
    assert se["title"] == "Sezonul 1"
    assert se["season_type"] == "season"
    assert se["position"] == 0  # first one


def test_create_ova_movie_special_auto_slug(admin_headers, series):
    payloads = [
        ({"season_type": "ova", "number": 1}, "ova-1", "OVA 1"),
        ({"season_type": "movie", "number": 1}, "movie-1", "Film 1"),
        ({"season_type": "special", "number": 1}, "special-1", "Special 1"),
    ]
    for payload, expected_slug, expected_title in payloads:
        r = requests.post(f"{API}/anime-series/{series['id']}/seasons",
                          headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        se = r.json()
        assert se["slug"] == expected_slug
        assert se["title"] == expected_title
        assert se["season_type"] == payload["season_type"]


def test_create_season_unknown_type_falls_back_to_season(admin_headers, series):
    r = requests.post(f"{API}/anime-series/{series['id']}/seasons",
                      headers=admin_headers,
                      json={"season_type": "bogus", "number": 2, "slug": "s02-x"},
                      timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["season_type"] == "season"


def test_create_season_duplicate_slug(admin_headers, series):
    r = requests.post(f"{API}/anime-series/{series['id']}/seasons",
                      headers=admin_headers,
                      json={"number": 1, "slug": "s01"}, timeout=15)
    assert r.status_code == 400


def test_create_season_series_not_found(admin_headers):
    r = requests.post(f"{API}/anime-series/does-not-exist/seasons",
                      headers=admin_headers, json={"number": 1}, timeout=15)
    assert r.status_code == 404


# ---------- Listing ----------

def test_list_public_active_only(admin_headers, series, db):
    # mark one season inactive directly
    db.anime_seasons.update_one({"series_id": series["id"], "slug": "ova-1"},
                                {"$set": {"active": False}})
    r = requests.get(f"{API}/anime-series/{series['id']}/seasons", timeout=15)
    assert r.status_code == 200
    slugs = [s["slug"] for s in r.json()]
    assert "s01" in slugs
    assert "ova-1" not in slugs
    for s in r.json():
        assert "episode_count" in s


def test_list_admin_all_includes_inactive(admin_headers, series):
    r = requests.get(f"{API}/anime-series/{series['id']}/seasons/all",
                     headers=admin_headers, timeout=15)
    assert r.status_code == 200
    slugs = [s["slug"] for s in r.json()]
    assert "ova-1" in slugs  # inactive, still visible to admin


def test_list_admin_all_requires_auth(series):
    r = requests.get(f"{API}/anime-series/{series['id']}/seasons/all", timeout=15)
    assert r.status_code in (401, 403)


# ---------- Get by id/slug + pair ----------

def test_get_season_by_id_and_slug(series, db):
    se_doc = db.anime_seasons.find_one({"series_id": series["id"], "slug": "s01"})
    for key in (se_doc["id"], se_doc["slug"]):
        r = requests.get(f"{API}/anime-seasons/{key}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slug"] == "s01"
        assert d["series"]["id"] == series["id"]
        assert "episodes" in d and isinstance(d["episodes"], list)
        assert "episode_count" in d


def test_get_season_by_pair_ok_and_mismatch(admin_headers, series):
    # good pair
    r = requests.get(f"{API}/anime-series/{series['slug']}/seasons/s01", timeout=15)
    assert r.status_code == 200

    # Create a second series with a season using the SAME slug 's01', then
    # verify the pair endpoint refuses to cross series boundaries.
    r2 = requests.post(f"{API}/anime-series", headers=admin_headers,
                       json={"name": f"TEST_S23B_{uuid.uuid4().hex[:6]}"}, timeout=15)
    other = r2.json()
    try:
        r3 = requests.post(f"{API}/anime-series/{other['id']}/seasons",
                           headers=admin_headers, json={"number": 1}, timeout=15)
        assert r3.status_code == 200

        # Requesting other-series with a season that doesn't belong to it:
        # but s01 exists in BOTH — instead use a slug that exists only in `series`.
        r4 = requests.get(f"{API}/anime-series/{other['slug']}/seasons/ova-1", timeout=15)
        assert r4.status_code == 404
    finally:
        requests.delete(f"{API}/anime-series/{other['id']}", headers=admin_headers, timeout=15)


# ---------- PATCH ----------

def test_patch_season(admin_headers, series, db):
    se = db.anime_seasons.find_one({"series_id": series["id"], "slug": "s02-x"})
    r = requests.patch(f"{API}/anime-seasons/{se['id']}",
                       headers=admin_headers,
                       json={"title": "Renamed S2", "year": 2024, "active": True},
                       timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["title"] == "Renamed S2"
    assert d["year"] == 2024


def test_patch_slug_collision(admin_headers, series, db):
    se = db.anime_seasons.find_one({"series_id": series["id"], "slug": "s02-x"})
    r = requests.patch(f"{API}/anime-seasons/{se['id']}",
                       headers=admin_headers, json={"slug": "s01"}, timeout=15)
    assert r.status_code == 400


# ---------- Season delete guard ----------

def test_delete_season_blocked_when_has_episodes(admin_headers, series, db):
    se = db.anime_seasons.find_one({"series_id": series["id"], "slug": "s01"})
    fake_vid = {
        "id": f"TEST_v_{uuid.uuid4().hex[:6]}",
        "title": "ep", "status": "ready",
        "anime_season_id": se["id"], "anime_series_id": series["id"],
        "is_anime": True, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.videos.insert_one(fake_vid)
    try:
        r = requests.delete(f"{API}/anime-seasons/{se['id']}",
                            headers=admin_headers, timeout=15)
        assert r.status_code == 400
    finally:
        db.videos.delete_one({"id": fake_vid["id"]})

    # Now it's empty → delete should succeed
    r2 = requests.delete(f"{API}/anime-seasons/{se['id']}",
                         headers=admin_headers, timeout=15)
    assert r2.status_code == 200
    # Confirm gone
    assert db.anime_seasons.find_one({"id": se["id"]}) is None


# ---------- PATCH video derives series from season ----------

def test_patch_video_derives_series_from_season(admin_headers, series, db):
    # Ensure we have a season to attach to
    se = db.anime_seasons.find_one({"series_id": series["id"], "slug": "movie-1"})
    assert se
    # Create a plain non-anime video directly
    vid = {
        "id": f"TEST_v_{uuid.uuid4().hex[:6]}",
        "title": "ep-x", "status": "ready", "is_anime": False,
        "uploader_id": "admin", "uploader_username": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.videos.insert_one(vid)
    try:
        r = requests.patch(f"{API}/videos/{vid['id']}",
                           headers=admin_headers,
                           json={"is_anime": True, "anime_season_id": se["id"]},
                           timeout=15)
        assert r.status_code == 200, r.text
        db_vid = db.videos.find_one({"id": vid["id"]})
        assert db_vid.get("anime_season_id") == se["id"]
        assert db_vid.get("anime_series_id") == series["id"]

        # Invalid anime_season_id -> 400
        r2 = requests.patch(f"{API}/videos/{vid['id']}",
                            headers=admin_headers,
                            json={"anime_season_id": "does-not-exist"}, timeout=15)
        assert r2.status_code == 400
    finally:
        db.videos.delete_one({"id": vid["id"]})


# ---------- Series get includes both seasons + episodes ----------

def test_get_series_includes_seasons_and_episodes(series):
    r = requests.get(f"{API}/anime-series/{series['slug']}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "seasons" in d and isinstance(d["seasons"], list)
    assert "episodes" in d and isinstance(d["episodes"], list)
    for s in d["seasons"]:
        assert "episode_count" in s


# ---------- Cascade delete ----------

def test_delete_series_cascade(admin_headers, db):
    r = requests.post(f"{API}/anime-series", headers=admin_headers,
                      json={"name": f"TEST_S23C_{uuid.uuid4().hex[:6]}"}, timeout=15)
    s = r.json()
    # Create a season
    rs = requests.post(f"{API}/anime-series/{s['id']}/seasons",
                       headers=admin_headers, json={"number": 1}, timeout=15)
    se = rs.json()
    # Attach a video directly
    vid = {
        "id": f"TEST_v_{uuid.uuid4().hex[:6]}",
        "title": "ep-c", "status": "ready", "is_anime": True,
        "anime_series_id": s["id"], "anime_season_id": se["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.videos.insert_one(vid)
    try:
        r2 = requests.delete(f"{API}/anime-series/{s['id']}",
                             headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        # Season cascaded
        assert db.anime_seasons.find_one({"id": se["id"]}) is None
        # Video detached
        v = db.videos.find_one({"id": vid["id"]})
        assert v["is_anime"] is False
        assert v.get("anime_series_id") is None
        assert v.get("anime_season_id") is None
    finally:
        db.videos.delete_one({"id": vid["id"]})
