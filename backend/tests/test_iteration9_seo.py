"""Backend tests for SEO Dashboard (Google Search Console) — iteration 9.

Covers:
- Admin auth requirement on /admin/seo/* endpoints
- POST /admin/seo/credentials validation (empty, malformed JSON, wrong type)
- POST with valid service-account-shaped JSON (fake) -> saves and returns smoke_test_error
- GET /admin/seo/dashboard error path (no creds, fake creds 403/404/500)
- DELETE /admin/seo/credentials clears stored creds
- Non-admin/unauthenticated users get 401/403
"""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://stream-convert-hub-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASSWORD = "Admin123!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_token():
    """Try to register a non-admin user; if it exists, login."""
    email = "TEST_seo_user@example.com"
    password = "TestPass123!"
    # Try register
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "username": "TEST_seo_user"}, timeout=15)
    if r.status_code not in (200, 201, 400, 409):
        pytest.skip(f"Cannot register test user: {r.status_code} {r.text}")
    # Login
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Cannot login non-admin: {r.status_code} {r.text}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module", autouse=True)
def cleanup_creds(admin_headers):
    """Ensure clean state before and after this test module."""
    requests.delete(f"{API}/admin/seo/credentials", headers=admin_headers, timeout=15)
    yield
    requests.delete(f"{API}/admin/seo/credentials", headers=admin_headers, timeout=15)


# ------------ Auth guards ------------

class TestSeoAuthGuards:
    def test_save_creds_requires_auth(self):
        r = requests.post(f"{API}/admin/seo/credentials", json={"site_url": "x", "service_account_json": "{}"}, timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code} {r.text}"

    def test_dashboard_requires_auth(self):
        r = requests.get(f"{API}/admin/seo/dashboard", timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code} {r.text}"

    def test_delete_creds_requires_auth(self):
        r = requests.delete(f"{API}/admin/seo/credentials", timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code} {r.text}"

    def test_save_creds_non_admin_forbidden(self, user_token):
        h = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        r = requests.post(f"{API}/admin/seo/credentials", headers=h,
                          json={"site_url": "x", "service_account_json": "{}"}, timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code} {r.text}"

    def test_dashboard_non_admin_forbidden(self, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = requests.get(f"{API}/admin/seo/dashboard", headers=h, timeout=15)
        assert r.status_code in (401, 403), f"Expected 401/403 got {r.status_code} {r.text}"


# ------------ Validation ------------

class TestSeoCredsValidation:
    def test_empty_payload_returns_400(self, admin_headers):
        r = requests.post(f"{API}/admin/seo/credentials", headers=admin_headers, json={}, timeout=15)
        assert r.status_code == 400, f"Expected 400 got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "site_url and service_account_json are required" in detail, f"Unexpected detail: {detail}"

    def test_missing_sa_json_returns_400(self, admin_headers):
        r = requests.post(f"{API}/admin/seo/credentials", headers=admin_headers,
                          json={"site_url": "https://example.com/"}, timeout=15)
        assert r.status_code == 400
        assert "required" in r.json().get("detail", "")

    def test_malformed_json_returns_400(self, admin_headers):
        r = requests.post(f"{API}/admin/seo/credentials", headers=admin_headers,
                          json={"site_url": "https://example.com/", "service_account_json": "{not valid json"}, timeout=15)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "service_account_json is not valid JSON" in detail, f"Unexpected detail: {detail}"

    def test_wrong_type_returns_400(self, admin_headers):
        bad = json.dumps({"type": "user_account", "client_email": "x@x.com"})
        r = requests.post(f"{API}/admin/seo/credentials", headers=admin_headers,
                          json={"site_url": "https://example.com/", "service_account_json": bad}, timeout=15)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "type" in detail and "service_account" in detail, f"Unexpected detail: {detail}"


# ------------ Dashboard no-creds path ------------

class TestSeoDashboardNoCreds:
    def test_dashboard_no_creds_returns_400(self, admin_headers):
        # Ensure deleted
        requests.delete(f"{API}/admin/seo/credentials", headers=admin_headers, timeout=15)
        r = requests.get(f"{API}/admin/seo/dashboard", headers=admin_headers, timeout=15)
        assert r.status_code == 400, f"Expected 400 got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "Google Search Console credentials not configured" in detail, f"Unexpected detail: {detail}"


# ------------ Save fake but well-shaped SA + dashboard error path ------------

# A syntactically-valid (but cryptographically fake) service-account JSON.
FAKE_SA = {
    "type": "service_account",
    "project_id": "fake-test-project",
    "private_key_id": "0" * 40,
    "private_key": (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj\n"
        "-----END PRIVATE KEY-----\n"
    ),
    "client_email": "fake-sa@fake-test-project.iam.gserviceaccount.com",
    "client_id": "123456789012345678901",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


class TestSeoSaveAndDashboardErrorPath:
    def test_save_fake_sa_succeeds_with_smoke_error(self, admin_headers):
        payload = {
            "site_url": "https://test-fake-site-9999.example.com/",
            "service_account_json": json.dumps(FAKE_SA),
        }
        r = requests.post(f"{API}/admin/seo/credentials", headers=admin_headers, json=payload, timeout=60)
        assert r.status_code == 200, f"Expected 200 got {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("client_email") == FAKE_SA["client_email"]
        assert data.get("site_url") == payload["site_url"]
        # smoke_test_error must be a non-null string (fake credentials cannot reach GSC).
        smoke = data.get("smoke_test_error")
        assert isinstance(smoke, str) and len(smoke) > 0, f"Expected non-empty smoke_test_error, got {smoke!r}"

    def test_dashboard_after_fake_creds_returns_useful_error(self, admin_headers):
        r = requests.get(f"{API}/admin/seo/dashboard", headers=admin_headers, timeout=60)
        assert r.status_code in (403, 404, 500), f"Expected 403/404/500 got {r.status_code} {r.text}"
        # The detail should be a string message, not a traceback dump.
        body = r.json()
        detail = body.get("detail", "")
        assert isinstance(detail, str) and len(detail) > 0, f"Expected useful error detail, got {body}"
        # Make sure it's not a Python traceback leaking
        assert "Traceback" not in detail, f"Detail leaks traceback: {detail}"

    def test_delete_clears_credentials(self, admin_headers):
        r = requests.delete(f"{API}/admin/seo/credentials", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # After delete, dashboard should again return 400 "not configured"
        r2 = requests.get(f"{API}/admin/seo/dashboard", headers=admin_headers, timeout=15)
        assert r2.status_code == 400
        assert "not configured" in r2.json().get("detail", "")
