---
doc: M1-C-07 fork-head fetch local verification
status: LOCAL_CANDIDATE_ONLY
date: 2026-10-09
bounded-operation: M1-C-07
runner-operation: b35ba45d-1288-4cb4-bc48-3713ec7e92b9
---

# GOV-01-R01/R02: fork-head checkout correction

The untracked candidate `.github/workflows/test-pyramid.yml` previously fetched a pull-request head SHA from the base `github.repository` URL in all six jobs. A true fork-only commit may not exist there. The Sonnet implementation call changed those six sites to take `github.event.pull_request.head.repo.full_name` as environment data, validate an owner/repo slug, construct the tokenless URL from `github.server_url`, and fetch the 40-hex event head SHA. It preserved existing checkout commands and the workflow's held-capability disclosures. No other product file was changed by that call.

Independent local checks: Ruby parsed the YAML as six jobs; all 16 shell run blocks passed `bash -n`; all six fetch steps read the event head repository, place the slug guard before URL construction and fetch, and pass the pinned head SHA to `git fetch`. Three execution jobs have an additional `rev-parse HEAD` readback; the three pre-existing applicability jobs use `checkout FETCH_HEAD` without that extra readback. The guarded operation completed exit 0 and recorded a material code checkpoint. The worker's synthetic slug checks accepted ordinary fork names and refused metacharacters, traversal, empty, extra-segment and newline inputs.

This is not live proof. The workflow is uncommitted and has not run in GitHub CI. CAP-008 remains pinned to local Colima, so Linux integration is held; CAP-011/012 qualification and the known local regression failures remain unresolved. No SCN-016/036/061/071 PASS, R01/R02 certification, or security capability grant is inferred. C06 OSV/typecheck-CI scope remains in C05; C06 itself remains held on its separate R03 capability decision.
