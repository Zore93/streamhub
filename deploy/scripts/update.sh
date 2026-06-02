#!/usr/bin/env bash
# StreamHub — fast update from GitHub (no full reinstall).
#
# Pulls latest code into /opt/streamhub and rebuilds + restarts the docker
# stack.  Preserves uploads, Mongo data, certbot certs and admin settings.
#
# Usage:
#   sudo bash /opt/streamhub/deploy/scripts/update.sh
#
# Flags:
#   --no-build      Skip image rebuild (use existing images, just restart)
#   --backend-only  Restart only backend (e.g. after backend/.env or models change)
#   --frontend-only Restart only frontend (e.g. after UI-only changes)

set -euo pipefail

# ─── pretty output ──────────────────────────────────────────────────────────
green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    red "This script must be run as root (sudo)."
    exit 1
fi

REPO_DIR=/opt/streamhub
COMPOSE_FILE="$REPO_DIR/deploy/docker-compose.yml"
ENV_FILE="$REPO_DIR/deploy/.env"

if [[ ! -d "$REPO_DIR/.git" ]]; then
    red "$REPO_DIR is not a git checkout."
    red "Run the initial installer first:  sudo bash $REPO_DIR/deploy/scripts/install.sh"
    exit 1
fi

NO_BUILD=0
ONLY=""
for arg in "$@"; do
    case "$arg" in
        --no-build)      NO_BUILD=1 ;;
        --backend-only)  ONLY="backend" ;;
        --frontend-only) ONLY="frontend" ;;
        *) red "Unknown flag: $arg"; exit 1 ;;
    esac
done

# ─── 1) git pull ────────────────────────────────────────────────────────────
blue "→ git pull origin"
cd "$REPO_DIR"
# safe.directory=* prevents 'dubious ownership' errors when the repo is owned
# by a different uid than the user running sudo.
git -c safe.directory=* fetch --all --prune
BEFORE=$(git -c safe.directory=* rev-parse HEAD)
git -c safe.directory=* pull --ff-only
AFTER=$(git -c safe.directory=* rev-parse HEAD)

if [[ "$BEFORE" == "$AFTER" ]]; then
    green "Already up-to-date (HEAD = ${BEFORE:0:12})."
else
    green "Updated ${BEFORE:0:12} → ${AFTER:0:12}"
    blue  "Changed files since last update:"
    git -c safe.directory=* --no-pager diff --name-only "$BEFORE" "$AFTER"
fi

# ─── 2) rebuild + restart ───────────────────────────────────────────────────
cd "$REPO_DIR/deploy"

DC="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

if [[ -n "$ONLY" ]]; then
    if [[ "$NO_BUILD" -eq 0 ]]; then
        blue "→ Building $ONLY image"
        $DC build "$ONLY"
    fi
    blue "→ Restarting $ONLY"
    $DC up -d --no-deps "$ONLY"
else
    if [[ "$NO_BUILD" -eq 1 ]]; then
        blue "→ Restarting all containers (no rebuild)"
        $DC up -d
    else
        blue "→ Rebuilding + restarting all containers"
        $DC up -d --build
    fi
fi

# ─── 3) post-update health check ────────────────────────────────────────────
# Backend isn't exposed on the host; it's proxied by nginx.  We exec into the
# container and use python (guaranteed to exist — it's the runtime) to hit the
# loopback API.  Curl/wget aren't in the slim image.
blue "→ Waiting for backend to come back…"
HEALTH_PY='import urllib.request,sys
try:
    urllib.request.urlopen("http://127.0.0.1:8001/api/site/config", timeout=2).read()
    sys.exit(0)
except Exception:
    sys.exit(1)'
ok=0
for i in $(seq 1 30); do
    if docker exec sh-backend python3 -c "$HEALTH_PY" >/dev/null 2>&1; then
        green "✓ Backend healthy"
        ok=1
        break
    fi
    sleep 2
done
if [[ $ok -eq 0 ]]; then
    red "Backend did not respond after 60s.  Last 30 log lines:"
    $DC logs --tail=30 backend || true
    red ""
    red "If the log above shows the backend is actually serving requests, the"
    red "container just lacks the health-check tool — try opening the site directly."
    exit 1
fi

green ""
green "✓ Update complete."
green "  New HEAD: $(git -c safe.directory=* rev-parse --short HEAD)"
green ""
blue  "Tip: tail logs with:  $DC logs -f"
