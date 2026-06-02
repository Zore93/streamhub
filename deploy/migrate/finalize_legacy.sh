#!/usr/bin/env bash
# Apply post-import fixups to a legacy-migrated MongoDB:
#  - mark <=90s clips as shorts
#  - flip every legacy video to access_tier=pro
set -euo pipefail
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_FILE="$DEPLOY_DIR/migrate/finalize_legacy.py"

echo "→ Dry-run preview"
docker exec -i sh-backend python - --dry-run < "$PY_FILE"
read -r -p "Apply the changes above? [y/N] " yn
[[ "$yn" == "y" || "$yn" == "Y" ]] || { echo "abort"; exit 0; }
docker exec -i sh-backend python - < "$PY_FILE"
echo "✓ Done. Refresh the site."
