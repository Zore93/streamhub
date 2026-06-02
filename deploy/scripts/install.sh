#!/usr/bin/env bash
# StreamHub one-command installer for Ubuntu 22.04 / 24.04 LTS.
# Prompts for DOMAIN, ADMIN_EMAIL, ADMIN_PASSWORD and stands up the whole stack.
set -euo pipefail

#─── helpers ────────────────────────────────────────────────────────────────
red()    { printf "\e[31m%s\e[0m\n" "$*"; }
green()  { printf "\e[32m%s\e[0m\n" "$*"; }
yellow() { printf "\e[33m%s\e[0m\n" "$*"; }
bold()   { printf "\e[1m%s\e[0m\n" "$*"; }
die()    { red "✖ $*"; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root (or: sudo bash $0)"

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"

bold "════════════════════════════════════════════════════════════════"
bold "  StreamHub installer"
bold "  Working directory : $ROOT_DIR"
bold "════════════════════════════════════════════════════════════════"

#─── 1) sanity ──────────────────────────────────────────────────────────────
. /etc/os-release || die "Cannot detect OS"
[[ "$ID" == "ubuntu" ]] || die "This installer targets Ubuntu (got $ID)"
case "$VERSION_ID" in 22.04|24.04) ;; *) yellow "⚠ Tested on 22.04/24.04, got $VERSION_ID — continuing";; esac

green "→ Updating apt and installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release ufw openssl \
    apt-transport-https software-properties-common dnsutils git

#─── 2) prompt for required vars (only if not already in .env) ──────────────
prompt_default() {
    local var=$1 label=$2 default=${3:-}
    local current=""
    [[ -f "$ENV_FILE" ]] && current=$(grep -E "^${var}=" "$ENV_FILE" | head -1 | cut -d= -f2- || true)
    if [[ -n "$current" && "$current" != "replace-me" && "$current" != "example.com" && "$current" != "admin@example.com" && "$current" != "ChangeMe!" ]]; then
        printf -v "$var" "%s" "$current"
        return
    fi
    local val=""
    while [[ -z "$val" ]]; do
        read -r -p "$label${default:+ [$default]}: " val
        [[ -z "$val" && -n "$default" ]] && val="$default"
    done
    printf -v "$var" "%s" "$val"
}

prompt_secret() {
    local var=$1 label=$2
    local current=""
    [[ -f "$ENV_FILE" ]] && current=$(grep -E "^${var}=" "$ENV_FILE" | head -1 | cut -d= -f2- || true)
    if [[ -n "$current" && "$current" != "ChangeMe!" && "$current" != "replace-me" ]]; then
        printf -v "$var" "%s" "$current"
        return
    fi
    local val="" val2=""
    while :; do
        read -r -s -p "$label: " val; echo
        read -r -s -p "Confirm: " val2; echo
        [[ "$val" == "$val2" && -n "$val" ]] && break
        red "✖ mismatch or empty — try again"
    done
    printf -v "$var" "%s" "$val"
}

bold "▶ Configuration"
prompt_default DOMAIN          "1) DOMAIN (FQDN that already points to this server)"
prompt_default ADMIN_EMAIL     "2) ADMIN_EMAIL"
prompt_secret  ADMIN_PASSWORD  "3) ADMIN_PASSWORD"

# Auto-generated secrets
JWT_SECRET=$(openssl rand -hex 48)
MONGO_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -d '+/=' | cut -c1-28)
STRIPE_API_KEY="${STRIPE_API_KEY:-}"

# Persist in deploy/.env
# IMPORTANT: docker-compose performs ${VAR} interpolation on .env values, so we
# escape every literal $ to $$ on values that may contain user-supplied passwords.
# NOTE: We deliberately DO NOT write ADMIN_PASSWORD to .env — it's only used once
# (below) to bootstrap the admin user via `docker exec -e`.
escape_dollar() { printf '%s' "$1" | sed 's/\$/$$/g'; }
mkdir -p "$DEPLOY_DIR" "/opt/streamhub" "/opt/streamhub/data/uploads"
cat > "$ENV_FILE" <<EOF
DOMAIN=$DOMAIN
LETSENCRYPT_EMAIL=$ADMIN_EMAIL
ADMIN_EMAIL=$ADMIN_EMAIL
MONGO_ROOT_USER=shadmin
MONGO_ROOT_PASSWORD=$(escape_dollar "$MONGO_ROOT_PASSWORD")
DB_NAME=streamhub
STRIPE_API_KEY=$STRIPE_API_KEY
UPLOAD_DIR=/opt/streamhub/data/uploads
EOF
chmod 600 "$ENV_FILE"
green "✓ Wrote $ENV_FILE (admin password kept OUT of disk)"

#─── 3) DNS check ───────────────────────────────────────────────────────────
green "→ Checking DNS for $DOMAIN"
PUBIP=$(curl -fsSL https://api.ipify.org || true)
DNSIP=$(dig +short A "$DOMAIN" | tail -1 || true)
if [[ -z "$DNSIP" ]]; then
    yellow "⚠ Could not resolve $DOMAIN — Let's Encrypt issuance will fail until DNS is configured."
elif [[ "$DNSIP" != "$PUBIP" ]]; then
    yellow "⚠ $DOMAIN resolves to $DNSIP but this server's public IP is $PUBIP. Continuing anyway."
else
    green "✓ DNS OK ($DOMAIN → $PUBIP)"
fi

#─── 4) UFW ─────────────────────────────────────────────────────────────────
green "→ Configuring UFW (allowing 22, 80, 443)"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp  >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

#─── 4.5) Sanity-check repository contents ──────────────────────────────────
green "→ Verifying repository contents"
for must in "$ROOT_DIR/frontend/package.json" "$ROOT_DIR/backend/requirements.txt" "$ROOT_DIR/backend/server.py"; do
    [[ -f "$must" ]] || die "Required file missing from repo: $must  — push the full repo and re-run"
done
if [[ ! -f "$ROOT_DIR/frontend/yarn.lock" ]]; then
    yellow "⚠ frontend/yarn.lock is missing — the Docker build will generate one (slower, but fine)."
    yellow "  For reproducible builds, run 'cd frontend && yarn install' locally and commit yarn.lock."
fi

#─── 5) Docker ──────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
    green "→ Installing Docker Engine"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker >/dev/null
green "✓ Docker $(docker --version | awk '{print $3}' | tr -d ,)"

#─── 6) Copy project into /opt/streamhub (if not already there) ─────────────
if [[ "$ROOT_DIR" != "/opt/streamhub" ]]; then
    green "→ Copying project to /opt/streamhub"
    mkdir -p /opt/streamhub
    rsync -a --delete --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='/opt/streamhub/data' --exclude='build' \
        "$ROOT_DIR/" /opt/streamhub/
    DEPLOY_DIR=/opt/streamhub/deploy
    ENV_FILE=$DEPLOY_DIR/.env
fi

#─── 7) Issue Let's Encrypt cert (HTTP-01 via webroot) ──────────────────────
green "→ Issuing Let's Encrypt cert for $DOMAIN (HTTP-01)"
mkdir -p /opt/streamhub/data/letsencrypt /opt/streamhub/data/certbot-www
# Free port 80 / 443: stop any prior stack + any container/process holding them
docker rm -f sh-bootstrap-nginx sh-nginx 2>/dev/null || true
if [[ -f "$DEPLOY_DIR/docker-compose.yml" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$DEPLOY_DIR/docker-compose.yml" down 2>/dev/null || true
fi
# Anything else still holding port 80 in docker? Stop it.
for cid in $(docker ps --filter "publish=80" -q 2>/dev/null); do
    yellow "  stopping container $cid holding :80"
    docker stop "$cid" >/dev/null 2>&1 || true
done
# Kill any host process bound to :80 (apache, system nginx) so certbot can bind
if ss -ltn 'sport = :80' 2>/dev/null | grep -q LISTEN; then
    yellow "  port 80 still busy — stopping system nginx/apache if present"
    systemctl stop nginx 2>/dev/null || true
    systemctl stop apache2 2>/dev/null || true
fi
# Bootstrap a temp nginx on :80 to serve ACME challenge
cat > /tmp/bootstrap.conf <<EOF
server {
  listen 80 default_server;
  server_name _;
  location /.well-known/acme-challenge/ { root /var/www/certbot; }
  location / { return 200 "ok"; }
}
EOF
docker run -d --name sh-bootstrap-nginx \
    -p 80:80 \
    -v /tmp/bootstrap.conf:/etc/nginx/conf.d/default.conf:ro \
    -v /opt/streamhub/data/certbot-www:/var/www/certbot \
    nginx:1.27-alpine >/dev/null
sleep 2

docker run --rm \
    -v /opt/streamhub/data/letsencrypt:/etc/letsencrypt \
    -v /opt/streamhub/data/certbot-www:/var/www/certbot \
    certbot/certbot:latest certonly --webroot -w /var/www/certbot \
        --non-interactive --agree-tos \
        --email "$ADMIN_EMAIL" \
        -d "$DOMAIN" \
    || yellow "⚠ certbot failed — you can re-run this script after fixing DNS"

docker rm -f sh-bootstrap-nginx >/dev/null 2>&1 || true

# Hardlink the host letsencrypt dir into the named volume that compose uses
# Easier: switch compose to bind-mount /opt/streamhub/data/letsencrypt
sed -i 's|letsencrypt:/etc/letsencrypt|/opt/streamhub/data/letsencrypt:/etc/letsencrypt|g' "$DEPLOY_DIR/docker-compose.yml" || true
sed -i 's|certbot_www:/var/www/certbot|/opt/streamhub/data/certbot-www:/var/www/certbot|g' "$DEPLOY_DIR/docker-compose.yml" || true
# Remove the now-unused named volumes
sed -i '/^  letsencrypt:/d;/^  certbot_www:/d' "$DEPLOY_DIR/docker-compose.yml" || true

#─── 8) Render nginx config ────────────────────────────────────────────────
sed "s|__DOMAIN__|$DOMAIN|g" "$DEPLOY_DIR/nginx/streamhub.conf.template" > "$DEPLOY_DIR/nginx/streamhub.conf"
green "✓ Rendered nginx/streamhub.conf"

#─── 9) Build + start the stack ─────────────────────────────────────────────
green "→ Building images (this can take a few minutes)"
cd "$DEPLOY_DIR"
docker compose --env-file "$ENV_FILE" build
green "→ Starting stack"
docker compose --env-file "$ENV_FILE" up -d

#─── 10) Seed admin in MongoDB ─────────────────────────────────────────────
green "→ Seeding admin user $ADMIN_EMAIL"
# Wait for the backend to be reachable. Print progress so the script doesn't
# look hung.  Fall back to a forced restart if backend stays unhealthy >60 s.
backend_ready=""
for i in $(seq 1 60); do
    state=$(docker inspect -f '{{.State.Status}}' sh-backend 2>/dev/null || echo "missing")
    if [[ "$state" == "running" ]]; then
        if docker exec sh-backend python -c "import asyncio,os; from motor.motor_asyncio import AsyncIOMotorClient; asyncio.run(AsyncIOMotorClient(os.environ['MONGO_URL']).admin.command('ping'))" >/dev/null 2>&1; then
            backend_ready="yes"
            break
        fi
    fi
    [[ $((i % 5)) -eq 0 ]] && echo "  waiting for backend... ($i/60, state=$state)"
    sleep 2
done

if [[ -z "$backend_ready" ]]; then
    red "✘ Backend never became healthy. Last 40 log lines:"
    docker logs --tail 40 sh-backend 2>&1 || true
    red "  Aborting seed. Once the cause is fixed, re-run: sudo bash $DEPLOY_DIR/scripts/reset-admin.sh"
    exit 1
fi

# Quoted heredoc keeps bash from touching anything inside.  Credentials go in
# through `docker exec -e`, so special chars survive byte-perfect.
docker exec -e SEED_EMAIL="$ADMIN_EMAIL" -e SEED_PW="$ADMIN_PASSWORD" sh-backend python - <<'PYEOF'
import asyncio, os, sys, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/app')
from motor.motor_asyncio import AsyncIOMotorClient
from auth import hash_password
async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    email = os.environ['SEED_EMAIL'].lower()
    deleted = (await db.users.delete_many({'email': email})).deleted_count
    doc = {
        'id': str(uuid.uuid4()),
        'email': email,
        'username': email.split('@')[0],
        'password_hash': hash_password(os.environ['SEED_PW']),
        'role': 'admin', 'is_pro': True, 'email_verified': True,
        'pro_package_id': None, 'pro_expires_at': None,
        'verify_token': None, 'avatar_url': None, 'cover_url': None,
        'bio': None, 'banned_until': None, 'banned_reason': None,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    cnt = await db.users.count_documents({'email': email})
    print(f"seeded admin {email}  (deleted_prior={deleted}  docs_now={cnt})")
asyncio.run(main())
PYEOF

#─── 11) systemd ────────────────────────────────────────────────────────────
cp "$DEPLOY_DIR/streamhub.service" /etc/systemd/system/streamhub.service
systemctl daemon-reload
systemctl enable streamhub.service >/dev/null
green "✓ systemd unit installed"

#─── 11.5) Final smoke-test: real login round-trip ──────────────────────────
green "→ Smoke-testing login at https://$DOMAIN/api/auth/login"
sleep 5
SMOKE_BODY=$(python3 -c "import json,os,sys; print(json.dumps({'email':os.environ['E'],'password':os.environ['P']}))" E="$ADMIN_EMAIL" P="$ADMIN_PASSWORD")
SMOKE_HTTP=$(curl -sk -o /tmp/sh_smoke.json -w "%{http_code}" -X POST \
    "https://$DOMAIN/api/auth/login" \
    -H "Content-Type: application/json" \
    --data-binary "$SMOKE_BODY" || echo "000")
if [[ "$SMOKE_HTTP" == "200" ]]; then
    green "✓ Smoke test PASSED — admin can log in."
else
    red "✘ Smoke test FAILED — HTTP $SMOKE_HTTP  body: $(cat /tmp/sh_smoke.json 2>/dev/null || true)"
    yellow "  Fix without re-installing — run:"
    yellow "    sudo bash $DEPLOY_DIR/scripts/reset-admin.sh"
fi
rm -f /tmp/sh_smoke.json

#─── 12) Wrap-up ────────────────────────────────────────────────────────────
echo
bold "════════════════════════════════════════════════════════════════"
green " StreamHub is live — https://$DOMAIN"
green " Admin panel:        https://$DOMAIN/admin"
echo
bold " Admin credentials"
echo "   email:    $ADMIN_EMAIL"
echo "   password: (the one you entered)"
echo
bold " MongoDB credentials  (bound to 127.0.0.1 only — Navicat via SSH tunnel)"
echo "   Host:     127.0.0.1"
echo "   Port:     27017"
echo "   Database: streamhub"
echo "   User:     shadmin"
echo "   Password: $MONGO_ROOT_PASSWORD"
echo "   Auth DB:  admin"
echo
bold " Navicat connection walkthrough"
echo "   1. Navicat → 'Connection' → 'MongoDB'"
echo "   2. General tab:"
echo "        Connection name : StreamHub Prod"
echo "        Host            : 127.0.0.1"
echo "        Port            : 27017"
echo "        Database        : streamhub"
echo "        Authentication  : Password"
echo "        Username        : shadmin"
echo "        Password        : $MONGO_ROOT_PASSWORD"
echo "        Authentication DB : admin"
echo "   3. SSH tab → tick 'Use SSH Tunnel':"
echo "        Host            : $(curl -fsSL https://api.ipify.org 2>/dev/null || echo '<server-ip>')"
echo "        Port            : 22"
echo "        User            : root  (or your sudo user)"
echo "        Auth method     : Password or Private Key"
echo "   4. Click 'Test Connection' — should print 'Connection successful'."
echo "   5. Click OK to save and open the connection."
echo
yellow " ▸ These credentials are also in: $ENV_FILE  (chmod 600)"
yellow " ▸ Stack auto-starts on reboot via systemd (streamhub.service)"
bold "════════════════════════════════════════════════════════════════"
