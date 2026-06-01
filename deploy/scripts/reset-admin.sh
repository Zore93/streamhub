#!/usr/bin/env bash
# Reset the admin password on a live deployment.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"

[[ -f "$ENV_FILE" ]] || { echo "Cannot find $ENV_FILE"; exit 1; }
source <(grep -E '^(ADMIN_EMAIL|DB_NAME|MONGO_ROOT_USER|MONGO_ROOT_PASSWORD)=' "$ENV_FILE")

read -r -p "Admin email [${ADMIN_EMAIL}]: " email
email=${email:-$ADMIN_EMAIL}
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
    res = await db.users.update_one(
        {'email': os.environ['EMAIL'].lower()},
        {'$set': {'password_hash': hash_password(os.environ['PW']),
                  'role': 'admin', 'email_verified': True}},
        upsert=False,
    )
    print('matched=', res.matched_count, 'modified=', res.modified_count)
asyncio.run(main())
PYEOF
echo "Done."
