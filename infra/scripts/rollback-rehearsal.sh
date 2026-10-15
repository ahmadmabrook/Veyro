#!/usr/bin/env bash
# Local rollback rehearsal: rollback-rehearsal.sh [target]
# 1) deploy "good" (smoke must pass); 2) deploy "bad" (invalid config; smoke must FAIL);
# 3) redeploy "good" (smoke must pass). Containers are removed on exit.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="${1:-staging}"
export VEYRO_TARGET="$target"
trap 'VEYRO_RELEASE=good docker compose -f "$here/../compose.yaml" down >/dev/null 2>&1 || true' EXIT

bash "$here/deploy.sh" "$target" good

echo "deploying deliberately broken release"
VEYRO_RELEASE=bad docker compose -f "$here/../compose.yaml" -f "$here/../compose.broken.yaml" \
  up -d --build --force-recreate
if bash "$here/smoke.sh" "$target" bad 2>/dev/null; then
  echo "rehearsal FAILED: broken release passed smoke" >&2
  exit 1
fi
echo "broken release correctly failed smoke; rolling back to good"

bash "$here/deploy.sh" "$target" good
echo "rollback rehearsal OK"
