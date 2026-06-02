#!/usr/bin/env bash
# collect-bundle.sh — package everything a maintainer needs to diagnose a broken
# StreamHub install into a single redacted .tar.gz that's safe to share.
#
# What goes in:
#   • install-errors.log               (auto-collected by install.sh on failure)
#   • docker compose ps / logs (all containers, tail 500)
#   • docker inspect of every sh-* container
#   • redacted copy of deploy/.env  (passwords / tokens replaced with ***)
#   • redacted MongoDB settings document
#   • OS / kernel / disk / docker version info
#   • output of diagnose-login.sh
#
# Run as:  sudo bash /opt/streamhub/deploy/scripts/collect-bundle.sh
set -uo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
TS=$(date +%Y%m%d_%H%M%S)
BUNDLE_NAME="streamhub-bundle-${TS}"
WORK=$(mktemp -d -t "$BUNDLE_NAME.XXXXXX")
OUT="/opt/streamhub/data/${BUNDLE_NAME}.tar.gz"
mkdir -p "$(dirname "$OUT")"
trap 'rm -rf "$WORK"' EXIT

red()   { printf "\e[31m%s\e[0m\n" "$*"; }
green() { printf "\e[32m%s\e[0m\n" "$*"; }
note()  { printf "  • %s\n" "$*"; }

green "→ Collecting bundle into $OUT"

# 1) System info ─────────────────────────────────────────────────────────────
{
    echo "## System"
    uname -a
    echo
    echo "## OS-release"; cat /etc/os-release 2>/dev/null || true
    echo
    echo "## Disk"; df -h | head -10
    echo
    echo "## Docker"; docker --version 2>&1 || true; docker compose version 2>&1 || true
    echo
    echo "## UFW"; ufw status verbose 2>&1 || true
} > "$WORK/system.txt" 2>&1
note "system info"

# 2) Container snapshot ──────────────────────────────────────────────────────
mkdir -p "$WORK/containers"
{
    docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1 || true
    echo
    docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" ps 2>&1 || true
} > "$WORK/containers/ps.txt"

for c in sh-mongo sh-backend sh-frontend sh-nginx sh-certbot sh-bootstrap-nginx; do
    docker inspect "$c" > "$WORK/containers/${c}-inspect.json" 2>/dev/null || true
    docker logs --tail 500 "$c" > "$WORK/containers/${c}.log" 2>&1 || true
done
note "containers inspected + last 500 log lines for each"

# 3) deploy/.env (REDACTED) ─────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    awk -F= '
        /^MONGO_ROOT_PASSWORD=|^ADMIN_PASSWORD=|^STRIPE_API_KEY=|^JWT_SECRET=/ {
            printf "%s=***REDACTED***\n", $1; next
        }
        { print }
    ' "$ENV_FILE" > "$WORK/env.redacted"
    note ".env (sensitive values redacted)"
fi

# 4) MongoDB settings (REDACTED) ────────────────────────────────────────────
docker exec sh-backend python - > "$WORK/mongo-settings.json" 2>&1 <<'PY' || true
import asyncio, json, os
from motor.motor_asyncio import AsyncIOMotorClient
REDACT = {"jwt_secret","stripe_secret_key","cloudfront_private_key",
          "wasabi_secret_key","smtp_password","github_token"}
async def m():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    s = await db.settings.find_one({'_id':'main'}) or {}
    for k in REDACT:
        if s.get(k):
            s[k] = '***REDACTED***'
    if '_id' in s: s['_id'] = str(s['_id'])
    print(json.dumps(s, indent=2, default=str))
    counts = {}
    for c in ('users','videos','categories','packages','announcements'):
        counts[c] = await db[c].count_documents({})
    print("\n## Collection counts")
    print(json.dumps(counts, indent=2))
asyncio.run(m())
PY
note "MongoDB settings (secrets redacted) + collection counts"

# 5) Install error log ───────────────────────────────────────────────────────
if [[ -f /opt/streamhub/data/install-errors.log ]]; then
    cp /opt/streamhub/data/install-errors.log "$WORK/install-errors.log"
    note "install-errors.log included"
fi

# 6) Diagnose-login dump ─────────────────────────────────────────────────────
bash "$DEPLOY_DIR/scripts/diagnose-login.sh" > "$WORK/diagnose-login.txt" 2>&1 || true
note "diagnose-login.sh output"

# 7) Compose & nginx configs (no secrets) ────────────────────────────────────
mkdir -p "$WORK/config"
cp "$DEPLOY_DIR/docker-compose.yml" "$WORK/config/" 2>/dev/null || true
cp "$DEPLOY_DIR/nginx/streamhub.conf" "$WORK/config/" 2>/dev/null || true
cp "$DEPLOY_DIR/nginx/ssl-params.conf" "$WORK/config/" 2>/dev/null || true

# 8) Manifest ────────────────────────────────────────────────────────────────
{
    echo "Bundle generated: $(date -Iseconds)"
    echo "Hostname:         $(hostname -f 2>/dev/null || hostname)"
    echo "Public IP:        $(curl -fsSL https://api.ipify.org 2>/dev/null || echo unknown)"
    echo "Domain:           $(grep '^DOMAIN=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo unknown)"
    echo
    echo "Contents:"
    (cd "$WORK" && find . -type f -printf '  %p  (%s bytes)\n')
} > "$WORK/MANIFEST.txt"

# 9) Pack ────────────────────────────────────────────────────────────────────
tar czf "$OUT" -C "$(dirname "$WORK")" "$(basename "$WORK")"
SIZE=$(du -h "$OUT" | cut -f1)
green "✓ Bundle ready: $OUT  ($SIZE)"
echo
echo "  Inspect locally:   tar tzvf $OUT | less"
echo "  Send to support :  scp $OUT you@laptop:/tmp/   ← it contains NO plaintext secrets"
echo "                     (passwords, tokens, jwt secret, stripe key are redacted)"
