#!/usr/bin/env bash
# StreamHub — recover from a "nginx restarts because SSL cert is missing" loop.
#
# This happens when docker-compose.yml gets reset (e.g. after `git reset
# --hard`) and reverts to using a named volume for /etc/letsencrypt — the new
# empty volume doesn't contain your real certs, so nginx fails.
#
# The script:
#   1. Finds your existing certs (host bind path OR old named volume)
#   2. Wires docker-compose.yml back to the host bind-mount
#   3. Restarts the stack
#
# Usage:  sudo bash /opt/streamhub/deploy/scripts/fix-certs.sh

set -euo pipefail

green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    red "Run as root: sudo bash $0"
    exit 1
fi

REPO_DIR=/opt/streamhub
COMPOSE_FILE="$REPO_DIR/deploy/docker-compose.yml"
ENV_FILE="$REPO_DIR/deploy/.env"

# Source DOMAIN from .env (used to validate certs are for the right host)
[[ -f "$ENV_FILE" ]] || { red "$ENV_FILE missing — run install.sh first."; exit 1; }
# shellcheck disable=SC1090
. "$ENV_FILE"
[[ -n "${DOMAIN:-}" ]] || { red "DOMAIN is not set in $ENV_FILE"; exit 1; }
green "→ Domain: $DOMAIN"

HOST_CERT_DIR=/opt/streamhub/data/letsencrypt
HOST_LIVE="$HOST_CERT_DIR/live/$DOMAIN"

# 1) Look for certs on the host bind path
if [[ -f "$HOST_LIVE/fullchain.pem" && -f "$HOST_LIVE/privkey.pem" ]]; then
    green "✓ Found certs at $HOST_LIVE"
else
    blue "→ No certs at $HOST_LIVE — checking old docker volume…"
    # Try the named volume created by the previous compose layout
    VOL_MNT=$(docker volume inspect -f '{{.Mountpoint}}' deploy_letsencrypt 2>/dev/null || true)
    if [[ -n "$VOL_MNT" && -f "$VOL_MNT/live/$DOMAIN/fullchain.pem" ]]; then
        green "✓ Found certs inside docker volume — copying to host path"
        mkdir -p "$HOST_CERT_DIR"
        cp -a "$VOL_MNT"/* "$HOST_CERT_DIR/"
    else
        red "✘ No usable certs found in either location."
        red "  Re-issue with Let's Encrypt:"
        red "    docker stop sh-nginx 2>/dev/null"
        red "    docker run --rm -p 80:80 \\"
        red "      -v /opt/streamhub/data/letsencrypt:/etc/letsencrypt \\"
        red "      -v /opt/streamhub/data/certbot-www:/var/www/certbot \\"
        red "      certbot/certbot:latest certonly --standalone \\"
        red "        --non-interactive --agree-tos -m \"$LETSENCRYPT_EMAIL\" -d \"$DOMAIN\""
        exit 1
    fi
fi

# 2) Make sure docker-compose.yml uses the bind-mount path.  Newer repo
# versions already do this by default; older ones need patching.
if grep -q '^      - letsencrypt:/etc/letsencrypt' "$COMPOSE_FILE"; then
    blue "→ Patching $COMPOSE_FILE to use host bind-mount for certs"
    sed -i 's|^      - letsencrypt:/etc/letsencrypt|      - /opt/streamhub/data/letsencrypt:/etc/letsencrypt|g' "$COMPOSE_FILE"
    sed -i 's|^      - certbot_www:/var/www/certbot|      - /opt/streamhub/data/certbot-www:/var/www/certbot|g' "$COMPOSE_FILE"
    sed -i '/^  letsencrypt:$/d;/^  certbot_www:$/d' "$COMPOSE_FILE"
    green "✓ docker-compose.yml patched"
fi

# 3) Make sure certbot-www host dir exists (used for ACME renewals)
mkdir -p /opt/streamhub/data/certbot-www

# 4) Restart stack
blue "→ Restarting nginx + certbot"
cd "$REPO_DIR/deploy"
DC="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"
$DC up -d --force-recreate nginx certbot

# 5) Health check
blue "→ Waiting for nginx to come back…"
ok=0
for i in $(seq 1 20); do
    state=$(docker inspect -f '{{.State.Status}}' sh-nginx 2>/dev/null || echo missing)
    if [[ "$state" == "running" ]]; then
        # nginx running = config valid = cert loaded
        green "✓ nginx is up — your site should be reachable at https://$DOMAIN"
        ok=1
        break
    fi
    sleep 2
done
if [[ $ok -eq 0 ]]; then
    red "nginx is still not running. Last 30 log lines:"
    docker logs --tail=30 sh-nginx || true
    exit 1
fi
