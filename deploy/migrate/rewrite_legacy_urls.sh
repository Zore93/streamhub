#!/usr/bin/env bash
# Rewrite all migrated legacy URLs (thumbnails / videos / avatars / covers)
# to absolute Wasabi URLs using the bucket + endpoint already configured in
# Admin → Storage. Safe to run multiple times.
set -euo pipefail

echo "→ Dry-run preview"
docker exec -i sh-backend python /app/deploy/migrate/rewrite_legacy_urls.py --dry-run

read -r -p "Apply the changes above? [y/N] " yn
[[ "$yn" == "y" || "$yn" == "Y" ]] || { echo "abort"; exit 0; }

echo "→ Applying"
docker exec -i sh-backend python /app/deploy/migrate/rewrite_legacy_urls.py
echo "✓ Done. Refresh the site (Ctrl-Shift-R) and the thumbnails + videos should appear."
