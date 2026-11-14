# Iteration 28 helper: seed/check/cleanup TEST_ docs for startup stale-processing cleanup (no age cutoff, iteration 28)
import asyncio, os, sys, json
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
IDS = {"TEST_it28_stale10m": 10, "TEST_it28_fresh2m": 2, "TEST_it28_fresh10s": 0, "TEST_it28_ready3h": 180}


async def main(mode):
    now = datetime.now(timezone.utc)
    if mode == "seed":
        for vid, mins in IDS.items():
            await db.videos.insert_one({
                "id": vid, "title": vid, "status": "ready" if "ready" in vid else "processing",
                "progress": 30, "created_at": (now - timedelta(minutes=mins)).isoformat(),
                "renditions": [], "access_tier": "free",
            })
        print("seeded")
    elif mode == "check":
        for vid in IDS:
            d = await db.videos.find_one({"id": vid}, {"_id": 0, "id": 1, "status": 1, "progress": 1, "error": 1})
            print(json.dumps(d))
    elif mode == "clean":
        r = await db.videos.delete_many({"id": {"$in": list(IDS)}})
        print("deleted", r.deleted_count)

asyncio.run(main(sys.argv[1]))
