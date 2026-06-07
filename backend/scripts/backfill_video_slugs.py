#!/usr/bin/env python3
"""Backfill SEO slugs on every Video document that has none.

Run directly (no module syntax needed):

    # On the VPS, inside the backend container:
    docker exec -it streamhub-backend python /app/scripts/backfill_video_slugs.py

    # During local dev:
    cd /app/backend && python3 scripts/backfill_video_slugs.py

Idempotent — only sets `slug` when missing/empty.  Includes a `-2`, `-3`, …
collision fallback on the off-chance two videos hash to the same UUID suffix.
"""
import asyncio
import os
import sys
from pathlib import Path

# Make `server` importable no matter where this script is invoked from.
# We assume this file lives at .../backend/scripts/backfill_video_slugs.py
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Also chdir there so any relative paths (e.g. .env loading) work.
os.chdir(BACKEND_DIR)

from server import db, build_video_slug  # type: ignore  # noqa: E402


async def main() -> int:
    cur = db.videos.find({"slug": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "title": 1})
    docs = await cur.to_list(100000)
    print(f"[backfill] Found {len(docs)} videos with no slug.")
    used = {s for s in (await db.videos.distinct("slug")) if s}
    updated = 0
    for d in docs:
        slug = await build_video_slug(d.get("title", "") or "", d["id"])
        base = slug
        i = 2
        while slug in used:
            slug = f"{base}-{i}"
            i += 1
        used.add(slug)
        await db.videos.update_one({"id": d["id"]}, {"$set": {"slug": slug}})
        updated += 1
        if updated % 100 == 0:
            print(f"[backfill]   …{updated} updated so far")
    print(f"[backfill] Done. Updated {updated} document(s).")
    return updated


if __name__ == "__main__":
    asyncio.run(main())
