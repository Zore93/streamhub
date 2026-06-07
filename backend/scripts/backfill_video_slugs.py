"""One-off script: backfill `slug` on every Video document that has none.

Run after upgrading to the SEO-slug release:

    cd /app/backend
    python -m scripts.backfill_video_slugs

Idempotent — only sets `slug` when missing/empty.  Includes a collision
fallback (`-2`, `-3`, …) on the off-chance two videos hash to the same UUID
suffix.
"""
import asyncio
import sys
from pathlib import Path

# Allow running from anywhere in the repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import db, build_video_slug  # type: ignore  # noqa: E402


async def main():
    cur = db.videos.find({"slug": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "title": 1})
    docs = await cur.to_list(100000)
    print(f"Backfilling {len(docs)} videos with no slug...")
    used = set(s for s in (await db.videos.distinct("slug")) if s)
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
            print(f"  …{updated}")
    print(f"Done. Updated {updated} documents.")


if __name__ == "__main__":
    asyncio.run(main())
