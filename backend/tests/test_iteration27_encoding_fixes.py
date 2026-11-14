# Iteration 27 – retest of encoding pipeline fixes: failed-on-zero-renditions, probe/thumb/subtitle timeouts, orphan ffprobe kill
import asyncio
import os
import subprocess
import sys
import time

import pytest
import requests

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/tests")

from test_iteration26_encoding_timeouts import (  # noqa: E402
    BASE_URL, ADMIN, TINY, GARBAGE, _ensure_media, _upload, _wait_terminal, _make_fifo,
)


def _alive(pattern):
    r = subprocess.run(["pgrep", "-af", pattern], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "pgrep" not in l and "pytest" not in l]


@pytest.fixture(scope="module")
def token():
    _ensure_media()
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip("admin login failed")
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


@pytest.fixture
def short_wait_for(monkeypatch):
    orig = asyncio.wait_for
    seen = []

    async def capped(aw, timeout=None):
        seen.append(timeout)
        return await orig(aw, timeout=min(timeout or 3, 3))

    monkeypatch.setattr(asyncio, "wait_for", capped)
    return seen


# ---- (a) garbage upload ends as failed, not ready ----
class TestGarbageFails:
    def test_garbage_upload_status_failed(self, token, created_ids):
        g = _upload(token, GARBAGE, "TEST_it27_garbage")
        created_ids.append(g)
        doc, el = _wait_terminal(token, g, timeout=200)
        print(f"garbage: status={doc.get('status')} progress={doc.get('progress')} err={doc.get('error')!r} "
              f"renditions={doc.get('renditions')} t={el:.1f}s")
        assert doc["status"] == "failed"
        assert doc.get("progress") == 0
        assert doc.get("error") == "all renditions failed or timed out"
        assert not doc.get("renditions")

    def test_valid_upload_still_ready(self, token, created_ids):
        v = _upload(token, TINY, "TEST_it27_valid")
        created_ids.append(v)
        doc, el = _wait_terminal(token, v)
        print(f"valid: status={doc['status']} rend={len(doc.get('renditions') or [])} preview={doc.get('preview_url')} t={el:.1f}s")
        assert doc["status"] == "ready" and doc["progress"] == 100
        assert len(doc["renditions"]) >= 1
        assert doc.get("preview_url")
        assert not doc.get("error")

    def test_burst_5_all_terminal(self, token, created_ids):
        ids = [_upload(token, TINY, f"TEST_it27_burst_{i}") for i in range(5)]
        created_ids.extend(ids)
        res = [_wait_terminal(token, v, timeout=240) for v in ids]
        print("burst:", [(d["status"], round(t, 1)) for d, t in res])
        assert all(d["status"] in ("ready", "failed") for d, _ in res)
        assert all(d["status"] == "ready" for d, _ in res)


# ---- (b,c,d) FIFO-hang timeouts ----
class TestFifoTimeouts:
    def test_probe_timeout(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        t0 = time.time()
        info = asyncio.run(transcoder.probe_video(fifo))
        el = time.time() - t0
        print(f"probe -> {info} in {el:.1f}s seen={short_wait_for}")
        assert 30.0 in short_wait_for
        assert info["duration"] == 0 and info["width"] == 0
        assert el < 20
        time.sleep(0.3)
        assert _alive(f"ffprobe.*{fifo}") == []

    def test_subtitle_extract_timeout(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        out = tmp_path / "s.vtt"
        t0 = time.time()
        r = asyncio.run(transcoder._ffmpeg_extract_subtitle(fifo, 2, out, ["-c:s", "webvtt"]))
        el = time.time() - t0
        print(f"subtitle extract -> {r!r} in {el:.1f}s seen={short_wait_for}")
        assert r == "TIMEOUT"
        assert 120.0 in short_wait_for
        assert el < 15
        time.sleep(0.3)
        assert _alive(f"ffmpeg.*{fifo}") == []

    def test_thumbnail_timeout(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        t0 = time.time()
        paths = asyncio.run(transcoder.generate_thumbnails(fifo, str(tmp_path / "th"), "TEST_x", 10, 3))
        el = time.time() - t0
        print(f"thumbs -> {paths} in {el:.1f}s seen={short_wait_for}")
        assert paths == []
        assert short_wait_for.count(30.0) == 3
        assert el < 20
        time.sleep(0.3)
        assert _alive(f"ffmpeg.*{fifo}") == []

    def test_thumbnail_real_30s_timeout(self, tmp_path):
        """Un-capped: one hanging thumbnail must be killed at ~30s."""
        import transcoder
        fifo = _make_fifo(tmp_path)
        t0 = time.time()
        paths = asyncio.run(transcoder.generate_thumbnails(fifo, str(tmp_path / "th"), "TEST_y", 10, 1))
        el = time.time() - t0
        print(f"real thumb timeout {el:.1f}s")
        assert paths == [] and 29 <= el < 40

    def test_transcode_orphan_ffprobe_killed(self, tmp_path, short_wait_for):
        import transcoder
        fifo = _make_fifo(tmp_path)
        out = tmp_path / "o.mp4"
        ok = asyncio.run(transcoder.transcode_to_resolution(fifo, str(out), "360p", "default"))
        print(f"transcode -> {ok} seen={short_wait_for}")
        assert ok is False
        assert 15 in short_wait_for and 600.0 in short_wait_for
        time.sleep(0.5)
        left = _alive(f"(ffprobe|ffmpeg).*{fifo}")
        print("leftover:", left)
        assert left == []
