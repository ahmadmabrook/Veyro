# M1-C-06 — SCN-033/065 bounded email-pattern context triage, MOD-001 subtree (2026-10-09)

Status: **LOCAL FILE-CONTEXT CLASSIFICATION ONLY. NO SCENARIO PASS, NO PRIVACY ASSURANCE VERDICT, NO REVIEW CONSUMED.**

This is the next bounded R03 data-boundary step under M1-C-06, taken directly on
`M1-C-06-SCN033-REPO-PATTERN-INVENTORY-2026-10-09.md`'s non-value counts. It classifies
*file context* for the 91 email-shaped matches that inventory located inside
`knowledge/03-Modules/MOD-001/`. It does not promote `SCN-MOD001-033` or
`SCN-MOD001-065`, does not invoke an independent review, does not create or imply an
approval, and changed no code, test, scenario, requirement, capability record, plan, or
control-state file. Nothing was committed, pushed, or run in CI. No third-party or
unapproved scanner was invoked; no network call was made. No ignored local credential
file (`.env.local` or equivalent) was opened or scanned — per
`.claude/rules/infra/secrets.md`.

## 1. Method actually executed

Read-only, standard-library Python 3 (`python3 -I`) over the **local working tree**,
restricted to Git-tracked plus non-ignored untracked paths under
`knowledge/03-Modules/MOD-001/`:

1. Path set from `git ls-files -co --exclude-standard -z`, filtered to the MOD-001
   prefix → **512 paths scanned** (all readable as text with `errors="replace"`; zero
   read failures, zero skips).
2. Email-shaped regex `[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}` applied
   per line.
3. For each match, recorded: file path, line number, domain, local-part **length and
   character class only**, and up to 25 characters of preceding line context used as a
   structural key (e.g. presence of the token `owner`).
4. Distinctness measured by truncated SHA-256 of the matched string, so repetition could
   be counted **without transcribing any address**.

**Reproduction of the inventory is exact**, which is the main reason to trust this
subset as the right 91: total `91`, domains `e.com=57`, `example.com=31`,
`pytest.fixture=2`, `github.com=1` — identical to the inventory's stated
31 reserved / 60 non-reserved (57 `e.com`, two `pytest.fixture`, one `github.com`) split.
The inventory did not publish its own regex, so this is a re-derivation that agrees on
every bucket, not a verified re-use of the identical expression.

### Key observed fact: only 4 distinct literal strings

Across all 91 matches there are **4 distinct matched values**, repeated:

| Redacted identity | Domain | Local part | Occurrences | Distinct files |
|---|---|---|---:|---:|
| V1 | `e.com` (non-reserved) | 1 char, lowercase alpha | 57 | 8 |
| V2 | `example.com` (RFC 2606 reserved) | 4 chars, lowercase alpha | 31 | 10 |
| V3 | `pytest.fixture` (not a TLD) | 3 chars, non-alpha-only | 2 | 1 |
| V4 | `github.com` | 3 chars (`git`), protocol identity | 1 | 1 |

Values are withheld; V1/V2's local parts are given only as length + character class.
One pre-existing MOD-001 review record already prints V2 and V1 in prose as the fixture
addresses they are — that prior disclosure is noted, not republished or amplified here.

## 2. Classification table (91/91 accounted for)

Paths are relative to `knowledge/03-Modules/MOD-001/evidence/`. "Lines" = distinct
matching lines.

| # | Path | Matches / lines | Value | Class | Basis observed in file context |
|---|---|---:|---|---|---|
| 1 | `security/SCN070-ROUND3-ACPX-RAW-2026-10-04.txt` | 24 / 24 | V1×18, V2×6 | Tool/log example (literal synthetic fixture echoed in transcript) | Raw ACPX agent-transcript capture of SCN-070 drills; matches sit in `owner:` lines of heredoc-printed disposable migration-record YAML, plus one prose row echo |
| 2 | `security/SCN070-ROUND5-ACPX-RAW-2026-10-04.txt` | 18 / 18 | V1×16, V2×2 | Tool/log example | Same transcript shape, `owner:` field of throwaway migration records |
| 3 | `security/SCN070-ROUND4-ACPX-RAW-2026-10-04.txt` | 14 / 14 | V1×14 | Tool/log example | Same |
| 4 | `implementation/SCN070-ROUND4-ROOTCAUSE-ACPX-RETRY-RAW-2026-10-04.txt` | 11 / 11 | V2×11 | Tool/log example | Same |
| 5 | `security/SCN070-ROUND2-BOUNDED-ACPX-RAW-2026-10-04.txt` | 6 / 6 | V1×5, V2×1 | Tool/log example | Same |
| 6 | `implementation/SCN070-R3-ROOTCAUSE-ACPX-RAW-2026-10-04.txt` | 5 / 5 | V1×1, V2×4 | Tool/log example | Same |
| 7 | `implementation/SCN070-R2-REMEDIATION-ACPX-RAW-2026-10-04.txt` | 3 / 3 | V1×1, V2×2 | Tool/log example | Same; the `owner:`-field shape was read directly here |
| 8 | `security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND3-2026-10-04.md` | 2 / 1 | V1×1, V2×1 | Tool/log example — prose enumeration | One table cell of a prior security-review record, in the secrets-rule row, explicitly stating the fixtures use these addresses |
| 9 | `implementation/SCN009-INDEPENDENT-REVIEW-ACPX-RAW-2026-10-04.txt` | 2 / 2 | V3×2 | **False-positive syntax** | Literal text `45-@pytest.fixture(scope="session")` — a grep line-number prefix abutting a Python decorator. No `@`-delimited mailbox exists; no local part, and `fixture` is not a TLD |
| 10 | `implementation/SCN020-FORK-FEASIBILITY-API-2026-10-09.json` | 1 / 1 | V4×1 | **Protocol/tool example** | `git@github.com` SSH clone-URL identity inside a captured GitHub API response body. Service account identity, not a natural-person mailbox |
| 11 | `security/SCN070-MIGRATION-ORDERING-LINT-SECURITY-REVIEW-ROUND2-2026-10-04.md` | 1 / 1 | V1×1 | Tool/log example — prose enumeration | Same review-record row as #8 |
| 12 | `implementation/SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` | 1 / 1 | V2×1 | Literal synthetic fixture | `owner:` field of a documented synthetic migration record |
| 13 | `implementation/scn070_ordering_lint_mutation_killcheck.py` | 1 / 1 | V2×1 | Literal synthetic fixture | Inline synthetic migration-record fixture inside a mutation kill-check helper |
| 14 | `security/SCN070-ROUND2-ACPX-RAW-2026-10-04.txt` | 1 / 1 | V2×1 | Tool/log example | Same transcript shape as #1 |
| 15 | `implementation/SCN070-ROUND5-ROOTCAUSE-ACPX-RAW-2026-10-05.txt` | 1 / 1 | V2×1 | Tool/log example | Same |

### Grouped totals by class

| Class | Matches | Notes |
|---|---:|---|
| Literal synthetic fixture (authored artifact: one `.py` helper, one `.md` execution record) | 2 | V2 only (reserved domain) |
| Tool/log/protocol example (transcript echo of the above, or prose enumeration of it) | 87 | V1×57 + V2×29 + V4×1; 13 of the 15 files are capture/report/protocol artifacts, including the false-positive transcript |
| False-positive syntax | 2 | V3 |
| Protocol identity (counted inside the 87 above, called out separately) | 1 | V4 `git@github.com` |
| **Real-looking and unresolved** | **0 natural-person candidates; 1 residual hygiene item (see §3)** | V1's non-reserved domain |
| Total | 91 | |

Post-run deterministic reconciliation: the grouped example row is 87, not the worker's initial 86; its components are 57 + 29 + 1, and V1 spans 8 files. The per-file rows and 91-match inventory were unchanged.

## 3. Residual, unresolved items — deliberately not closed here

1. **V1 sits at a non-reserved domain.** `e.com` is not among RFC 2606's reserved
   names (`example.com/.net/.org`, `.example`, `.invalid`, `.test`, `.localhost`).
   Its single-character local part and its exclusive appearance in `owner:` fields of
   deliberately-throwaway migration records read as synthetic-by-construction, and no
   context in any of the 8 files suggests a person. **But structural shape is not proof.**
   Whether an address at a live third-party domain is acceptable in committed evidence is
   a qualified privacy/hygiene judgment reserved to `SCN-MOD001-065`'s
   `veyro-security-reviewer`/Opus boundary. Recorded here as **UNRESOLVED**, not as a
   pass and not as a defect.
2. **The counts overstate the candidate surface, but under-rule-out nothing.** 2 of 91
   matches are not addresses at all (V3) and 1 is a service identity (V4), so at most 88
   matches are mailbox-shaped — reducible to 2 distinct strings. That reduction is an
   observation about repetition, **not** a finding of zero real personal data.
3. **No zero-real-data inference from pattern shape.** This step did not, and may not,
   conclude that MOD-001 contains no real personal data. A regex non-match is not evidence
   of absence; a synthetic-looking match is not evidence of synthesis. `SCN-MOD001-033`
   additionally requires classification ending in zero real personal data, and
   `SCN-MOD001-065` requires manual qualified judgment that every fixture is clearly
   labeled synthetic — **neither is satisfied by this record**.
4. **Labeling obligation not yet checked.** `SCN-MOD001-065` expects fixtures "clearly
   labeled synthetic." Nothing in this triage verified that V1/V2 carry an explicit
   synthetic/`EXAMPLE_NOT_REAL`-style label at their use sites. Open.

## 4. Explicit non-coverage

- **No review or assurance verdict of any kind is given or implied.** No
  `REVIEW_IN_FLIGHT.md` claim was read as licence, written, or cleared; no review
  entitlement was consumed.
- **The other pattern families are untouched and unresolved by this step:** the
  inventory's 26 Jordanian phone-shaped matches (all *outside* the MOD-001 subtree,
  including the frozen design-bundle mockup already disclosed in MOD-000's
  `DATA_CLASSIFICATION_AUDIT.md`), the 208 broad card-shaped matches, and the SSN-shaped
  0-count. None of those were classified, re-counted, or adjudicated here.
- **The 90 non-MOD-001 email-shaped matches** (181 raw − 91) were out of scope by
  instruction and remain unclassified.
- Binary, ignored, and untracked-ignored content remains unclassified, as the inventory
  already stated.
- Scope was the local working tree at this session's state; no commit, branch, or remote
  ref was consulted.

## 5. Preserved state (unchanged by this record)

- Gate-2 findings **F01–F14 remain 14/14 CLOSED**.
- The **19-operation compressed plan remainder is not incremented**: per
  `M1-C-06-R03-SOURCE-BOUNDARY-2026-10-09.md` and
  `M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md`, M1-C-06 stays a single coherent
  operation; this triage is an increment *within* it, not a new operation.
- `SCN-MOD001-033` and `SCN-MOD001-065` both remain **NOT EXECUTED / not promoted**.
  MOD-001 exit remains 0/8; WIP=1 holds; MOD-002 stays locked.
- No capability status, registry row, owner approval, or gate-3 disposition changed.

## 6. Smallest next legal C06 action

**Verify synthetic labeling at the two authored use sites, then hand the residual to the
reserved privacy boundary.** Concretely, the smallest next step is: inspect the two
authored fixture sites only — `implementation/scn070_ordering_lint_mutation_killcheck.py`
and `implementation/SCN070-MIGRATION-ORDERING-EXECUTION-2026-10-04.md` — and record
whether V1/V2 are accompanied by an explicit synthetic label at the point of use, writing
that observation as its own bounded evidence note.

That is strictly smaller than, and must precede, either of the two real candidates for
after it: (a) the equivalent context triage of the 90 non-MOD-001 email matches and the
card/phone families, and (b) the qualified `SCN-MOD001-065` privacy judgment, which is
the only thing that can dispose of §3's V1 residual and is reserved to a fresh-context
`veyro-security-reviewer`/Opus under the planned shared R04 assurance — not a newly
inferred review entitlement. Neither (a) nor (b) is authorized by this record.
