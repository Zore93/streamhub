#!/usr/bin/env python3
"""Generate / refresh SEO slugs on every Video document.

Run directly (no module syntax needed):

    # On the VPS, inside the backend container:
    docker exec -it sh-backend python /app/scripts/backfill_video_slugs.py

    # During local dev:
    cd /app/backend && python3 scripts/backfill_video_slugs.py

By default, **regenerates the slug for every video** (so truncated slugs
from the previous release become full-length).  Pass `--missing-only` to
restrict to videos that have no slug yet.  Saves the old slug into
`legacy_slug` so previously-shared links keep resolving.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# Make `server` importable no matter where this script is invoked from.
HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from server import db, build_video_slug  # type: ignore  # noqa: E402


async def main(missing_only: bool) -> int:
    if missing_only:
        cur = db.videos.find({"slug": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "title": 1, "slug": 1})
    else:
        cur = db.videos.find({}, {"_id": 0, "id": 1, "title": 1, "slug": 1})
    docs = await cur.to_list(100000)
    print(f"[backfill] Processing {len(docs)} video(s) (missing_only={missing_only}).")
    used: set = set()
    updated = 0
    for d in docs:
        new_slug = await build_video_slug(d.get("title", "") or "", d["id"])
        base = new_slug
        i = 2
        while new_slug in used:
            new_slug = f"{base}-{i}"
            i += 1
        used.add(new_slug)
        upd = {"slug": new_slug}
        # Preserve the previous slug so links shared before this run still
        # resolve via the legacy_slug branch in find_video_by_id_or_slug.
        old_slug = d.get("slug")
        if old_slug and old_slug != new_slug:
            upd["legacy_slug"] = old_slug
        await db.videos.update_one({"id": d["id"]}, {"$set": upd})
        updated += 1
        if updated % 100 == 0:
            print(f"[backfill]   …{updated} so far")
    print(f"[backfill] Done. Updated {updated} document(s).")
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate video slugs.")
    parser.add_argument("--missing-only", action="store_true",
                        help="Only set slug on videos without one (default: regenerate all).")
    args = parser.parse_args()
    asyncio.run(main(args.missing_only))
