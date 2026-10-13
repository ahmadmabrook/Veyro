# M1-C-06 — OSV dependency-advisory client, synthetic increment (2026-10-09)

Status: **LOCAL SYNTHETIC CANDIDATE ONLY.** No CI run, no scan of Veyro's
real lock, no independent security assurance, no CAP approval, no scenario
disposition. `SCN-MOD001-094` remains **NOT EXECUTED**.

Operation `894573ec-0190-4d18-8351-611e898051d4`, role
`ARCHITECTURE_CRITICAL`, configured `claude-opus-5`; runtime model identity
is not separately attested here, so nothing in this record is a qualified
reviewer verdict. Governing-baseline check run first:
`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` → **PASS,
4/4 hashes match `PROJECT_INDEX.md`**.

## 1. What was built and why this shape

`M1-C-06-SCANNER-CAPABILITY-ROUTE-2026-10-09.md` §3.2 selected a
project-authored stdlib OSV client for the GOV-01-R03/R04 dependency-scanning
gap (candidate B, `pip-audit`, recorded as the pre-reasoned fallback if an
independent reviewer judges a self-authored client insufficient for a
Blocker-tier scenario). `M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md` §3
narrows the governance claim: this file is **project source**, governed by
`CAPABILITY_POLICY.md` like the eight `tools/validate_*.py` gate scripts, but
it is not a third-party executable, so it triggers no acquisition-provenance
review and **claims no CAP exemption**. Its assurance rides the planned shared
material-code review, which has not happened.

Two files created, nothing else touched:

| File | Lines | SHA-256 |
|---|---|---|
| `tools/scan_dependency_advisories.py` | 548 | `3c256b078108f860fde307ae331a35579a6d6b96f9744e096dee718f3c40ccd0` |
| `tools/tests/test_scan_dependency_advisories.py` | 467 | `e4c74efd61a7268233321128b8ff70a4752ffa3149747c62d7eb354639ae992a` |

Stdlib only (`argparse`, `json`, `re`, `sys`, `urllib`, `pathlib`,
`typing`) — no new dependency, no lock regeneration, consistent with
`generate_requirements_lock.py`/`net_failure_drill.py`'s existing convention.
The lockfile path is a **required positional argument with no default**, so no
invocation can drift onto the real project lock by omission.

## 2. Exit-code contract and fail-closed cases

`0` ALLOW · `1` DENY, validated advisory present · `2` DENY, a clean result
could not be established. Precedence is documented and tested: a detected
advisory wins over a transport/coverage problem, so a decisive finding is never
downgraded to exit 2. Both deny paths are nonzero, so neither can produce a
false clean.

ALLOW is expressed as a **positive equality** in the pure `decide()` function —
`clean_count == entry_count` with `entry_count > 0` — not as the absence of
problems. A future loop that skipped a package therefore fails closed as
`INCOMPLETE_ADVISORY_COVERAGE` rather than passing on a short result list.
Silence, an empty body, or "no rows" is never a pass.

Named deny codes, each covered by at least one focused test:

- Lock: `MISSING_LOCK`, `UNREADABLE_LOCK` (non-UTF-8 or unreadable path,
  including a directory), `EMPTY_LOCK`, `MALFORMED_LOCK_ENTRY` (missing hash,
  orphan hash line, second hash line, bad digest shape, pip directive),
  `UNPINNED_LOCK_ENTRY` (`>=`, `~=`, bare name, `==*`, extras, env marker),
  `DUPLICATE_LOCK_ENTRY`.
- Advisory source: `ADVISORY_SOURCE_UNREACHABLE` (URLError, timeout, any
  unexpected exception class), `ADVISORY_SOURCE_HTTP_STATUS` (HTTPError and any
  non-200 status), `ADVISORY_RESPONSE_TOO_LARGE` (>1 MiB, rejected unparsed),
  `MALFORMED_ADVISORY_RESPONSE` (not UTF-8, not JSON, not an object, `vulns`
  not a list, element not an object, `aliases` not a list, non-string alias,
  more than 256 advisories), `INVALID_ADVISORY_ID`.
- Verdict: `VULNERABILITY_ADVISORY_PRESENT`, `INCOMPLETE_ADVISORY_COVERAGE`,
  `INVALID_TIMEOUT`.

## 3. Untrusted-input handling

Both the lock file and every OSV response are treated as untrusted. The
response is parsed with `json.loads` and nothing else — the module contains no
`eval`/`exec`/`subprocess`/`__import__`/`pickle` (verified by direct grep;
`urllib.request.urlopen` at line 159 is the single network call site). Only
`vulns[].id` and `vulns[].aliases[]` are read at all; `summary`, `details`,
`references` and `affected` are never read and never printed.

Report hygiene follows the BUG-055 value-free discipline, applied to a second
untrusted source: the only response-derived values ever echoed are an advisory
ID matching `ADVISORY_ID_RE` and a CVE alias matching `CVE_RE`. A rejected
advisory ID is reported by index, never by value; non-CVE alias text is
reported as a **count**; an HTTP failure echoes the numeric status only, and a
transport failure echoes the exception class name only, never a
server-controlled message. Findings are deduplicated by advisory ID with CVE
aliases merged, and output is sorted, so the report is byte-stable across runs
(locked by `test_output_is_stable_across_runs`).

Bounds: per-query timeout default 10s, hard ceiling 120s, validated `>0` before
any query; response read capped at `MAX_RESPONSE_BYTES + 1` bytes so an
oversized body is *detectable* rather than silently truncated; at-limit bodies
are still parsed (both boundary cases tested).

## 4. Exact commands and results

All run from the repository root with the project venv interpreter
(Python 3.14.5). **pytest (CAP-011) and Ruff (CAP-010) were deliberately not
used**: both are registered DRAFT/QUALIFIED-not-APPROVED with "no reliance of
any kind permitted", so the focused tests are stdlib `unittest` — the same
convention as `tools/tests/test_assert_ci_python313.py` — and no Ruff lint or
SAST run was performed on any tree.

| Command | Result |
|---|---|
| `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | PASS 4/4 |
| `backend/.venv/bin/python -m py_compile tools/scan_dependency_advisories.py tools/tests/test_scan_dependency_advisories.py` | exit 0 |
| `backend/.venv/bin/python -I -m unittest discover -s tools/tests -p "test_scan_dependency_advisories.py"` | **45 tests, OK, exit 0** |
| `… scan_dependency_advisories.py <absent path>` | `MISSING_LOCK`, exit 2 |
| `… scan_dependency_advisories.py <comments-only lock>` | `EMPTY_LOCK`, exit 2 |
| `… scan_dependency_advisories.py <unpinned `>=` lock>` | `UNPINNED_LOCK_ENTRY` at line 3, exit 2 |
| `… scan_dependency_advisories.py <lock> --timeout 0` | `INVALID_TIMEOUT`, exit 2, no query attempted |
| `… scan_dependency_advisories.py` (no argument) | argparse usage error, exit 2 |

The four CLI drills ran against throwaway fixtures in an OS temp directory
(removed afterwards) and **all deny before the query loop is reached**, so no
network request was made by any command in this operation. Every advisory
response in the test suite is an injected fixture; the module's single network
path is never invoked, which `test_network_path_is_injectable_so_no_test_can_
reach_it` locks structurally by asserting the `fetcher` default of both `main`
and `run_scan` is the one network implementation and that nothing patches a
module global to get there.

Test coverage of the SCN-094 shape specifically: a synthetic known-vulnerable
response denies with exit 1 and cites the advisory ID **and** its CVE alias;
the patched/clean companion (`{}`, `{"vulns": []}`, `{"vulns": null}`) allows
with exit 0; a clean package does not mask a vulnerable one in the same lock.

## 5. Synthetic identifiers — no invented CVE

Every advisory identifier in the test corpus is deliberately impossible:
`CVE-1900-0001` (CVE IDs do not predate 1999), `GHSA-aaaa-bbbb-cccc`,
`PYSEC-1900-0001`, with package names `veyro-synthetic-clean` /
`veyro-synthetic-vulnerable`. **No real CVE was invented or asserted.**

**Unexecuted dependency for SCN-MOD001-094's live execution:** the scenario's
own text requires "a long-since-fixed historical CVE" in a throwaway lockfile.
That exact real advisory ID and the pin that carries it must be chosen from the
live advisory source at execution time by whoever executes the scenario; it is
recorded here as outstanding rather than guessed. Nothing in this operation
establishes that a real historical CVE will be flagged by this client — only
that a validated advisory-shaped response is.

## 6. Limitations (disclosed, not resolved)

1. **No CI wiring.** No workflow invokes this tool; GOV-01-R03's "runs in CI"
   acceptance criterion and GOV-01-R04's blocking-gate criterion are both
   unmet. No workflow file was created or edited.
2. **No live advisory-source behavior observed.** Every response is synthetic.
   That the real OSV API answers in the validated shape, within the size
   bound, for a PyPI `name==version` query is **assumed from its documented
   contract and prior sessions' recorded use, not demonstrated here.** A live
   query could reveal shape details this validator rejects — that is a
   fail-closed direction (exit 2), not a false clean, but it is unverified.
3. **One source, no severity/fix policy.** PyPI ecosystem only; no caching,
   retries, allowlist, severity threshold, or fixed-version suggestion. Any
   validated advisory denies. Deliberately minimal per the route decision.
4. **Parser accepts only the generated shape.** Multi-hash pip locks,
   environment markers, extras, direct URLs and non-`==` specifiers are all
   named denials, not supported inputs. One read-only test copies the text of
   `backend/requirements-dev.lock.txt` into the throwaway directory and parses
   the copy to prove the parser is non-vacuous against the real generated
   format — **zero advisory queries, no scan of the real lock, no result
   claimed about Veyro's dependencies.**
5. **No independent assurance.** This code was written and run by the
   implementing operation. Per DC-06 there is no self-approval: a fresh-context
   independent review is required before any reliance, and the §3.2 fallback to
   `pip-audit` remains live if that review judges a project-authored client
   insufficient for a Blocker-tier gate.
6. **No mutation/adversarial battery** was run against this validator beyond
   the focused negative cases above.

## 7. Explicit non-promotion

- `SCN-MOD001-094` remains **NOT EXECUTED**; no scenario disposition changed.
- No CI workflow, lockfile, capability registry row, module manifest, plan,
  scenario record, bug record or remote was created or modified. No commit, no
  push.
- No capability row is claimed for this script and none is implied; if the
  shared reviewer rules it needs one, `M1-C-06-CAP-ORDERING-PLAN-DECISION`
  §3's pre-reasoned reversal applies (one registry row inside the same reviewer
  slot, no sixth action).
- CAP-010/CAP-011/CAP-012 remain QUALIFIED-not-APPROVED and were not relied on.
  BUG-057 remains OPEN. All previously known findings stand; nothing is claimed
  closed by this operation.
- No paid service, no spend, no real member data, no deploy, no owner-reserved
  change. WIP=1 preserved; MOD-001 active, MOD-002 locked.

## 8. Correction — explicit-null `vulns` false-clean (2026-10-09, operation `5111c83b-8aa7-42ef-88eb-e657e1dfc346`, subgoal `M1-C-06-OSV-NULL-FAILCLOSED`)

**Defect, as observed before the edit.** `_validate_advisories` read
`payload.get("vulns", [])` and then returned CLEAN for `vulns in (None, [])`,
so an OSV response of exactly `{"vulns": null}` produced **CLEAN / exit 0** —
a false clean from a malformed untrusted response, contrary to §2's own
malformed-response-denies contract. Reproduced directly against the pinned
pre-edit source (hash below): `{}`, `{"vulns": []}` and `{"vulns": null}` all
returned `kind='clean'`. Governing-baseline check run first:
`backend/.venv/bin/python knowledge/00-System/verify_baselines.py` → **PASS,
4/4 hashes match `PROJECT_INDEX.md`**; both files hashed equal to §1's
recorded values before any edit, so the repair was applied to the artifact
this record describes.

**Fix (minimal, no behavior change outside this case).** Absence of the
`vulns` key is now distinguished from an explicit value: a missing key stays
CLEAN (OSV's own shape for "no advisories"), a non-list value — `null`
included — returns `ERROR` with the existing value-free
`MALFORMED_ADVISORY_RESPONSE — 'vulns' is not a list` and **exit 2**, and an
empty list stays CLEAN. No new message string, no new field read, no
value from the response echoed. The focused test's clean-shape loop keeps
`{}` and `{"vulns": []}`; `{"vulns": null}` moved out of it into a new
`test_null_vulns_denies_as_malformed`, which asserts exit 2,
`MALFORMED_ADVISORY_RESPONSE` present and `RESULT: ALLOW` absent through the
real JSON-decode path (the test responder encodes the dict to wire bytes).

**Changed hashes.**

| File | Lines | SHA-256 before | SHA-256 after |
|---|---|---|---|
| `tools/scan_dependency_advisories.py` | 548 → 555 | `3c256b078108f860fde307ae331a35579a6d6b96f9744e096dee718f3c40ccd0` | `2a75b00985adee5fe03555045d53cb72dba39a22621af1f78af4e8a30d42bbe4` |
| `tools/tests/test_scan_dependency_advisories.py` | 467 → 477 | `e4c74efd61a7268233321128b8ff70a4752ffa3149747c62d7eb354639ae992a` | `1b06ecec12d34260faf908b075a1cca1d29e79f62e99a27fa8144596bedbb7db` |

No other file was touched. Unrelated pre-existing dirty work in the tree was
left untouched and is not part of this correction.

**Observed this operation (nothing else was executed).**

| Command | Result |
|---|---|
| `backend/.venv/bin/python knowledge/00-System/verify_baselines.py` | PASS, 4/4 |
| `backend/.venv/bin/python -I -m unittest discover -s tools/tests -p "test_scan_dependency_advisories.py"` (pre-edit) | **45 tests, OK, exit 0** — matching §1's recorded baseline |
| `backend/.venv/bin/python -m py_compile` on both files | exit 0 |
| same unittest discovery (post-edit) | **46 tests, OK, exit 0** |
| direct call: `{}`, `{"vulns": []}` | `kind='clean'` (unchanged) |
| direct call: `{"vulns": null}`, `{"vulns": {}}`, `{"vulns": 0}` | `kind='error'`, value-free `MALFORMED_ADVISORY_RESPONSE` |

**Still-unexecuted boundaries — unchanged by this correction.** Every limit in
§6 and §7 stands exactly as written: no CI run, no live OSV query, no scan of
Veyro's real lock, no capability row or approval, no independent review, no
mutation/adversarial battery, and `SCN-MOD001-094` remains **NOT EXECUTED**.
This operation repaired one named defect and observed one focused synthetic
suite; it is **not** an assurance that the remaining response-shape surface is
free of comparable false-clean paths, and it is not a reviewer verdict on this
file. One adjacent leniency was deliberately **left unchanged** and is flagged
for the shared material-code review rather than silently edited here: an
advisory's `aliases` key is still coerced from `null` to `[]`
(`if aliases in (None,)`), which is a cite-fewer-aliases direction rather than
a false clean — the advisory itself still denies — but it is the same
null-tolerance pattern and was not in this operation's scope. No commit, no
push, no scenario or module-state change; WIP=1 preserved, MOD-001 active,
MOD-002 locked.
