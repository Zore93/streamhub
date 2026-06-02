#!/usr/bin/env bash
# Diagnose "Login failed" on a live StreamHub install.
# Reads .env line-by-line (no shell interpolation), dumps the actual admin
# document in MongoDB, attempts a real curl login, and prints a clear verdict.
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "✘ $ENV_FILE missing"; exit 1; }

env_get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

DOMAIN=$(env_get DOMAIN)
EMAIL=$(env_get ADMIN_EMAIL)
PASSWORD=$(env_get ADMIN_PASSWORD)

echo "════════════════════════════════════════════════════════════════"
echo " StreamHub login diagnosis"
echo "════════════════════════════════════════════════════════════════"
echo " DOMAIN          = $DOMAIN"
echo " ADMIN_EMAIL     = $EMAIL"
echo " ADMIN_PASSWORD  = $PASSWORD   ← literal value as stored in .env"
echo
echo "1) Container & DB state"
echo "──────────────────────────────────────────────────────"
status=$(docker inspect -f '{{.State.Status}}' sh-backend 2>/dev/null || echo "missing")
echo "   sh-backend container: $status"
if [[ "$status" != "running" ]]; then
    echo
    echo "   ✘ Backend is not running. Last 60 lines of logs:"
    echo "──────────────────────────────────────────────────────"
    docker logs --tail 60 sh-backend 2>&1 || true
    echo
    echo "   Try: cd $DEPLOY_DIR && sudo docker compose --env-file .env logs -f backend"
    exit 1
fi

docker exec sh-backend python - <<'PY' 2>&1 || true
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def m():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    n_users = await db.users.count_documents({})
    print(f"   users total           : {n_users}")
    admins = await db.users.find({'role':'admin'}, {'email':1,'is_pro':1,
        'email_verified':1,'banned_until':1,'password_hash':1,'id':1,'_id':0}).to_list(50)
    print(f"   admin docs            : {len(admins)}")
    for a in admins:
        a['password_hash_prefix'] = (a.pop('password_hash','') or '')[:10] or 'NONE'
        print("    ", a)
asyncio.run(m())
PY

echo
echo "2) Live login test against https://$DOMAIN/api/auth/login"
echo "──────────────────────────────────────────────────────"
BODY=$(E="$EMAIL" P="$PASSWORD" python3 -c "import json,os; print(json.dumps({'email':os.environ['E'],'password':os.environ['P']}))")
HTTP=$(curl -sk -o /tmp/dl.json -w "%{http_code}" -X POST "https://$DOMAIN/api/auth/login" \
    -H "Content-Type: application/json" --data-binary "$BODY")
echo "   HTTP $HTTP"
echo "   body: $(cat /tmp/dl.json 2>/dev/null)"
rm -f /tmp/dl.json
echo
case "$HTTP" in
    200) echo "✓ Login WORKS. If your browser still fails, hard-refresh (Ctrl-Shift-R) and clear localStorage.";;
    401) echo "✘ Wrong password — the bcrypt hash in DB doesn't match what's in .env.";
         echo "  → Fix: sudo bash $DEPLOY_DIR/scripts/reset-admin.sh";;
    403) echo "✘ 403 — account is banned or not email-verified.";
         echo "  → Fix: sudo bash $DEPLOY_DIR/scripts/reset-admin.sh   (it sets email_verified=true)";;
    429) echo "✘ Rate-limited. Wait the configured window (default 5 min) and retry, or lower the limit in Admin → Settings → Auth security.";;
    000) echo "✘ Network unreachable — DNS / SSL / nginx not up.";;
    5*)  echo "✘ Server error — check: docker compose -f $DEPLOY_DIR/docker-compose.yml logs backend";;
    *)   echo "? Unexpected status.";;
esac
