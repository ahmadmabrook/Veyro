#!/usr/bin/env bash
# Deploy an existing local release image: deploy.sh <local|development|staging> <release-tag>
# Never builds or pulls: veyro-api:<release-tag> must already exist (see build.sh). Rollback = deploy the previous tag.
# Starts it and fails (non-zero) unless the smoke check passes.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="${1:?target: local|development|staging}"
release="${2:?release tag}"
case "$target" in local|development|staging) ;; *) echo "deploy refused: invalid target '$target'" >&2; exit 1 ;; esac
case "$release" in *[!A-Za-z0-9_.-]* | "" | -* | .*) echo "deploy refused: invalid release tag '$release'" >&2; exit 1 ;; esac
export VEYRO_TARGET="$target" VEYRO_RELEASE="$release"
if ! image_id="$(docker image inspect -f '{{.Id}}' "veyro-api:$release" 2>/dev/null)"; then
  echo "deploy refused: image veyro-api:$release not found locally (run build.sh first)" >&2
  exit 1
fi
image_release="$(docker image inspect -f '{{ index .Config.Labels "veyro.release" }}' "veyro-api:$release")"
if [ "$image_release" != "$release" ]; then
  echo "deploy refused: image release label '$image_release' does not match tag '$release'" >&2
  exit 1
fi
compose=(docker compose -f "$here/../compose.yaml")
"${compose[@]}" up -d --no-build --pull never --force-recreate
running_id="$(docker inspect -f '{{.Image}}' "$("${compose[@]}" ps -q api)")"
if [ "$running_id" != "$image_id" ]; then
  echo "deploy FAILED: running image $running_id is not veyro-api:$release ($image_id)" >&2
  exit 1
fi
echo "deployed veyro-api:$release image=$image_id"
bash "$here/smoke.sh" "$target" "$release"
