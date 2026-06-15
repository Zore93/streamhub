"""Unit tests for the chunked-upload janitor / cleanup logic."""
import asyncio
import os
import sys
import time
from pathlib import Path

# Make `server` importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

import server  # type: ignore  # noqa: E402


def _make_pending(upload_id: str, *, age_seconds: float = 0) -> Path:
    """Create a synthetic pending upload directory with state.json + blob."""
    d = server.CHUNKS_DIR / upload_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "blob").write_bytes(b"x" * 128)
    server._write_chunk_state(upload_id, {
        "upload_id": upload_id,
        "user_id": "test-user",
        "filename": f"{upload_id}.mp4",
        "total_size": 1024,
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(d, (old, old))
    return d


def test_scan_chunk_uploads_returns_pending():
    # Clear out anything from previous runs
    if server.CHUNKS_DIR.exists():
        for child in server.CHUNKS_DIR.iterdir():
            if child.is_dir():
                server._purge_chunk_upload(child.name)

    _make_pending("fresh-1")
    _make_pending("stale-1", age_seconds=48 * 3600)  # 48h ago
    items = server._scan_chunk_uploads()
    ids = {i["upload_id"] for i in items}
    assert "fresh-1" in ids and "stale-1" in ids
    stale = next(i for i in items if i["upload_id"] == "stale-1")
    fresh = next(i for i in items if i["upload_id"] == "fresh-1")
    assert stale["stale"] is True
    assert fresh["stale"] is False


def test_cleanup_only_removes_stale():
    if server.CHUNKS_DIR.exists():
        for child in server.CHUNKS_DIR.iterdir():
            if child.is_dir():
                server._purge_chunk_upload(child.name)

    _make_pending("keep-me")
    _make_pending("kill-me", age_seconds=48 * 3600)
    purged = server._cleanup_stale_chunks(max_age_hours=24)
    assert purged == 1
    remaining = {c.name for c in server.CHUNKS_DIR.iterdir() if c.is_dir()}
    assert "keep-me" in remaining
    assert "kill-me" not in remaining
    # Final cleanup
    server._purge_chunk_upload("keep-me")


def test_finish_purges_chunks_on_success(monkeypatch):
    """The /finish endpoint must remove the chunk staging dir on a happy path."""
    upload_id = "happy-path"
    _make_pending(upload_id)
    blob = server._chunk_blob_path(upload_id)
    # Make the blob's size equal to total_size so finish doesn't 400
    blob.write_bytes(b"x" * 1024)

    # Mock out DB write + background task scheduling
    async def fake_insert_one(_d):
        return type("R", (), {"inserted_id": "x"})()
    monkeypatch.setattr(server.db.videos, "insert_one", fake_insert_one)

    class _BG:
        def add_task(self, *_a, **_kw):
            pass

    payload = {"title": "Test", "tags": "a,b"}
    user = {"id": "test-user", "username": "tester"}
    asyncio.run(server.upload_video_finish(upload_id, payload, _BG(), user))

    # The chunk staging directory should be GONE
    assert not (server.CHUNKS_DIR / upload_id).exists()
