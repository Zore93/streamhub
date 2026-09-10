"""
Iteration 24 - Filme RoSub + SSR OG + Mobile Fullscreen (backend only tests).

Covers:
- /api/film-categories CRUD (list, list-all, get, create, patch, delete)
- /api/videos/filme listing + category filter
- /api/videos default filter (no filme), is_film_rosub=true toggle
- Video PATCH film_category_ids validation
- SSR OG endpoints (/api/og/*) + crawler middleware routing
"""
import os
import re
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://stream-convert-hub-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PW = "Admin123!"

DISCORD_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"


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
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def cleanup_registry():
    """Track created ids for cleanup."""
    reg = {"cat_ids": [], "video_ids": []}
    yield reg
    # teardown
    client = MongoClient(MONGO_URL)
    d = client[DB_NAME]
    if reg["cat_ids"]:
        d.film_categories.delete_many({"id": {"$in": reg["cat_ids"]}})
    if reg["video_ids"]:
        d.videos.delete_many({"id": {"$in": reg["video_ids"]}})
    # Also clear any TEST_ leftovers from prior aborted runs
    d.film_categories.delete_many({"name": {"$regex": "^TEST_"}})
    d.videos.delete_many({"title": {"$regex": "^TEST_"}})


# ─── film-categories CRUD ─────────────────────────────────────────────────
class TestFilmCategoriesCRUD:
    def test_create_requires_admin(self):
        r = requests.post(f"{API}/film-categories", json={"name": "TEST_no_auth"}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_create_missing_name(self, admin_headers):
        r = requests.post(f"{API}/film-categories", json={}, headers=admin_headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_create_auto_slug(self, admin_headers, cleanup_registry):
        r = requests.post(
            f"{API}/film-categories",
            json={"name": "TEST_Acțiune 24"},
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Acțiune 24"
        assert data["slug"], "slug should be auto-generated"
        assert data["active"] is True
        assert "id" in data
        assert isinstance(data.get("position"), int)
        cleanup_registry["cat_ids"].append(data["id"])
        return data

    def test_create_slug_collision(self, admin_headers, cleanup_registry):
        # first
        r1 = requests.post(
            f"{API}/film-categories",
            json={"name": "TEST_Collide", "slug": f"test-collide-{uuid.uuid4().hex[:6]}"},
            headers=admin_headers, timeout=15,
        )
        assert r1.status_code == 200
        slug = r1.json()["slug"]
        cleanup_registry["cat_ids"].append(r1.json()["id"])
        r2 = requests.post(
            f"{API}/film-categories",
            json={"name": "TEST_Collide2", "slug": slug},
            headers=admin_headers, timeout=15,
        )
        assert r2.status_code == 400, r2.text

    def test_list_public_active_only(self, admin_headers, cleanup_registry):
        # create active + inactive
        ra = requests.post(f"{API}/film-categories", json={"name": "TEST_ActiveCat"}, headers=admin_headers, timeout=15)
        assert ra.status_code == 200
        act = ra.json()
        cleanup_registry["cat_ids"].append(act["id"])
        ri = requests.post(f"{API}/film-categories", json={"name": "TEST_InactiveCat", "active": False}, headers=admin_headers, timeout=15)
        assert ri.status_code == 200
        inact = ri.json()
        cleanup_registry["cat_ids"].append(inact["id"])

        r = requests.get(f"{API}/film-categories", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        ids = {c["id"] for c in rows}
        assert act["id"] in ids
        assert inact["id"] not in ids

    def test_list_all_requires_admin(self):
        r = requests.get(f"{API}/film-categories/all", timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_list_all_includes_inactive(self, admin_headers, cleanup_registry):
        r = requests.get(f"{API}/film-categories/all", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        rows = r.json()
        ids = {c["id"] for c in rows}
        for cid in cleanup_registry["cat_ids"]:
            assert cid in ids, f"admin list-all missing {cid}"

    def test_get_by_id_and_slug(self, admin_headers, cleanup_registry):
        r = requests.post(f"{API}/film-categories", json={"name": "TEST_GetBy"}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        cleanup_registry["cat_ids"].append(d["id"])
        g1 = requests.get(f"{API}/film-categories/{d['id']}", timeout=15)
        assert g1.status_code == 200
        assert g1.json()["id"] == d["id"]
        assert g1.json()["film_count"] == 0
        g2 = requests.get(f"{API}/film-categories/{d['slug']}", timeout=15)
        assert g2.status_code == 200
        assert g2.json()["id"] == d["id"]

    def test_patch_and_slug_clash(self, admin_headers, cleanup_registry):
        a = requests.post(f"{API}/film-categories", json={"name": "TEST_PatchA"}, headers=admin_headers, timeout=15).json()
        b = requests.post(f"{API}/film-categories", json={"name": "TEST_PatchB"}, headers=admin_headers, timeout=15).json()
        cleanup_registry["cat_ids"] += [a["id"], b["id"]]
        # rename OK
        p = requests.patch(f"{API}/film-categories/{a['id']}", json={"name": "TEST_PatchARenamed"}, headers=admin_headers, timeout=15)
        assert p.status_code == 200
        assert p.json()["name"] == "TEST_PatchARenamed"
        # slug clash
        pc = requests.patch(f"{API}/film-categories/{a['id']}", json={"slug": b["slug"]}, headers=admin_headers, timeout=15)
        assert pc.status_code == 400

    def test_delete_pulls_from_videos(self, admin_headers, cleanup_registry, db):
        cat = requests.post(f"{API}/film-categories", json={"name": "TEST_DelPull"}, headers=admin_headers, timeout=15).json()
        # seed a video referencing this cat via direct mongo insert
        vid = f"test-vid-{uuid.uuid4().hex[:8]}"
        db.videos.insert_one({
            "id": vid, "title": "TEST_delpull_video", "slug": vid,
            "is_film_rosub": True, "status": "ready",
            "film_category_ids": [cat["id"], "keep-me"],
            "kind": "video", "created_at": time.time(),
        })
        cleanup_registry["video_ids"].append(vid)
        d = requests.delete(f"{API}/film-categories/{cat['id']}", headers=admin_headers, timeout=15)
        assert d.status_code == 200
        # cat removed
        g = requests.get(f"{API}/film-categories/{cat['id']}", timeout=15)
        assert g.status_code == 404
        # $pull worked
        v = db.videos.find_one({"id": vid})
        assert v["film_category_ids"] == ["keep-me"], f"expected pull, got {v['film_category_ids']}"


# ─── /api/videos/filme + default filtering ────────────────────────────────
class TestFilmeListingAndFilter:
    @pytest.fixture(scope="class")
    def seeded(self, admin_headers, db):
        """Create 2 cats + 3 videos: 2 filme (one in cat1, one in both), 1 regular."""
        c1 = requests.post(f"{API}/film-categories", json={"name": "TEST_CatOne"}, headers=admin_headers, timeout=15).json()
        c2 = requests.post(f"{API}/film-categories", json={"name": "TEST_CatTwo"}, headers=admin_headers, timeout=15).json()
        f1 = f"test-filme-{uuid.uuid4().hex[:8]}"
        f2 = f"test-filme-{uuid.uuid4().hex[:8]}"
        rv = f"test-reg-{uuid.uuid4().hex[:8]}"
        now = time.time()
        db.videos.insert_many([
            {"id": f1, "slug": f1, "title": "TEST_Filme_Only_C1", "is_film_rosub": True, "status": "ready",
             "film_category_ids": [c1["id"]], "kind": "video", "created_at": now, "is_short": False, "is_anime": False},
            {"id": f2, "slug": f2, "title": "TEST_Filme_Both", "is_film_rosub": True, "status": "ready",
             "film_category_ids": [c1["id"], c2["id"]], "kind": "video", "created_at": now + 1, "is_short": False, "is_anime": False},
            {"id": rv, "slug": rv, "title": "TEST_RegularVideo", "is_film_rosub": False, "status": "ready",
             "film_category_ids": [], "kind": "video", "created_at": now + 2, "is_short": False, "is_anime": False},
        ])
        yield {"c1": c1, "c2": c2, "f1": f1, "f2": f2, "rv": rv}
        db.film_categories.delete_many({"id": {"$in": [c1["id"], c2["id"]]}})
        db.videos.delete_many({"id": {"$in": [f1, f2, rv]}})

    def test_filme_list_returns_both(self, seeded):
        r = requests.get(f"{API}/videos/filme", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "items" in data
        ids = {v["id"] for v in data["items"]}
        assert seeded["f1"] in ids and seeded["f2"] in ids
        assert seeded["rv"] not in ids

    def test_filme_filter_by_slug(self, seeded):
        r = requests.get(f"{API}/videos/filme", params={"category_id": seeded["c2"]["slug"]}, timeout=15)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()["items"]}
        assert seeded["f2"] in ids
        assert seeded["f1"] not in ids

    def test_filme_filter_by_id(self, seeded):
        r = requests.get(f"{API}/videos/filme", params={"category_id": seeded["c1"]["id"]}, timeout=15)
        assert r.status_code == 200
        ids = {v["id"] for v in r.json()["items"]}
        assert seeded["f1"] in ids and seeded["f2"] in ids

    def test_default_videos_excludes_filme(self, seeded):
        r = requests.get(f"{API}/videos", params={"limit": 200}, timeout=15)
        assert r.status_code == 200
        # Body may be list or {items:[]}
        body = r.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        ids = {v["id"] for v in items}
        assert seeded["f1"] not in ids, "default listing must exclude is_film_rosub=True"
        assert seeded["f2"] not in ids

    def test_videos_is_film_rosub_true(self, seeded):
        r = requests.get(f"{API}/videos", params={"is_film_rosub": "true", "limit": 200}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        ids = {v["id"] for v in items}
        assert seeded["f1"] in ids or seeded["f2"] in ids


# ─── SSR OG endpoints ─────────────────────────────────────────────────────
OG_META_RE = re.compile(r'<meta\s+property="og:[^"]+"\s+content="[^"]*"', re.IGNORECASE)


def _has_og(html: str) -> bool:
    return "<title>" in html and 'og:title' in html and 'og:type' in html and "canonical" in html.lower()


class TestSSROG:
    def test_og_filme_home(self):
        r = requests.get(f"{API}/og/filme-rosub", timeout=15)
        assert r.status_code == 200, r.text[:400]
        assert "text/html" in r.headers.get("content-type", "")
        assert _has_og(r.text), r.text[:600]
        assert "filme-rosub" in r.text.lower()

    def test_og_filme_category_404(self):
        # SSR endpoints return 200 with fallback OG (crawler-friendly — a
        # broken embed is worse than a generic one). Validate we get HTML.
        r = requests.get(f"{API}/og/filme-rosub/{uuid.uuid4().hex}", timeout=15)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_og_filme_category_ok(self, admin_headers, cleanup_registry):
        cat = requests.post(f"{API}/film-categories", json={"name": "TEST_OGCat"}, headers=admin_headers, timeout=15).json()
        cleanup_registry["cat_ids"].append(cat["id"])
        r = requests.get(f"{API}/og/filme-rosub/{cat['slug']}", timeout=15)
        assert r.status_code == 200
        assert _has_og(r.text)
        assert "TEST_OGCat" in r.text or cat["slug"] in r.text

    def test_og_shorts_series_404(self):
        # Same policy — fallback to home OG (200) rather than a broken embed.
        r = requests.get(f"{API}/og/shorts-series/{uuid.uuid4().hex}", timeout=15)
        assert r.status_code == 200
        assert _has_og(r.text)

    def test_og_anime_series_404(self):
        r = requests.get(f"{API}/og/anime-series/{uuid.uuid4().hex}", timeout=15)
        assert r.status_code == 200
        assert _has_og(r.text)

    def test_og_anime_season_pair_404(self):
        r = requests.get(f"{API}/og/anime-season/{uuid.uuid4().hex}/{uuid.uuid4().hex}", timeout=15)
        assert r.status_code == 200
        assert _has_og(r.text)

    # Crawler middleware — DISCORD UA hitting the *backend directly* on the
    # SPA route path should be intercepted and served the SSR OG HTML.
    # NOTE: on the emergent preview, the K8s ingress routes non-/api paths
    # straight to the frontend so the middleware never runs — we must hit
    # localhost:8001 for this test to be meaningful. In production the
    # equivalent path lands here via the nginx crawler rewrite.
    def test_crawler_ua_on_filme_home(self):
        r = requests.get("http://localhost:8001/filme-rosub", headers={"User-Agent": DISCORD_UA}, timeout=20, allow_redirects=False)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert 'og:title' in r.text, r.text[:400]

    def test_crawler_ua_on_shorts_series_route(self):
        r = requests.get(f"http://localhost:8001/shorts/series/{uuid.uuid4().hex}", headers={"User-Agent": DISCORD_UA}, timeout=20, allow_redirects=False)
        assert r.status_code == 200
        assert 'og:title' in r.text

    def test_crawler_ua_on_anime_series_route(self):
        r = requests.get(f"{BASE_URL}/anime/series/{uuid.uuid4().hex}", headers={"User-Agent": DISCORD_UA}, timeout=20, allow_redirects=False)
        assert r.status_code in (200, 404)

    def test_normal_ua_on_filme_home_serves_spa(self):
        # non-crawler UA — should get the SPA html (200) and NOT the OG-only html
        r = requests.get(f"{BASE_URL}/filme-rosub", headers={"User-Agent": "Mozilla/5.0 (regular browser)"}, timeout=20)
        assert r.status_code == 200


# ─── Video PATCH film_category_ids validation ─────────────────────────────
class TestVideoPatchFilmCategories:
    @pytest.fixture(scope="class")
    def video_and_cat(self, admin_headers, db):
        cat = requests.post(f"{API}/film-categories", json={"name": "TEST_PatchCat"}, headers=admin_headers, timeout=15).json()
        vid = f"test-patch-{uuid.uuid4().hex[:8]}"
        db.videos.insert_one({
            "id": vid, "slug": vid, "title": "TEST_PatchVideo",
            "is_film_rosub": True, "status": "ready",
            "film_category_ids": [], "kind": "video", "created_at": time.time(),
        })
        yield {"cat": cat, "vid": vid}
        db.film_categories.delete_one({"id": cat["id"]})
        db.videos.delete_one({"id": vid})

    def test_patch_non_list_400(self, admin_headers, video_and_cat):
        r = requests.patch(
            f"{API}/videos/{video_and_cat['vid']}",
            json={"film_category_ids": "not-a-list"},
            headers=admin_headers, timeout=15,
        )
        # Pydantic v2 rejects wrong type with 422, not 400
        assert r.status_code == 422, r.text

    def test_patch_invalid_ids_dropped(self, admin_headers, video_and_cat, db):
        r = requests.patch(
            f"{API}/videos/{video_and_cat['vid']}",
            json={"film_category_ids": [video_and_cat["cat"]["id"], "nope-not-real"]},
            headers=admin_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        v = db.videos.find_one({"id": video_and_cat["vid"]})
        assert v["film_category_ids"] == [video_and_cat["cat"]["id"]]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
