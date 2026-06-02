"""
Backfill metadata + thumbnails for legacy videos imported from the old
hentairosub.ro database.

For every video in MongoDB that has:
    * status = "ready"
    * empty thumbnail_options / duration_sec == 0 / original_width == 0
this script:
    1. Picks the lowest-resolution rendition URL (fastest to download).
    2. Streams it through ffprobe to fill duration_sec / width / height.
    3. Generates the 10 thumbnails locally (or uploads them to Wasabi).
    4. Persists everything back.

Designed to be **resumable** (idempotent) and **safe to interrupt**: it skips
videos that already have complete metadata, so running it twice is harmless.

Run inside the live backend container so it shares MONGO_URL, UPLOAD_DIR,
ffmpeg and (if configured) Wasabi credentials with the running site:

    docker exec sh-backend python /app/scripts/backfill_metadata.py \
        --batch-size 4 \
        --dry-run            # remove to actually write

Or directly from host with Python 3.11+ if you wire env vars yourself.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app")
from transcoder import generate_thumbnails, probe_video  # noqa: E402
from storage import upload_file as wasabi_upload, wasabi_configured  # noqa: E402

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/app/uploads"))


def _is_remote(u: str) -> bool:
    return u.startswith(("http://", "https://"))


def _local_path(url: str) -> Optional[Path]:
    if _is_remote(url):
        return None
    return UPLOAD_DIR / url.lstrip("/")


async def _fetch_to_temp(url: str) -> Path:
    """Stream a remote video into a temp file and return its path."""
    suffix = Path(urlparse(url).path).suffix or ".mp4"
    tmp = Path(tempfile.mkstemp(suffix=suffix, prefix="bf_")[1])
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as cx:
        async with cx.stream("GET", url) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=1 << 20):
                    f.write(chunk)
    return tmp


def _needs_backfill(v: dict) -> bool:
    return (
        (v.get("duration_sec") or 0) == 0
        or len(v.get("thumbnail_options") or []) < 5
        or (v.get("original_width") or 0) == 0
    )


async def _backfill_one(db, settings: dict, v: dict, dry_run: bool) -> str:
    rendition_url = None
    if v.get("renditions"):
        # smallest rendition by resolution string ordering (240p < 360p < ...)
        order = ["240p", "360p", "480p", "720p", "1080p", "2048p", "4096p"]
        for r in sorted(v["renditions"], key=lambda x: order.index(x["resolution"]) if x["resolution"] in order else 99):
            rendition_url = r["url"]
            break
    if not rendition_url:
        return "skip: no rendition url"

    local = _local_path(rendition_url)
    tmp_to_clean: Optional[Path] = None
    if local and local.exists():
        src_path = local
    else:
        # remote → download to tmp
        try:
            tmp_to_clean = await _fetch_to_temp(rendition_url)
            src_path = tmp_to_clean
        except Exception as e:
            return f"fail: download failed ({e})"

    try:
        info = await probe_video(str(src_path))
        duration = info["duration"]
        width = info["width"]
        height = info["height"]
        if duration <= 0:
            return "fail: ffprobe returned 0 duration"

        thumbs_dir = UPLOAD_DIR / "thumbnails"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_paths = await generate_thumbnails(
            str(src_path), str(thumbs_dir), v["id"], duration, 10
        )
        if not thumb_paths:
            return "fail: thumbnail generation produced 0 frames"

        thumb_urls = []
        use_wasabi = wasabi_configured(settings)
        for tp in thumb_paths:
            rel = f"thumbnails/{Path(tp).name}"
            if use_wasabi:
                url = await wasabi_upload(tp, rel, settings, "image/jpeg")
                if url:
                    thumb_urls.append(url)
                    try: os.remove(tp)
                    except Exception: pass
                else:
                    thumb_urls.append(rel)
            else:
                thumb_urls.append(rel)

        update = {
            "duration_sec": duration,
            "original_width": width,
            "original_height": height,
            "thumbnail_options": thumb_urls,
        }
        # only set primary thumbnail if it wasn't already pointing somewhere useful
        if not v.get("thumbnail_url"):
            update["thumbnail_url"] = thumb_urls[0]

        if dry_run:
            return f"dry-run: would set duration={duration:.1f}s {width}x{height} thumbs={len(thumb_urls)}"
        await db.videos.update_one({"id": v["id"]}, {"$set": update})
        return f"ok: duration={duration:.1f}s {width}x{height} thumbs={len(thumb_urls)}"
    finally:
        if tmp_to_clean and tmp_to_clean.exists():
            try: tmp_to_clean.unlink()
            except Exception: pass


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=4, help="Parallel videos.")
    ap.add_argument("--limit", type=int, default=0, help="Cap total videos processed (0=all).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    settings = await db.settings.find_one({"_id": "main"}) or {}

    cursor = db.videos.find({"status": "ready"}, {"_id": 0})
    todo = []
    async for v in cursor:
        if _needs_backfill(v):
            todo.append(v)
            if args.limit and len(todo) >= args.limit:
                break
    print(f"→ {len(todo)} videos need backfill", flush=True)

    sem = asyncio.Semaphore(max(1, args.batch_size))

    async def runner(vid):
        async with sem:
            res = await _backfill_one(db, settings, vid, args.dry_run)
            print(f"  [{vid['id'][:8]}] {vid['title'][:60]!r}: {res}", flush=True)

    await asyncio.gather(*[runner(v) for v in todo])
    print("✓ backfill complete")


if __name__ == "__main__":
    asyncio.run(main())
