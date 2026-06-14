"""Sanity tests for transcoder helpers that don't need a real ffmpeg binary.
Run with:  cd /app/backend && python -m pytest tests/test_subtitle_extract.py -q
"""
import asyncio
from unittest.mock import patch, AsyncMock
import json

from transcoder import probe_video, extract_embedded_subtitles, _LANG_LABELS  # type: ignore


class _FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr

    async def wait(self):
        return self.returncode


def test_probe_video_parses_subtitle_streams(monkeypatch):
    """ffprobe JSON with two embedded subtitle tracks is parsed correctly."""
    payload = {
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
            {"index": 2, "codec_type": "subtitle", "codec_name": "subrip",
             "tags": {"language": "ron", "title": "Romanian"}},
            {"index": 3, "codec_type": "subtitle", "codec_name": "ass",
             "tags": {"language": "jpn", "title": ""}},
            {"index": 4, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle",
             "tags": {"language": "eng"}},  # bitmap → must be parsed, but skipped during extraction
        ],
        "format": {"duration": "12.34"},
    }
    fake = _FakeProc(stdout=json.dumps(payload).encode())

    async def fake_exec(*args, **kw):
        return fake

    with patch("transcoder.asyncio.create_subprocess_exec", side_effect=fake_exec):
        info = asyncio.run(probe_video("/fake.mkv"))
    assert info["width"] == 1280
    assert info["height"] == 720
    assert info["duration"] == 12.34
    subs = info["subtitle_streams"]
    assert len(subs) == 3
    assert {s["codec_name"] for s in subs} == {"subrip", "ass", "hdmv_pgs_subtitle"}
    assert next(s for s in subs if s["codec_name"] == "subrip")["language"] == "ron"


def test_extract_skips_bitmap_subs(tmp_path, monkeypatch):
    """Bitmap subtitle codecs (PGS / DVD) must be ignored — only text subs extracted."""
    streams = [
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip",
         "tags": {"language": "ron", "title": "RoSub"}},
        {"index": 3, "codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle",
         "tags": {"language": "eng"}},
    ]
    payload = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720}] + streams,
               "format": {"duration": "1"}}

    call_log = []

    async def fake_exec(*args, **kw):
        # First call is ffprobe (returns JSON), all subsequent calls are ffmpeg
        # extract commands.  We simulate ffmpeg by creating the output file.
        cmd = args[0]
        if cmd == "ffprobe":
            return _FakeProc(stdout=json.dumps(payload).encode())
        # ffmpeg ... -map 0:<idx> ... output_path
        out_path = args[-1]
        with open(out_path, "w") as f:
            f.write("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n")
        call_log.append(args)
        return _FakeProc(returncode=0)

    with patch("transcoder.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = asyncio.run(
            extract_embedded_subtitles("/fake.mkv", str(tmp_path), "vid1")
        )

    # Exactly one extraction call (subrip), bitmap skipped
    extract_calls = [c for c in call_log if c[0] == "ffmpeg"]
    assert len(extract_calls) == 1, extract_calls
    assert "-map" in extract_calls[0]
    map_arg = extract_calls[0][extract_calls[0].index("-map") + 1]
    assert map_arg == "0:2"  # the subrip stream
    assert len(result) == 1
    assert result[0]["language"] == "ron"
    assert result[0]["label"] == "RoSub"  # title wins over language label


def test_extract_uses_language_label_when_no_title(tmp_path):
    payload = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 640, "height": 360},
            {"index": 2, "codec_type": "subtitle", "codec_name": "subrip",
             "tags": {"language": "ja"}},
        ],
        "format": {"duration": "1"},
    }

    async def fake_exec(*args, **kw):
        cmd = args[0]
        if cmd == "ffprobe":
            return _FakeProc(stdout=json.dumps(payload).encode())
        with open(args[-1], "w") as f:
            f.write("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhi\n")
        return _FakeProc(returncode=0)

    with patch("transcoder.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = asyncio.run(
            extract_embedded_subtitles("/fake.mkv", str(tmp_path), "vid1")
        )
    assert len(result) == 1
    assert result[0]["language"] == "ja"
    assert result[0]["label"] == _LANG_LABELS["ja"]  # "Japanese"
