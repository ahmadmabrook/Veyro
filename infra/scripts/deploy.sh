#!/usr/bin/env bash
# Deploy a release locally: deploy.sh <local|development|staging> <release-tag>
# Builds image veyro-api:<release-tag>, starts it, and fails (non-zero) unless the smoke check passes.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="${1:?target: local|development|staging}"
release="${2:?release tag}"
export VEYRO_TARGET="$target" VEYRO_RELEASE="$release"
docker compose -f "$here/../compose.yaml" up -d --build --force-recreate
bash "$here/smoke.sh" "$target" "$release"
