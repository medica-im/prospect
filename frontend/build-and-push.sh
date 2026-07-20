#!/usr/bin/env bash
#
# Build and push the frontend production image to GitHub Container Registry.
#
# Usage:
#   ./build-and-push.sh                 # build + push ghcr.io/medica-im/prospect:production
#   ./build-and-push.sh --no-push       # build only, do not push
#   IMAGE=ghcr.io/foo/bar:tag ./build-and-push.sh
#
# Requires: docker, and a prior `docker login ghcr.io` (unless --no-push).

set -euo pipefail

# Directory of this script = frontend build context.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE="${IMAGE:-ghcr.io/medica-im/prospect:production}"
PUSH=1

for arg in "$@"; do
	case "$arg" in
		--no-push) PUSH=0 ;;
		-h|--help)
			grep '^#' "${BASH_SOURCE[0]}" | sed 's/^#//; s/^ //'
			exit 0
			;;
		*)
			echo "Unknown argument: $arg" >&2
			exit 2
			;;
	esac
done

echo "==> Image:   $IMAGE"
echo "==> Context: $SCRIPT_DIR"
echo "==> Push:    $([ "$PUSH" -eq 1 ] && echo yes || echo no)"

# Record the git commit the image is built from (for traceability).
GIT_SHA="$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
if ! git -C "$SCRIPT_DIR" diff --quiet 2>/dev/null || ! git -C "$SCRIPT_DIR" diff --cached --quiet 2>/dev/null; then
	GIT_SHA="${GIT_SHA}-dirty"
fi
echo "==> Git:     $GIT_SHA"

echo "==> Building image..."
docker build \
	--label "org.opencontainers.image.revision=$GIT_SHA" \
	-t "$IMAGE" \
	"$SCRIPT_DIR"

# Sanity check: the SvelteKit adapter-node build must be present in the image.
echo "==> Verifying build output inside image..."
if ! docker run --rm --entrypoint sh "$IMAGE" -c 'test -f build/index.js && test -f build/handler.js'; then
	echo "ERROR: build/ output missing in image — build likely failed." >&2
	exit 1
fi
echo "    build output OK"

if [ "$PUSH" -eq 1 ]; then
	echo "==> Pushing $IMAGE ..."
	docker push "$IMAGE"
	echo "==> Pushed $IMAGE (from git $GIT_SHA)"
else
	echo "==> Skipping push (--no-push). Image built locally as $IMAGE"
fi
