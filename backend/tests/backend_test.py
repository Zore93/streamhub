"""StreamHub backend tests."""
import os
import time
import uuid
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://stream-convert-hub-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"

state = {}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    state["admin_token"] = tok
    state["admin_id"] = r.json()["user"]["id"]
    return tok


@pytest.fixture(scope="session")
def user_creds(s):
    suffix = uuid.uuid4().hex[:8]
    email = f"test_{suffix}@example.com"
    password = "Pass123!"
    username = f"tester_{suffix}"
    r = s.post(f"{API}/auth/register", json={"email": email, "username": username, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "username": username, "password": password, "token": data["token"], "id": data["user"]["id"]}


def auth_hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ AUTH ============
class TestAuth:
    def test_admin_login(self, admin_token):
        assert admin_token

    def test_register_and_me(self, s, user_creds):
        r = s.get(f"{API}/auth/me", headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == user_creds["email"]

    def test_login_invalid(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "x@y.z", "password": "bad"})
        assert r.status_code == 401

    def test_duplicate_register(self, s, user_creds):
        r = s.post(f"{API}/auth/register", json={"email": user_creds["email"], "username": "x", "password": "x"})
        assert r.status_code == 400


# ============ CATEGORIES ============
class TestCategories:
    def test_list_seeded(self, s):
        r = s.get(f"{API}/categories")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        for n in ["Music", "Gaming", "Tech", "Education", "Comedy", "Travel"]:
            assert n in names

    def test_create_and_delete(self, s, admin_token):
        r = s.post(f"{API}/categories", json={"name": "TEST_Cat"}, headers=auth_hdr(admin_token))
        assert r.status_code == 200
        cid = r.json()["id"]
        r2 = s.delete(f"{API}/categories/{cid}", headers=auth_hdr(admin_token))
        assert r2.status_code == 200

    def test_create_requires_admin(self, s, user_creds):
        r = s.post(f"{API}/categories", json={"name": "x"}, headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 403


# ============ VIDEOS upload + transcode ============
class TestVideos:
    def test_sections(self, s):
        for sec in ["latest", "popular", "random"]:
            r = s.get(f"{API}/videos", params={"section": sec, "limit": 5})
            assert r.status_code == 200
            assert isinstance(r.json(), list)

    def test_upload_transcode_full_flow(self, s, user_creds, admin_token):
        # generate small mp4
        path = "/tmp/test.mp4"
        if not os.path.exists(path):
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
                check=True, capture_output=True,
            )
        with open(path, "rb") as f:
            files = {"file": ("test.mp4", f, "video/mp4")}
            data = {"title": "TEST_Video", "description": "d", "tags": "a,b", "access_tier": "free"}
            r = s.post(f"{API}/videos/upload", files=files, data=data, headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200, r.text
        vid_id = r.json()["id"]
        state["video_id"] = vid_id

        # poll
        ready = False
        for _ in range(60):
            time.sleep(2)
            rr = s.get(f"{API}/videos/{vid_id}")
            if rr.status_code == 200 and rr.json().get("status") == "ready":
                ready = True
                video = rr.json()
                break
        assert ready, f"video not ready: {rr.json() if rr.status_code==200 else rr.text}"
        assert len(video.get("thumbnail_options", [])) == 10
        assert len(video.get("renditions", [])) >= 1

    def test_view_like(self, s, user_creds):
        vid = state["video_id"]
        s.post(f"{API}/videos/{vid}/view")
        r = s.post(f"{API}/videos/{vid}/like", headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200
        assert r.json()["liked"] is True

    def test_recommendations(self, s):
        r = s.get(f"{API}/videos/{state['video_id']}/recommendations", params={"limit": 15})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_comment_flow(self, s, user_creds):
        vid = state["video_id"]
        r = s.post(f"{API}/videos/{vid}/comments", json={"content": "hi"}, headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200
        cid = r.json()["id"]
        r2 = s.get(f"{API}/videos/{vid}/comments")
        assert any(c["id"] == cid for c in r2.json())
        r3 = s.delete(f"{API}/comments/{cid}", headers=auth_hdr(user_creds["token"]))
        assert r3.status_code == 200

    def test_update_video(self, s, user_creds):
        vid = state["video_id"]
        r = s.patch(f"{API}/videos/{vid}", json={"title": "TEST_Renamed"}, headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Renamed"

    def test_user_videos(self, s, user_creds):
        r = s.get(f"{API}/users/{user_creds['id']}/videos")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_delete_video_owner(self, s, user_creds):
        vid = state["video_id"]
        r = s.delete(f"{API}/videos/{vid}", headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200


# ============ PACKAGES ============
class TestPackages:
    def test_packages_crud(self, s, admin_token):
        r = s.post(f"{API}/packages", json={"name": "TEST_Pkg", "price": 9.99, "duration_days": 30}, headers=auth_hdr(admin_token))
        assert r.status_code == 200
        pid = r.json()["id"]
        state["pkg_id"] = pid
        r2 = s.get(f"{API}/packages")
        assert any(p["id"] == pid for p in r2.json())
        r3 = s.patch(f"{API}/packages/{pid}", json={"price": 19.99}, headers=auth_hdr(admin_token))
        assert r3.status_code == 200
        assert r3.json()["price"] == 19.99


# ============ ANNOUNCEMENTS ============
class TestAnnouncements:
    def test_announcement_crud(self, s, admin_token):
        r = s.post(f"{API}/announcements", json={"title": "TEST_A", "content": "hi"}, headers=auth_hdr(admin_token))
        assert r.status_code == 200
        aid = r.json()["id"]
        r2 = s.get(f"{API}/announcements/active")
        assert any(a["id"] == aid for a in r2.json())
        r3 = s.delete(f"{API}/announcements/{aid}", headers=auth_hdr(admin_token))
        assert r3.status_code == 200


# ============ ADMIN ============
class TestAdmin:
    def test_stats(self, s, admin_token):
        r = s.get(f"{API}/admin/stats", headers=auth_hdr(admin_token))
        assert r.status_code == 200
        for k in ["total_videos", "total_users", "total_views", "total_pro_users", "total_likes", "total_comments"]:
            assert k in r.json()

    def test_users_list(self, s, admin_token):
        r = s.get(f"{API}/admin/users", headers=auth_hdr(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ban_unban(self, s, admin_token, user_creds):
        uid = user_creds["id"]
        r = s.post(f"{API}/admin/users/{uid}/ban", json={"duration": "1day", "reason": "test"}, headers=auth_hdr(admin_token))
        assert r.status_code == 200
        # banned login
        r2 = s.post(f"{API}/auth/login", json={"email": user_creds["email"], "password": user_creds["password"]})
        assert r2.status_code == 403
        # unban
        r3 = s.post(f"{API}/admin/users/{uid}/unban", headers=auth_hdr(admin_token))
        assert r3.status_code == 200
        r4 = s.post(f"{API}/auth/login", json={"email": user_creds["email"], "password": user_creds["password"]})
        assert r4.status_code == 200

    def test_role(self, s, admin_token, user_creds):
        r = s.post(f"{API}/admin/users/{user_creds['id']}/role", json={"role": "user"}, headers=auth_hdr(admin_token))
        assert r.status_code == 200

    def test_settings_update(self, s, admin_token):
        r = s.get(f"{API}/admin/settings", headers=auth_hdr(admin_token))
        assert r.status_code == 200
        r2 = s.patch(f"{API}/admin/settings",
                     json={"ffmpeg_concurrency": 3, "max_upload_size_mb": 2048, "allow_user_uploads": True,
                           "enabled_resolutions": ["360p", "720p"], "storage_backend": "local",
                           "smtp_host": "smtp.test", "wasabi_bucket": "x", "stripe_secret_key": "",
                           "github_repo": "x/y"},
                     headers=auth_hdr(admin_token))
        assert r2.status_code == 200
        assert r2.json()["ffmpeg_concurrency"] == 3
        assert r2.json()["max_upload_size_mb"] == 2048


# ============ PROFILE uploads ============
class TestProfile:
    def test_avatar_cover(self, s, user_creds):
        img = b"\xff\xd8\xff\xe0" + b"\x00" * 50  # tiny fake jpg
        r = s.post(f"{API}/users/me/avatar", files={"file": ("a.jpg", img, "image/jpeg")}, headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200
        assert "avatar_url" in r.json()
        r2 = s.post(f"{API}/users/me/cover", files={"file": ("c.jpg", img, "image/jpeg")}, headers=auth_hdr(user_creds["token"]))
        assert r2.status_code == 200


# ============ PAYMENTS ============
class TestPayments:
    def test_checkout(self, s, user_creds, admin_token):
        pid = state.get("pkg_id")
        if not pid:
            r0 = s.post(f"{API}/packages", json={"name": "TEST_Pay", "price": 5.0, "duration_days": 30}, headers=auth_hdr(admin_token))
            pid = r0.json()["id"]
            state["pkg_id"] = pid
        r = s.post(f"{API}/payments/checkout",
                   json={"package_id": pid, "origin_url": BASE_URL},
                   headers=auth_hdr(user_creds["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "url" in data and "session_id" in data
        sid = data["session_id"]
        r2 = s.get(f"{API}/payments/status/{sid}")
        assert r2.status_code == 200


# ============ EMAIL VERIFICATION ============
class TestEmailVerification:
    def test_verification_flow(self, s, admin_token):
        # enable
        s.patch(f"{API}/admin/settings", json={"require_email_verification": True}, headers=auth_hdr(admin_token))
        try:
            suffix = uuid.uuid4().hex[:8]
            email = f"verify_{suffix}@example.com"
            r = s.post(f"{API}/auth/register", json={"email": email, "username": f"v_{suffix}", "password": "Pass123!"})
            assert r.status_code == 200
            assert r.json().get("require_verification") is True
            assert "token" not in r.json()
            # login should 403
            r2 = s.post(f"{API}/auth/login", json={"email": email, "password": "Pass123!"})
            assert r2.status_code == 403
        finally:
            s.patch(f"{API}/admin/settings", json={"require_email_verification": False}, headers=auth_hdr(admin_token))


# Cleanup
@pytest.fixture(scope="session", autouse=True)
def cleanup(request, s):
    yield
    tok = state.get("admin_token")
    if tok and state.get("pkg_id"):
        s.delete(f"{API}/packages/{state['pkg_id']}", headers=auth_hdr(tok))
