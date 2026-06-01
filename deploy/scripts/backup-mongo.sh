#!/usr/bin/env bash
# One-off MongoDB dump.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
source <(grep -E '^(DB_NAME|MONGO_ROOT_USER|MONGO_ROOT_PASSWORD)=' "$ENV_FILE")

OUT="$DEPLOY_DIR/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"

docker exec sh-mongo mongodump \
    --authenticationDatabase admin \
    -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" \
    --db "$DB_NAME" --archive --gzip > "$OUT/$DB_NAME.archive.gz"

echo "Dump written to $OUT/$DB_NAME.archive.gz"
