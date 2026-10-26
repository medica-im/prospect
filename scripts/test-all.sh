#!/usr/bin/env bash
set -uo pipefail

# Runs every test suite and prints a pass/fail summary. Exits non-zero when any
# step fails, so it can gate a deploy. Steps keep going after a failure: one
# broken suite should not hide the state of the others.
#
# Not `set -e` on purpose, for that same reason; each step's status is
# collected instead.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose-development.yml")

RED='\033[0;31m'
ORANGE='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

usage() {
    echo "Usage: $0 [--lint] [--browser] [--only backend|frontend]"
    echo
    echo "Runs the backend Django tests (in the dev web container), then the"
    echo "frontend type check and unit tests."
    echo
    echo "  --lint      also run prettier and eslint (currently failing: 34"
    echo "              unformatted files, eslint-plugin-storybook missing)"
    echo "  --browser   also run the vitest browser project (needs the"
    echo "              Playwright Chromium build vitest expects)"
    echo "  --only X    run only the backend or only the frontend steps"
    echo "  -h, --help  show this help and exit"
}

LINT=0
BROWSER=0
ONLY=""
while [ $# -gt 0 ]; do
    case "$1" in
        --lint) LINT=1 ;;
        --browser) BROWSER=1 ;;
        --only)
            shift
            case "${1:-}" in
                backend|frontend) ONLY="$1" ;;
                *) echo "error: --only takes backend or frontend" >&2; exit 1 ;;
            esac
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "error: unknown argument '$1'" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

declare -a RESULTS=()

run_step() {
    local name="$1"
    shift
    echo
    echo -e "==> ${name}"
    local start=$SECONDS
    if "$@"; then
        RESULTS+=("${GREEN}pass${NC}  $name ($((SECONDS - start))s)")
    else
        RESULTS+=("${RED}FAIL${NC}  $name ($((SECONDS - start))s)")
        FAILED=1
    fi
}

backend_tests() {
    # Reuse the running dev container when there is one; otherwise start a
    # throwaway one (compose brings up db, redis and rabbitmq for it).
    if [ -n "$("${COMPOSE[@]}" ps --status running -q web 2>/dev/null)" ]; then
        "${COMPOSE[@]}" exec -T web python manage.py test
    else
        echo -e "${ORANGE}web is not running; using a one-off container${NC}"
        "${COMPOSE[@]}" run --rm -T web python manage.py test
    fi
}

frontend() {
    (cd "$FRONTEND_DIR" && pnpm "$@")
}

FAILED=0

if [ "$ONLY" != "frontend" ]; then
    run_step "backend: django tests" backend_tests
fi

if [ "$ONLY" != "backend" ]; then
    run_step "frontend: type check" frontend run check
    run_step "frontend: unit tests" frontend exec vitest --run --project server
    if [ "$BROWSER" = 1 ]; then
        run_step "frontend: browser tests" frontend exec vitest --run --project client
    fi
    if [ "$LINT" = 1 ]; then
        run_step "frontend: lint" frontend run lint
    fi
fi

echo
echo "==> Summary"
for line in "${RESULTS[@]}"; do
    echo -e "    $line"
done

exit "$FAILED"
