#!/usr/bin/env bash
# Local code rollback rehearsal: rollback-rehearsal.sh [target]
# Builds two images from different code bytes in temp contexts (repo is never modified):
#   A = copy of backend/ as-is; B = same copy with a deliberate defect in app/main.py.
# Deploys A (smoke must pass), B (smoke must FAIL), then A again WITHOUT rebuild (same image ID, smoke must pass).
# Tags are unique per run and never overwritten; containers, temp dirs and the images this run built are removed on exit.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
backend="$(cd "$here/../../backend" && pwd)"
target="${1:-staging}"
case "$target" in local|development|staging) ;; *) echo "rehearsal refused: invalid target '$target'" >&2; exit 1 ;; esac
export VEYRO_TARGET="$target"
compose=(docker compose -f "$here/../compose.yaml")

run="rehearsal-$(date +%s)-$$"
tag_a="$run-a"
tag_b="$run-b"
tmp="$(mktemp -d)"
built=()
cleanup() {
  VEYRO_RELEASE="$tag_a" "${compose[@]}" down >/dev/null 2>&1 || true
  for t in ${built[@]+"${built[@]}"}; do docker image rm "veyro-api:$t" >/dev/null 2>&1 || true; done
  rm -rf "$tmp"
}

# Do not disturb an existing deployment of this target.
if [ -n "$(VEYRO_RELEASE="$tag_a" "${compose[@]}" ps -aq 2>/dev/null)" ]; then
  echo "rehearsal refused: containers already exist for target '$target'; stop them first" >&2
  exit 1
fi
trap cleanup EXIT

mkdir "$tmp/a" "$tmp/b"
for d in a b; do
  cp -R "$backend/Dockerfile" "$backend/requirements.txt" "$backend/app" "$tmp/$d/"
  find "$tmp/$d" -name __pycache__ -prune -exec rm -rf {} +
  chmod -R a+rX "$tmp/$d"
done
sed 's/"status": "ok"/"status": "degraded"/' "$tmp/a/app/main.py" >"$tmp/b/app/main.py"
if cmp -s "$tmp/a/app/main.py" "$tmp/b/app/main.py"; then
  echo "rehearsal FAILED: defect injection changed nothing" >&2
  exit 1
fi

bash "$here/build.sh" "$tag_a" "$tmp/a"
built+=("$tag_a")
bash "$here/build.sh" "$tag_b" "$tmp/b"
built+=("$tag_b")
id_a="$(docker image inspect -f '{{.Id}}' "veyro-api:$tag_a")"
id_b="$(docker image inspect -f '{{.Id}}' "veyro-api:$tag_b")"
echo "image A $tag_a $id_a"
echo "image B $tag_b $id_b"
if [ "$id_a" = "$id_b" ]; then
  echo "rehearsal FAILED: images A and B are identical" >&2
  exit 1
fi

if ! bash "$here/deploy.sh" "$target" "$tag_a"; then
  VEYRO_RELEASE="$tag_a" "${compose[@]}" logs api --tail 80 >&2 || true
  exit 1
fi

echo "deploying release B (deliberate code defect); smoke must fail"
if bash "$here/deploy.sh" "$target" "$tag_b"; then
  echo "rehearsal FAILED: defective release passed smoke" >&2
  exit 1
fi
echo "release B correctly failed; rolling back to A without rebuild"

bash "$here/deploy.sh" "$target" "$tag_a"
if [ "$(docker image inspect -f '{{.Id}}' "veyro-api:$tag_a")" != "$id_a" ]; then
  echo "rehearsal FAILED: image A changed during rollback" >&2
  exit 1
fi
echo "rollback rehearsal OK (A=$id_a B=$id_b)"
