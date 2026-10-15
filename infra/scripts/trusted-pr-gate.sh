#!/usr/bin/env bash
# Trusted-base PR guard. Runs from the protected base checkout; candidate content is only ever
# fetched as inert Git objects and compared, never checked out, sourced, or executed.
#
# Inputs (environment, set by .github/workflows/veyro-trusted-gate.yml):
#   PR_NUMBER  numeric pull request number
#   HEAD_SHA   40-hex candidate head SHA from the event payload
set -euo pipefail

fail() {
  echo "::error::trusted-base PR guard: $*"
  exit 1
}

: "${PR_NUMBER:?PR_NUMBER is required}"
: "${HEAD_SHA:?HEAD_SHA is required}"

[[ "$PR_NUMBER" =~ ^[1-9][0-9]{0,9}$ ]] || fail "PR_NUMBER is not a plain positive integer"
[[ "$HEAD_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "HEAD_SHA is not a 40-hex SHA"

base_sha="$(git rev-parse --verify HEAD^{commit})"

# Fetch the candidate as inert objects into a fixed ref; nothing is checked out.
git fetch --no-tags --quiet origin "+refs/pull/${PR_NUMBER}/head:refs/remotes/candidate/head"
fetched_sha="$(git rev-parse --verify refs/remotes/candidate/head^{commit})"
[[ "$fetched_sha" == "$HEAD_SHA" ]] \
  || fail "fetched candidate ${fetched_sha} does not match event head ${HEAD_SHA}"

# Compare the candidate's protected gate files to the current protected base. This fails closed
# on stale branches and prohibits a newly added sibling workflow with a spoofed check name.
merge_base="$(git merge-base "$base_sha" "$fetched_sha")" \
  || fail "no merge base between base ${base_sha} and candidate ${fetched_sha}"

echo "base=${base_sha} merge-base=${merge_base} candidate=${fetched_sha}"

# --no-renames lists both old and new paths of a rename; -z keeps odd file names unambiguous.
status=0
while IFS= read -r -d '' changed; do
  if [[ "$changed" == .github/workflows/* || "$changed" == .github/actions/* ||
        "$changed" == infra/scripts/trusted-pr-gate.sh ]]; then
    echo "::error::candidate differs from protected base at a gate file"
    status=1
  fi
done < <(git diff --no-ext-diff --no-textconv --no-renames --name-only -z "$base_sha" "$fetched_sha")

if [[ "$status" -ne 0 ]]; then
  fail "candidate differs from protected base in workflow/action/guard files; use a separately reviewed bootstrap"
fi

git diff --check --no-ext-diff "$merge_base" "$fetched_sha" \
  || fail "git diff --check reported whitespace errors"

echo "trusted-base PR guard passed"
