#!/usr/bin/env bash
# Build an immutable local release image: build.sh [release-tag] [build-context]
# Tags veyro-api:<release-tag> once; refuses to overwrite an existing tag.
# Default tag is the 12-char git SHA, and then the backend tree must be clean so the tag matches its bytes.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
release="${1:-}"
context="${2:-$repo/backend}"
if [ -z "$release" ]; then
  if [ -n "$(git -C "$repo" status --porcelain -- backend)" ]; then
    echo "build refused: backend/ has uncommitted changes; commit or pass an explicit release tag" >&2
    exit 1
  fi
  release="$(git -C "$repo" rev-parse --short=12 HEAD)"
fi
case "$release" in
  *[!A-Za-z0-9_.-]* | "" | -* | .*) echo "build refused: invalid release tag '$release'" >&2; exit 1 ;;
esac
if docker image inspect "veyro-api:$release" >/dev/null 2>&1; then
  echo "build refused: veyro-api:$release already exists (release tags are immutable; use a new tag)" >&2
  exit 1
fi
docker build -t "veyro-api:$release" "$context"
echo "built veyro-api:$release id=$(docker image inspect -f '{{.Id}}' "veyro-api:$release")"
