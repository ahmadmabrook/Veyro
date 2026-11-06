# MOD-004 — §6 reconciliation ledger for `INTERNAL_CAP_MODE = UNMETERED`

`OWNER-2026-11-06-internal-cap-unmetered.md` §6 requires that five live documents be reconciled
prospectively, each in its own reviewed change, once that record is effective, "preserving every
historical figure and the recorded overrun as history". The record became effective on 2026-11-06:
independent Opus review APPROVED on SHA-256
`56966906282b8028e1a37986535e34550735cbb2afa4e9cccfe4778497be3cab` (asserted — post-runner reviews
leave no `*.evidence.json`), owner attestation (recorded by `first_publish_audit` on the basis
"operator attestation, not cryptographic proof"), published `e41a695`, exact-SHA push CI run
`42272690841` conclusion `success`.

This file records what was done for each item and **exactly how far each one's review got**. It is a
ledger, not an authorization: it grants nothing, closes no blocker, and supersedes no clause on its
own. Every supersession named here is the owner record's own.

## Publication and review state — read this before the table

At the time of writing, **nothing below is published.** Every edit is uncommitted working-tree
content, and this file is untracked.

**Each item is pinned by SHA-256 below.** An earlier revision of this ledger dispositioned the five
items without pinning any of them, and went stale within minutes: it certified two sentences as
deleted from `CAP-ENVELOPE.md` while a later edit had already restored and annotated them, so the
ledger asserted deletions that no longer existed. A reviewer caught it. Hashes are the fix, because
a hash fails when the bytes move and a prose claim does not.

**The review position, stated without flattery.** Every item went through at least one independent
round, and every blocking finding was confirmed first-hand and remediated. But **no item's final
bytes carry an independent APPROVED**, because in every case remediation produced new bytes after
the last review of that subject — including item 1, which was APPROVED and then edited again to take
five of that review's seven advisories. The closing gate is therefore a single consolidated
independent review over the final bytes of the whole change set, not six separate re-reviews. Where
a last correction was self-verified instead of re-reviewed, it is marked and the reason is given.

**The two-iteration rule, and how it was applied.** The owner's directive sets a circuit breaker
after two unsuccessful review iterations. Three subjects reached that point — items 3 and 5 and this
ledger — each with findings that were *checkable facts* rather than judgments: a miscounted
enumeration, a false attribution of owner reservation, an account of deletions that had been undone.
Each was verified directly against the records and the bytes and corrected, rather than sent for a
third round. The breaker stops the loop; it does not license publishing a sentence known to be
false.

**Commit plan against §6's "in its own reviewed change".** Each item lands as its own commit, in this
order: this ledger first, so that artifacts citing it do not reference a missing path; then
`CAP-EVIDENCE.md`, so `CLAUDE.md`'s reference to "the deviation sections" is true when it lands; then
items 1, 2, 3 and 5. They are pushed together, so the exact-SHA CI result attaches to the head
commit and validates the resulting tree, not each commit separately. Stated so it is not mistaken
for per-commit CI.

## Dispositions

| §6 item | Document and final SHA-256 | Disposition | Review state |
|---|---|---|---|
| 1 | `CLAUDE.md` — `49fdeb3bf699631899e44a0b9374af90d0701484e116319a5b5db5188df9d32f` | **Edited.** §2's six supersessions enumerated; the pre-pull/security half restated as still gating with §2's delegation and the wider pull predicate; the surviving attempt, spending and measurement limits named, with the custom-rule-creation cap marked already reached; "unmetered is not unblocked" stated. A false sentence corrected — see below. | R1 **CHANGES_REQUESTED** (blocking: claimed only one clause lost force where §2 supersedes six, which would have left the PAUSED-and-BLOCKED stoppage reading as live). R2 **APPROVED**, with 7 advisories; **5 were then taken, so the final bytes postdate that approval.** |
| 2 | `knowledge/03-Modules/MOD-004/CAP-ENVELOPE.md` — `308b285a99d24a4bd839f4859008092a8339c355038c9035174ab149d376c4b3` | **Edited by annotation only.** A Status section supersedes the ceiling, the stop rule's limits and the stoppage. **No original sentence is deleted** — see the exact account below. | R1 **APPROVED** on then-current bytes with 4 advisories, 2 taken. R2 **CHANGES_REQUESTED** (3: two false preservation claims and a mislocated annotation). Remediated; final bytes self-verified, not re-reviewed. |
| 3 | `knowledge/03-Modules/MOD-004/REQUIREMENTS.md` — `296426e380e6c3a6a8267b195c0056d1968ef9c7184b67a344a39e14f0446def` | **Edited.** The quoted clause split into superseded and surviving halves; owner-reserved item 1 struck in place; item 2 scoped to what §2 actually delegated; the section header qualified. A false sentence corrected — see below. | R1 **CHANGES_REQUESTED** (2). R2 **CHANGES_REQUESTED** (2 blocking: an invented owner reservation, and a blanket header the items contradicted; plus 4 advisories, all taken). Remediated under the circuit breaker; final bytes self-verified. |
| 4 | `contracts/engineering/mod004-s0-scenario-qa.md` — `a146c060a175b62d80f6a2f830ca7d8f56a47a11ac7cbb9f9d5d93df3d527c6c`, **unchanged** | **Not edited, by decision.** See below. | Not applicable: no change was made. Both independent reviewers tested the reasoning and neither found a lawful cheaper path. |
| 5 | `contracts/engineering/module-capabilities.yaml` — `925c983d993b4c3939d8527f503ea445f0c411e6c27a3cf7690c94946a6c8feb`; `mod004-s0-capability.json` — `5baad4ab1431488adb15a7e712628365f2cf3d048cba88c5f37e05ca6894e7e4`. **`mod004-s0-eligibility.json` is NOT edited**, and stays at `92aad9c46ba0dd8405ab49d43e4f27328c3285de745721a7ed8b7e0dc197deea` | **Annotated, not deleted.** §6 names only the manifest among these; `mod004-s0-capability.json` is named in no `OWNER-*` record at all, and its authority basis is stated in its own annotation. An earlier revision also annotated the eligibility certificate; those edits were **reverted** — see below. | R1 **CHANGES_REQUESTED** (3). R2 **CHANGES_REQUESTED** (1 blocking). Close-out review **CHANGES_REQUESTED** (1 blocking: the certificate edits were barred by the same clause used to decline item 4). All confirmed and remediated; final bytes self-verified. |
| — | this ledger | Created. | R1 **CHANGES_REQUESTED** (5). R2 **CHANGES_REQUESTED** (3: a stale item-2 account, a verification method that could not fail, and no hashes pinned). All three corrected in these bytes. |

A sixth change, outside §6, records in `knowledge/03-Modules/MOD-004/CAP-EVIDENCE.md` — final SHA-256
`d614083c96fb3e7a1f6067b8003cedca5c073750763d19afe2f84958b06b3926` — that
`OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §2 **condition 1 is unmet**. Its
independent review returned **CHANGES_REQUESTED** on one blocking finding — the LGPL-3.0 limb was
stated flatly as unassessed when the record scopes it to a distributing use and already positions the
loopback-only one — plus three advisories, all taken. The reviewer tested the central claim in both
directions, argued the narrower reading at length and rejected it. Remediated; final bytes
self-verified.

## Item 2 — the exact account, twice corrected

This row has been wrong in both directions, so it is stated plainly and pinned to a hash.

**First revision.** Described the change as "Edited additively" with the "STOPPED" section "kept
verbatim". That was false: two paragraphs inside the section had been rewritten and two sentences
deleted.

**Second revision.** Recorded those deletions — and by then they had been undone. A later edit
restored both sentences and the original heading and bounded them with in-place annotations instead,
so the ledger then certified deletions that no longer existed. That is the first error with its sign
reversed, and it is the reason this table now pins hashes.

**What is true of `308b285a…`, the bytes being published.** No original sentence is deleted from
`CAP-ENVELOPE.md`. Specifically:

- The heading "What a new envelope would buy, if the owner grants one" is present, as in the original.
- "A new envelope is the owner's own act under the authorizing record's Reserved list" is present.
- "and together they must fit inside what is left" is present.
- The replacement heading an earlier revision introduced, "What remained when the stoppage hit", is
  absent.
- Each of those restored statements carries an in-place annotation marking it superseded —
  prospectively, by §2.4 and §4 for the reservation and by the absence of any remaining balance for
  the fit-inside clause.

**How to re-verify, by a method that can fail.** A line-based `grep -c` is **not** valid here: the
first sentence is hard-wrapped across two lines, so `grep -c` returns 0 whether or not the sentence
is present, and an earlier revision of this ledger offered exactly that as proof. Use a
whitespace-normalized search over the whole file, for example
`python3 -I -c 'import re,sys; w=re.sub(r"\s+"," ",open(sys.argv[1]).read()); print(s in w)'` with
the sentence as `s`. Measured that way all three statements above are PRESENT and the replacement
heading is ABSENT.

**What survives untouched**, confirmed block by block against SHA-256 by the first independent review
of this file's then-current bytes, and re-checked by a sentence-level pass over all 70 of the
original's sentences on the final bytes: the ledger table and its three entries, "100 of 180 minutes,
427,621 of 400,000 tokens", the 27,621 overrun, the 297,621/130,000 breakdown with 118,208 and
179,413, the exhausted prior 45/50,000 envelope, the UNKNOWN earlier usage, the metering-limits
disclosure, the three unremediated ADR-0006 `CHANGES_REQUESTED` findings and the sequencing
deviation. The only line the diff removes is a reflow of a file path that survives word for word in
its replacement.

## Item 4 — why the scenario-qa packet is not edited, and why the certificate is not either

The decisive ground is not the hash pins. It is that **no authority of any kind exists for a manual
edit to either S0 document today**, and it applies to both by name.

**This ground was first stated asymmetrically, and that was wrong.** An earlier revision of this
ledger used it to decline the §6 item 4 packet reconciliation while the same change made four manual
edits to `contracts/engineering/mod004-s0-eligibility.json`, concluding "the packet cannot lawfully
be edited, these two can". The close-out review found that false, and it was. The bar is
file-agnostic, and `OWNER-2026-10-28-s0-deterministic-preflight-recovery.md` `Covers` names **both**
`mod004-s0-eligibility.json` and `mod004-s0-scenario-qa.md`. Worse, that record's item 4 enumerates
the permitted certificate change exactly — `scenario_qa_packet.sha256`,
`scenario_qa_packet.sha256_note` and top-level `runner_gate.sha256` — and ends "All other
certificate values, including historical successor-runner observations, stay unchanged." None of the
four edits was inside that enumeration, and
`OWNER-2026-11-05-delegation-activation-and-exception-closure.md` adds "Where two limits apply the
smallest governs." **The certificate edits are therefore reverted**; it is byte-identical to HEAD.
Publishing a reading that licensed two uninstructed edits while excusing one declined instruction
would have left a precedent with no distinguishing principle, which is exactly what the preserved-history
rule forbids.

`contracts/engineering/mod004-s0-capability.json` is in a different position and is still annotated:
it is named in **no** `OWNER-*` record at all, so no manual-edit bar reaches it. That is a weaker
basis than an instruction, not a stronger one, and its own annotation says so.

- `OWNER-2026-10-28-s0-deterministic-preflight-recovery.md` item 3 ends: "No manual document edit
  outside the runner-recorded task." Its item 6 permits "exactly one new runner-recorded Sonnet
  correction after successful preflight", with "No review shopping or extra correction cycle".
- `OWNER-2026-10-28-s0-rebind-hash-recovery.md` item 2 admits "exactly one separately identified
  owner-CLI, runner-recorded Sonnet correction of the two named documents", rejects "a second
  correction", records that "The original fixed-ID write remains spent", and adds that an
  interruption "cannot become a retry oracle".
- Both lanes are single-use and recorded consumed or blocked, and `CLAUDE.md` forbids restarting,
  repairing or rebuilding the retired runner, or replacing it with another scheduler or dispatcher.
- No accepted ADR `Covers` `contracts/engineering/`. Checked first-hand across all five headers:
  ADR-0001 covers `governance/`, `knowledge/00-Decisions/`, `tools/governance/`,
  `.github/workflows/` and three named `tools/mission_runner/` files; ADR-0002 covers
  `backend/app/tenancy/`, `backend/migrations/`, `backend/tests/integration/tenancy/` and
  `infra/db/`; ADR-0003 and ADR-0004 cover named `tools/mission_runner/` files; ADR-0005 covers
  `knowledge/03-Modules/MOD-004/MOD-004.md`.

So the route a correction would normally take is closed, and the route an ADR would normally take
does not exist.

**The hash pins are a second, independent obstacle.** The packet's SHA-256
`a146c060a175b62d80f6a2f830ca7d8f56a47a11ac7cbb9f9d5d93df3d527c6c` is pinned by two `OWNER-*`
records — `OWNER-2026-10-28-s0-rebind-hash-recovery.md` and
`OWNER-2026-10-28-s0-deterministic-preflight-recovery.md`. Both are frozen baseline:
`tools/governance/governance_check.py` unions every `knowledge/00-Decisions/OWNER-*` path into the
frozen set and excludes it from the controlled one, with the comment "never authorizable by an ADR",
then requires `--decision` to be an `OWNER-*` stem. Re-pointing those pins needs a further
owner-authenticated publication, and manufacturing one in order to tidy a sentence is the opposite
of what the owner's directive asks for. The packet's pin also currently **matches** live bytes, so an
edit would break a correspondence that is true today.

**A reason wrongly claimed, which has since become true.** An earlier revision argued that leaving
the packet alone keeps the pending two-document review's subject stable. That was false when
written, because the same change moved the certificate — the other half of that subject. With the
certificate reverted the subject is in fact stable again: both documents are byte-identical to HEAD,
the packet at `a146c060a175b62d80f6a2f830ca7d8f56a47a11ac7cbb9f9d5d93df3d527c6c` and the certificate
at `92aad9c46ba0dd8405ab49d43e4f27328c3285de745721a7ed8b7e0dc197deea`. It is recorded as a secondary
observation, not as the ground relied on; the ground is the absence of authority, above.

**The reconciliation is therefore by supersession rather than by edit**, which is how the owner record
itself operates: it "edits no file" and "supersedes clauses of other records prospectively by its own
authority; superseding is not editing". In that packet:

- The §6-named sentence at `mod004-s0-scenario-qa.md:9` is **not false**. The budget was exhausted, as
  history; the module is still blocked, on four OPEN blockers; and the sentence already says the work
  is CAP-independent.
- `mod004-s0-scenario-qa.md:62` is the sentence that needs naming: "The existing CAP pause,
  module-wide PROVISIONAL manifest and historical BLOCKED outcomes are unchanged." §2.5 supersedes
  that PAUSED-and-BLOCKED stoppage prospectively, so "the existing CAP pause … unchanged" no longer
  describes a live stoppage. The manifest is still PROVISIONAL and the historical BLOCKED outcomes
  are unchanged, so the rest stands. A similar clause appears at `:99`; `:5` already frames its
  reference as "CAP paused **history**".

**The residual risk, stated.** §6's rationale is that "an agent reads some of those before it reads
any owner record", and answering a read-first problem with a supersession recorded elsewhere is
weaker than editing would be. The mitigation is that `CLAUDE.md` — the file actually read first — now
carries the supersession and names what survives. If the owner ever authorizes another
runner-recorded or manual correction of that packet, `:62` and `:99` are the lines to reconcile.

## Item 5 — authority basis, which §6 does not supply for two of the three files

§6 names **two** files in `contracts/engineering/`: `module-capabilities.yaml` at item 5 and
`mod004-s0-scenario-qa.md` at item 4. For the manifest the instruction is direct — its two budget
fields "should be annotated as historical rather than deleted" — and an owner record outranks an ADR.

The change also touches one file **§6 never names**: `mod004-s0-capability.json`. Two distinct things
were done to it, with different bases:

1. **Re-pointing `module_manifest.sha256`** is necessary maintenance caused by the owner-directed
   manifest annotation. Leaving those pins stale would leave two artifacts declaring a dependency on
   bytes that no longer exist. In scope by necessity.
2. **Adding a `cap_budget_reconciliation` annotation** is covered by no instruction. Its substance is
   conservative and correct — §2.5 supersedes exactly the PAUSED-and-BLOCKED stoppage and the "no
   additional budget" bar that those sentences restate — but the authority is the orchestrating
   session's engineering judgment under §6's purpose. That is stated in each annotation, not left to
   be assumed.

**The remaining asymmetry, and why it is not the earlier one.** One document the owner did not list
is reconciled by edit, while one the owner did list is not. The distinction is now a stated
principle rather than a convenience: the two S0 documents named in the preflight-recovery record's
`Covers` are both left alone, and the only annotated S0 artifact is the one no `OWNER-*` record
names. An earlier revision claimed only one §6-named file sat in this directory, which was wrong —
§6 names two — and that error made the asymmetry harder to see. Both are corrected.

**The controlled-path tension, and the reading taken.** ADR-0002 calls the capability manifest "a
controlled contracts change" and places it "outside this ADR's authority", while the owner record's
own "Not claimed" list disclaims being "authorization for … any controlled-path change" — yet §6
items 4 and 5 direct the reconciliation of two `contracts/engineering/` files. The reading taken is
that the disclaimer refers to the validator's ten `CONTROLLED` entries, none of which matches
`contracts/engineering/`, and that §6's direct instruction governs the manifest. **That is recorded
as a reading, not a certainty**, and two independent reviewers flagged it as the one point worth the
owner's own eye. If the owner disagrees, the manifest annotation is the part to revisit.

**Two pins left stale in the unedited certificate, failing closed.** Because
`mod004-s0-eligibility.json` is reverted, it goes on naming `module_manifest.sha256`
`2958958c1212deafbb9bc3e34673bb4ee145913f655671ae709d4a552dde526a` (the pre-annotation manifest) and
`capability_declaration.sha256` `f1f1af309477c087c1bb9bfa7e8de04311a90a6bd404335b05b6f00d17e5a1a8`
(the pre-annotation declaration). Both are now stale, and a verifier rehashing either target against
them will mismatch.

That is the correct outcome and is deliberately not fixed. The certificate's permitted delta is
enumerated to three values, neither pin among them. And the second pin sits directly on an APPROVED
review record (`mod004-s0-capability-opus-review-20261023`) whose coverage must not be made to look
wider than the bytes it actually saw — so even inside a correction lane it should be left alone,
while `module_manifest.sha256` would be the change to make. **No verifier performs that rehash
today**: nothing in `tools/` or `.github/workflows/` reads either artifact, so the mismatch is a
property a human or future verifier can rely on rather than an enforced check.

`tools/mission_runner/blocker_dispositions.json` also records the manifest's pre-annotation hash,
inside `review_candidate.files[]` of `mod004-cap-provenance-final-opus-review-20261018`. That is
likewise a record of **which bytes a reviewer actually reviewed**, and it is left untouched:
re-pointing it would falsify a historical review record. It is not one of the six controlled exact
files under `tools/mission_runner/`, so editing it would have been permitted — the non-edit is a
judgment, not an oversight.

## Two statements that were simply false, corrected in items 1 and 3

Both `CLAUDE.md` and `REQUIREMENTS.md` stated that "PostgreSQL, `psycopg` and `psycopg_pool` are
neither pulled nor installed". Checked first-hand rather than assumed, that is false as to pulling,
and the element-by-element verification below was reproduced by independent reviewers (asserted on
the same terms as every post-runner review here — their performance leaves no `*.evidence.json`),
as well as first-hand by the orchestrating session:

- The pinned PostgreSQL 17 image **is** in the local Colima image store as
  `postgres@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`, CAP-001's
  pinned index digest, with `PG_VERSION=17.11-1.pgdg12+2`, held **untagged** and pulled by digest. A
  second, unrelated `postgres` digest tagged `16-alpine` is also present from well before this
  authorization and is not the assessed artifact.
- One of the four pinned distributions, `psycopg_binary-3.3.6-cp313-cp313-macosx_11_0_arm64.whl`, **is**
  on disk outside the repository at its pinned hash
  `373704aea331d3f3e3402c125a1543f5875e2986ebb54f97d1647942161f803f`, with its bundled
  `libpq.5.dylib` extracted beside it. The other three exist only as PyPI JSON metadata.
- **Nothing is installed.** The qualification virtual environment contains only `pip 26.1`, and
  `import psycopg` raises `ModuleNotFoundError` there and on every other interpreter checked. No
  third-party dependency is added to `backend/`.

`CAP-EVIDENCE.md` had the opposite imprecision — it said the wheel was "fetched into memory" — and now
carries a correction bounding that without editing it. Correcting a statement that is false in the
project's own favour is not optional, and it is recorded here because it falls outside §6's literal
list.

## Not claimed

- Not a capability activation, not a Ready judgment, not module acceptance, not a Scenario Review or
  product PASS, and not evidence for any CAP blocker.
- Not a reset. No counter, envelope, attempt budget or review outcome is reset, recalculated or
  re-characterised by this file or by any change it records.
- **Not a claim that any item's final bytes are independently approved.** The review-state column is
  exact; where it says self-verified, that is what happened and why.
- **Not a claim that nothing is widened.** Item 5 reaches one file §6 does not name, on the basis
  stated above. An earlier revision claimed to widen nothing while doing exactly that; the claim is
  withdrawn rather than the disclosure softened.
- Not a `check-change` result. No path in this change set matches a validator `CONTROLLED` or frozen
  entry, so the gate judged nothing: it returns PASS under a deliberately wrong `--decision` too.
  That PASS is never offered here as evidence of examination.
- Where this ledger and the owner record differ, the record governs.
