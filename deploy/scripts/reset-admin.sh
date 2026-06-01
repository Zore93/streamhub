#!/usr/bin/env bash
# Reset the admin password on a live deployment.
# Bypasses docker-compose env interpolation by passing the password via
# `docker exec -e` directly to the running backend container.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"

[[ -f "$ENV_FILE" ]] || { echo "Cannot find $ENV_FILE"; exit 1; }

# Read ADMIN_EMAIL from .env without `source` (which would re-interpret $...).
DEFAULT_EMAIL=$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)

read -r -p "Admin email [$DEFAULT_EMAIL]: " email
email=${email:-$DEFAULT_EMAIL}
[[ -n "$email" ]] || { echo "email required"; exit 1; }

read -r -s -p "New password: " pw; echo
read -r -s -p "Confirm:      " pw2; echo
[[ "$pw" == "$pw2" && -n "$pw" ]] || { echo "mismatch/empty"; exit 1; }

docker exec -e EMAIL="$email" -e PW="$pw" sh-backend python - <<'PYEOF'
import asyncio, os, sys
sys.path.insert(0, '/app')
from motor.motor_asyncio import AsyncIOMotorClient
from auth import hash_password
async def main():
    client = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = client[os.environ['DB_NAME']]
    email = os.environ['EMAIL'].lower()
    res = await db.users.update_one(
        {'email': email},
        {'$set': {'password_hash': hash_password(os.environ['PW']),
                  'role': 'admin', 'email_verified': True, 'is_pro': True}},
        upsert=True,
    )
    print('matched=', res.matched_count, 'modified=', res.modified_count,
          'upserted=', res.upserted_id)
asyncio.run(main())
PYEOF
echo "✓ Password reset. Try logging in now."
