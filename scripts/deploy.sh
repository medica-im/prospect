#!/usr/bin/env bash
#
# Pull prebuilt images on the production server and restart the containers.
#
# Deliberately never builds: scripts/build-image.sh builds and pushes from a
# dev machine, this pulls those exact tags. Production therefore runs the same
# artefact that was tested, not a rebuild that could drift.
#
# Usage:
#   ./scripts/deploy.sh                      # deploy the current commit's images
#   ./scripts/deploy.sh --tag 8162620        # deploy/roll back to a specific tag
#   ./scripts/deploy.sh --dry-run            # print what would run, touch nothing
#   ./scripts/deploy.sh --frontend           # one component only
#   ./scripts/deploy.sh --status             # what is running now, then exit
#
# Rollback is the same command with the tag you want:
#   ./scripts/deploy.sh --tag <previous-sha>
#
# Environment:
#   DEPLOY_HOST   ssh target      (default: mastodon)
#   DEPLOY_DIR    directory there (default: /opt/prospect)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DEPLOY_HOST="${DEPLOY_HOST:-mastodon}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/prospect}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose-production.yml}"

FRONTEND_IMAGE_REPO="${FRONTEND_IMAGE_REPO:-ghcr.io/medica-im/prospect-frontend}"
BACKEND_IMAGE_REPO="${BACKEND_IMAGE_REPO:-ghcr.io/medica-im/prospect-backend}"

TAG_OVERRIDE=""
DRY_RUN=0
STATUS_ONLY=0
DO_FRONTEND=1
DO_BACKEND=1

usage() {
	sed -e '1d' -e '/^[^#]/q' "${BASH_SOURCE[0]}" \
		| sed -e '/^[^#]/d' -e 's/^#//' -e 's/^ //'
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--tag)
			[[ $# -ge 2 ]] || { echo "error: --tag needs a value" >&2; exit 2; }
			TAG_OVERRIDE="$2"; shift 2 ;;
		--tag=*) TAG_OVERRIDE="${1#*=}"; shift ;;
		--dry-run) DRY_RUN=1; shift ;;
		--status) STATUS_ONLY=1; shift ;;
		--frontend) DO_BACKEND=0; shift ;;
		--backend) DO_FRONTEND=0; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
	esac
done

ssh_run() { ssh -o BatchMode=yes "$DEPLOY_HOST" "$@"; }

if [[ "$STATUS_ONLY" -eq 1 ]]; then
	echo "==> Status on $DEPLOY_HOST:$DEPLOY_DIR"
	ssh_run bash -s <<EOF
set -euo pipefail
cd "$DEPLOY_DIR"
docker compose -f "$COMPOSE_FILE" ps --format '    {{.Service}}  {{.Image}}  {{.Status}}'
EOF
	exit 0
fi

# The tag to deploy. Defaults to this checkout's commit, which is what
# build-image.sh tagged, so build-then-deploy needs no copy-pasting.
if [[ -n "$TAG_OVERRIDE" ]]; then
	TAG="$TAG_OVERRIDE"
else
	TAG="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
	if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
		echo "error: working tree is dirty, so the current commit ($TAG) does not" >&2
		echo "       describe what you would deploy. Commit and rebuild, or name a" >&2
		echo "       tag explicitly: $0 --tag <sha>" >&2
		exit 1
	fi
fi

FRONTEND_REF="$FRONTEND_IMAGE_REPO:$TAG"
BACKEND_REF="$BACKEND_IMAGE_REPO:$TAG"

echo "==> Deploying tag: $TAG"
echo "    host:    $DEPLOY_HOST:$DEPLOY_DIR"
[[ "$DO_FRONTEND" -eq 1 ]] && echo "    frontend: $FRONTEND_REF"
[[ "$DO_BACKEND" -eq 1 ]] && echo "    backend:  $BACKEND_REF"
echo

# Verify every tag exists in the registry BEFORE touching the server.
#
# Without this, `docker compose pull` of a tag that was never pushed leaves the
# old image in place and `up -d` cheerfully restarts it: a release that reports
# success while running the previous code. That exact failure is why this check
# runs first, and why it resolves the digest — which is what actually gets
# deployed below.
resolve_digest() {
	local ref="$1" digest
	if ! digest="$(docker manifest inspect --verbose "$ref" 2>/dev/null \
		| python3 -c 'import json,sys
d=json.load(sys.stdin)
d=d[0] if isinstance(d,list) else d
print(d.get("Descriptor",{}).get("digest",""))' 2>/dev/null)"; then
		digest=""
	fi
	printf '%s' "$digest"
}

echo "==> Verifying images exist in the registry"
FRONTEND_DIGEST=""
BACKEND_DIGEST=""
missing=0
if [[ "$DO_FRONTEND" -eq 1 ]]; then
	FRONTEND_DIGEST="$(resolve_digest "$FRONTEND_REF")"
	if [[ -z "$FRONTEND_DIGEST" ]]; then
		echo "error: $FRONTEND_REF not found in the registry." >&2
		missing=1
	else
		echo "    frontend $FRONTEND_DIGEST"
	fi
fi
if [[ "$DO_BACKEND" -eq 1 ]]; then
	BACKEND_DIGEST="$(resolve_digest "$BACKEND_REF")"
	if [[ -z "$BACKEND_DIGEST" ]]; then
		echo "error: $BACKEND_REF not found in the registry." >&2
		missing=1
	else
		echo "    backend  $BACKEND_DIGEST"
	fi
fi
if [[ "$missing" -eq 1 ]]; then
	echo >&2
	echo "       Build and push it first:  ./scripts/build-image.sh all" >&2
	echo "       Or deploy a tag that exists: $0 --tag <sha>" >&2
	exit 1
fi

# Deploy by digest, not by tag. A tag can be overwritten between this check and
# the pull; a digest names one immutable image, so what was verified above is
# exactly what runs.
FRONTEND_PINNED="$FRONTEND_IMAGE_REPO@$FRONTEND_DIGEST"
BACKEND_PINNED="$BACKEND_IMAGE_REPO@$BACKEND_DIGEST"

# Keep whatever is already deployed for the component we are not touching, so a
# --frontend deploy does not blank BACKEND_IMAGE in the server's environment.
if [[ "$DO_FRONTEND" -eq 0 ]]; then FRONTEND_PINNED=""; fi
if [[ "$DO_BACKEND" -eq 0 ]]; then BACKEND_PINNED=""; fi

if [[ "$DRY_RUN" -eq 1 ]]; then
	echo
	echo "==> (dry run) would run on $DEPLOY_HOST:"
	echo "    cd $DEPLOY_DIR"
	[[ -n "$FRONTEND_PINNED" ]] && echo "    FRONTEND_IMAGE=$FRONTEND_PINNED"
	[[ -n "$BACKEND_PINNED" ]] && echo "    BACKEND_IMAGE=$BACKEND_PINNED"
	echo "    docker compose -f $COMPOSE_FILE pull --quiet"
	echo "    docker compose -f $COMPOSE_FILE up -d --wait --remove-orphans"
	exit 0
fi

echo
echo "==> Pulling and restarting on $DEPLOY_HOST"

# The images are passed as environment variables rather than written into the
# server's .env: nothing on the server is edited, so a failed deploy leaves no
# half-applied state, and the previous .env stays valid for a manual recovery.
#
# They are also persisted to .env.deployed purely as a record of what is
# running, which --status and a human can read. It is not an input to compose.
ssh_run bash -s <<EOF
set -euo pipefail
cd "$DEPLOY_DIR"

if [[ ! -f .env ]]; then
    echo "error: .env missing on the remote host. Copy .env.production.example" >&2
    echo "       and fill it in before deploying." >&2
    exit 1
fi

# SITE_URL builds the absolute unsubscribe links placed inside outgoing emails
# (emails/services/unsubscribe.py). It defaults to http://localhost:8000, so an
# unset value does not fail loudly — it silently mails dead links to real
# recipients. Checked here because a deploy is the moment it starts mattering.
SITE_URL_VALUE="\$(grep '^SITE_URL=' .env | cut -d= -f2- | tr -d '"'"'"'"' || true)"
case "\$SITE_URL_VALUE" in
    https://*) ;;
    *)
        echo "error: SITE_URL must be a public https:// URL (got: '\$SITE_URL_VALUE')." >&2
        echo "       Unsubscribe links in outgoing email are built from it." >&2
        exit 1
        ;;
esac

# Carry forward the currently-deployed image for any component not in this
# deploy, so compose still has a value for it.
if [[ -f .env.deployed ]]; then
    # shellcheck disable=SC1091
    set -a; . ./.env.deployed; set +a
fi

${FRONTEND_PINNED:+export FRONTEND_IMAGE="$FRONTEND_PINNED"}
${BACKEND_PINNED:+export BACKEND_IMAGE="$BACKEND_PINNED"}

if [[ -z "\${FRONTEND_IMAGE:-}" || -z "\${BACKEND_IMAGE:-}" ]]; then
    echo "error: FRONTEND_IMAGE/BACKEND_IMAGE not both set. A partial deploy" >&2
    echo "       needs a previous full deploy to inherit from." >&2
    exit 1
fi

echo "    frontend: \$FRONTEND_IMAGE"
echo "    backend:  \$BACKEND_IMAGE"

echo "    pulling"
# --quiet: stdout is a pipe here, not a terminal, so Docker's progress bars
# degrade to one line per frame. Errors are still reported.
docker compose -f "$COMPOSE_FILE" pull --quiet

echo "    starting (waiting for healthchecks)"
# --wait blocks until every service with a healthcheck reports healthy, and
# exits non-zero if one does not. That is what turns "the container started"
# into "the app answers": web's healthcheck queries the database through
# /healthz, so a container that boots and then fails every request is caught
# here instead of by a user.
if ! docker compose -f "$COMPOSE_FILE" up -d --wait --remove-orphans; then
    echo >&2
    echo "error: deploy failed to become healthy. Current state:" >&2
    docker compose -f "$COMPOSE_FILE" ps >&2
    echo >&2
    echo "Recent logs:" >&2
    docker compose -f "$COMPOSE_FILE" logs --tail 40 web frontend >&2 || true
    exit 1
fi

# Record what is now running. Written only after a successful --wait, so it
# always names a version that actually came up healthy — which is what makes it
# safe to inherit from on a partial deploy.
{
    echo "FRONTEND_IMAGE=\$FRONTEND_IMAGE"
    echo "BACKEND_IMAGE=\$BACKEND_IMAGE"
} > .env.deployed

echo "    running:"
docker compose -f "$COMPOSE_FILE" ps --format '      {{.Service}}  {{.Status}}'

# Untagged layers from previous deploys add up on a small VPS.
docker image prune -f >/dev/null
EOF

echo
echo "==> Deployed $TAG to $DEPLOY_HOST"
echo "    Roll back with:  $0 --tag <previous-sha>"
