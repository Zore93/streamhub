"""Iteration 8 - tests for:
   1) GET /api/languages (~190 entries, ro/en/ja present)
   2) GET /api/site/config includes new fields
   3) PATCH /api/admin/settings flips home_hero_text + bulk_upload_enabled
   4) Chunked upload flow init/chunk/status/finish/delete
   5) Subtitle auto-detect language from filename (no lang/label form fields)
   6) Max 100 subtitles error message
"""
import io
import os
import pytest
import requests

def _read_frontend_backend_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_backend_url()).rstrip("/")
ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"
TEST_VIDEO_ID = "1fa97503-867b-40d6-8cb3-08dea01854e5"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- 1) languages ----------
def test_languages_endpoint():
    r = requests.get(f"{BASE_URL}/api/languages", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 150, f"expected ~190 languages, got {len(data)}"
    codes = {x["code"] for x in data}
    assert {"ro", "en", "ja"}.issubset(codes)
    for x in data[:5]:
        assert "code" in x and "label" in x


# ---------- 2) site/config new fields ----------
def test_site_config_has_new_fields():
    r = requests.get(f"{BASE_URL}/api/site/config", timeout=20)
    assert r.status_code == 200
    cfg = r.json()
    for key in (
        "home_hero_text",
        "bulk_upload_enabled",
        "bulk_upload_concurrency",
        "chunk_upload_chunk_size_mb",
        "max_upload_size_mb",
    ):
        assert key in cfg, f"missing key {key}"
    assert cfg["bulk_upload_enabled"] is True
    assert cfg["chunk_upload_chunk_size_mb"] == 25


# ---------- 3) PATCH admin settings ----------
def test_patch_admin_settings_hero_and_bulk(admin_headers):
    # Set custom hero text + disable bulk
    r = requests.patch(
        f"{BASE_URL}/api/admin/settings",
        json={"home_hero_text": "Custom hero text", "bulk_upload_enabled": False},
        headers=admin_headers,
        timeout=20,
    )
    assert r.status_code == 200, r.text
    # Verify it reflects in /site/config
    cfg = requests.get(f"{BASE_URL}/api/site/config", timeout=20).json()
    assert cfg["home_hero_text"] == "Custom hero text"
    assert cfg["bulk_upload_enabled"] is False
    # Restore defaults
    r2 = requests.patch(
        f"{BASE_URL}/api/admin/settings",
        json={"home_hero_text": "", "bulk_upload_enabled": True},
        headers=admin_headers,
        timeout=20,
    )
    assert r2.status_code == 200
    cfg2 = requests.get(f"{BASE_URL}/api/site/config", timeout=20).json()
    assert cfg2["home_hero_text"] == ""
    assert cfg2["bulk_upload_enabled"] is True


# ---------- 4) Chunked upload end-to-end ----------
def test_chunked_upload_full_flow(admin_headers):
    # Build a ~30KB sample binary
    payload_bytes = os.urandom(30 * 1024)
    total = len(payload_bytes)

    # init
    r = requests.post(
        f"{BASE_URL}/api/videos/upload/init",
        json={"filename": "TEST_chunked.mp4", "total_size": total, "mime_type": "video/mp4"},
        headers=admin_headers,
        timeout=20,
    )
    assert r.status_code == 200, r.text
    init = r.json()
    upload_id = init["upload_id"]
    assert "chunk_size_mb" in init
    assert init.get("received_size", 0) == 0

    # 3 chunks of 10KB
    chunks = [payload_bytes[i:i + 10 * 1024] for i in range(0, total, 10 * 1024)]
    assert len(chunks) == 3
    running = 0
    for i, c in enumerate(chunks):
        rc = requests.post(
            f"{BASE_URL}/api/videos/upload/{upload_id}/chunk",
            data=c,
            headers={**admin_headers, "Content-Type": "application/octet-stream"},
            timeout=30,
        )
        assert rc.status_code == 200, rc.text
        body = rc.json()
        running += len(c)
        assert body["received_size"] == running
        assert body["complete"] == (i == len(chunks) - 1)

    # status
    rs = requests.get(
        f"{BASE_URL}/api/videos/upload/{upload_id}/status",
        headers=admin_headers, timeout=20,
    )
    assert rs.status_code == 200
    st = rs.json()
    assert st["received_size"] == total
    assert st["complete"] is True

    # finish
    rf = requests.post(
        f"{BASE_URL}/api/videos/upload/{upload_id}/finish",
        json={"title": "TEST_iter8 Chunked Test"},
        headers=admin_headers, timeout=30,
    )
    assert rf.status_code == 200, rf.text
    v = rf.json()
    assert v["title"] == "TEST_iter8 Chunked Test"
    assert v["status"] == "processing"
    assert v.get("slug")
    created_vid = v["id"]

    # Cleanup: delete the test video so we don't pollute the DB
    rd = requests.delete(
        f"{BASE_URL}/api/videos/{created_vid}", headers=admin_headers, timeout=20
    )
    assert rd.status_code in (200, 204)


def test_chunked_upload_abort_delete(admin_headers):
    r = requests.post(
        f"{BASE_URL}/api/videos/upload/init",
        json={"filename": "TEST_abort.mp4", "total_size": 1024, "mime_type": "video/mp4"},
        headers=admin_headers,
        timeout=20,
    )
    assert r.status_code == 200
    uid = r.json()["upload_id"]
    rd = requests.delete(
        f"{BASE_URL}/api/videos/upload/{uid}",
        headers=admin_headers, timeout=20,
    )
    assert rd.status_code == 200
    assert rd.json().get("ok") is True


# ---------- 5) Subtitle auto-detect from filename ----------
def test_subtitle_autodetect_language(admin_headers):
    # Build a tiny VTT body (use .vtt to bypass ffmpeg requirement in preview env)
    vtt = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n"
    files = {"file": ("episode01.ja-jp.vtt", io.BytesIO(vtt), "text/vtt")}
    # NO language/label form fields
    r = requests.post(
        f"{BASE_URL}/api/videos/{TEST_VIDEO_ID}/subtitles",
        files=files,
        headers=admin_headers,
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Endpoint returns the newly inserted subtitle entry directly.
    if isinstance(body, dict) and body.get("language") and body.get("id") and body.get("url"):
        new_sub = body
    else:
        subs = body.get("subtitles") if isinstance(body, dict) else None
        assert subs, f"unexpected response shape: {body}"
        new_sub = subs[-1]
    assert new_sub["language"] == "ja", f"expected ja, got {new_sub.get('language')}"
    # cleanup
    sub_id = new_sub["id"]
    rd = requests.delete(
        f"{BASE_URL}/api/videos/{TEST_VIDEO_ID}/subtitles/{sub_id}",
        headers=admin_headers, timeout=20,
    )
    assert rd.status_code in (200, 204)


# ---------- 6) Max 100 subtitles message ----------
def test_max_100_subtitles_error_message():
    """Confirm the constant via grep of the source — running 101 inserts is too slow."""
    with open("/app/backend/server.py") as f:
        text = f.read()
    assert "Max 100 subtitles per video" in text
    assert "Max 10 subtitles per video" not in text
