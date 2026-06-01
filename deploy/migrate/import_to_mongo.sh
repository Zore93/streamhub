#!/usr/bin/env bash
# Import the JSON files produced by parse_legacy_dump.py into a running
# StreamHub MongoDB.  Run AFTER scripts/install.sh has brought the stack up.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "Cannot find $ENV_FILE — install.sh first"; exit 1; }
source <(grep -E '^(DB_NAME|MONGO_ROOT_USER|MONGO_ROOT_PASSWORD)=' "$ENV_FILE")

OUT_DIR="${1:-$DEPLOY_DIR/migrate/out}"
[[ -d "$OUT_DIR" ]] || { echo "Output dir $OUT_DIR missing — run parse_legacy_dump.py first"; exit 1; }

for f in categories users videos; do
    file="$OUT_DIR/$f.json"
    [[ -f "$file" ]] || { echo "skip $f (no file)"; continue; }
    echo "→ importing $f.json into MongoDB.$DB_NAME.$f"
    docker exec -i sh-mongo mongoimport \
        --uri="mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@127.0.0.1:27017/${DB_NAME}?authSource=admin" \
        --collection="$f" \
        --mode=upsert \
        --upsertFields=legacy_id \
        < "$file"
done

echo "✓ Import complete.  Restart backend to refresh caches:  sudo systemctl restart streamhub"
