#!/usr/bin/env bash
#
# Build and deploy prospect to the production host.
#
# The frontend is built ON the production server rather than pushed from a
# registry: there is a single production host and no registry configured, so
# building there avoids managing registry credentials entirely.
#
# Usage:
#   scripts/deploy-production.sh [--host HOST] [--ref GIT_REF] [--no-build] [--dry-run]
#
# Defaults: --host production --ref main
#
# Requires on the remote host:
#   ~/git/prospect cloned, a populated .env, docker + compose plugin.

set -euo pipefail

HOST="${PROSPECT_DEPLOY_HOST:-production}"
REF="main"
REMOTE_DIR="${PROSPECT_REMOTE_DIR:-~/git/prospect}"
PROJECT="prospect"
COMPOSE_FILE="docker-compose-production.yml"
BUILD=1
DRY_RUN=0

while [[ $# -gt 0 ]]; do
	case "$1" in
		--host) HOST="$2"; shift 2 ;;
		--ref) REF="$2"; shift 2 ;;
		--no-build) BUILD=0; shift ;;
		--dry-run) DRY_RUN=1; shift ;;
		-h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "Unknown option: $1" >&2; exit 2 ;;
	esac
done

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# The whole deployment runs as one remote script so a dropped SSH connection
# cannot leave the stack half-updated.
read -r -d '' REMOTE_SCRIPT <<REMOTE || true
set -euo pipefail

cd ${REMOTE_DIR}

if [ ! -f .env ]; then
	echo "ERROR: .env missing on the remote host. Copy it from .env.production.example and fill it in." >&2
	exit 1
fi

# FRONTEND_IMAGE names the locally built image; compose requires it to be set.
if ! grep -q '^FRONTEND_IMAGE=' .env; then
	echo "ERROR: FRONTEND_IMAGE is not set in .env (e.g. FRONTEND_IMAGE=prospect-frontend:latest)." >&2
	exit 1
fi
FRONTEND_IMAGE=\$(grep '^FRONTEND_IMAGE=' .env | cut -d= -f2-)

# SITE_URL builds the absolute unsubscribe links placed inside outgoing emails.
# A localhost value would send dead links to real recipients.
SITE_URL=\$(grep '^SITE_URL=' .env | cut -d= -f2- || true)
case "\$SITE_URL" in
	https://*) ;;
	*) echo "ERROR: SITE_URL must be a public https:// URL (got: '\$SITE_URL'). Unsubscribe links are built from it." >&2; exit 1 ;;
esac

echo "--> Fetching ${REF}"
git fetch --all --prune
git checkout ${REF}
git pull --ff-only
git --no-pager log --oneline -1

if [ "${BUILD}" = "1" ]; then
	echo "--> Building frontend image: \${FRONTEND_IMAGE}"
	docker build -t "\${FRONTEND_IMAGE}" ./frontend
fi

echo "--> Building backend image"
docker compose -p ${PROJECT} -f ${COMPOSE_FILE} build web

echo "--> Running migrations"
docker compose -p ${PROJECT} -f ${COMPOSE_FILE} run --rm migrate

echo "--> Starting services"
docker compose -p ${PROJECT} -f ${COMPOSE_FILE} up -d

echo "--> Collecting static files"
docker compose -p ${PROJECT} -f ${COMPOSE_FILE} exec -T web python manage.py collectstatic --noinput | tail -2

echo "--> Pruning dangling images"
docker image prune -f >/dev/null

echo "--> Status"
docker compose -p ${PROJECT} -f ${COMPOSE_FILE} ps
REMOTE

if [[ "$DRY_RUN" == "1" ]]; then
	log "Dry run — commands that would run on '${HOST}':"
	echo "$REMOTE_SCRIPT"
	exit 0
fi

log "Deploying ref '${REF}' to '${HOST}'"
ssh -o BatchMode=yes "$HOST" "bash -s" <<< "$REMOTE_SCRIPT"

log "Deployed. Verify: https://prospect.medica.im"
