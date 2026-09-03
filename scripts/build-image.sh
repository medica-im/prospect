#!/usr/bin/env bash
#
# Build and push a production image to the GitHub Container Registry.
#
# Usage:
#   ./scripts/build-image.sh frontend          # build + push the frontend
#   ./scripts/build-image.sh backend           # build + push the backend
#   ./scripts/build-image.sh all               # both, frontend first
#   ./scripts/build-image.sh backend --no-push # build and verify only
#   ./scripts/build-image.sh frontend --tag staging
#
# Each build pushes two tags: the moving one (:production by default) and an
# immutable :<short-sha> that never moves, so a bad release can be rolled back
# to an exact image. The FRONTEND_IMAGE / BACKEND_IMAGE line to put in .env is
# printed at the end.
#
# Follows clinic-cms/skcms, which has run this shape in production for months.
#
# Requires: docker, and a prior `docker login ghcr.io` (unless --no-push).
# The GitHub token needs write:packages.

set -euo pipefail

# Anchored to this script's own location, not the caller's cwd: `git rev-parse`
# would answer for whatever repo the invoking shell happens to sit in.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# <project>-<component>, matching clinic-cms-backend / postgres-non-root.
# Separate repositories per component: one shared name would mean the two
# images overwrite each other's tags.
FRONTEND_IMAGE_REPO="${FRONTEND_IMAGE_REPO:-ghcr.io/medica-im/prospect-frontend}"
BACKEND_IMAGE_REPO="${BACKEND_IMAGE_REPO:-ghcr.io/medica-im/prospect-backend}"

TAG="${TAG:-production}"
PUSH=1
COMPONENT=""

usage() {
	# Only the header block: stop at the first non-comment line, and skip the
	# shebang. A bare `grep '^#'` would dump every internal comment too.
	sed -e '1d' -e '/^[^#]/q' "${BASH_SOURCE[0]}" \
		| sed -e '/^[^#]/d' -e 's/^#//' -e 's/^ //'
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--no-push) PUSH=0; shift ;;
		--tag)
			[[ $# -ge 2 ]] || { echo "error: --tag needs a value" >&2; exit 2; }
			TAG="$2"; shift 2 ;;
		--tag=*) TAG="${1#*=}"; shift ;;
		-h|--help) usage; exit 0 ;;
		-*) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
		frontend|backend|all)
			[[ -z "$COMPONENT" ]] || {
				echo "error: build one component at a time (got '$COMPONENT' and '$1')" >&2
				exit 2
			}
			COMPONENT="$1"; shift ;;
		*) echo "error: unknown component '$1' (want: frontend, backend, all)" >&2; exit 2 ;;
	esac
done

if [[ -z "$COMPONENT" ]]; then
	echo "error: say what to build (frontend, backend, or all)" >&2
	echo >&2
	usage >&2
	exit 2
fi

# Record the git commit the image is built from, for traceability. Untracked
# files count as dirty (hence status --porcelain, not diff --quiet): a file that
# exists only locally still changes the build context. Checked over the whole
# repo, not just the component, because the tag is a claim about the checkout.
GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)" ]]; then
	GIT_SHA="${GIT_SHA}-dirty"
fi

# A dirty tree means the pushed image cannot be reproduced from any commit, and
# its :<sha> tag names a commit that does not contain what is in the image.
# Fine for a staging spin, so warn rather than block, but say it plainly.
if [[ "$PUSH" -eq 1 && "$GIT_SHA" == *-dirty ]]; then
	echo "warning: working tree is dirty — the pushed image will not correspond" >&2
	echo "         to any commit. Commit first if this is a real release." >&2
	echo >&2
fi

# Fail before a multi-minute build if the push cannot possibly succeed.
if [[ "$PUSH" -eq 1 ]]; then
	REGISTRY="${FRONTEND_IMAGE_REPO%%/*}"
	if ! grep -q "$REGISTRY" "${DOCKER_CONFIG:-$HOME/.docker}/config.json" 2>/dev/null; then
		echo "error: no stored credentials for $REGISTRY." >&2
		echo "       Run: docker login $REGISTRY   (token needs write:packages)" >&2
		echo "       Or build without pushing: $0 $COMPONENT --no-push" >&2
		exit 1
	fi
fi

# Build one component. Verification differs per component, so each caller
# passes the check it wants as a shell snippet run inside the built image.
build_one() {
	local name="$1" repo="$2" context="$3" verify="$4"
	local moving="$repo:$TAG" immutable="$repo:$GIT_SHA"

	echo "==> [$name] Building"
	echo "    context: $context"
	echo "    tags:    $moving"
	echo "             $immutable"

	docker build \
		--build-arg GIT_SHA="$GIT_SHA" \
		--label "org.opencontainers.image.revision=$GIT_SHA" \
		--label "org.opencontainers.image.source=https://github.com/medica-im/prospect" \
		-t "$moving" \
		-t "$immutable" \
		"$context"

	# A build can fail in ways that still produce an image, so confirm the
	# thing the image exists to run is actually in it before pushing.
	echo "==> [$name] Verifying image contents"
	if ! docker run --rm --entrypoint sh "$moving" -c "$verify"; then
		echo "error: [$name] verification failed — the build did not produce what it should." >&2
		exit 1
	fi
	echo "    ok"

	if [[ "$PUSH" -eq 0 ]]; then
		echo "==> [$name] Skipping push (--no-push). Built locally as:"
		echo "      $moving"
		echo "      $immutable"
		echo
		return 0
	fi

	echo "==> [$name] Pushing"
	docker push "$moving"
	docker push "$immutable"
	echo "==> [$name] Pushed $moving (git $GIT_SHA)"
	echo
}

build_frontend() {
	# adapter-node emits build/ contents at /app, so index.js and handler.js
	# are what must be present.
	build_one frontend "$FRONTEND_IMAGE_REPO" "$REPO_ROOT/frontend" \
		'test -f index.js && test -f handler.js'
}

build_backend() {
	# Import the wsgi module: exactly what gunicorn loads at startup, so it
	# exercises settings, the app registry and every dependency they import. A
	# missing package or a syntax error in settings otherwise surfaces only on
	# first boot in production — `docker build` itself never loads the app.
	# Needs no database or .env, verified against this image.
	build_one backend "$BACKEND_IMAGE_REPO" "$REPO_ROOT/backend" \
		'python -c "import prospect.wsgi"'
}

case "$COMPONENT" in
	frontend) build_frontend ;;
	backend)  build_backend ;;
	all)      build_frontend; build_backend ;;
esac

if [[ "$PUSH" -eq 1 ]]; then
	# No .env editing: deploy.sh reads the tag from the commit being deployed
	# and passes the resolved digests to compose as environment variables, so
	# the server's .env is never touched by a release.
	echo "Deploy with:"
	if [[ "$GIT_SHA" == *-dirty ]]; then
		echo "    ./scripts/deploy.sh --tag $GIT_SHA"
		echo
		echo "(a clean tree lets you just run ./scripts/deploy.sh — it takes the"
		echo " tag from HEAD, and refuses to deploy a dirty one.)"
	else
		echo "    ./scripts/deploy.sh"
		echo
		echo "It deploys $GIT_SHA, the commit these images were built from."
		echo "Roll back later with: ./scripts/deploy.sh --tag <previous-sha>"
	fi
fi
