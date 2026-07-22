"""Iteration 11 — LLM key migrated from ENV to DB (AppSettings.emergent_llm_key).

Tests:
  * GET  /api/admin/settings returns the field.
  * PATCH /api/admin/settings persists the field.
  * GET  /api/site/config does NOT expose it.
  * POST /api/admin/videos/{id}/generate-synopsis works when key is in DB.
  * POST /api/admin/videos/{id}/generate-synopsis returns friendly error when
    key is empty AND EMERGENT_LLM_KEY env-var is absent.
  * POST /api/admin/videos/generate-synopsis-bulk picks up DB key.

The suite talks directly to 127.0.0.1:8001 to bypass the preview-URL Cloudflare
error page that hides FastAPI's real HTTP 500 body.
"""
from __future__ import annotations

import os
import time
import pytest
import requests

# Direct to backend to bypass ingress-side error pages
BASE_URL = "http://127.0.0.1:8001"
ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"
TEST_KEY = "sk-emergent-4A501A18c0dFb3d248"


# ---------- Shared fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_video_id(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/videos?limit=5", headers=admin_headers, timeout=10)
    assert r.status_code == 200
    payload = r.json()
    items = payload.get("items") if isinstance(payload, dict) else payload
    assert items, "No videos in DB — cannot test synopsis endpoints"
    return items[0]["id"]


@pytest.fixture(scope="module", autouse=True)
def restore_key_after_module(admin_headers):
    """After tests run, put the good key back."""
    yield
    try:
        requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": TEST_KEY},
            timeout=10,
        )
    except Exception:
        pass


# ---------- Settings endpoint tests ----------
class TestSettingsField:
    """AppSettings.emergent_llm_key exposure via /api/admin/settings."""

    def test_admin_settings_returns_emergent_llm_key_field(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "emergent_llm_key" in data, "emergent_llm_key must be present in admin settings"
        assert isinstance(data["emergent_llm_key"], str)

    def test_patch_saves_emergent_llm_key(self, admin_headers):
        # Save a marker value, GET, verify, then restore real key.
        marker = "TEST_marker_key_iter11"
        r = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": marker},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("emergent_llm_key") == marker

        # GET verifies persistence
        r2 = requests.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers, timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("emergent_llm_key") == marker

        # Restore real key so downstream tests can call the LLM
        r3 = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": TEST_KEY},
            timeout=10,
        )
        assert r3.status_code == 200
        assert r3.json().get("emergent_llm_key") == TEST_KEY

    def test_public_site_config_does_not_expose_key(self):
        r = requests.get(f"{BASE_URL}/api/site/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "emergent_llm_key" not in data, "PUBLIC /api/site/config must NEVER include emergent_llm_key"


# ---------- Synopsis generation tests ----------
class TestSynopsisGeneration:
    """The end-to-end AI synopsis flow now sourcing the key from DB."""

    def test_generate_synopsis_with_db_key(self, admin_headers, sample_video_id):
        """With the real key in DB → expect 200 with Romanian text."""
        # Ensure real key is set (belt & suspenders)
        requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": TEST_KEY},
            timeout=10,
        )
        r = requests.post(
            f"{BASE_URL}/api/admin/videos/{sample_video_id}/generate-synopsis",
            headers=admin_headers,
            json={},
            timeout=60,
        )
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text[:400]}"
        data = r.json()
        assert "synopsis" in data
        assert isinstance(data["synopsis"], str)
        assert len(data["synopsis"]) > 50, "synopsis too short"
        assert data.get("word_count", 0) > 20
        assert "model" in data and isinstance(data["model"], str)
        assert data.get("video_id") == sample_video_id

    def test_generate_synopsis_without_key_returns_friendly_error(self, admin_headers, sample_video_id):
        """Empty DB key + no env-var → friendly HTTP error message."""
        # Wipe the DB key
        r = requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": ""},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json().get("emergent_llm_key") == ""

        # Confirm env var not present
        env_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()

        try:
            r = requests.post(
                f"{BASE_URL}/api/admin/videos/{sample_video_id}/generate-synopsis",
                headers=admin_headers,
                json={},
                timeout=15,
            )
            # The endpoint wraps the inner HTTPException(500) into HTTPException(502)
            # via `except Exception`, so the observed status is 502.  The important
            # regression checks are (a) the friendly text is in the response, and
            # (b) the old "EMERGENT_LLM_KEY not configured in backend .env" message
            # is NOT present.
            if env_key:
                pytest.skip(
                    "EMERGENT_LLM_KEY env var is set on the host — cannot test the "
                    "'both empty' path.  This test is env-specific."
                )
            body = r.text
            assert r.status_code in (500, 502), f"expected 500/502, got {r.status_code}: {body[:400]}"
            # Friendly new message present
            assert "Emergent LLM Key not configured" in body, (
                f"Expected new friendly message, got: {body[:400]}"
            )
            assert "Admin" in body and "Settings" in body
            # Old backend-.env message MUST be gone
            assert "EMERGENT_LLM_KEY not configured in backend .env" not in body
        finally:
            # Restore key
            requests.patch(
                f"{BASE_URL}/api/admin/settings",
                headers=admin_headers,
                json={"emergent_llm_key": TEST_KEY},
                timeout=10,
            )

    def test_bulk_synopsis_uses_db_key(self, admin_headers, sample_video_id):
        """Bulk endpoint must also read the DB key."""
        # Ensure key present
        requests.patch(
            f"{BASE_URL}/api/admin/settings",
            headers=admin_headers,
            json={"emergent_llm_key": TEST_KEY},
            timeout=10,
        )
        # Use skip_existing=False so we force generation for a single video
        r = requests.post(
            f"{BASE_URL}/api/admin/videos/generate-synopsis-bulk",
            headers=admin_headers,
            json={"video_ids": [sample_video_id], "skip_existing": False},
            timeout=90,
        )
        assert r.status_code == 200, f"bulk failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert data.get("submitted") == 1
        assert data.get("success") == 1, f"bulk did not succeed: {data}"
        results = data.get("results", [])
        assert results and results[0]["ok"] is True
        assert "error" not in results[0] or not results[0].get("error")
