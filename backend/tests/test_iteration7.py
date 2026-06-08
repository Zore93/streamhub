"""Iteration 7 tests — slug+UUID dual-resolution, shop leaderboard, SSR.

Covers:
- /videos/{id_or_slug}/* endpoints accept both UUID and slug
- New comment posted via slug stores canonical UUID as video_id
- View counter increments persist (verified via UUID and via slug)
- build_video_slug includes full title (no truncation)
- legacy_slug resolves
- GET /api/shop/leaderboard contract
- /api/og/video/{slug-or-uuid} returns SSR HTML
- /watch/{slug-or-uuid} crawler middleware returns og:title HTML
"""
import os
import re
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@streamhub.io", "password": "Admin123!"}

VID_UUID = "1fa97503-867b-40d6-8cb3-08dea01854e5"
VID_SLUG = "testsubvideo-1854e5"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# --- 1. GET /videos/{id_or_slug} returns same doc ---
def test_get_video_by_uuid_and_slug_match():
    a = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10)
    b = requests.get(f"{BASE}/api/videos/{VID_SLUG}", timeout=10)
    assert a.status_code == 200 and b.status_code == 200
    da, db = a.json(), b.json()
    assert da["id"] == db["id"] == VID_UUID
    assert da["slug"] == db["slug"] == VID_SLUG


# --- 2. View counter: 3x POST via slug must increment by exactly 3 ---
def test_view_counter_increments_via_slug():
    pre = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()["views"]
    for _ in range(3):
        r = requests.post(f"{BASE}/api/videos/{VID_SLUG}/view", timeout=10)
        assert r.status_code == 200
    post = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()["views"]
    assert post - pre == 3, f"expected +3, got {pre}->{post}"


# --- 3. Like via slug works (was 'silently nothing' bug) ---
def test_like_via_slug_works(admin_headers):
    r = requests.post(f"{BASE}/api/videos/{VID_SLUG}/like", headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "liked" in body and "count" in body
    # Toggle back so test is idempotent
    requests.post(f"{BASE}/api/videos/{VID_SLUG}/like", headers=admin_headers, timeout=10)


# --- 4. Comment via slug stores canonical UUID ---
def test_new_comment_via_slug_uses_uuid(admin_headers):
    payload = {"content": "TEST_iter7_slug_comment"}
    r = requests.post(
        f"{BASE}/api/videos/{VID_SLUG}/comments",
        headers=admin_headers, json=payload, timeout=10,
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["video_id"] == VID_UUID, f"expected UUID, got {c['video_id']}"


# --- 5. list comments via slug == via UUID (both return same set) ---
def test_list_comments_slug_vs_uuid_equal():
    a = requests.get(f"{BASE}/api/videos/{VID_UUID}/comments", timeout=10).json()
    b = requests.get(f"{BASE}/api/videos/{VID_SLUG}/comments", timeout=10).json()
    assert len(a) == len(b)
    assert {c["id"] for c in a} == {c["id"] for c in b}


# --- 6. Recommendations endpoint via slug ---
def test_recommendations_via_slug():
    r = requests.get(f"{BASE}/api/videos/{VID_SLUG}/recommendations?limit=5", timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)


# --- 7. PATCH /videos/{slug} works ---
def test_patch_video_via_slug(admin_headers):
    # patch description to a unique marker then revert
    marker = "TEST_iter7_marker"
    cur = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()
    orig_desc = cur.get("description", "")
    try:
        r = requests.patch(
            f"{BASE}/api/videos/{VID_SLUG}",
            headers=admin_headers,
            json={"description": marker}, timeout=10,
        )
        assert r.status_code == 200, r.text
        after = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()
        assert after.get("description") == marker
    finally:
        requests.patch(
            f"{BASE}/api/videos/{VID_UUID}",
            headers=admin_headers,
            json={"description": orig_desc}, timeout=10,
        )


# --- 8. build_video_slug — no truncation (verified via PATCH a title) ---
def test_slug_not_truncated_on_long_title(admin_headers):
    long_title = "Sora iubitei mele cu tate mari m-a sedus si mi-am dat drumul in ea"
    cur = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()
    orig = cur.get("title")
    orig_slug = cur.get("slug")
    try:
        r = requests.patch(
            f"{BASE}/api/videos/{VID_UUID}",
            headers=admin_headers,
            json={"title": long_title}, timeout=10,
        )
        assert r.status_code == 200
        new = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()
        slug = new["slug"]
        # ALL words from title must appear in slug
        for word in re.findall(r"[a-zA-Z0-9]+", long_title.lower()):
            assert word in slug, f"slug missing word '{word}': {slug}"
        # And ends with 6-hex of UUID
        assert slug.endswith("1854e5"), slug
    finally:
        requests.patch(
            f"{BASE}/api/videos/{VID_UUID}",
            headers=admin_headers,
            json={"title": orig}, timeout=10,
        )
        # restore slug too (build_video_slug recomputes from title)
        after = requests.get(f"{BASE}/api/videos/{VID_UUID}", timeout=10).json()
        assert after["slug"] == orig_slug


# --- 9. legacy_slug resolves ---
def test_legacy_slug_resolves(admin_headers):
    import pymongo
    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "test_database"
    cli = pymongo.MongoClient(mongo_url)
    coll = cli[db_name]["videos"]
    legacy = "foo-bar-baz-iter7"
    coll.update_one({"id": VID_UUID}, {"$set": {"legacy_slug": legacy}})
    try:
        r = requests.get(f"{BASE}/api/videos/{legacy}", timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["id"] == VID_UUID
    finally:
        coll.update_one({"id": VID_UUID}, {"$unset": {"legacy_slug": ""}})


# --- 10. /api/shop/leaderboard ---
def test_leaderboard_anonymous():
    r = requests.get(f"{BASE}/api/shop/leaderboard?limit=10", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "top" in body and "me" in body
    assert body["me"] is None
    assert isinstance(body["top"], list) and len(body["top"]) >= 1
    first = body["top"][0]
    for key in ("rank", "id", "username", "coins", "is_pro"):
        assert key in first, f"missing {key}"
    assert first["rank"] == 1
    # selected_frame key present (None or dict)
    assert "selected_frame" in first
    assert "avatar_url" in first
    # admin should be #1 with 10000 coins per problem statement
    if first["username"] in ("admin", "admin@streamhub.io"):
        assert first["coins"] >= 9000


def test_leaderboard_authenticated_includes_me(admin_headers):
    r = requests.get(
        f"{BASE}/api/shop/leaderboard?limit=10",
        headers=admin_headers, timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["me"] is not None
    me = body["me"]
    for key in ("rank", "id", "username", "coins"):
        assert key in me
    assert isinstance(me["rank"], int) and me["rank"] >= 1


# --- 11. OG SSR endpoint ---
def test_og_endpoint_uuid_and_slug():
    for key in (VID_UUID, VID_SLUG):
        r = requests.get(f"{BASE}/api/og/video/{key}", timeout=10)
        assert r.status_code == 200, key
        html = r.text
        assert "og:title" in html
        assert "og:image" in html
        # absolute URL on og:image
        m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        assert m, "og:image not found"
        assert m.group(1).startswith("http"), m.group(1)


# --- 12. Crawler middleware on /watch/{slug} ---
def test_watch_crawler_returns_og_title():
    # backend served at port 8001 internally
    r = requests.get(
        "http://localhost:8001/watch/" + VID_SLUG,
        headers={"User-Agent": "facebookexternalhit/1.1"},
        timeout=10, allow_redirects=False,
    )
    assert r.status_code == 200
    assert "TEST_SubVideo" in r.text or "og:title" in r.text
    # also via UUID
    r2 = requests.get(
        "http://localhost:8001/watch/" + VID_UUID,
        headers={"User-Agent": "facebookexternalhit/1.1"},
        timeout=10, allow_redirects=False,
    )
    assert r2.status_code == 200
    assert "og:title" in r2.text
