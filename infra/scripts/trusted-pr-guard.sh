#!/usr/bin/env bash
# Execute only from the protected base snapshot. The PR head is inspected as
# Git objects, never checked out or executed. HEAD_SHA is validated by the
# workflow against the fetched refs/pull/N/head before this script runs.
set -euo pipefail

deny() { printf '::error::trusted-base PR guard: %s\n' "$1" >&2; exit 1; }

[[ "${BASE_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || deny 'invalid base SHA'
[[ "${HEAD_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || deny 'invalid head SHA'
[[ "$(git rev-parse HEAD)" == "$BASE_SHA" ]] || deny 'not running from the base snapshot'
git cat-file -e "$HEAD_SHA^{commit}" || deny 'candidate commit is absent'

# Compare only changes authored since this PR forked. Comparing base..head
# would falsely treat base-owned files as deletions on an older PR branch.
fork="$(git merge-base "$BASE_SHA" "$HEAD_SHA")" || deny 'no common ancestor'
[[ -n "$fork" ]] || deny 'empty merge base'
changes="$(mktemp)"
trap 'rm -f "$changes"' EXIT
git diff --no-ext-diff --no-textconv --no-renames --name-only -z \
  "$fork" "$HEAD_SHA" > "$changes" || deny 'cannot enumerate PR changes'

while IFS= read -r -d '' path; do
  case "$path" in
    .github|.github/*|CODEOWNERS|docs/CODEOWNERS|infra/scripts|infra/scripts/trusted-pr-guard.sh|infra/scripts/opus_review_gate.py|infra/scripts/tests/test_opus_review_gate.py)
      deny 'PR changes protected .github content, CODEOWNERS, or a trusted guard/review-gate script'
      ;;
  esac
done < "$changes"

git diff --no-ext-diff --no-textconv --check "$fork" "$HEAD_SHA" \
  || deny 'PR contains whitespace errors'
printf 'trusted-base PR guard: PASS (base=%s fork=%s head=%s)\n' \
  "$BASE_SHA" "$fork" "$HEAD_SHA"
