#!/usr/bin/env bash
# Rewrite all migrated legacy URLs (thumbnails / videos / avatars / covers)
# to absolute Wasabi URLs using the bucket + endpoint already configured in
# Admin → Storage. Safe to run multiple times.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_FILE="$DEPLOY_DIR/migrate/rewrite_legacy_urls.py"
[[ -f "$PY_FILE" ]] || { echo "✘ $PY_FILE not found"; exit 1; }

echo "→ Dry-run preview"
docker exec -i sh-backend python - --dry-run < "$PY_FILE"

read -r -p "Apply the changes above? [y/N] " yn
[[ "$yn" == "y" || "$yn" == "Y" ]] || { echo "abort"; exit 0; }

echo "→ Applying"
docker exec -i sh-backend python - < "$PY_FILE"
echo "✓ Done. Refresh the site (Ctrl-Shift-R) and the thumbnails + videos should appear."
