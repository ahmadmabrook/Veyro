# CAP-001 — MOD-004 D12.3a qualification stack, pre-pull evidence dossier

**PROVISIONAL. PRE-PULL REVIEW PENDING. NOT GATE-ELIGIBLE.** Documentation/lock preparation only for ADR-0002 D12.3a. One bounded qualification-stack CAP draft, not separate ACTIVE registrations. Claims no ACTIVE lifecycle, Ready, Scenario PASS, security PASS or S1 authorization. Nothing was pulled, fetched, installed or run to write this record. This write does not approve the pre-pull gate and is not D4.3 selection of PostgreSQL, psycopg or psycopg_pool.

**Evidence classification (applies to the whole record).** Every fact below is a SUPPLIED METADATA ASSERTION: it was supplied by the requester from prior read-only observation and was NOT independently verified or re-fetched in the authoring session or by any reviewer. No fact in this record is INDEPENDENTLY VERIFIED EVIDENCE. Where a statement cites a source, time or tool, that attribution is as supplied and is unconfirmed. The EIP capability supplement is not accessible to the worker, so the field list follows the requester's CAP field list, not the EIP schema. Anything not stated is UNKNOWN or OPEN.

## 0. Explicit OPEN blockers (evidence absent; none closed by this record)

| ID | Blocker | Status |
|---|---|---|
| B1 | CAP owner | OPEN: UNKNOWN, not stated |
| B2 | Free Colima runtime and terms (no-spend, license/terms applicability of Colima and its VM/Docker components) | OPEN: not verified |
| B3 | Image provenance, license closure and CVE applicability | OPEN: no verified evidence |
| B4 | Wheel hashes and transitive hashes | OPEN: hashes are supplied assertions, not verified against PyPI by a reviewer |
| B5 | Reviewer fetch verification (an independent reviewer fetching and checking registry/PyPI/upstream sources) | OPEN: not performed |
| B6 | psycopg-binary native-library inventory, native-library CVE status and LGPL obligations | OPEN: not verified (see §3, §4) |
| B7 | D4.3 selection of PostgreSQL / psycopg / psycopg_pool | OPEN: not decided by this record |
| BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME | Runtime/attempt-budget blocker for this candidate. Prior attempt use: UNKNOWN. Remaining budget: NOT ESTABLISHED. No pull (and no fetch or install) is allowed until this blocker is reconciled. | OPEN |

## 1. CAP fields

| Field | Value |
|---|---|
| type | Third-party capability stack: one OCI image + three Python wheels (+ one transitive wheel) |
| source | Docker Hub official image `postgres`; PyPI wheels (see §2, §3) |
| version/ref/hash | See §2, §3; wheel lock `mod004-d123a-wheel-lock.txt` |
| profile/module | Backend/data profile; MOD-004 S1 qualification (ADR-0002 D11, D12.3a) |
| permissions | Local no-spend container and isolated Python environment; no repo production-path writes |
| data/network access | Synthetic data only; container bound to loopback only; no non-loopback published port. Wheel/image download at execution time is the only external network use, after approval |
| risk | See §4. Unresolved CVE, license and provenance items are OPEN |
| owner / reviewer | Owner: UNKNOWN (OPEN blocker B1). Independent pre-pull reviewer: Opus; reviews so far returned CHANGES_REQUESTED (see reviewer history below §1); no APPROVED review exists |
| operational status | null (not operational) |
| lifecycle status | null (no ACTIVE/DEPRECATED/REVOKED claim) |
| last reviewed at / next review due | null / null (independent reviewer dates unset) |
| rollback target/procedure | PROVISIONAL: remove these two files; no runtime effect. Execution rollback is the D12.3a teardown (§6) |
| attempt/budget evidence | Blocker BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME: prior attempt use UNKNOWN (not zero); remaining budget NOT ESTABLISHED; no pull allowed until reconciled. Manifest budgets are not reset by this record. One fixed candidate set below; no second candidate is chosen |

Authority (runner-supplied, UNVERIFIED from this sandbox): the runner supplied that the D12.3a amendment had an independent bound Opus APPROVED review, identifier `mod004-adr-qualification-remediation-opus-review-20261018`, published at 807f2dd with exact-head CI run 39160223908 reported as success. This sandbox cannot check the review record or the CI run; both identifiers are attributions as supplied and are not evidence here. Even if accurate, they would permit only a later qualification after every conditional ADR D12.3a requirement and every pre-pull control in §6 is met; they do not waive any of them.

**Reviewer history for this CAP (as supplied by the runner; not verifiable here).**
- The bound Opus pre-pull review `mod004-d123a-prepull-bound-opus-review-20261018` ran and returned CHANGES_REQUESTED.
- The first remediation of the original write `mod004-d123a-prepull-evidence-sonnet-20261018` was then reviewed in `mod004-d123a-prepull-remed-opus-review-20261018`, which also requested changes.
- This edit is the second and final bounded remediation of that original write. No APPROVED pre-pull review exists for this CAP.

## 2. Image candidate (metadata only; preserved exactly)

Observed from existing runner metadata snapshot at 2026-10-18T07:50:31Z.

- Tag (mutable, never used alone for execution): `docker.io/library/postgres:17.11-bookworm` (PostgreSQL 17.11, Debian bookworm).
- OCI index: `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`
- linux/arm64 manifest: `sha256:a85953d6f830fd55a12929df3b7a4fa94dc96d652de62d2d714e0867ccb3670d`
- Supplied assertion: the requester stated both digests match Registry/Docker Hub metadata. The actual source, time and tool of any match are not recorded and no independent match is claimed; reviewer fetch verification is OPEN (B5).
- Source: official-images catalog https://raw.githubusercontent.com/docker-library/official-images/master/library/postgres maps the tag to docker-library/postgres commit `2603e26e245e558218728ee14e0a42dcb020dc7f`. Dockerfile https://raw.githubusercontent.com/docker-library/postgres/2603e26e245e558218728ee14e0a42dcb020dc7f/17/bookworm/Dockerfile pins PG_VERSION `17.11-1.pgdg12+2`.
- Base: `debian:bookworm-slim@sha256:a1b86db52ce3daef089e45aabe36dfec4091f82464c25c1fdcf03de197cbe82a`.
- License: core https://www.postgresql.org/about/licence/. Base and image packages carry varied licenses; this is not a blanket PostgreSQL License.
- Attestations: arm64 OCI attestation manifest `sha256:865d14b614365066d4523d6f144602ef0ac2e6c3d3b6d1c382e2cceb60d2e56c` holds
  - SPDX 2.3 in-toto blob `sha256:1166fb99b1c4ecbe844f5597939f1d0d74a3332fe804938e23b9bae220ba7cea` (5,933,891 bytes);
  - SLSA provenance v0.2 blob `sha256:956ac4074202920eff9e4440acf66a32ca81cdcd78b23c937203d9104c65cabe` (53,546 bytes).
  Supplied assertion only: the requester stated that a prior read-only retrieval rehashed both blobs and found each subject bound to the arm64 image manifest. The tool, time and operator of that rehash are not recorded, no evidence of it exists in this record, and it is not claimed as verified. Even if true it would be digest integrity and subject binding, NOT a verified cryptographic signature. Attestation verification is OPEN (B3, B5).
- SPDX content: 204 packages, 7,603 files; includes postgresql-17 17.11-1.pgdg12+2, libpq5 18.6-1.pgdg12+2, OpenSSL 3.0.22-1~deb12u1. 17 package `licenseDeclared` fields are NOASSERTION.

## 3. Python wheel candidate (Python 3.13.13, macOS arm64, wheel-only)

Source: PyPI version-specific JSON `https://pypi.org/pypi/NAME/VERSION/json` and Simple API (filenames, hashes, Requires-Dist, license).

| Package | Wheel | SHA-256 | License |
|---|---|---|---|
| psycopg==3.3.6 | psycopg-3.3.6-py3-none-any.whl | a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631 | LGPL-3.0-only |
| psycopg-binary==3.3.6 | psycopg_binary-3.3.6-cp313-cp313-macosx_11_0_arm64.whl | 373704aea331d3f3e3402c125a1543f5875e2986ebb54f97d1647942161f803f | LGPL-3.0-only |
| psycopg-pool==3.3.3 | psycopg_pool-3.3.3-py3-none-any.whl | 9b9cd6a4fcec47a410f7e82d408540e7f77b478509e91b44c1a5457a13e5ff37 | LGPL-3.0-only |
| typing-extensions==4.16.0 | typing_extensions-4.16.0-py3-none-any.whl | 481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8 | PSF-2.0 |

**Dependency closure.** psycopg-pool unconditionally requires typing-extensions>=4.6; typing-extensions has no further runtime deps. This closes the target-specific Python dependency graph (test/dev extras and platform-inapplicable markers excluded). It does NOT cover binary embedded-library inventory in psycopg-binary.

**Why psycopg-binary (bundled libpq) is a candidate versus system libpq.** psycopg-binary is the fixed candidate because it is a wheel-only artifact: it installs under `--only-binary=:all:` with a hash lock and needs no compiler or host-installed libpq, so the qualification environment is isolated and reproducible. The alternative, psycopg's pure-Python mode against a system libpq (e.g. a Homebrew-installed one), would depend on host state outside the hash lock, which is not pinned or recorded here. The trade-off is that the bundled libpq and its OpenSSL/Kerberos/OpenLDAP copies are not enumerated, so inventory, CVE status and LGPL obligations are OPEN (B6). This is a candidate rationale only; neither option is selected, and D4.3 is not decided here (B7).

**Publisher/provenance.**
- PyPI Simple API does not advertise provenance attestations for the psycopg wheels. typing-extensions has one: https://pypi.org/integrity/typing-extensions/4.16.0/typing_extensions-4.16.0-py3-none-any.whl/provenance (not verified in this record).
- Upstream signed tag https://github.com/psycopg/psycopg/releases/tag/3.3.6 and tagged workflow https://github.com/psycopg/psycopg/blob/3.3.6/.github/workflows/packages-bin.yml indicate intended bundled libpq 18.6, OpenSSL 3.5.8, MIT Kerberos 1.22.2 and OpenLDAP 2.6.14. This is intended build configuration, NOT an exact wheel binary inventory/SBOM or cryptographic wheel provenance. The wheel must not be asserted to embed OpenSSL 3.5.8 from the workflow alone.
- Relevant license sources: https://www.postgresql.org/about/licence/ ; https://github.com/openssl/openssl/blob/openssl-3.5.8/LICENSE.txt ; https://web.mit.edu/kerberos/krb5-latest/doc/mitK5license.html ; https://www.openldap.org/software/release/license.html . Exact notices and inventory are OPEN.

## 4. Risk and unresolved issues (not softened; none closed)

**Image / PostgreSQL**
- PostgreSQL official security page https://www.postgresql.org/support/security/ lists 17.11 as fixing multiple 2026 PG CVEs, including CVE-2026-19385, CVE-2026-18408, CVE-2026-18024. This does NOT assess Debian/base package CVEs.
- Debian/base packages: read-only OSV Debian:12 querybatch over 199 Debian SPDX entries (105 binary-to-source mappings) gave 140 unique source/CVE pairs. Against the official Debian Security Tracker JSON current feed: 139 OPEN, 1 UNDETERMINED for bookworm. Of the OPEN, 85 have unassigned urgency, 53 unimportant, 1 low. Mapping is incomplete (42 package pages lacked a source link) and query semantics may miss advisories. Example OPEN: OpenSSL CVE-2026-35189 on the exact SBOM OpenSSL version, https://security-tracker.debian.org/tracker/CVE-2026-35189.
- This is NOT a safety pass. Zero vulnerabilities is NOT claimed. Opus must judge applicability and risk for loopback-only synthetic qualification; unresolved issues stay explicit.
- Publisher signature status: OPEN. Exact package license closure (including 17 NOASSERTION): OPEN.

**Python wheels**
- OSV queries for the four pinned PyPI versions returned no PyPI advisory IDs at observation time. This is NOT proof of safety and does not assess bundled native libraries.
- Official OpenSSL advisories https://openssl-library.org/news/vulnerabilities/ say 3.5.8 is affected by 13 CVEs fixed in 3.5.9, including HIGH CVE-2026-84782 (DTLS). DTLS may be outside libpq use, but applicability is not dismissed without independent security review. Whether the wheel embeds 3.5.8: UNKNOWN.
- Bundled libpq 18.6, MIT Kerberos 1.22.2 and OpenLDAP 2.6.14 CVE status: UNKNOWN (not assessed).
- LGPL-3.0-only licensing of three packages and bundled-library license terms: obligations not assessed; OPEN.
- psycopg wheel cryptographic provenance: absent/unverified.
- Native-library inventory of psycopg-binary: OPEN (B6). Native-library CVE evidence: OPEN (B6). LGPL-3.0 obligations and bundled-library licenses: OPEN (B6). None is verified; D4.3 is not decided (B7).
- OSV and PyPI statements above are supplied assertions (see classification), not reviewer-verified.

## 5. Remaining unknowns (summary)

Owner; image publisher signature; image package license closure; Debian CVE applicability; wheel binary inventory/SBOM and notices; wheel cryptographic provenance (psycopg*); native-library CVE status; prior overall attempt/time/token totals; current validity of all metadata (snapshot 2026-10-18T07:50:31Z, must be rechecked before pull).

## 6. Execution controls (apply only after ALL prerequisites below are met; an APPROVED pre-pull review alone is insufficient)

Before any pull, ALL of the following must hold; an APPROVED pre-pull review by itself does not authorize a pull:
1. BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME attempt budget reconciled (prior attempt use and remaining budget established).
2. ADR D12.3a control 1 source/provenance/license/CVE review completed (the OPEN items in §4, B3, B4, B6).
3. Free runtime verified (see Runtime below; OPEN B2).
4. All other controls in this section met.

- Runtime: Colima Docker context on macOS Virtualization Framework is an UNVERIFIED PREREQUISITE tied to OPEN B2. Nothing in this record verifies that Colima is installed or running, or that its use is no-spend. Before any pull, it must be confirmed that the free terms of Colima and its VM/Docker components apply (no spend, no account or license choice required) and the runtime itself must be confirmed running. If either cannot be confirmed at execution time, execution stays BLOCKED and escalates as owner-reserved.
- Pull by digest only (arm64 manifest above); recheck digests and platform before pull.
- Synthetic data only; loopback-bound published port; no persistent volumes.
- Python install only from `mod004-d123a-wheel-lock.txt` with `--require-hashes --only-binary=:all:`, in an isolated environment outside repository production paths.
- No S1 path writes (`backend/app/tenancy/`, `backend/migrations/`, `infra/db/`, `backend/tests/integration/tenancy/`); no production/backend lockfile change; harness and SQL are throwaway.
- One image and one version of each package. On any failure: stop and return to review; no automatic second candidate.
- Teardown after evidence capture: container, image, network and isolated environment removed, with removal recorded.
- Evidence of RLS, role and pool behavior (including tenant-switch and check-in reset) tied to the pinned digest and hashes.

## 7. Requested decision

An independent Opus reviewer is asked to decide this candidate's pre-pull gate (APPROVE / REJECT / CHANGES REQUIRED) on the evidence above, including applicability of the OPEN CVE, license and provenance items. This record does not self-approve; prior reviews returned CHANGES_REQUESTED.

An APPROVED pre-pull review alone is insufficient to pull. Nothing may be pulled, fetched or installed until, in addition to such a review: the BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME attempt budget is reconciled; ADR D12.3a control 1 source/provenance/license/CVE review is completed; the free runtime is verified (B2); and all other §6 controls are met. Until then the lock file is inert and D12.3 applies unchanged. This record stays PROVISIONAL and not gate-eligible, with B1–B7 unresolved, one candidate set, no D4.3 selection, and no ACTIVE, Ready or S1 claim.
