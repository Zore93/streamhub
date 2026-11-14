# Iteration 28 – tier-2/tier-3 intermediate->webvtt ffmpeg conversion timeout + kill (FIFO trick)
import asyncio
import subprocess
import sys
import time

import pytest

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/tests")

from test_iteration26_encoding_timeouts import _make_fifo  # noqa: E402


def _alive(pattern):
    r = subprocess.run(["pgrep", "-af", pattern], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "pgrep" not in l and "pytest" not in l]


def _setup(monkeypatch, tmp_path, cap):
    import transcoder
    fifo = _make_fifo(tmp_path)
    seen_timeouts, calls = [], []
    orig_wait_for = asyncio.wait_for
    orig_exec = asyncio.create_subprocess_exec

    async def capped(aw, timeout=None):
        seen_timeouts.append(timeout)
        return await orig_wait_for(aw, timeout=min(timeout or cap, cap) if cap else timeout)

    async def fake_probe(_p):
        return {"subtitle_streams": [{"index": 2, "codec_name": "subrip", "language": "ro"}]}

    async def fake_extract(src, idx, out, codec_args):
        if codec_args[-1] == "webvtt":
            return "TEST tier1 fail"
        out.write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n\n")  # non-empty intermediate
        return ""

    async def spy_exec(*args, **kw):
        args = list(args)
        if args and args[0] == "ffmpeg" and "-i" in args:
            i = args.index("-i") + 1
            calls.append({"args": list(args), "stdin": kw.get("stdin")})
            args[i] = fifo  # make the intermediate input hang forever
        return await orig_exec(*args, **kw)

    monkeypatch.setattr(asyncio, "wait_for", capped)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy_exec)
    monkeypatch.setattr(transcoder, "probe_video", fake_probe)
    monkeypatch.setattr(transcoder, "_ffmpeg_extract_subtitle", fake_extract)
    return transcoder, fifo, seen_timeouts, calls


def test_tier2_tier3_webvtt_timeout_capped(monkeypatch, tmp_path):
    transcoder, fifo, seen, calls = _setup(monkeypatch, tmp_path, cap=3)
    t0 = time.time()
    res = asyncio.run(transcoder.extract_embedded_subtitles("/nonexistent.mkv", str(tmp_path / "o"), "TEST_it28"))
    el = time.time() - t0
    print(f"res={res} el={el:.1f}s seen={seen} calls={calls}")
    assert res == []
    assert seen.count(60.0) == 2  # tier-2 + tier-3 conversions both guarded
    assert len(calls) == 2
    for c in calls:
        assert "-nostdin" in c["args"]
        assert c["stdin"] == asyncio.subprocess.DEVNULL
        assert "webvtt" in c["args"]
    assert el < 15
    time.sleep(0.3)
    assert _alive(f"ffmpeg.*{fifo}") == []
    # intermediates cleaned up
    assert not list((tmp_path / "o").glob("*.srt"))


def test_tier2_webvtt_real_60s_timeout(monkeypatch, tmp_path):
    """Un-capped: each hanging conversion must be killed at ~60s (2 tiers => ~120s)."""
    transcoder, fifo, seen, calls = _setup(monkeypatch, tmp_path, cap=None)
    t0 = time.time()
    res = asyncio.run(transcoder.extract_embedded_subtitles("/nonexistent.mkv", str(tmp_path / "o"), "TEST_it28r"))
    el = time.time() - t0
    print(f"real: res={res} el={el:.1f}s")
    assert res == [] and 118 <= el < 135
    time.sleep(0.3)
    assert _alive(f"ffmpeg.*{fifo}") == []
