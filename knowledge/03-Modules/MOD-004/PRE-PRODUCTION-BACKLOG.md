# MOD-004 pre-production backlog

**Deferral is not closure.** Every item below is OPEN and stays OPEN. Nothing here is a finding
that an item is resolved, waived, reduced in scope or no longer required, and nothing here closes a
blocker, satisfies a condition, records an evidence ID or supports a PASS of any kind. The point of
this file is the opposite: to hold items that have been *set aside* so they are not lost, in one
place a reader can check, rather than left implicit in a long evidence file.

**Why it exists.** The owner's directive of 2026-11-07 (relayed to this session in the Claude Code
conversation; its date is as relayed and is not verifiable from the repository) instructs, item 7,
to "defer nonessential security documentation, repeated CVE inventory work, and optional tooling
enhancements to a clearly recorded pre-production backlog". The same directive, item 1, instructs
that open-ended security research not strictly necessary to safely develop or test product
functionality stop; item 3, that a production-readiness issue not be treated as an automatic
blocker for unrelated local coding, unit tests or static analysis; and item 5, that no effective
gate be bypassed and no outstanding security finding be claimed resolved. This file is item 7's
artifact and it obeys item 5: the gates below are left standing exactly as they are.

**What this file does not do.** It does not reclassify a gate as non-blocking. Where an item gates
something — manifest activation, the Ready-for-S1 judgment, S1 product code, a deployed use — that
gate still holds and the "Blocks" column says so. It makes no owner decision and takes no
owner-reserved action. The four DC-16 actions stay reserved.

**Source of each state.** Every row's state is copied from the artifact named in its last column,
which is where the evidence and its limits live. Where a row says VERIFIED or CLOSED that is the
state recorded there, with the caveats recorded there, not a fresh claim by this file.

---

## 1. Deferred to pre-production: image and wheel supply-chain evidence

These are the `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §2 condition 1
limbs that remain open. Condition 1 is assessed **NOT MET on four limbs**, and that assessment is
unchanged by this file. The qualification scope the authorization covers is a local, loopback-only
container with synthetic fixtures; a deployed or production use of these artifacts is DC-16
`production-promotion` and reserved to the owner regardless of anything below.

| Item | State | What closing it needs | Blocks | Recorded in |
|---|---|---|---|---|
| B3 publisher signature for the pinned digests | OPEN. Searched across four mechanisms, none yielding one. **Not established that none could ever be obtained** | Either a found signature, or an exhaustive search of the Docker Content Trust version history rather than the sampled one, or an owner disposition on the limb | §2 condition 1, therefore §3 activation, the §4 Ready-for-S1 judgment and all S1 product code | `CAP-EVIDENCE.md`, "Condition 1 assessed limb by limb" |
| B3 exact package licence closure | OPEN, bounded. 126 of 141 CLOSED on formal self-consistency, 3 NOT CLOSED, 12 NEEDS-READING, 57 of 198 SBOM names undetermined | Resolve the 3 undefined declarations (`base-passwd`, `libldap-2.5-0`, `libllvm19`), read the 12 aggregate notice files, determine the 57 names | As above | `CAP-EVIDENCE.md`, "The per-package pass" |
| B3 CVE applicability | OPEN, measured not closed. 154 open bookworm CVEs on the image's own SBOM; a lower bound, since the SBOM carries only `dpkg` metadata | Per-CVE applicability for the measured set; a non-`dpkg` inventory for the remainder | As above | `CAP-EVIDENCE.md`, "B3 continued" |
| B3 Go stdlib reachability | OPEN. 59 advisories apply to Go 1.24.6; reachability **NOT ASSESSED**. `moby/sys/user` 0.1.0 is AFFECTED by `CVE-2026-61801` in a function gosu calls | `govulncheck`, which cannot be installed under the no-new-dependency rule, or a manual call-graph reading | As above | `CAP-EVIDENCE.md`, "B3 continued (2)" |
| B6 two REACHABLE bundled-OpenSSL CVEs | OPEN. `CVE-2026-35189` reachable in a default TLS handshake; `CVE-2026-54872` conditionally. Held **only by a scope argument**, which fails if the scope changes | A bundled OpenSSL ≥ 3.5.9, or a scope that keeps them unreachable, stated and held | As above, and any change of use | `CAP-EVIDENCE.md`, "B6 continued" |
| B6 OpenLDAP version and six sibling libraries | OPEN. OpenLDAP 2.6.14 is an **inference** from a disassembly reading — `libldap` carries no banner — and six siblings have no version of their own | A version determination that does not rest on inference, then their CVE status | As above | `CAP-EVIDENCE.md`, B6 rows |
| B6 LGPL-3.0 obligations for a distributing use | OPEN. Not triggered by the loopback-only scope; not assessed for any other | An obligations assessment for the intended distributing use | Any distributing use. Reserved under DC-16 `production-promotion` | `CAP-EVIDENCE.md`, B6 rows |
| B2 residual: terms of the VM images Colima fetches | OPEN, narrow. Colima 0.10.3 MIT, Lima 2.2.0 Apache-2.0 and docker CLI 29.6.0 Apache-2.0 are verified; **not claimed** that the VM images carry the same terms | Read the terms of the images actually fetched at runtime | Nothing today; relevant if the runtime is relied on beyond qualification | `CAP-EVIDENCE.md`, B2 section |

**Historical counters, recorded and not reset.** The exhausted 45-minute / 50,000-token envelope,
the recorded **427,621 of 400,000 tokens** against the later envelope — a **27,621** overrun, on a
count whose own basis `CAP-ENVELOPE.md` sets out for the owner to judge rather than take — and the
UNKNOWN earlier usage all stand as history there. `OWNER-2026-11-06-internal-cap-unmetered.md` removed exhaustion as a *stop
condition* prospectively; it reset nothing, and deferring the work above does not either.

## 2. Deferred: blocked on the PostgreSQL capability, not on research

These need a running database. They are not security documentation and are not deferrable by
choice — they are unreachable until `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` closes, which needs
§2 condition 1. Listed here so the reason is on the record.

| Item | State | Blocks | Recorded in |
|---|---|---|---|
| ADR-0002 D5 live catalog assertions | OPEN. The static SQL half is built (`tools/migration_lint/`, 25 rules); the catalog half asserts `pg_roles`, `relforcerowsecurity`, ownership, `prosecdef`, `pg_auth_members`, `pg_db_role_setting`, `pg_default_acl` and `datacl` against a real cluster | `BLK-SKL-MIGRATION-LINT`, therefore §3.2 | `tools/migration_lint/migration_lint.py` docstring; ADR-0007 D4 |
| RULE-001 / RULE-002 runtime-negative qualification | OPEN. The role-privilege test (runtime role is not a table owner, no BYPASSRLS or membership escape) and the transaction-pool-reuse test (`app.*` does not leak across transactions on a reused connection). The path-scope half is built (`tools/rule_scope/`) | `BLK-RULE-QUALIFICATION`, therefore §3.3 | `RULE-001-mod004-rls.md` "Outstanding qualification"; `tools/rule_scope/rule_scope.py` docstring |
| ADR-0002 D6.6 failure tests (21) and D9 cross-tenant fuzz | OPEN. Obligations, no evidence | S1 evidence; not reducible under §6's testing-approach delegation | ADR-0002 D6.6, D9 |
| EIP §9.1 scenario and QA set; `SCN-MOD-004-101..104` | OPEN. 101-103 need a real migration to lint; 104's execution needs the lint **and** a database | Implementation Complete | `SCENARIOS.md` |

## 3. Deferred: optional tooling enhancements

Item 7's third category. None of these blocks anything today.

| Item | State | Note |
|---|---|---|
| CI coverage for `tools/migration_lint/` and `tools/rule_scope/` | OPEN. Both suites are **local-only**; CI runs neither, so their 165 and 41 tests must not be read as CI coverage | `.github/workflows/` is CONTROLLED. ADR-0007 is PROPOSED and its `Covers` reaches only the workflow file while its D3 names only the migration-lint step, so wiring both needs ADR-0007 amended or its own ADR, each with a review |
| The migration lint's round-two remediation is unreviewed | OPEN. Two independent reviews of the lint both returned **CHANGES_REQUESTED**; 29 demonstrated false negatives between them are remediated, and the second remediation no reviewer has seen | The owner's circuit breaker stops a review loop after two unsuccessful iterations, so no third review was dispatched. §3.2's independent-review limb is therefore **also** unsatisfied, independently of the missing catalog half |
| `tools/rule_scope/` does not exercise Claude Code's rule matcher | OPEN, structural. It qualifies the **declared** globs under stated semantics; the harness that applies `.claude/rules/*` is not observed and its semantics are undocumented here | Needs documented harness semantics or an observation of it. Five divergences from gitignore convention are documented and pinned by tests |
| D6.2 privilege matrix beyond the named privileges | OPEN. The lint refuses TRUNCATE and REFERENCES to either runtime role and DELETE and TRIGGER to `veyro_cp_app`; the rest of the matrix is not implemented | Disclosed in the lint's limits list |
| Rule-file hashes in the RULE records | OPEN. Both records say `NOT_COMPUTED ... runner must verify externally`, and the runner is retired. Both hashes are **computed and verified correct** against `mod004-s0-capability.json`'s pinned values by `tools/rule_scope/` | Recording them in the records themselves needs a change whose own subject is that; `contracts/engineering/capability-records/` sits inside ADR-0006's `Covers`, but ADR-0006's subject is the D4.3 driver selection and citing it here would use path coverage as a loophole |

## 4. Not deferrable here: owner-reserved

Listed so this file is not read as having swept them up. None of these is an agent's to take,
defer or close.

- The four DC-16 actions: `spend-paid-activation`, `production-promotion`,
  `material-product-business-change`, `real-member-data`.
- Module acceptance for MOD-004 and every module, and the MOD-005 unlock.
- All UI-bearing MOD-004 work: CON-04, ADM-SET-01, ADM-SET-02, ADM-SET-06, the D14
  screen-ownership mapping review, finding **F3**, and the ADM-SET-06 domain-authority conflict.
  `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW` stays OPEN and is not closed by §3.
- Whether the two D16 correction cycles survive the 2026-10-30 infrastructure failure. Not
  resolved, not re-counted.
- OWNER-Q1 (interim access log; default remains none in S1) and OWNER-Q2 (Appendix F ¶8741 lint
  timing). Scenario Review stays **BLOCKED**.
- Regions, data-residency policy and KMS keys; retention durations, deletion approvers and quorum;
  hierarchy cardinalities, brand separation extent and template contents where the Blueprint is
  silent.
- Any second S0-style product-code slice. The published S0 slice rests on its own owner record and
  two reviewed certificates, and its one-write and one-review limits are consumed. A further
  pure-domain slice outside the §5 paths would need the same authority, which is the owner's to
  publish and not an agent's to infer.

## Not claimed

- Not module acceptance, not Ready, not an activation, not a Scenario Review PASS, not a security
  PASS, not a product PASS, not a Gatekeeper verdict.
- Not closure, waiver, narrowing or reduction of any item above, and no CAP, SKL or RULE evidence
  ID.
- Not a finding that any deferred item is low-risk, acceptable or safe. Deferral here records only
  that the work is not being done now and why.
- Not legal advice, and not a supply-chain or security certification.
