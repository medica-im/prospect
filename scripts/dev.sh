#!/usr/bin/env bash
set -euo pipefail

# Starts the SvelteKit dev server on the fixed port that the
# dev.prospect.medica.im nginx vhost proxies to, after making sure the backend's
# docker compose services are up.
#
# Unlike clinic-cms there is one site here, so there is no context file and no
# submodule to check out: the port is fixed because nginx hardcodes it.
#
# Lives in the repo-root scripts/ rather than frontend/ so that editing it does
# not touch the containers: ./backend and ./frontend are bind-mounted into the
# dev services, and ./backend is a docker build context on top of that.

# Anchored to this script's own location, not the caller's cwd: `git rev-parse`
# would answer for whatever repo the invoking shell happens to sit in.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$REPO_ROOT/frontend}"
BACKEND_COMPOSE_FILE="${BACKEND_COMPOSE_FILE:-$REPO_ROOT/docker-compose-development.yml}"
DEV_HOST="${DEV_HOST:-dev.prospect.medica.im}"

# Must match the proxy_pass in /etc/nginx/sites-available/dev.prospect.medica.im.
# DEV_PORT overrides it for a one-off; nginx will not follow, so the site is
# only reachable at the default.
#
# Deliberately not 5173: that is Vite's default, so every other checkout on this
# box grabs it, and whichever project started first wins the port while the
# others silently walk to 5174+ and stop being reachable through their vhost.
# The 30xx range is already how this box allocates dev servers — clinic-cms
# takes 3010-3019 for its sites and 3100-3199 for e2e workers — so prospect
# takes the next free slot above the site range.
DEV_PORT="${DEV_PORT:-3020}"

# Bind IPv4 explicitly. Vite's default host resolves to [::1] on this box, and
# the vhost proxies to 127.0.0.1 — a v6-only listener means nginx connects to
# nothing and the site 502s while `pnpm dev` looks perfectly healthy.
BIND_HOST="${BIND_HOST:-127.0.0.1}"

NGINX_VHOST="${NGINX_VHOST:-/etc/nginx/sites-enabled/$DEV_HOST}"

RESTART=0

usage() {
    echo "Usage: $0 [--restart]"
    echo
    echo "Ensures the backend's dev docker compose services are running and"
    echo "healthy (starting them if needed), then runs vite on port $DEV_PORT"
    echo "bound to $BIND_HOST, which is where the $DEV_HOST vhost proxies."
    echo
    echo "Reach the app at https://$DEV_HOST/"
    echo
    echo "  --restart  stop whatever already holds port $DEV_PORT first"
    echo "  -h, --help show this help and exit"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --restart) RESTART=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; usage >&2; exit 1 ;;
    esac
done

ORANGE='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

# nginx decides where the browser lands; this script decides where the server
# listens. When they disagree the site is unreachable rather than merely
# misconfigured, so say so here instead of letting it look like the app is down.
if [[ -r "$NGINX_VHOST" ]]; then
    MAPPED_PORT=$(grep -oP 'proxy_pass\s+http://127\.0\.0\.1:\K[0-9]+' "$NGINX_VHOST" \
        | grep -v '^8000$' | head -1 || true)
    if [[ -n "$MAPPED_PORT" && "$MAPPED_PORT" != "$DEV_PORT" ]]; then
        echo -e "${ORANGE}==> warning: starting on port $DEV_PORT, but $NGINX_VHOST proxies to $MAPPED_PORT${NC}" >&2
        echo "https://$DEV_HOST will not reach this server until they agree." >&2
    fi
fi

backend_services_healthy() {
    local total up
    total=$(docker compose -f "$BACKEND_COMPOSE_FILE" config --services 2>/dev/null | wc -l)
    up=$(docker compose -f "$BACKEND_COMPOSE_FILE" ps --format json 2>/dev/null \
        | jq -s '[.[] | select(.State == "running" and (.Health == "healthy" or .Health == ""))] | length')
    [[ "$total" -gt 0 && "$up" -eq "$total" ]]
}

echo "==> Checking backend services in $REPO_ROOT"
(
    cd "$REPO_ROOT"
    if backend_services_healthy; then
        echo -e "${GREEN}==> Backend services are already running and healthy${NC}"
    else
        echo "==> Starting backend services (this may take a while)..."
        docker compose -f "$BACKEND_COMPOSE_FILE" up -d --wait
        echo -e "${GREEN}==> Backend services are running and healthy${NC}"
    fi
)

cd "$FRONTEND_DIR"

# Prints the pid listening on a port, or nothing. Always succeeds: an empty
# result is a normal answer ("nothing is listening"), and under `set -e` a
# non-zero grep here would abort the script instead. No `sport =` filter — that
# misses a v6-only listener, which is exactly the case worth catching.
pid_on_port() { ss -ltnpH 2>/dev/null | awk -v p=":$1\$" '$4 ~ p' | grep -oP 'pid=\K[0-9]+' | head -1 || true; }

port_free() { ! ss -ltnH 2>/dev/null | awk -v p=":$1\$" '$4 ~ p' | grep -q .; }

# Wait for the port to come back after a kill, so the exec below does not race
# the kernel releasing it and die on --strictPort.
stop_server() {
    local pid="$1" port="$2"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 100); do
        port_free "$port" && return 0
        sleep 0.1
    done
    echo "error: pid $pid still holds port $port" >&2
    return 1
}

if OWN_PID=$(pid_on_port "$DEV_PORT") && [[ -n "$OWN_PID" ]]; then
    if [[ "$RESTART" == "1" ]]; then
        echo -e "${ORANGE}==> stopping dev server on port $DEV_PORT (pid $OWN_PID)${NC}"
        stop_server "$OWN_PID" "$DEV_PORT" || exit 1
    else
        echo -e "${ORANGE}==> port $DEV_PORT is already held by pid $OWN_PID${NC}" >&2
        echo "Re-run with --restart to replace it, or stop it yourself:" >&2
        echo "    kill $OWN_PID" >&2
        exit 1
    fi
fi

echo "==> Starting dev server on $BIND_HOST:$DEV_PORT (https://$DEV_HOST/)"
# `pnpm exec vite`, not `pnpm run dev -- …`: with the latter pnpm passes the
# flags after `--` as positional arguments, so vite keeps its own --port and
# walks to the next free one — the exact drift --strictPort is here to stop.
exec pnpm exec vite dev --host "$BIND_HOST" --port "$DEV_PORT" --strictPort
