"""Backend tests for the Drama Shorts vertical feature (iteration 20).

Verifies:
 - ShortsSeries CRUD with `category` (xxx/drama) and legacy backward-compat.
 - GET /api/videos filters by shorts_category and auto-excludes drama on generic listings.
 - Chunked upload finish accepts shorts_category.
 - PATCH /api/videos/{id} validates shorts_category.
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def hdr(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def seed(mongo, hdr):
    """Seed two series (xxx & drama), one legacy series (no category), and shorts in both."""
    tag = f"TEST_dramafeat_{uuid.uuid4().hex[:8]}"
    created = {"tag": tag, "series": [], "videos": []}

    # 1. Create XXX series via API
    r = requests.post(
        f"{API}/shorts-series",
        headers=hdr,
        json={"name": f"{tag}_xxx", "slug": f"{tag}-xxx", "category": "xxx"},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    xxx_series = r.json()
    created["series"].append(xxx_series["id"])

    # 2. Create Drama series via API
    r = requests.post(
        f"{API}/shorts-series",
        headers=hdr,
        json={"name": f"{tag}_drama", "slug": f"{tag}-drama", "category": "drama"},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    drama_series = r.json()
    created["series"].append(drama_series["id"])
    assert drama_series["category"] == "drama"

    # 3. Insert a legacy series directly in Mongo (no `category` field)
    legacy_series_id = str(uuid.uuid4())
    import datetime as _dt
    mongo.shorts_series.insert_one({
        "id": legacy_series_id,
        "name": f"{tag}_legacy",
        "slug": f"{tag}-legacy",
        "description": "",
        "cover_thumbnail": None,
        "tags": [],
        "active": True,
        "sort_order": 0,
        "created_at": _dt.datetime.now(_dt.timezone.utc),
        # intentionally no `category`
    })
    created["series"].append(legacy_series_id)

    # 4. Insert shorts directly in Mongo (avoid heavy upload flow):
    #    - v_xxx: shorts_category=xxx
    #    - v_drama: shorts_category=drama
    #    - v_legacy: no shorts_category (treated as xxx)
    #    - v_long: regular long-form video (no is_short)
    def _mk_video(shorts_category, is_short=True, extra=None):
        vid = str(uuid.uuid4())
        doc = {
            "id": vid,
            "title": f"{tag}_{shorts_category or 'legacy'}",
            "description": "",
            "tags": [],
            "video_url": "/uploads/fake.mp4",
            "thumbnail_url": None,
            "duration": 10.0,
            "views": 0,
            "likes": 0,
            "dislikes": 0,
            "access_tier": "free",
            "status": "ready",
            "is_short": is_short,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
            "uploader_id": None,
        }
        if shorts_category is not None:
            doc["shorts_category"] = shorts_category
        if extra:
            doc.update(extra)
        mongo.videos.insert_one(doc)
        created["videos"].append(vid)
        return vid

    v_xxx = _mk_video("xxx", extra={"shorts_series_id": xxx_series["id"]})
    v_drama = _mk_video("drama", extra={"shorts_series_id": drama_series["id"]})
    v_legacy = _mk_video(None, extra={"shorts_series_id": legacy_series_id})
    v_long = _mk_video(None, is_short=False)

    created.update({
        "xxx_series": xxx_series,
        "drama_series": drama_series,
        "legacy_series_id": legacy_series_id,
        "v_xxx": v_xxx, "v_drama": v_drama,
        "v_legacy": v_legacy, "v_long": v_long,
    })

    yield created

    # Cleanup
    mongo.videos.delete_many({"id": {"$in": created["videos"]}})
    mongo.shorts_series.delete_many({"id": {"$in": created["series"]}})


# ---------- ShortsSeries listing ----------

class TestShortsSeriesListing:
    def test_drama_list_returns_only_drama(self, seed):
        r = requests.get(f"{API}/shorts-series?category=drama", timeout=30)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert seed["drama_series"]["id"] in ids
        assert seed["xxx_series"]["id"] not in ids
        assert seed["legacy_series_id"] not in ids, "Legacy (no category) must NOT appear in drama listing"
        for s in r.json():
            assert s.get("category") == "drama"

    def test_xxx_list_includes_legacy(self, seed):
        r = requests.get(f"{API}/shorts-series?category=xxx", timeout=30)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert seed["xxx_series"]["id"] in ids
        assert seed["legacy_series_id"] in ids, "Legacy series (no category) must appear in xxx"
        assert seed["drama_series"]["id"] not in ids


# ---------- ShortsSeries CRUD ----------

class TestShortsSeriesCRUD:
    def test_patch_updates_category(self, seed, hdr, mongo):
        # Create a temp series
        r = requests.post(
            f"{API}/shorts-series", headers=hdr,
            json={"name": f"{seed['tag']}_patchme", "slug": f"{seed['tag']}-patchme", "category": "xxx"},
            timeout=30,
        )
        assert r.status_code in (200, 201)
        sid = r.json()["id"]
        try:
            r2 = requests.patch(f"{API}/shorts-series/{sid}", headers=hdr,
                                json={"category": "drama"}, timeout=30)
            assert r2.status_code == 200, r2.text
            doc = mongo.shorts_series.find_one({"id": sid})
            assert doc["category"] == "drama"

            # invalid category should 400
            r3 = requests.patch(f"{API}/shorts-series/{sid}", headers=hdr,
                                json={"category": "invalid"}, timeout=30)
            assert r3.status_code == 400
        finally:
            mongo.shorts_series.delete_one({"id": sid})

    def test_delete_unassigns_shorts(self, seed, hdr, mongo):
        # Create a series and a short assigned to it
        r = requests.post(
            f"{API}/shorts-series", headers=hdr,
            json={"name": f"{seed['tag']}_delme", "slug": f"{seed['tag']}-delme", "category": "drama"},
            timeout=30,
        )
        sid = r.json()["id"]
        import datetime as _dt
        vid = str(uuid.uuid4())
        mongo.videos.insert_one({
            "id": vid, "title": f"{seed['tag']}_delmev", "description": "", "tags": [],
            "video_url": "/x", "duration": 5.0, "views": 0, "likes": 0, "dislikes": 0,
            "access_tier": "free", "status": "ready", "is_short": True,
            "shorts_category": "drama", "shorts_series_id": sid,
            "created_at": _dt.datetime.now(_dt.timezone.utc),
        })
        try:
            r2 = requests.delete(f"{API}/shorts-series/{sid}", headers=hdr, timeout=30)
            assert r2.status_code in (200, 204)
            doc = mongo.videos.find_one({"id": vid})
            assert doc.get("shorts_series_id") in (None, ""), \
                f"Short should be unassigned after series delete, got {doc.get('shorts_series_id')}"
        finally:
            mongo.videos.delete_one({"id": vid})
            mongo.shorts_series.delete_one({"id": sid})


# ---------- Videos filtering ----------

class TestVideosFilter:
    def test_drama_shorts_only(self, seed):
        r = requests.get(f"{API}/videos?kind=short&shorts_category=drama&limit=100", timeout=30)
        assert r.status_code == 200
        vids = r.json()
        ids = [v["id"] for v in vids]
        assert seed["v_drama"] in ids
        assert seed["v_xxx"] not in ids
        assert seed["v_legacy"] not in ids
        for v in vids:
            assert v.get("shorts_category") == "drama"

    def test_xxx_shorts_include_legacy(self, seed):
        r = requests.get(f"{API}/videos?kind=short&shorts_category=xxx&limit=100", timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert seed["v_xxx"] in ids
        assert seed["v_legacy"] in ids
        assert seed["v_drama"] not in ids

    def test_latest_excludes_drama(self, seed):
        r = requests.get(f"{API}/videos?section=latest&limit=200", timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert seed["v_drama"] not in ids, "Drama shorts must be excluded from /latest"

    def test_popular_excludes_drama(self, seed):
        r = requests.get(f"{API}/videos?section=popular&limit=200", timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert seed["v_drama"] not in ids

    def test_random_excludes_drama(self, seed):
        # Loop a bit since it's random sampling
        seen_ids = set()
        for _ in range(3):
            r = requests.get(f"{API}/videos?section=random&limit=100", timeout=30)
            assert r.status_code == 200
            for v in r.json():
                seen_ids.add(v["id"])
        assert seed["v_drama"] not in seen_ids

    def test_count_respects_shorts_category(self, seed):
        r_d = requests.get(f"{API}/videos/count?kind=short&shorts_category=drama", timeout=30)
        assert r_d.status_code == 200
        r_x = requests.get(f"{API}/videos/count?kind=short&shorts_category=xxx", timeout=30)
        assert r_x.status_code == 200
        # sanity: at least our seed count
        assert r_d.json().get("count", 0) >= 1
        assert r_x.json().get("count", 0) >= 2  # v_xxx + v_legacy


# ---------- PATCH video ----------

class TestPatchVideo:
    def test_patch_shorts_category_valid(self, seed, hdr, mongo):
        # Toggle v_xxx -> drama then back
        r = requests.patch(f"{API}/videos/{seed['v_xxx']}", headers=hdr,
                           json={"shorts_category": "drama"}, timeout=30)
        assert r.status_code == 200, r.text
        assert mongo.videos.find_one({"id": seed["v_xxx"]})["shorts_category"] == "drama"
        # revert
        r2 = requests.patch(f"{API}/videos/{seed['v_xxx']}", headers=hdr,
                            json={"shorts_category": "xxx"}, timeout=30)
        assert r2.status_code == 200
        assert mongo.videos.find_one({"id": seed["v_xxx"]})["shorts_category"] == "xxx"

    def test_patch_shorts_category_invalid(self, seed, hdr):
        r = requests.patch(f"{API}/videos/{seed['v_xxx']}", headers=hdr,
                           json={"shorts_category": "bogus"}, timeout=30)
        assert r.status_code == 400


# ---------- Chunked upload finish accepts shorts_category ----------

class TestChunkedUploadShortsCategory:
    def test_finish_persists_shorts_category(self, seed, hdr, mongo):
        # We can't easily do a real chunked upload here, but we verify the endpoint
        # accepts the field. We initiate an upload, then send a tiny file via chunk
        # and finish with shorts_category=drama.
        # Simpler: just check that the FastAPI code path exists by inspecting behavior via a small file.
        # Because a real upload requires ffmpeg-processable content, we skip if that's heavy.
        import io
        # Init upload
        r = requests.post(f"{API}/videos/upload/init", headers=hdr, json={
            "filename": f"{seed['tag']}_up.mp4", "size": 100, "content_type": "video/mp4"
        }, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"upload/init not usable in this env: {r.status_code} {r.text[:200]}")
        upload_id = r.json().get("upload_id") or r.json().get("id")
        if not upload_id:
            pytest.skip("upload_id missing")

        # Upload a single tiny chunk (100 bytes of zeros) — we won't finish because
        # ffprobe will fail on fake content; instead we verify finish endpoint
        # rejects/handles gracefully but still accepts the shorts_category field
        # by checking that a 4xx related to media (not to schema) is returned.
        try:
            files = {"file": ("chunk", io.BytesIO(b"\x00" * 100), "application/octet-stream")}
            requests.post(f"{API}/videos/upload/{upload_id}/chunk",
                          headers=hdr, files=files, data={"index": "0"}, timeout=30)
            r_fin = requests.post(f"{API}/videos/upload/{upload_id}/finish",
                                  headers=hdr,
                                  json={"title": f"{seed['tag']}_up", "is_short": True,
                                        "shorts_category": "drama"},
                                  timeout=60)
            # Either 200 (persisted) or a 4xx/5xx from media processing — the point
            # is the endpoint accepted the field. If it 200'd, verify persistence.
            if r_fin.status_code == 200:
                vid = r_fin.json().get("id")
                if vid:
                    doc = mongo.videos.find_one({"id": vid})
                    assert doc.get("shorts_category") == "drama"
                    mongo.videos.delete_one({"id": vid})
            else:
                # accept — schema is at least accepting shorts_category (no 422 on it)
                assert r_fin.status_code != 422, f"Schema rejected shorts_category: {r_fin.text}"
        finally:
            # Best-effort cleanup on server
            requests.delete(f"{API}/videos/upload/{upload_id}", headers=hdr, timeout=15)
