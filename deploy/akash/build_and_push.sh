#!/usr/bin/env bash
# Build Rematch image and push to Docker Hub for Akash.
#
# Usage:
#   export DOCKERHUB_USER=yourname
#   ./deploy/akash/build_and_push.sh
#   # optional tag:
#   TAG=v0.1.0 ./deploy/akash/build_and_push.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -z "${DOCKERHUB_USER:-}" ]]; then
  echo "Set DOCKERHUB_USER (Docker Hub username), e.g.:"
  echo "  export DOCKERHUB_USER=yourname"
  exit 1
fi

TAG="${TAG:-latest}"
IMAGE="${DOCKERHUB_USER}/rematch:${TAG}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker Desktop or: brew install colima docker && colima start"
  exit 1
fi

echo "[build] ${IMAGE}"
docker build -f Dockerfile.akash -t "${IMAGE}" .

echo "[push] ${IMAGE}"
docker push "${IMAGE}"

echo
echo "Done. Next:"
echo "  1. Edit deploy/akash/deploy.yml → image: ${IMAGE}"
echo "  2. Open https://console.akash.network/ → Upload SDL"
echo "  3. Paste secrets from .env into env fields"
echo "  4. See docs/AKASH_DEPLOY.md"
