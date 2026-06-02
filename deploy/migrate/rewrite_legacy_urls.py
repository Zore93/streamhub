"""Rewrite migrated legacy video URLs (and user avatars/covers) to absolute
Wasabi URLs using the bucket/endpoint settings already configured in Admin →
Storage.

Idempotent: rows that already have absolute http(s) URLs are skipped.

Usage (on the VPS, with the stack up):

    docker exec sh-backend python /app/deploy/migrate/rewrite_legacy_urls.py
    # or to preview without writing:
    docker exec sh-backend python /app/deploy/migrate/rewrite_legacy_urls.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


def _is_remote(u: str | None) -> bool:
    return bool(u) and u.startswith(("http://", "https://"))


def _build_base(settings: dict) -> str:
    """Pick the best base URL: explicit CDN > endpoint/<bucket>."""
    base = (settings.get("wasabi_public_base_url") or "").rstrip("/")
    if base:
        return base
    endpoint = (settings.get("wasabi_endpoint") or "https://s3.wasabisys.com").rstrip("/")
    bucket = (settings.get("wasabi_bucket") or "").strip()
    if not bucket:
        return ""
    return f"{endpoint}/{bucket}"


def _prefix(path: str | None, base: str) -> str | None:
    if not path or _is_remote(path):
        return path
    return f"{base}/{path.lstrip('/')}"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    settings = await db.settings.find_one({"_id": "main"}) or {}
    base = _build_base(settings)
    if not base:
        print("✘ Wasabi not configured (Admin → Settings → Storage). Aborting.",
              file=sys.stderr)
        sys.exit(2)
    print(f"→ Using base URL: {base}")

    v_updated = v_skipped = 0
    async for v in db.videos.find({}, {"_id": 0, "id": 1, "thumbnail_url": 1,
                                       "thumbnail_options": 1, "renditions": 1}):
        upd = {}
        if not _is_remote(v.get("thumbnail_url")):
            new = _prefix(v.get("thumbnail_url"), base)
            if new and new != v.get("thumbnail_url"):
                upd["thumbnail_url"] = new
        opts = v.get("thumbnail_options") or []
        if any(not _is_remote(t) for t in opts):
            upd["thumbnail_options"] = [_prefix(t, base) for t in opts]
        rends = v.get("renditions") or []
        if any(not _is_remote(r.get("url")) for r in rends):
            upd["renditions"] = [{**r, "url": _prefix(r["url"], base)} for r in rends]
        if upd:
            v_updated += 1
            if not args.dry_run:
                await db.videos.update_one({"id": v["id"]}, {"$set": upd})
        else:
            v_skipped += 1
    print(f"✓ videos: rewritten={v_updated}  unchanged={v_skipped}")

    u_updated = u_skipped = 0
    async for u in db.users.find({}, {"_id": 0, "id": 1, "avatar_url": 1, "cover_url": 1}):
        upd = {}
        if u.get("avatar_url") and not _is_remote(u["avatar_url"]):
            upd["avatar_url"] = _prefix(u["avatar_url"], base)
        if u.get("cover_url") and not _is_remote(u["cover_url"]):
            upd["cover_url"] = _prefix(u["cover_url"], base)
        if upd:
            u_updated += 1
            if not args.dry_run:
                await db.users.update_one({"id": u["id"]}, {"$set": upd})
        else:
            u_skipped += 1
    print(f"✓ users : rewritten={u_updated}  unchanged={u_skipped}")
    if args.dry_run:
        print("(--dry-run: no documents were modified)")


if __name__ == "__main__":
    asyncio.run(main())
