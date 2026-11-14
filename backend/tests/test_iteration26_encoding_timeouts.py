# Iteration 26 – encoding pipeline: ffmpeg timeouts, semaphore release, upload→ready E2E
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")

ADMIN = {"email": "admin@streamhub.io", "password": "Admin123!"}
TINY = "/tmp/tiny.mp4"
TINY2 = "/tmp/tiny2.mp4"
GARBAGE = "/tmp/garbage.mp4"


def _ensure_media():
    if not os.path.exists(TINY):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=duration=3:size=640x360:rate=24", "-f", "lavfi", "-i", "sine=d=3",
                        "-c:v", "libx264", "-c:a", "aac", "-shortest", TINY], check=True)
    if not os.path.exists(TINY2):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=duration=4:size=640x360:rate=24", "-c:v", "libx264", TINY2], check=True)
    if not os.path.exists(GARBAGE):
        with open(GARBAGE, "wb") as f:
            f.write(os.urandom(200000))


@pytest.fixture(scope="module")
def token():
    _ensure_media()
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code} {r.text[:200]}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def created_ids(token):
    ids = []
    yield ids
    for vid in ids:
        try:
            requests.delete(f"{BASE_URL}/api/videos/{vid}",
                            headers={"Authorization": f"Bearer {token}"}, timeout=30)
        except Exception:
            pass


def _upload(token, path, title):
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/videos/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (os.path.basename(path), f, "video/mp4")},
            data={"title": title, "access_tier": "free"},
            timeout=120,
        )
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["status"] == "processing"
    assert "_id" not in d
    return d["id"]


def _wait_terminal(token, vid, timeout=150):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        r = requests.get(f"{BASE_URL}/api/videos/{vid}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        assert r.status_code == 200
        last = r.json()
        if last.get("status") == "failed":
            return last, time.time() - t0
        if last.get("status") == "ready" and last.get("progress") == 100:
            return last, time.time() - t0
        time.sleep(2)
    return last, time.time() - t0


# ---- E2E: single upload reaches ready ----
class TestUploadE2E:
    def test_single_upload_ready(self, token, created_ids):
        vid = _upload(token, TINY, "TEST_enc_single")
        created_ids.append(vid)
        doc, el = _wait_terminal(token, vid)
        print(f"single upload: status={doc.get('status')} progress={doc.get('progress')} t={el:.1f}s")
        assert doc["status"] == "ready", doc.get("error")
        assert doc["progress"] == 100
        assert len(doc.get("renditions") or []) >= 1
        assert doc["renditions"][0]["resolution"] == "360p"
        assert doc.get("preview_url"), "preview clip missing"
        assert el < 120

    # ---- Back-to-back + garbage file: queue must not deadlock ----
    def test_back_to_back_with_garbage(self, token, created_ids):
        g = _upload(token, GARBAGE, "TEST_enc_garbage")
        a = _upload(token, TINY, "TEST_enc_b2b_a")
        b = _upload(token, TINY2, "TEST_enc_b2b_b")
        created_ids.extend([g, a, b])
        da, ta = _wait_terminal(token, a)
        db_, tb = _wait_terminal(token, b)
        dg, tg = _wait_terminal(token, g)
        print(f"a={da['status']} {ta:.1f}s  b={db_['status']} {tb:.1f}s  garbage={dg['status']} err={dg.get('error')!r} {tg:.1f}s")
        assert da["status"] == "ready" and len(da["renditions"]) >= 1
        assert db_["status"] == "ready" and len(db_["renditions"]) >= 1
        assert dg["status"] in ("failed", "ready")

    def test_burst_more_than_concurrency(self, token, created_ids):
        ids = [_upload(token, TINY, f"TEST_enc_burst_{i}") for i in range(5)]
        created_ids.extend(ids)
        results = [_wait_terminal(token, v, timeout=200) for v in ids]
        statuses = [(d["status"], round(t, 1)) for d, t in results]
        print("burst:", statuses)
        assert all(d["status"] == "ready" for d, _ in results)


# ---- Unit: timeouts kill hanging ffmpeg and return False (FIFO input never delivers data) ----
def _make_fifo(tmp_path):
    p = tmp_path / "hang.mp4"
    os.mkfifo(p)
    return str(p)


@pytest.fixture
def short_wait_for(monkeypatch):
    """Cap every asyncio.wait_for timeout to 3s so 90s/600s hard caps can be exercised quickly."""
    orig = asyncio.wait_for
    seen = []

    async def capped(aw, timeout=None):
        seen.append(timeout)
        return await orig(aw, timeout=min(timeout or 3, 3))

    monkeypatch.setattr(asyncio, "wait_for", capped)
    return seen


class TestTimeoutsUnit:
    def test_preview_timeout_kills_and_returns_false(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        out = tmp_path / "prev.mp4"
        t0 = time.time()
        ok = asyncio.run(transcoder.extract_preview_clip(fifo, str(out), 5))
        el = time.time() - t0
        print(f"preview returned {ok} in {el:.1f}s, timeouts requested={short_wait_for}")
        assert ok is False
        assert 90.0 in short_wait_for
        assert el < 20
        r = subprocess.run(["pgrep", "-f", str(fifo)], capture_output=True, text=True)
        assert r.stdout.strip() == "", f"ffmpeg still alive: {r.stdout}"

    def test_transcode_timeout_kills_and_returns_false(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        out = tmp_path / "out_360p.mp4"
        t0 = time.time()
        ok = asyncio.run(transcoder.transcode_to_resolution(fifo, str(out), "360p", "default"))
        el = time.time() - t0
        print(f"transcode returned {ok} in {el:.1f}s, timeouts requested={short_wait_for}")
        assert ok is False
        assert 600.0 in short_wait_for, "expected max(600, dur*20) with unknown duration"
        assert not out.exists()
        assert el < 30
        time.sleep(0.5)
        r = subprocess.run(["pgrep", "-af", "ffmpeg.*hang.mp4"], capture_output=True, text=True)
        leftovers = [l for l in r.stdout.splitlines() if "pgrep" not in l]
        print("leftover procs:", leftovers)

    def test_transcode_timeout_scales_with_duration(self, tmp_path, monkeypatch):
        import transcoder
        orig = asyncio.wait_for
        seen = []

        async def spy(aw, timeout=None):
            seen.append(timeout)
            return await orig(aw, timeout=timeout)

        monkeypatch.setattr(asyncio, "wait_for", spy)
        out = tmp_path / "o.mp4"
        ok = asyncio.run(transcoder.transcode_to_resolution(TINY, str(out), "360p", "default"))
        assert ok is True and out.exists()
        assert 600.0 in seen  # 3s * 20 = 60 < 600 → min clamp

    def test_semaphore_released_after_timeout(self, tmp_path, short_wait_for):
        """Simulate process_video's `async with semaphore` around a hanging transcode."""
        import transcoder
        fifo = _make_fifo(tmp_path)

        async def scenario():
            sem = asyncio.Semaphore(1)

            async def job(src, out):
                async with sem:
                    return await transcoder.transcode_to_resolution(src, out, "360p", "default")

            r1 = await job(fifo, str(tmp_path / "a.mp4"))
            r2 = await asyncio.wait_for(job(TINY, str(tmp_path / "b.mp4")), timeout=60)
            return r1, r2, sem.locked()

        r1, r2, locked = asyncio.run(scenario())
        assert r1 is False and r2 is True and locked is False
