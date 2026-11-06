# ADR-0006 — MOD-004 D4.3 driver and database selection, and digest pinning

- ID: ADR-0006
- Status: ACCEPTED
- Review: VR-ADR0006-20261106-003 APPROVED
- Decision-Key: mod004-d43-selection
- Covers: contracts/engineering/module-capabilities.yaml, contracts/engineering/capability-records/

**Scope and limits.** This ADR closes CAP-001 blocker **B7** by selecting the D4.3 driver and database and by fixing how those artifacts must be referenced. It is authorized by `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §2.4, which delegates B7 as an engineering decision while requiring that recording it be an accepted ADR. It authorizes **no code and no capability activation**: it does not make the MOD-004 capability manifest ACTIVE, does not judge Ready, does not pass Scenario Review, claims no product PASS, and satisfies no part of PLT-01-R01..R07. It approves no DC-16 reserved action and reaches no frozen path. **It does not satisfy §2's condition 1, and it does not authorize the CI workflow change S1 will need** — see D4 and D5, which are where this revision differs most from its predecessor drafts.

**Review header: what it refers to.** **`VR-ADR0006-20261106-003` is a document-assigned label**, not an identifier carried by the review's own artifacts. It labels the independent Opus review of the exact bytes of this file performed before its publication. The label `VR-ADR0006-20261106-001` belongs to the review that returned **CHANGES_REQUESTED** on three blocking findings against the first draft; that outcome stands, is not rewritten, and is the reason this file exists. No review was performed on the intermediate `-002` draft, which was superseded before dispatch by the B3 evidence recorded at commit `2cfdba7`; that label is recorded as unused rather than quietly reassigned. The present review ran in the Claude Code session that commissioned it, so it has **no runner run-evidence artifact, no run identifier and no `review_bound_verified` field**: reviews after the runner's retirement leave no `*.evidence.json`, and this paragraph is the only account of it. Its performance, its performer and the reviewer's lack of write tools are asserted here and are not independently verifiable. The validator checks only the format of the id (`^[A-Za-z0-9._-]{3,64} APPROVED$`) and never confirms that a review exists. Any edit to this file after publication is new bytes needing its own review and CI, and none is claimed in advance.

**Authority path, and what `Covers` does not buy.** The standing authority for this file is ADR-0001 (key `governance-foundation-change-control`), which covers `knowledge/00-Decisions/` and is not part of this change; this ADR cannot authorize its own file. `Covers` names `contracts/engineering/module-capabilities.yaml` and `contracts/engineering/capability-records/` only. **Neither is in `tools/governance/governance_check.py`'s `CONTROLLED` tuple**, so a `check-change` PASS on either path judges nothing and must never be cited as evidence that such a change was examined; a well-formed but meaningless `--decision` returns the same PASS. ADR-0002 calls `contracts/engineering/**` a controlled contracts change, which is accurate as discipline and unenforced by the validator. The real constraint on those paths is review, not the gate. The first draft covered the whole `contracts/engineering/` prefix, which also reached `mod004-s0-capability.json` and `mod004-s0-eligibility.json` — the S0 forbidden-import closure and the S0 eligibility certificate, the latter being a document whose permitted delta is enumerated by a published owner record. That prefix is withdrawn here and both S0 artifacts are outside this ADR.

## Context

ADR-0002 D4.3 proposed PostgreSQL, `psycopg` and `psycopg_pool` but excluded the selection from its accepted scope, leaving it a PROPOSAL. CAP-001 records B7 as "D4.3 selection … not decided by this record".

**The evidence state, as `knowledge/03-Modules/MOD-004/CAP-EVIDENCE.md` records it at commit `2cfdba7`** — stated precisely, because the first draft summarised it as "B2, B3, B4 and B6 closed" and an independent review found that stronger than the record supports:

| Blocker | Recorded state |
|---|---|
| B2 free runtime and terms | VERIFIED, closed |
| B4 wheel and transitive hashes | VERIFIED, closed |
| B3 image provenance and digest binding | **VERIFIED in part. CVE applicability OPEN and now measured: 154 distinct open Debian bookworm CVEs against the image's own SPDX SBOM, versus CAP-001's 140 on the same OSV basis. A lower bound: the SBOM carries only `dpkg` metadata, and the six PGDG packages — `postgresql-17`, `postgresql-18`, `postgresql-client-17`, `postgresql-client-common`, `postgresql-common`, `libpq5` — were never queried, so the database's own packages are UNKNOWN. Package licence closure OPEN: `licenseConcluded` is `NOASSERTION` on all 204 SPDX packages. Publisher signature OPEN.** |
| B6 native-library inventory | Inventory, embedded OpenSSL version, CVE count and severities **CLOSED**. Remaining and **OPEN**: four of the twelve Low CVEs individually; bundled libpq, Kerberos and OpenLDAP versions. The LGPL-3.0 limb is open **for a distributing use** only and is positioned, not triggered, for this scope. |
| B5 independent fetch verification | SATISFIED for B3 and B4 |
| B1 CAP owner | recorded |
| B7 D4.3 selection | OPEN — closed by this ADR |

## Decision

### D1. Selected driver and database

For the MOD-004 S1 control-plane slice, in a **local** container on **macOS arm64** only:

| Artifact | Selected version | Reference that must be used |
|---|---|---|
| Database | PostgreSQL 17.11 (`PG_VERSION 17.11-1.pgdg12+2`), Debian bookworm build | OCI index digest `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`, resolved to the **linux/arm64** manifest `sha256:a85953d6f830fd55a12929df3b7a4fa94dc96d652de62d2d714e0867ccb3670d` |
| Driver | `psycopg` 3.3.6 | sha256 `a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631` |
| Driver binary | `psycopg-binary` 3.3.6, wheel `psycopg_binary-3.3.6-cp313-cp313-macosx_11_0_arm64.whl` | sha256 `373704aea331d3f3e3402c125a1543f5875e2986ebb54f97d1647942161f803f` |
| Pool | `psycopg-pool` 3.3.3 | sha256 `9b9cd6a4fcec47a410f7e82d408540e7f77b478509e91b44c1a5457a13e5ff37` |
| Transitive | `typing-extensions` 4.16.0 | sha256 `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` |

The set is closed. Adding a package, an extra or a version needs a change to this ADR with its own review. `typing-extensions` is in the set because `psycopg-pool` requires it unconditionally; `psycopg` itself requires it only on Python below 3.13 and so pulls nothing on the selected 3.13.13 interpreter.

**The selection is platform-specific, and that is stated in the table rather than left implicit.** The assessed artifacts are a linux/arm64 image manifest and a macOS arm64 wheel. No linux/amd64 artifact is selected, assessed or authorized by this ADR. See D4.

**`psycopg-binary` rather than a system `libpq` is selected deliberately**, and the trade-off is recorded rather than hidden. It installs under `--only-binary=:all:` with a hash lock and needs no compiler or host `libpq`, so the environment is reproducible and pinned. The cost is that it bundles its own native libraries, including **OpenSSL 3.5.8**, the branch affected by the thirteen CVEs fixed in 3.5.9. The alternative, pure-Python `psycopg` against a host `libpq`, would depend on host state outside the hash lock. Reproducibility is preferred because the qualification and S1 test environment must be identical across runs; the exposure is bounded in D3.

### D2. Execution pins digests, never tags, and the platform manifest rather than the index

**No tag may be used to obtain any of these artifacts for execution.** This is not a style preference. The B5 verification established that the mutable tag `postgres:17` now resolves to a `debian:trixie-slim` build, and that **the narrower `17.11-bookworm` tag has also moved off the pinned digest** to a rebuilt bookworm image. So no tag resolves to the assessed artifact, and CAP-001's Debian CVE assessment describes the pinned digest alone. Any reference by tag would run an unassessed image while appearing to comply.

**Pinning the index digest is not sufficient on its own either.** An OCI index resolves per platform, so the same index digest yields a *different* manifest on a different architecture. Execution must therefore pin the **platform manifest** digest named in D1, or pull the index digest only on macOS arm64 where it resolves to that manifest. Pinning the index digest on an amd64 host would resolve to the amd64 member, which this project has never assessed — reproducing across architecture exactly the hazard D2 exists to prevent across tags.

**The cost of the pin, now quantified rather than described.** The pinned digest is an **older** bookworm build, so it carries no package update published since the pin. Concretely, from the B3 evidence: of the 154 open entries, **eight have a bookworm fix available that this digest predates** — six in the image's system `openssl` (`CVE-2026-84782`, `-35189`, `-54872`, `-75805`, `-75806`, `-77696`, all fixed in `3.0.22-1~deb12u2`), plus `apt` `CVE-2026-109518` (fixed in `2.6.2`) and `cyrus-sasl2` `CVE-2026-107161` (fixed in `2.1.28+dfsg-10+deb12u1`). **One of those, `CVE-2026-84782`, is the single High.** Moving to a newer digest is permitted only by a change to this ADR carrying a fresh CVE assessment of that digest; it is not an operational convenience. See Alternatives.

### D3. Exposure boundary, and what it does not cover

The bundled OpenSSL 3.5.8, MIT Kerberos and OpenLDAP copies, and the image's own system libraries, are confined to the local qualification and S1 test environment. Within it:

1. Connections are loopback only, to a container published on localhost, with synthetic fixtures and no real member data.
2. GSSAPI and LDAP authentication are not configured and not used, so those bundled libraries are not exercised by the harness.
3. **Wheel side.** The one High CVE is unreachable *through the bundled driver*: `nm -u` on the bundled `libpq.5.dylib` shows no DTLS and no QUIC symbol, and OpenSSL's DTLS retransmission path is reachable only through a DTLS method object libpq never constructs.
4. Four of the twelve Low CVEs on the bundled OpenSSL — `CVE-2026-35189`, `-54872`, `-54875`, `-77696` — are **not** argued unreachable, and no such claim is made for them.
5. The bundled libpq, Kerberos and OpenLDAP **versions** are not established; CAP-001's libpq 18.6 remains a supplied assertion, and their CVE status is OPEN, not clear.

**What point 3 does not cover, stated because the distinction is easy to lose.** That symbol argument is about the **wheel's** bundled libpq. The **image** independently carries the same High in its own system `openssl` at `3.0.22-1~deb12u1`, and **no reachability argument is made for the image side here.** It is a different artifact at a different version, and the fact that a fix exists for one says nothing about the other. The reason that is tolerable for this scope is the boundary itself and nothing cleverer: a loopback-only container, published on localhost, with no listener reachable off the host, synthetic fixtures, no real member data, no TLS termination configured for the qualification harness, and no production, staging or deployed use. **Image-side reachability is recorded as OPEN, not as argued.** If any of those scope facts stops being true, this disposition no longer covers the use.

**Any use outside that boundary is outside this ADR.** Deployed, staging or production use of these artifacts is a DC-16 `production-promotion` matter reserved to the owner, and distributing any Veyro artifact that embeds these LGPL-3.0-only packages needs its own licence assessment, which this ADR does not perform and which B6 records as open for a distributing use.

### D4. No CI platform artifact is selected, and the workflow change is not authorized here

The first draft covered `.github/workflows/veyro-foundation-ci.yml` so that a PostgreSQL service could be added for S1 integration tests. **That grant is withdrawn**, because it was incoherent with D1 and would have caused the very substitution D2 forbids:

- Foundation CI runs on `ubuntu-24.04` (`.github/workflows/veyro-foundation-ci.yml:14`), which is x86_64.
- D1's assessed artifacts are a **linux/arm64** manifest and a **macOS arm64** wheel. On an amd64 runner the index digest resolves to the unassessed amd64 member, and the pinned wheel cannot install at all.
- So literal compliance with D2 in CI would have run an image carrying none of the attestation, SBOM or CVE assessment behind the recorded bookworm position.

Adding a PostgreSQL service to Foundation CI therefore requires a **further ADR** that first selects and assesses, on their own terms: a **linux/amd64** manifest digest for the chosen image, with its own CVE assessment and its own attestation-subject binding; and a **manylinux** `psycopg-binary` wheel, with its own hash, its own bundled-library inventory and its own CVE status. None of that evidence exists. An amd64 assessment is a fresh B3/B4/B6-equivalent exercise with its own independent fetch verification; it is not an extension of the arm64 one.

**Until that ADR exists and is accepted, S1 integration tests are local-only and Foundation CI does not cover them.** Owner-record §5 requires this to be "stated plainly wherever S1 evidence is reported rather than left to look like coverage", and that obligation is inherited here: any S1 test evidence must say on its face that CI runs none of it.

### D5. What this ADR does not satisfy, stated because the first draft implied otherwise

**§2 condition 1 is not satisfied, and this ADR does not satisfy it.** That condition requires B2, B3, B4 and B6 "closed by evidence actually produced and recorded", and names what closure must cover: for B3, "image provenance, licence closure and CVE applicability"; for B6, "the `psycopg-binary` bundled-library inventory with its CVE status and LGPL-3.0 obligations". The Context table records B3's CVE applicability and licence closure as OPEN, and B6's four Low CVEs and bundled-library versions as OPEN. Condition 1 is therefore **unmet on its face**, and `CAP-EVIDENCE.md` records that finding with its consequences and the reading it rests on.

Three consequences follow, and none is softened:

1. **The pull was not authorized.** §2's pull authority is conditioned on "conditions 1-6 and the remaining CAP-001 §6 execution controls" holding. The image and one wheel were nevertheless fetched on 2026-11-06. `CAP-EVIDENCE.md` records that deviation against conditions 1, 2 and 4. A breach is not made lawful by being disclosed.
2. **`BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` is not closed**, because owner-record §3.1 requires it closed "by the §2 evidence" before activation. The capability manifest therefore stays PROVISIONAL with `gate_eligible: false`.
3. **No install, no container run, and no S1 product code is authorized.** Owner-record §5 takes effect only once §3 activation and the §4 Ready-for-S1 judgment are reached. Neither is reachable while condition 1 is unmet. ADR-0002 D12 stands and is not relaxed.

What remains is evidence work, not an authorization, and under `INTERNAL_CAP_MODE = UNMETERED` it has no budget ceiling — only a standard of proof.

### D6. Production dependency sequencing

The selected packages are **not** added to `backend/requirements.txt` or `backend/requirements*.lock` by this ADR. That change is permitted only after qualification completes and the manifest is ACTIVE under owner-record §3; it is itself a change needing an accepted ADR citing ADR-0001 with its own independent review per §5; and ADR-0002 D12.3a control 5 bars it during qualification. It is **not** owner-reserved — no record reserves it — and recording it as such would invent an approval the records delegate. Until then the qualification environment is an isolated virtual environment outside the repository and `backend/` keeps its existing approved dependency set.

The stdlib-only rules are unchanged: `tools/`, `backend/app/l10n/` and the published S0 slice stay stdlib-only, and the S0 forbidden-import closure in `contracts/engineering/mod004-s0-capability.json` is untouched and outside `Covers`.

## Consequences

**B7 is closed.** The qualification artifacts have a named, pinned, platform-explicit, reviewed selection, and the way they must be referenced is fixed. That is all that is closed. B3's CVE applicability and licence closure, B6's four Low CVEs and bundled-library versions, the publisher signature question and image-side reachability for the High all remain OPEN; condition 1 remains unmet; the manifest stays PROVISIONAL; no code, install or container run is authorized; and every gate in owner-record §3, §4 and §5 applies in full.

The risk accepted and recorded: an older bookworm image build carrying 154 open Debian CVEs of which eight have a fix this digest predates, one of them the single High with **no image-side reachability argument**; a bundled OpenSSL on the affected 3.5.8 branch with four Low CVEs whose reachability is unargued; three bundled libraries whose versions are unestablished; and a package set in which nothing has a concluded licence. All confined to a loopback-only local environment with synthetic data, and none of it accepted for any deployed use.

## Alternatives considered

**A newer `postgres:17` digest.** This is now the strongest alternative, and it is recorded as a live option rather than dismissed. A newer bookworm build would retire the eight fixable entries including the High. It is not selected here for two reasons: the current `postgres:17` tag resolves to `debian:trixie-slim`, a different distribution with no assessment in this project, and selecting any newer digest discards the only CVE assessment that exists while requiring a full fresh one. D2 states the route — a change to this ADR carrying that assessment. **If the image-side High matters more than the cost of re-assessment, this is the decision to revisit first**, and the scope boundary in D3 is what makes deferring it tolerable rather than any claim about the flaw.

**System `libpq` with pure-Python `psycopg`.** Rejected for S1: it depends on unpinned host state, so the test environment would not be reproducible and the hash lock would not describe what runs. It remains the better option if the bundled-library exposure is later judged unacceptable, and choosing it would be a change to this ADR, not a silent substitution. It would also sidestep the amd64 wheel problem in D4, at the cost of reintroducing host dependence in CI.

**Selecting amd64 artifacts now, so that CI could run the tests.** Rejected: there is no amd64 evidence, and selecting an unassessed artifact in order to obtain CI coverage would buy the appearance of verification at the cost of the thing being verified. D4 states the route instead.

**Waiting for an OpenSSL 3.5.9-based wheel.** Not available in the pinned candidate set, and introducing a different wheel would reopen B3, B4 and B6 in full. Recorded as the natural upgrade path once such a wheel exists.

## Not claimed

- Not a capability activation; `contracts/engineering/module-capabilities.yaml` stays PROVISIONAL until owner-record §3 is satisfied on evidence.
- Not satisfaction of owner-record §2 condition 1, and not a retrospective authorization of the fetch that condition should have gated.
- Not a Ready judgment, not module acceptance, not a Scenario Review PASS, not a product or security PASS.
- Not a safety pass or security certification for any selected artifact, and not a claim that any CVE is absent, unreachable on the image side, or harmless.
- Not authorization for code, migration, install, container run, CI workflow change, lockfile change or any UI-bearing work.
- Not an answer to OWNER-Q1, OWNER-Q2 or ADR-0002 D15.10 Q1-Q8.
- Approves no DC-16 reserved action and grants no authority over any frozen path or `OWNER-*` record.
- Supersedes no review outcome. The first draft's `CHANGES_REQUESTED` stands.
