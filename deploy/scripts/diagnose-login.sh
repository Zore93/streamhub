#!/usr/bin/env bash
# Diagnostic helper: tries to login locally with the admin credentials from .env
# and reports exactly why login is rejected (no-such-user vs bad-password vs banned).
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "Cannot find $ENV_FILE"; exit 1; }

EMAIL=$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | head -1 | cut -d= -f2-)
# Read raw password line as-is (no shell interpretation):
PASSWORD=$(grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)

echo "Reading credentials from $ENV_FILE …"
echo "  ADMIN_EMAIL    = $EMAIL"
echo "  ADMIN_PASSWORD = $PASSWORD   (literal value from .env)"

# Show what docker compose ACTUALLY passes to the container after interpolation:
echo
echo "What docker compose would inject (after \$VAR interpolation):"
docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" \
    config 2>/dev/null | grep -A2 -E '^\s+ADMIN' || true

echo
echo "Checking DB for the user…"
docker exec sh-backend python - <<'PY'
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def m():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    users = await db.users.find({'role':'admin'}, {'email':1,'role':1,'is_pro':1,
        'email_verified':1,'banned_until':1,'password_hash':1,'_id':0}).to_list(50)
    if not users:
        print("✘ No admin user in DB at all.")
        return
    for u in users:
        ph = u.pop('password_hash','')
        u['hash_prefix'] = ph[:7]
        print(u)
asyncio.run(m())
PY

echo
echo "Attempting login against http://127.0.0.1 (frontend nginx)…"
RES=$(curl -ks -o /tmp/login.json -w "%{http_code}" -X POST \
    "https://$(grep ^DOMAIN= "$ENV_FILE" | cut -d= -f2)/api/auth/login" \
    -H "Content-Type: application/json" \
    --data-binary "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" || true)
echo "HTTP $RES"
cat /tmp/login.json; echo
case "$RES" in
    200) echo "✓ Login works.";;
    401) echo "✘ 401 Invalid credentials — password in DB does NOT match the .env value. Run: sudo bash $(dirname "$0")/reset-admin.sh";;
    403) echo "✘ 403 — account is verified=false or banned.  Run reset-admin.sh to fix.";;
    *)   echo "✘ Unexpected response. Check: docker compose logs backend";;
esac
