#!/usr/bin/env bash
# Reset / re-create the admin user on a live deployment.
# Wipes any document with that email and writes a fresh, fully-formed User
# document (all required fields populated) using bcrypt. Verifies by counting
# matching docs and aborts with exit-1 if the insert silently failed.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "✘ Cannot find $ENV_FILE — run install.sh first"; exit 1; }

DEFAULT_EMAIL=$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2- || true)
read -r -p "Admin email [$DEFAULT_EMAIL]: " email
email=${email:-$DEFAULT_EMAIL}
[[ -n "$email" ]] || { echo "email required"; exit 1; }

read -r -s -p "New password: " pw; echo
read -r -s -p "Confirm:      " pw2; echo
[[ "$pw" == "$pw2" && -n "$pw" ]] || { echo "✘ password mismatch/empty"; exit 1; }

# Verify the backend container is up before we touch it
if ! docker inspect sh-backend >/dev/null 2>&1; then
    echo "✘ Container 'sh-backend' not found. Is the stack running? Try: sudo systemctl status streamhub"
    exit 1
fi

set +e
OUT=$(docker exec -e EMAIL="$email" -e PW="$pw" sh-backend python - <<'PYEOF' 2>&1
import asyncio, os, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/app')
from motor.motor_asyncio import AsyncIOMotorClient
from auth import hash_password
async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    email = os.environ['EMAIL'].lower()
    deleted = (await db.users.delete_many({'email': email})).deleted_count
    doc = {
        'id': str(uuid.uuid4()),
        'email': email,
        'username': email.split('@')[0],
        'password_hash': hash_password(os.environ['PW']),
        'role': 'admin', 'is_pro': True, 'email_verified': True,
        'pro_package_id': None, 'pro_expires_at': None,
        'verify_token': None, 'avatar_url': None, 'cover_url': None,
        'bio': None, 'banned_until': None, 'banned_reason': None,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    count = await db.users.count_documents({'email': email})
    print(f"deleted_existing={deleted}  inserted_id={doc['id']}  docs_with_email={count}  bcrypt_prefix={doc['password_hash'][:7]}")
asyncio.run(main())
PYEOF
)
RC=$?
set -e

echo "$OUT"
[[ $RC -eq 0 ]] || { echo "✘ docker exec failed (rc=$RC)"; exit 1; }
echo "$OUT" | grep -q "docs_with_email=1" || { echo "✘ User was not actually inserted — check the python output above"; exit 1; }

# Optional smoke-test against the local API
DOMAIN=$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2-)
if [[ -n "$DOMAIN" ]]; then
    echo
    echo "→ Verifying login via https://$DOMAIN/api/auth/login …"
    BODY=$(python3 -c "import json,os,sys; print(json.dumps({'email':os.environ['E'],'password':os.environ['P']}))" E="$email" P="$pw")
    HTTP=$(curl -sk -o /tmp/r.json -w "%{http_code}" -X POST "https://$DOMAIN/api/auth/login" \
        -H "Content-Type: application/json" --data-binary "$BODY")
    if [[ "$HTTP" == "200" ]]; then
        echo "✓ Login OK — admin is ready to use."
    else
        echo "✘ Login still returns HTTP $HTTP — body: $(cat /tmp/r.json)"
        exit 1
    fi
fi
