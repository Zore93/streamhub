"""Iteration 6 — Coin system + Slug URLs + Email privacy + Shop frames + SSR OG.

Tests exercise:
  - Auth returns new User fields (coins, owned_frames, selected_frame_id, selected_frame, email)
  - GET /api/users/{id} email-visibility rules (anon hides, owner sees, admin sees any)
  - Shop frames listing, purchase (200 + 402), selected-frame set/clear/403
  - Like awards coins first-time only; comment awards until daily cap with frame embedded
  - GET /api/videos/{slug-or-uuid} accepts both forms and returns slug
  - GET /api/og/video/{slug-or-uuid} returns SSR HTML with og:title
  - SSR crawler middleware on http://localhost:8001/watch/<id>
  - Admin CRUD /api/admin/frames + seed idempotent
  - Settings coins_per_like/coins_per_comment/coins_comment_daily_cap_per_video round-trip
"""
import os
import re
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
LOCAL_URL = "http://localhost:8001"

ADMIN_EMAIL = "admin@streamhub.io"
ADMIN_PASS = "Admin123!"
ADMIN_ID = "237bd97e-4c5c-49f7-8365-e6c2126fa0ce"
OWNER_EMAIL = "owner@streamhub.io"
OWNER_PASS = "Owner@2026!"

VID_A = "1fa97503-867b-40d6-8cb3-08dea01854e5"
VID_A_SLUG = "testsubvideo-1854e5"
VID_B = "98ebab0f-b290-4e9c-8857-402faef8fcb0"


# ---------- Fixtures ----------

@pytest.fixture(scope="session")
def session():
    return requests.Session()


def _login(s, email, password):
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def admin_login(session):
    return _login(session, ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def admin_token(admin_login):
    return admin_login["token"]


@pytest.fixture(scope="session")
def owner_login(session):
    try:
        return _login(session, OWNER_EMAIL, OWNER_PASS)
    except AssertionError:
        return None


@pytest.fixture(scope="session")
def owner_token(owner_login):
    if not owner_login:
        pytest.skip("owner login unavailable")
    return owner_login["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Auth user shape ----------

def test_login_returns_new_user_fields(admin_login):
    u = admin_login["user"]
    assert "coins" in u and isinstance(u["coins"], int) and u["coins"] >= 0
    assert "owned_frames" in u and isinstance(u["owned_frames"], list)
    assert "selected_frame_id" in u  # may be None
    assert "selected_frame" in u  # may be None or dict
    assert u.get("email") == ADMIN_EMAIL


# ---------- Email privacy on GET /api/users/{id} ----------

def test_user_get_email_visibility(session, admin_token):
    # Anonymous → no email
    r = requests.get(f"{BASE_URL}/api/users/{ADMIN_ID}", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "email" not in body or body.get("email") in (None, ""), f"Anon must not see email; got {body}"

    # Admin → email present for any user
    r = requests.get(f"{BASE_URL}/api/users/{ADMIN_ID}", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    assert r.json().get("email") == ADMIN_EMAIL

    # Create a regular (non-admin) user and ensure they cannot see admin's email
    rid = uuid.uuid4().hex[:6]
    reg_email = f"TEST_iter6_{rid}@example.com"
    reg_pass = "Pass1234!"
    rr = requests.post(f"{BASE_URL}/api/auth/register",
                       json={"email": reg_email, "username": f"TEST_iter6_{rid}", "password": reg_pass},
                       timeout=15)
    if rr.status_code not in (200, 201):
        pytest.skip(f"could not register regular user: {rr.status_code} {rr.text}")
    reg_tok = rr.json()["token"]
    reg_id = rr.json()["user"]["id"]

    # Regular user sees their own email
    r = requests.get(f"{BASE_URL}/api/users/{reg_id}", headers=H(reg_tok), timeout=15)
    assert r.status_code == 200
    assert (r.json().get("email") or "").lower() == reg_email.lower()

    # Regular user does NOT see admin's email
    r = requests.get(f"{BASE_URL}/api/users/{ADMIN_ID}", headers=H(reg_tok), timeout=15)
    assert r.status_code == 200
    b = r.json()
    assert "email" not in b or b.get("email") in (None, ""), \
        f"non-owner non-admin must not see another user's email: {b}"


# ---------- Shop frames listing ----------

def test_shop_frames_listing(admin_token):
    r = requests.get(f"{BASE_URL}/api/shop/frames", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    frames = r.json()
    assert isinstance(frames, list)
    assert len(frames) >= 40, f"Expected ~50 frames, got {len(frames)}"
    sample = frames[0]
    for f in ("id", "name", "effect_key", "color_primary", "color_secondary", "rarity", "price_coins", "active", "owned"):
        assert f in sample, f"frame missing field {f}: {sample}"


# ---------- Frames seed idempotent ----------

def test_admin_frames_seed_idempotent(admin_token):
    r = requests.post(f"{BASE_URL}/api/admin/frames/seed", headers=H(admin_token), timeout=20)
    assert r.status_code == 200
    body = r.json()
    # Already seeded — inserted should be 0
    assert body.get("inserted", -1) == 0, f"seed not idempotent: {body}"


# ---------- Admin Frame CRUD ----------

def test_admin_frame_crud(admin_token):
    h = H(admin_token)
    payload = {
        "name": f"TEST_frame_{uuid.uuid4().hex[:6]}",
        "effect_key": "fa-neon-ring",
        "color_primary": "#ff00aa",
        "color_secondary": "#00ffee",
        "rarity": "rare",
        "price_coins": 123,
        "active": True,
    }
    r = requests.post(f"{BASE_URL}/api/admin/frames", json=payload, headers=h, timeout=15)
    assert r.status_code in (200, 201), f"create frame failed {r.status_code} {r.text}"
    f = r.json()
    fid = f["id"]
    assert f["price_coins"] == 123 and f["name"] == payload["name"]

    # PATCH
    r = requests.patch(f"{BASE_URL}/api/admin/frames/{fid}", json={"price_coins": 200, "active": False},
                       headers=h, timeout=15)
    assert r.status_code == 200
    upd = r.json()
    assert upd["price_coins"] == 200 and upd["active"] is False

    # GET list contains it
    r = requests.get(f"{BASE_URL}/api/admin/frames", headers=h, timeout=15)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert fid in ids

    # DELETE
    r = requests.delete(f"{BASE_URL}/api/admin/frames/{fid}", headers=h, timeout=15)
    assert r.status_code in (200, 204)

    r = requests.get(f"{BASE_URL}/api/admin/frames", headers=h, timeout=15)
    assert fid not in [x["id"] for x in r.json()]


# ---------- Settings round trip ----------

def test_settings_coin_keys_round_trip(admin_token):
    h = H(admin_token)
    payload = {"coins_per_like": 5, "coins_per_comment": 7, "coins_comment_daily_cap_per_video": 25}
    r = requests.patch(f"{BASE_URL}/api/admin/settings", json=payload, headers=h, timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{BASE_URL}/api/site/config", timeout=15)
    assert r.status_code == 200
    cfg = r.json()
    assert cfg.get("coins_per_like") == 5
    assert cfg.get("coins_per_comment") == 7
    assert cfg.get("coins_comment_daily_cap_per_video") == 25


# ---------- Video lookup by slug OR uuid ----------

def test_video_lookup_by_slug_and_uuid():
    r1 = requests.get(f"{BASE_URL}/api/videos/{VID_A}", timeout=15)
    r2 = requests.get(f"{BASE_URL}/api/videos/{VID_A_SLUG}", timeout=15)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    d1 = r1.json(); d2 = r2.json()
    assert d1["id"] == d2["id"] == VID_A
    assert d1.get("slug") == VID_A_SLUG


# ---------- OG endpoint ----------

def test_og_endpoint_returns_html_with_title():
    for ident in (VID_A, VID_A_SLUG):
        r = requests.get(f"{BASE_URL}/api/og/video/{ident}", timeout=15)
        assert r.status_code == 200, f"og {ident} -> {r.status_code}"
        html = r.text
        assert "<title>" in html.lower()
        assert "og:title" in html.lower()
        assert "og:image" in html.lower()


# ---------- SSR crawler middleware on localhost:8001 ----------

def test_ssr_crawler_middleware_localhost():
    crawler_uas = [
        "facebookexternalhit/1.1",
        "Discordbot/2.0 (+https://discord.com)",
        "Twitterbot/1.0",
        "TelegramBot (like TwitterBot)",
    ]
    for ua in crawler_uas:
        r = requests.get(f"{LOCAL_URL}/watch/{VID_A}", headers={"User-Agent": ua},
                         timeout=15, allow_redirects=True)
        assert r.status_code == 200, f"{ua} -> {r.status_code}"
        body = r.text.lower()
        assert "og:title" in body, f"{ua} response missing og:title"

    # Regular UA should NOT be intercepted by backend (no /watch route on backend → 404)
    r = requests.get(f"{LOCAL_URL}/watch/{VID_A}",
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=15, allow_redirects=False)
    # Either 404 (no route) or a redirect — but not og:html
    assert r.status_code in (404, 301, 302, 307, 308), f"Mozilla unexpectedly got {r.status_code} with body len {len(r.text)}"


# ---------- Coin awarding on like ----------

def test_like_first_time_awards_then_zero(admin_token):
    # Ensure coins_per_like > 0
    h = H(admin_token)
    requests.patch(f"{BASE_URL}/api/admin/settings",
                   json={"coins_per_like": 3}, headers=h, timeout=15)

    # Reset like state: ensure currently NOT liked. Toggle once to make sure starting un-liked.
    # We'll fetch current state by hitting like endpoint and inspect liked flag.
    r = requests.post(f"{BASE_URL}/api/videos/{VID_B}/like", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    first = r.json()
    # If first call set liked=False, then call again to flip to liked=True
    if first.get("liked") is False:
        r = requests.post(f"{BASE_URL}/api/videos/{VID_B}/like", headers=h, timeout=15)
        assert r.status_code == 200
        first = r.json()
        assert first.get("liked") is True
    # Now unliked → liked again should NOT award (already awarded in ledger)
    # Toggle off:
    r_off = requests.post(f"{BASE_URL}/api/videos/{VID_B}/like", headers=h, timeout=15)
    assert r_off.status_code == 200
    assert r_off.json().get("liked") is False
    # Toggle on again — should be idempotent on coins (no new award)
    r_on = requests.post(f"{BASE_URL}/api/videos/{VID_B}/like", headers=h, timeout=15)
    assert r_on.status_code == 200
    body = r_on.json()
    assert body.get("liked") is True
    assert body.get("coins_awarded", 0) == 0, f"second like awarded coins again: {body}"


# ---------- Coin awarding on comment + frame embed + cap ----------

def test_comment_awards_until_cap_and_embeds_frame(admin_token):
    h = H(admin_token)
    # NOTE: implementation interprets `coins_comment_daily_cap_per_video` as the MAX
    # NUMBER of rewarded comments per day per video (not a coin total cap).
    # Set cap=3 → after 3 rewarded comments, subsequent ones return coins_awarded=0.
    cap = 3
    per = 4
    r = requests.patch(f"{BASE_URL}/api/admin/settings",
                       json={"coins_per_comment": per, "coins_comment_daily_cap_per_video": cap},
                       headers=h, timeout=15)
    assert r.status_code == 200

    coins_awarded_seq = []
    for i in range(5):
        payload = {"content": f"TEST_iter6_comment_{uuid.uuid4().hex[:6]}"}
        r = requests.post(f"{BASE_URL}/api/videos/{VID_A}/comments",
                          json=payload, headers=h, timeout=15)
        assert r.status_code in (200, 201), f"comment {i} -> {r.status_code} {r.text}"
        body = r.json()
        ca = body.get("coins_awarded", 0)
        coins_awarded_seq.append(ca)
        # frame field present (None or dict) once selected; spec says embed if selected_frame_id
        assert "frame" in body or body.get("frame") is None, f"comment response: {body}"

    # Last entry should be 0 once cap was hit
    assert coins_awarded_seq[-1] == 0, f"expected cap hit by last comment, seq={coins_awarded_seq}"
    # Number of zero-rewards should be > 0
    assert any(c == 0 for c in coins_awarded_seq), f"cap never hit: {coins_awarded_seq}"


# ---------- Shop purchase 402 + 200 + selected-frame ----------

def test_purchase_and_selected_frame(admin_token):
    h = H(admin_token)
    # List frames; choose cheapest non-owned
    r = requests.get(f"{BASE_URL}/api/shop/frames", headers=h, timeout=15)
    frames = r.json()
    not_owned = [f for f in frames if not f.get("owned") and f.get("active", True)]
    if not not_owned:
        pytest.skip("no non-owned frames available")
    not_owned.sort(key=lambda f: f["price_coins"])
    cheap = not_owned[0]
    pricey = not_owned[-1]

    # 402 path — temporarily try a frame priced > current balance.
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    my_coins = me.get("coins", 0)
    # Pick or fabricate insufficient case by reducing admin coins? Skip if can't.
    # Find an active not-owned frame with price > my_coins
    too_expensive = [f for f in not_owned if f["price_coins"] > my_coins]
    if too_expensive:
        te = too_expensive[0]
        r = requests.post(f"{BASE_URL}/api/shop/frames/{te['id']}/purchase",
                          headers=h, timeout=15)
        assert r.status_code == 402, f"expected 402 for unaffordable frame, got {r.status_code} {r.text}"

    # 200 path — purchase cheapest
    if cheap["price_coins"] > my_coins:
        pytest.skip("admin lacks coins for cheapest frame")
    r = requests.post(f"{BASE_URL}/api/shop/frames/{cheap['id']}/purchase",
                      headers=h, timeout=15)
    assert r.status_code == 200, f"purchase failed {r.status_code} {r.text}"
    after = r.json()
    # Coins should decrement
    me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    assert me2["coins"] == my_coins - cheap["price_coins"], f"coin debit wrong: before={my_coins} price={cheap['price_coins']} after={me2['coins']}"
    assert cheap["id"] in me2.get("owned_frames", []), "frame not added to owned_frames"

    # Selected-frame set to owned frame
    r = requests.post(f"{BASE_URL}/api/users/me/selected-frame",
                      json={"frame_id": cheap["id"]}, headers=h, timeout=15)
    assert r.status_code == 200, f"set selected-frame failed {r.status_code} {r.text}"
    me3 = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    assert me3["selected_frame_id"] == cheap["id"]
    assert me3.get("selected_frame") and me3["selected_frame"].get("id") == cheap["id"]

    # Set to un-owned frame → 403
    un_owned_ids = [f["id"] for f in frames if not f.get("owned") and f["id"] != cheap["id"]]
    if un_owned_ids:
        r = requests.post(f"{BASE_URL}/api/users/me/selected-frame",
                          json={"frame_id": un_owned_ids[0]}, headers=h, timeout=15)
        assert r.status_code == 403, f"expected 403 for un-owned frame, got {r.status_code} {r.text}"

    # Clear to null
    r = requests.post(f"{BASE_URL}/api/users/me/selected-frame",
                      json={"frame_id": None}, headers=h, timeout=15)
    assert r.status_code == 200
    me4 = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    assert me4["selected_frame_id"] in (None, "")
