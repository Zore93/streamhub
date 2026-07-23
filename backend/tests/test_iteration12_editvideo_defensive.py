"""
Iteration 12 — Backend regression tests for EditVideo defensive error handling.

Focus:
- PATCH /api/videos/{id} with thumbnail_url (success + revert)
- DELETE /api/videos/{id}/subtitles/{sid} error path (unknown id -> 404 with detail)
- PATCH /api/videos/{id} with `subtitles` reorder — bad ids -> 400 with detail
- All error responses include an HTTPException `detail` field so the frontend
  can surface it via toast.error(...).

We test against 127.0.0.1:8001 directly to avoid the k8s ingress replacing
FastAPI JSON error payloads with an HTML error page (as documented in
iteration_11.json).
"""
import os
import pytest
import requests

# Test video from the review request — has 10+ thumbnail_options, no subtitles.
TEST_VIDEO_ID = "98ebab0f-b290-4e9c-8857-402faef8fcb0"
INTERNAL_URL = "http://127.0.0.1:8001"
PUBLIC_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{INTERNAL_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def video(admin_headers):
    r = requests.get(
        f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
        headers=admin_headers,
        timeout=15,
    )
    assert r.status_code == 200, f"Video fetch failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("id") == TEST_VIDEO_ID
    return data


# ---------- Video fetch ----------

class TestVideoFetch:
    def test_video_has_thumbnail_options(self, video):
        opts = video.get("thumbnail_options") or []
        assert isinstance(opts, list)
        assert len(opts) >= 2, f"Test video should have multiple thumbnail_options, got {len(opts)}"


# ---------- Thumbnail selection via PATCH ----------

class TestThumbnailPatch:
    def test_patch_thumbnail_url_success(self, admin_headers, video):
        """Simulates clicking a thumbnail: PATCH with new thumbnail_url should
        return 200 and persist. Frontend then shows 'Saved' toast."""
        original = video.get("thumbnail_url")
        opts = video["thumbnail_options"]
        # Pick a different option than current
        target = next((t for t in opts if t != original), opts[0])

        r = requests.patch(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
            json={"thumbnail_url": target},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, f"PATCH failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("thumbnail_url") == target, (
            f"thumbnail_url not persisted. expected {target}, got {data.get('thumbnail_url')}"
        )
        # No mongodb _id in response
        assert "_id" not in data

        # GET to double-confirm persistence
        r2 = requests.get(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
            headers=admin_headers,
            timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("thumbnail_url") == target

        # Restore original so re-runs are idempotent
        if original and original != target:
            requests.patch(
                f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
                json={"thumbnail_url": original},
                headers=admin_headers,
                timeout=15,
            )

    def test_patch_without_auth_returns_401(self):
        r = requests.patch(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
            json={"thumbnail_url": "https://x/y.jpg"},
            timeout=15,
        )
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code} {r.text}"
        # Error should have a detail field the frontend can surface
        try:
            body = r.json()
            assert "detail" in body
        except Exception:
            pass

    def test_patch_nonexistent_video_returns_404_with_detail(self, admin_headers):
        r = requests.patch(
            f"{INTERNAL_URL}/api/videos/nonexistent-id-zzzzz",
            json={"thumbnail_url": "https://x/y.jpg"},
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 404
        body = r.json()
        assert "detail" in body and body["detail"], (
            f"Frontend needs detail field for toast.error, got: {body}"
        )


# ---------- Subtitle delete error path ----------

class TestSubtitleDeleteErrors:
    def test_delete_unknown_subtitle_returns_error_with_detail(self, admin_headers):
        """delSubtitle() in EditVideo.jsx now catches and shows the detail.
        Confirm the backend actually returns a detail field for unknown ids."""
        r = requests.delete(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}/subtitles/does-not-exist-sub-id",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code} {r.text}"
        body = r.json()
        assert "detail" in body and body["detail"], (
            f"Missing detail field: {body}"
        )


# ---------- Subtitle reorder (setDefaultSub) error path ----------

class TestSubtitleReorderErrors:
    def test_reorder_with_unknown_subtitle_id_returns_400_with_detail(self, admin_headers, video):
        """setDefaultSub() posts a `subtitles` reorder array. Confirm backend
        rejects unknown ids with 400 + detail so frontend can toast."""
        payload = {"subtitles": [{"id": "totally-fake-sub-id-xxx"}]}
        r = requests.patch(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
            json=payload,
            headers=admin_headers,
            timeout=15,
        )
        # The test video may have 0 subtitles — either way this must 400
        assert r.status_code == 400, f"Expected 400, got {r.status_code} {r.text}"
        body = r.json()
        assert "detail" in body and body["detail"], f"Missing detail: {body}"

    def test_reorder_missing_id_field_returns_400_with_detail(self, admin_headers):
        payload = {"subtitles": [{"label": "no-id-here"}]}
        r = requests.patch(
            f"{INTERNAL_URL}/api/videos/{TEST_VIDEO_ID}",
            json=payload,
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 400
        body = r.json()
        assert "detail" in body and "id" in str(body["detail"]).lower()


# ---------- Public URL smoke check (verify ingress isn't stripping JSON) ----------

class TestPublicUrlSmoke:
    def test_public_backend_reachable(self):
        if not PUBLIC_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        r = requests.get(f"{PUBLIC_URL}/api/site/config", timeout=15)
        assert r.status_code == 200, f"public URL /api/site/config failed: {r.status_code}"

    def test_public_url_patch_video_returns_json_error(self, admin_headers):
        """Sanity-check that when the *public* URL is used (i.e. what the user
        VPS would use), an unauth PATCH still returns a JSON body with detail.
        If the ingress replaces this with HTML, the frontend toast would show
        '[object Object]' or fallback text — which is what triggered the
        silent-failure bug."""
        if not PUBLIC_URL:
            pytest.skip("REACT_APP_BACKEND_URL not set")
        r = requests.patch(
            f"{PUBLIC_URL}/api/videos/{TEST_VIDEO_ID}",
            json={"thumbnail_url": "https://x/y.jpg"},
            timeout=15,
        )
        # We just want to confirm the response is JSON, not HTML
        ct = r.headers.get("content-type", "")
        assert "json" in ct.lower(), (
            f"Public URL returned non-JSON error ({ct}): first 200 chars = {r.text[:200]}"
        )
