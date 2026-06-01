"""Tests for StreamHub new features (iteration 2):
- Admin settings round-trip for contact_email and CloudFront fields
- Public contact-config endpoint
- POST /api/contact (validation + 503 when not configured)
- Admin contact-messages list + delete
- Video subtitles upload (srt -> vtt conversion via ffmpeg), limit, validation, owner-check, delete, list
- Pro video subtitle URLs are signed
- Smoke tests on a few existing flows
"""
import os
import time
import uuid
import subprocess
import pytest
import requests

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL")
    or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip()
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"
OWNER_EMAIL = "owner@streamhub.io"
OWNER_PASS = "Owner@2026!"


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ Fixtures ============
@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_tok(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def owner_tok(s):
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_a(s):
    sfx = uuid.uuid4().hex[:8]
    email = f"test_a_{sfx}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "username": f"ua_{sfx}", "password": "Pass123!"})
    assert r.status_code == 200
    d = r.json()
    return {"email": email, "password": "Pass123!", "token": d["token"], "id": d["user"]["id"]}


@pytest.fixture(scope="module")
def user_b(s):
    sfx = uuid.uuid4().hex[:8]
    email = f"test_b_{sfx}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "username": f"ub_{sfx}", "password": "Pass123!"})
    assert r.status_code == 200
    d = r.json()
    return {"email": email, "password": "Pass123!", "token": d["token"], "id": d["user"]["id"]}


def _mk_mp4(path):
    if not os.path.exists(path):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
            check=True, capture_output=True,
        )


def _mk_srt(path, idx=1, text="Hello"):
    content = f"{idx}\n00:00:00,000 --> 00:00:02,000\n{text}\n"
    with open(path, "w") as f:
        f.write(content)


@pytest.fixture(scope="module")
def video_id(s, user_a):
    path = "/tmp/test_sub_video.mp4"
    _mk_mp4(path)
    with open(path, "rb") as f:
        r = s.post(
            f"{API}/videos/upload",
            files={"file": ("v.mp4", f, "video/mp4")},
            data={"title": "TEST_SubVideo", "description": "d", "access_tier": "free"},
            headers=auth(user_a["token"]),
        )
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    # wait for ready
    for _ in range(60):
        time.sleep(2)
        rr = s.get(f"{API}/videos/{vid}")
        if rr.status_code == 200 and rr.json().get("status") == "ready":
            return vid
    pytest.fail(f"video did not become ready: {rr.json() if rr.status_code==200 else rr.text}")


# ============ Existing admin login still works ============
class TestAdminLogin:
    def test_admin_primary(self, admin_tok):
        assert admin_tok

    def test_admin_owner(self, owner_tok):
        assert owner_tok


# ============ Admin settings round-trip ============
class TestSettingsRoundTrip:
    SAMPLE_PEM = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBOgIBAAJBAJv9...not-real...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )

    def test_set_and_get_new_fields(self, s, admin_tok):
        payload = {
            "contact_email": "TEST_support@example.com",
            "cloudfront_enabled": False,
            "cloudfront_domain": "d123.cloudfront.net",
            "cloudfront_key_pair_id": "APKAEXAMPLE",
            "cloudfront_private_key": self.SAMPLE_PEM,
            "signed_url_ttl_seconds": 600,
        }
        r = s.patch(f"{API}/admin/settings", json=payload, headers=auth(admin_tok))
        assert r.status_code == 200, r.text
        body = r.json()
        for k, v in payload.items():
            assert body[k] == v, f"{k}: {body.get(k)} != {v}"

        r2 = s.get(f"{API}/admin/settings", headers=auth(admin_tok))
        assert r2.status_code == 200
        body2 = r2.json()
        for k, v in payload.items():
            assert body2[k] == v


# ============ Public contact-config + contact form ============
class TestContact:
    def test_config_enabled_when_set(self, s, admin_tok):
        s.patch(f"{API}/admin/settings", json={"contact_email": "TEST_support@example.com"}, headers=auth(admin_tok))
        r = s.get(f"{API}/site/contact-config")
        assert r.status_code == 200
        assert r.json() == {"enabled": True}

    def test_config_disabled_when_blank(self, s, admin_tok):
        s.patch(f"{API}/admin/settings", json={"contact_email": ""}, headers=auth(admin_tok))
        r = s.get(f"{API}/site/contact-config")
        assert r.status_code == 200
        assert r.json() == {"enabled": False}

    def test_post_contact_503_when_unconfigured(self, s, admin_tok):
        # ensure blank
        s.patch(f"{API}/admin/settings", json={"contact_email": ""}, headers=auth(admin_tok))
        r = s.post(f"{API}/contact", json={"title": "t", "message": "m", "email": "x@y.z"})
        assert r.status_code == 503, r.text

    def test_post_contact_missing_fields(self, s, admin_tok):
        s.patch(f"{API}/admin/settings", json={"contact_email": "TEST_support@example.com"}, headers=auth(admin_tok))
        r = s.post(f"{API}/contact", json={"title": "", "message": "m", "email": "x@y.z"})
        assert r.status_code == 400
        r2 = s.post(f"{API}/contact", json={"title": "t", "message": "", "email": "x@y.z"})
        assert r2.status_code == 400
        r3 = s.post(f"{API}/contact", json={"title": "t", "message": "m", "email": ""})
        assert r3.status_code == 400

    def test_post_contact_success_and_admin_list_delete(self, s, admin_tok):
        s.patch(f"{API}/admin/settings", json={"contact_email": "TEST_support@example.com"}, headers=auth(admin_tok))
        unique_title = f"TEST_Title_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/contact", json={"title": unique_title, "message": "hello world", "email": "from@user.io"})
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

        # admin list
        r2 = s.get(f"{API}/admin/contact-messages", headers=auth(admin_tok))
        assert r2.status_code == 200
        msgs = r2.json()
        assert isinstance(msgs, list)
        target = next((m for m in msgs if m["title"] == unique_title), None)
        assert target is not None
        assert target["message"] == "hello world"
        assert target["email"] == "from@user.io"
        assert "id" in target and "created_at" in target

        # verify sort desc: first item created_at >= last
        if len(msgs) >= 2:
            assert msgs[0]["created_at"] >= msgs[-1]["created_at"]

        # delete
        r3 = s.delete(f"{API}/admin/contact-messages/{target['id']}", headers=auth(admin_tok))
        assert r3.status_code == 200

        # verify removed
        r4 = s.get(f"{API}/admin/contact-messages", headers=auth(admin_tok))
        assert all(m["id"] != target["id"] for m in r4.json())

    def test_admin_messages_requires_admin(self, s, user_a):
        r = s.get(f"{API}/admin/contact-messages", headers=auth(user_a["token"]))
        assert r.status_code == 403


# ============ Subtitles ============
class TestSubtitles:
    def test_upload_srt_converts_to_vtt(self, s, user_a, video_id):
        srt_path = "/tmp/sub_en.srt"
        _mk_srt(srt_path)
        with open(srt_path, "rb") as f:
            r = s.post(
                f"{API}/videos/{video_id}/subtitles",
                files={"file": ("sub.srt", f, "application/x-subrip")},
                data={"language": "en", "label": "English"},
                headers=auth(user_a["token"]),
            )
        assert r.status_code == 200, r.text
        sub = r.json()
        assert sub["id"]
        assert sub["language"] == "en"
        assert sub["label"] == "English"
        assert sub["format"] == "srt"
        # url should point to a .vtt
        assert sub["url"].endswith(".vtt"), sub["url"]
        # Fetch the vtt content via /api/media/<rel>
        media_url = f"{BASE_URL}/api/media/{sub['url']}"
        rv = s.get(media_url)
        assert rv.status_code == 200, f"fetched {media_url} -> {rv.status_code}"
        assert rv.text.lstrip().startswith("WEBVTT"), rv.text[:100]

        # GET /api/videos/{vid} returns subtitles[]
        rg = s.get(f"{API}/videos/{video_id}")
        assert rg.status_code == 200
        assert any(sx["id"] == sub["id"] for sx in rg.json().get("subtitles", []))
        # save first sub id for later
        s.headers.update({})  # noop
        pytest.first_sub_id = sub["id"]

    def test_subtitle_owner_check(self, s, user_b, video_id):
        srt_path = "/tmp/sub_other.srt"
        _mk_srt(srt_path, idx=1, text="Hi from B")
        with open(srt_path, "rb") as f:
            r = s.post(
                f"{API}/videos/{video_id}/subtitles",
                files={"file": ("sub.srt", f, "application/x-subrip")},
                data={"language": "fr", "label": "French"},
                headers=auth(user_b["token"]),
            )
        assert r.status_code == 403, r.text

    def test_subtitle_format_validation(self, s, user_a, video_id):
        with open("/tmp/notsub.txt", "w") as f:
            f.write("not a subtitle")
        with open("/tmp/notsub.txt", "rb") as f:
            r = s.post(
                f"{API}/videos/{video_id}/subtitles",
                files={"file": ("notsub.txt", f, "text/plain")},
                data={"language": "en", "label": "Bad"},
                headers=auth(user_a["token"]),
            )
        assert r.status_code == 400, r.text

    def test_subtitle_limit_10(self, s, user_a, video_id):
        # Already 1 uploaded. Push to 10, then 11th should fail.
        rg = s.get(f"{API}/videos/{video_id}")
        existing = len(rg.json().get("subtitles", []))
        to_add = 10 - existing
        for i in range(to_add):
            p = f"/tmp/sub_{i}.srt"
            _mk_srt(p, idx=i + 1)
            with open(p, "rb") as f:
                r = s.post(
                    f"{API}/videos/{video_id}/subtitles",
                    files={"file": (f"sub{i}.srt", f, "application/x-subrip")},
                    data={"language": f"l{i}", "label": f"Lang{i}"},
                    headers=auth(user_a["token"]),
                )
            assert r.status_code == 200, f"upload {i} failed: {r.text}"

        # Confirm 10
        rg = s.get(f"{API}/videos/{video_id}")
        assert len(rg.json()["subtitles"]) == 10

        # 11th
        p11 = "/tmp/sub_11.srt"
        _mk_srt(p11, idx=11)
        with open(p11, "rb") as f:
            r11 = s.post(
                f"{API}/videos/{video_id}/subtitles",
                files={"file": ("sub11.srt", f, "application/x-subrip")},
                data={"language": "xx", "label": "Eleventh"},
                headers=auth(user_a["token"]),
            )
        assert r11.status_code == 400, r11.text
        assert "Max 10" in r11.text or "10" in r11.text

    def test_delete_subtitle(self, s, user_a, video_id):
        rg = s.get(f"{API}/videos/{video_id}")
        subs = rg.json().get("subtitles", [])
        assert len(subs) > 0
        sid = subs[0]["id"]
        r = s.delete(f"{API}/videos/{video_id}/subtitles/{sid}",
                     headers=auth(user_a["token"]))
        assert r.status_code == 200, r.text

        rg2 = s.get(f"{API}/videos/{video_id}")
        assert all(sx["id"] != sid for sx in rg2.json().get("subtitles", []))


# ============ Pro signed-URL for subtitles ============
class TestProSignedSubtitles:
    def test_pro_video_subtitle_signed(self, s, admin_tok, user_a, video_id):
        # Convert the test video to Pro tier (admin can update any video)
        r = s.patch(
            f"{API}/videos/{video_id}",
            json={"access_tier": "pro"},
            headers=auth(admin_tok),
        )
        # Uploader update might fail if access_tier change is uploader-only. Try owner.
        if r.status_code != 200:
            r = s.patch(
                f"{API}/videos/{video_id}",
                json={"access_tier": "pro"},
                headers=auth(user_a["token"]),
            )
        assert r.status_code == 200, r.text

        # Ensure at least one subtitle exists
        rg = s.get(f"{API}/videos/{video_id}")
        if not rg.json().get("subtitles"):
            srt_path = "/tmp/sub_pro.srt"
            _mk_srt(srt_path)
            with open(srt_path, "rb") as f:
                ru = s.post(
                    f"{API}/videos/{video_id}/subtitles",
                    files={"file": ("sub.srt", f, "application/x-subrip")},
                    data={"language": "en", "label": "English"},
                    headers=auth(user_a["token"]),
                )
            assert ru.status_code == 200

        # Fetch as ADMIN (admin is pro)
        rr = s.get(f"{API}/videos/{video_id}", headers=auth(admin_tok))
        assert rr.status_code == 200
        body = rr.json()
        # not locked (admin is pro)
        assert not body.get("locked"), body
        subs = body.get("subtitles", [])
        assert len(subs) >= 1
        # URL should be signed: contains ?exp= and sig= for local storage
        url = subs[0]["url"]
        assert ("exp=" in url and "sig=" in url) or url.startswith("https://"), url

        # Revert to free so video can be deleted by owner if needed
        s.patch(f"{API}/videos/{video_id}", json={"access_tier": "free"}, headers=auth(admin_tok))


# ============ Existing flows smoke ============
class TestSmoke:
    def test_categories_listing(self, s):
        r = s.get(f"{API}/categories")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_packages_listing(self, s):
        r = s.get(f"{API}/packages")
        assert r.status_code == 200

    def test_announcements_active(self, s):
        r = s.get(f"{API}/announcements/active")
        assert r.status_code == 200

    def test_admin_stats(self, s, admin_tok):
        r = s.get(f"{API}/admin/stats", headers=auth(admin_tok))
        assert r.status_code == 200
        for k in ["total_videos", "total_users", "total_views", "total_pro_users"]:
            assert k in r.json()

    def test_video_listing(self, s):
        for sec in ["latest", "popular", "random"]:
            r = s.get(f"{API}/videos", params={"section": sec, "limit": 3})
            assert r.status_code == 200


# ============ Final cleanup: reset settings ============
@pytest.fixture(scope="module", autouse=True)
def reset_settings(request, s):
    yield
    try:
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        if r.status_code != 200:
            return
        tok = r.json()["token"]
        # reset per request: contact_email=support@example.com, cloudfront_enabled=false
        requests.patch(
            f"{API}/admin/settings",
            json={
                "contact_email": "support@example.com",
                "cloudfront_enabled": False,
                "cloudfront_domain": "",
                "cloudfront_key_pair_id": "",
                "cloudfront_private_key": "",
                "signed_url_ttl_seconds": 300,
            },
            headers=auth(tok),
        )
        # delete the test video
        vid = getattr(request.node, "_vid", None)
    except Exception as e:  # noqa
        print(f"cleanup warn: {e}")
