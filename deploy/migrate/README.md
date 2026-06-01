# Migrating from a legacy WoWonder / hentairosub.ro deployment

This folder converts a phpMyAdmin **MySQL/MariaDB** dump from the legacy site
into MongoDB-ready JSON files that match the StreamHub schema, then imports
them into your fresh StreamHub install.

## What gets migrated

| Legacy table                       | Destination | Notes                                                              |
| ---------------------------------- | ----------- | ------------------------------------------------------------------ |
| `users`                            | `users`     | Email, username, password (bcrypt `$2y$`→`$2b$`), avatar, cover, admin role, is_pro, pro expiry, verified flag. |
| `langs` (rows with `type=category`) | `categories` | The legacy app stores categories inside the language strings table — this is the WoWonder convention. We pick `english` as canonical name and create a slug. |
| `videos`                           | `videos`    | Title, description, tags, thumbnail, duration, views, uploader, category, **all enabled resolutions** (240p/360p/480p/720p/1080p/2048p/4096p) — flagged columns are expanded into `renditions[]` using the `_<res>_converted.mp4` naming convention. |

User IDs and category IDs are remapped to UUIDs; the original integers are
preserved in `legacy_id` on every document so the foreign-key relationships
(uploader_id, category_id) are correctly relinked.

## One-time conversion

```bash
# On any machine with python 3.10+
python3 deploy/migrate/parse_legacy_dump.py \
    --sql /path/to/loadingv_video.sql \
    --out-dir ./migration_out \
    --wasabi-base-url "https://s3.eu-central-2.wasabisys.com/your-bucket"   # optional
```

Flags:
- `--wasabi-base-url` — if you migrate the relative `video_location` paths
  (e.g. `upload/videos/.../foo_360p_converted.mp4`) onto Wasabi at a known
  base, prepend it so all rendition URLs become absolute and play immediately.
- `--include-only-active` — skip un-approved / soft-deleted rows.

Outputs (in `--out-dir`):

```
users.json          one JSON document per line (NDJSON)
categories.json
videos.json
legacy_id_maps.json  legacy_int_id → new_uuid for users & categories + counts
```

## Import on the VPS

After running `scripts/install.sh` (the StreamHub installer):

```bash
# Copy the migration_out folder onto the VPS, e.g. via scp:
scp -r ./migration_out root@vps:/opt/streamhub/deploy/migrate/out

# Then on the VPS:
sudo bash /opt/streamhub/deploy/migrate/import_to_mongo.sh
```

The import is **idempotent** (upserts by `legacy_id`) so it's safe to re-run.

## Pre-converted data for the user-supplied dump

`streamhub_migration_data.tar.gz` (in this folder) **already contains** the
three NDJSON files produced from your `loadingv_video.sql`:

- 2 544 users (passwords intact, bcrypt-verified)
- 19 categories (Romanian names: Alien, Demoni, JAV ROSub, etc.)
- 1 420 videos (with renditions linked to their Wasabi paths)

To use it directly on the VPS:

```bash
tar xzf streamhub_migration_data.tar.gz -C /opt/streamhub/deploy/migrate/
mv /opt/streamhub/deploy/migrate/streamhub_migration_data /opt/streamhub/deploy/migrate/out
sudo bash /opt/streamhub/deploy/migrate/import_to_mongo.sh
```

## Verifying after import

```bash
docker exec sh-backend python - <<PY
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def m():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for c in ("users", "categories", "videos"):
        print(c, await db[c].count_documents({}))
asyncio.run(m())
PY
```

Then open `https://<your-domain>/admin` → **Dashboard** to confirm counts.

## Caveats

- Original site uses MariaDB-specific datetime formats — we coerce
  `time` (unix epoch) into ISO-8601 UTC.
- `video_location` in the dump was the **360p converted** filename; flagged
  resolutions are *assumed* present at the conventional sibling filename
  (`…_720p_converted.mp4` etc). If your Wasabi bucket only has a subset, the
  player still works (it just skips broken sources via standard HTML5
  fallback). Run `parse_legacy_dump.py` again with adjusted naming if your
  layout differs.
- `password_hash` is preserved verbatim — the **first** time a user logs in
  with their old password it will validate successfully (bcrypt `$2y$` and
  `$2b$` are byte-identical). No password reset needed.
- Subtitles are **not** in the legacy dump — they can be uploaded after the
  migration via the new Edit Video page.
