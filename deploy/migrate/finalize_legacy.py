"""Finalize an already-imported legacy migration in MongoDB:

  * mark videos with duration <= 90 s (or vertical aspect) as `is_short=True`
  * set every legacy-imported video to `access_tier='pro'`

Idempotent — safe to run multiple times.

Usage (on the VPS):

    cd /opt/streamhub
    sudo bash deploy/migrate/finalize_legacy.sh
"""
import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-short-seconds", type=int, default=90)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # legacy_id is set by our migration parser; only operate on those rows.
    legacy_filter = {"legacy_id": {"$exists": True}}

    # 1) Mark shorts (duration <= max-short-seconds)
    short_filter = {**legacy_filter, "duration_sec": {"$lte": args.max_short_seconds, "$gt": 0}}
    n_shorts = await db.videos.count_documents(short_filter)
    print(f"→ Videos with duration <= {args.max_short_seconds}s: {n_shorts}")
    if not args.dry_run:
        r = await db.videos.update_many(short_filter, {"$set": {"is_short": True}})
        print(f"  is_short=True applied to: {r.modified_count}")

    # ensure longer videos are explicitly is_short=false
    long_filter = {**legacy_filter, "duration_sec": {"$gt": args.max_short_seconds}}
    if not args.dry_run:
        r2 = await db.videos.update_many(long_filter, {"$set": {"is_short": False}})
        print(f"  is_short=False applied to: {r2.modified_count}")

    # 2) Force legacy videos to PRO tier
    n_total = await db.videos.count_documents(legacy_filter)
    print(f"→ Total legacy videos: {n_total}")
    if not args.dry_run:
        r3 = await db.videos.update_many(legacy_filter, {"$set": {"access_tier": "pro"}})
        print(f"  access_tier=pro applied to: {r3.modified_count}")

    # 3) Quick stats
    pro_count = await db.videos.count_documents({"access_tier": "pro"})
    short_count = await db.videos.count_documents({"is_short": True})
    long_count = await db.videos.count_documents({"is_short": {"$ne": True}})
    print(f"\n✓ Done.  pro videos: {pro_count} · shorts: {short_count} · long videos: {long_count}")
    if args.dry_run:
        print("(--dry-run: nothing was modified)")


if __name__ == "__main__":
    asyncio.run(main())
