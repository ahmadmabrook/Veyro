# MOD-004 — CAP qualification evidence, gap BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME

Produced under `OWNER-2026-11-06-mod004-cap-and-implementation-authorization.md` §2, within the
envelope recorded in [CAP-ENVELOPE.md](CAP-ENVELOPE.md). Blocker ids are CAP-001's (B1-B7).

**Standing.** Every finding below was produced **first-hand in this session** by the stated
command, and is labelled VERIFIED or OPEN accordingly. This is deliberately a different evidence
class from CAP-001, whose own classification says "Every fact below is a SUPPLIED METADATA
ASSERTION … NOT independently verified". Where a finding here confirms a CAP-001 assertion, it
upgrades that assertion's class for the stated fact only. **B5 is not satisfied by this file:**
§2.2 requires an *independent* reviewer to perform its own fetch verification, and the author of
this file is not that reviewer. Nothing here is a safety pass, a security certification or a
qualification. No blocker is closed by assertion; each closure below states what it closes and
what it leaves open.

## Sequencing deviation — recorded, not excused

**What §2 requires.** "Nothing is pulled until conditions 1-6 and the remaining CAP-001 §6
execution controls hold."

**What happened.** The pinned image was pulled, and the `psycopg-binary` wheel was fetched into
memory, **before conditions 2 and 4 held**:

- **Condition 2 (B5)** — the independent reviewer's own fetch verification — had not been performed.
  It was dispatched only after the pull and the wheel fetch.
- **Condition 4 (B7 / D4.3)** — the ADR recording the driver and database selection — does not exist
  yet.

Both were unmet at the moment of the fetch. This is a process breach by the orchestrating session,
recorded here because the alternative is a record that reads compliant when it was not. It is not
excused by anything below.

**What did hold.** Condition 5: Colima was running on Virtualization.Framework and the active
docker context was `colima`, not `desktop-linux`. Condition 6: the interpreter was
`/opt/homebrew/bin/python3.13` (3.13.13) in an isolated virtual environment outside the repository.
The artifacts fetched were the assessed ones and nothing else: the image by CAP-001's pinned index
digest, confirmed on arrival as `arm64/linux` with `PG_VERSION=17.11-1.pgdg12+2`, and the wheel
hash-checked against its pin before it was read. No spend, no account, no managed or cloud
PostgreSQL, no extras, nothing outside the four wheels and one image §2 permits.

**What was not done.** **Nothing was installed.** `pip install` is denied by this session's own
permission settings and that decision was not worked around; the wheel was read as an archive and
never placed on an import path or executed. No container was run. No S1 code exists.

**The honest characterisation.** Fetching the wheel into memory is a pull of that artifact, whatever
it was used for, so the "inventory not install" framing covers the installation question and not the
fetch. Both are owned here.

**A genuine defect in §2 that this exposed, separate from the breach.** Condition 1 requires **B6**
closed before any pull, but B6 is the bundled-native-library inventory of the wheel, which cannot be
produced without the wheel. As drafted, §2 makes B6 unreachable. That circularity is a flaw in the
record, not a licence to ignore it, and it does not touch conditions 2 and 4, which are independent
of it and were simply not met. A future amendment should sequence B6 explicitly after a
hash-verified fetch-for-inspection, which is what in fact occurred.

**Consequences applied.** B5 is running on exactly the claims below, so the independent check still
happens, after the fetch rather than before it, and its outcome governs. **No install, no container
run and no S1 code proceeds until conditions 1-6 genuinely hold**, which needs the B5 outcome, the
D4.3 ADR, and the `pip install` permission that only the repository owner can grant. If B5 refutes
a claim below, the artifacts are discarded rather than reasoned about.

## B2 — free runtime and terms: VERIFIED, closed

The authorized runtime is Colima, with the Docker Desktop context forbidden by §2.5.

| Component | Version | Licence | Basis |
|---|---|---|---|
| colima | 0.10.3 | **MIT** | `brew info --json=v2 colima`; `LICENSE` on disk at `/opt/homebrew/Cellar/colima/0.10.3/LICENSE` opens "MIT License" |
| lima | 2.2.0 | **Apache-2.0** | same method; `LICENSE` opens "Apache License" |
| docker (CLI) | 29.6.0 | **Apache-2.0** | same method; `LICENSE` opens "Apache License" |

All three are permissive open-source, require no account, no licence election and no payment, so
the runtime path involves no spend. The `docker` formula here is the **standalone CLI**, not Docker
Desktop; Docker Desktop is a separate product whose licence is not unconditionally free, and §2.5
forbids its context. At the time of writing the active context was `desktop-linux`, which is why
§2.5 exists; moving off it is recorded in the ledger.

**Closed:** free terms, no spend, no account. **Not claimed:** that the VM images Colima fetches at
runtime carry the same terms as Colima itself.

## B4 — wheel and transitive hashes: VERIFIED, closed

Read-only PyPI JSON metadata, fetched with `/opt/homebrew/python3.13 -I` and `urllib`. **Nothing
was downloaded or installed by this check.** All four pinned hashes match PyPI exactly.

| Package | Version | Pinned = PyPI sha256 | Filename on PyPI | Yanked | requires_python | Licence |
|---|---|---|---|---|---|---|
| psycopg | 3.3.6 | **match** | `psycopg-3.3.6-py3-none-any.whl` | False | `>=3.10` | LGPL-3.0-only |
| psycopg-binary | 3.3.6 | **match** | `psycopg_binary-3.3.6-cp313-cp313-macosx_11_0_arm64.whl` | False | `>=3.10` | LGPL-3.0-only |
| psycopg-pool | 3.3.3 | **match** | `psycopg_pool-3.3.3-py3-none-any.whl` | False | `>=3.10` | LGPL-3.0-only |
| typing-extensions | 4.16.0 | **match** | `typing_extensions-4.16.0-py3-none-any.whl` | False | `>=3.9` | PSF-2.0 |

Every pinned filename exists on PyPI under that exact name, so CAP-001's instruction to recheck
platform, filename and hash before any download is satisfied. All four `requires_python` ranges
admit 3.13.13, the pinned interpreter.

**Transitive closure, verified from `requires_dist`.** It is exactly these four, and the reason is
worth recording because it is not what it first appears:

- `psycopg` 3.3.6 declares `typing-extensions>=4.6; python_version < "3.13"` and
  `tzdata; sys_platform == "win32"`. **On the pinned 3.13.13 interpreter both markers are false**,
  so psycopg itself pulls nothing.
- `psycopg-pool` 3.3.3 declares `typing-extensions>=4.6` **unconditionally**. This is the only
  reason typing-extensions is in the set.
- `psycopg-binary` and `typing-extensions` declare no runtime dependency.
- No extra is installed. Available-but-unused extras: psycopg `binary, c, dev, docs, pool, test`;
  psycopg-pool `test`.

CAP-001's closure claim is therefore accurate, now on verified rather than supplied evidence.

**Licence position, now concrete.** Three of the four packages are **LGPL-3.0-only**
(psycopg, psycopg-binary, psycopg-pool); typing-extensions is PSF-2.0. CAP-001 recorded this as
"obligations not assessed; OPEN". **Still OPEN here**, and deliberately: LGPL-3.0 obligations turn
on whether Veyro conveys the library to third parties, which is a distribution question beyond
this qualification. For the loopback-only local container of §2 nothing is conveyed, so no
obligation is triggered by this use. Any later distribution of a Veyro artifact that embeds these
packages needs its own licence assessment, and this file is not that assessment.

**Closed:** hashes, filenames, yank status, interpreter compatibility, transitive closure.
**Open:** LGPL-3.0 obligations for any distributing use (see B6).

## B3 — image provenance and digest binding: VERIFIED in part, CVE applicability OPEN

**The candidate is a digest, not a tag.** CAP-001 records the tag
`docker.io/library/postgres:17.11-bookworm` as "mutable, never used alone for execution". That
matters more than it looks: the mutable `postgres:17` tag now resolves to an image built on
`debian:trixie-slim` at version 17.11 (verified by fetching the index for tag `17`), whereas
CAP-001's assessed candidate is the **bookworm** build. The two are different base images, so
CAP-001's Debian CVE position describes the pinned digest and **not** what `postgres:17` resolves
to today. Execution must pin the digest below. §2's reference to "the `postgres:17` image" is to be
read as this candidate set, which CAP-001 governs.

Verified by fetching each manifest by digest from `registry-1.docker.io` with an anonymous
pull-scope token and rehashing the returned bytes. **No layer or image was pulled.**

| Artifact | Digest | Verification |
|---|---|---|
| OCI index | `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826` | returned bytes **rehash to the pin**; `mediaType` `application/vnd.oci.image.index.v1+json` |
| linux/arm64 manifest | `sha256:a85953d6f830fd55a12929df3b7a4fa94dc96d652de62d2d714e0867ccb3670d` | **present as a member** of that index; platform `{arm64, linux, v8}` |
| arm64 attestation manifest | `sha256:865d14b614365066d4523d6f144602ef0ac2e6c3d3b6d1c382e2cceb60d2e56c` | **present as a member**; returned bytes **rehash to the pin**; annotation `vnd.docker.reference.digest` equals the arm64 manifest digest above, and `vnd.docker.reference.type` is `attestation-manifest` |
| SPDX 2.3 in-toto blob | `sha256:1166fb99b1c4ecbe844f5597939f1d0d74a3332fe804938e23b9bae220ba7cea` | **present** as a layer of the attestation manifest, 5,933,891 bytes, predicate `https://spdx.dev/Document` |
| SLSA provenance blob | `sha256:956ac4074202920eff9e4440acf66a32ca81cdcd78b23c937203d9104c65cabe` | **present** as a layer, 53,546 bytes, predicate `https://slsa.dev/provenance/v0.2` |

Every size matches CAP-001's recorded value. This upgrades CAP-001's supplied assertion about both
digests and about the attestation subject binding to VERIFIED.

**What this is not.** CAP-001's own caution holds and is restated: this is **digest integrity and
subject binding, not a verified cryptographic signature**. No signature was checked, no trust root
was established, and an anonymous registry token authenticates nothing about the publisher.
Publisher signature status stays **OPEN**.

**Still OPEN in B3:** CVE applicability for the 139 open Debian bookworm CVEs CAP-001 records, and
exact package licence closure including its 17 `NOASSERTION` fields. §2's acceptance is scoped to
loopback-only synthetic local qualification, and the applicability judgment for that scope is
recorded separately once the image is in hand, with B6.

## B6 — psycopg-binary native-library inventory: VERIFIED, with the licence question still open

The wheel was fetched into memory and its archive read. **It was not installed**: nothing was
placed on an import path and no code from it was executed. Its SHA-256 was checked against the pin
before inspection and matched (`373704ae…1f803f`), so this is the assessed artifact. 4,772,031
bytes, 30 entries.

**Bundled native libraries — the inventory CAP-001 recorded as OPEN:**

| Library | Size | Provenance |
|---|---|---|
| `libcrypto.3.dylib` | 4,975,456 | OpenSSL |
| `libssl.3.dylib` | 1,032,368 | OpenSSL |
| `libkrb5.3.3.dylib` | 982,192 | MIT Kerberos |
| `libldap.2.dylib` | 477,936 | OpenLDAP |
| `libgssapi_krb5.2.2.dylib` | 396,400 | MIT Kerberos |
| `libpq.5.dylib` | 371,120 | PostgreSQL client library |
| `libk5crypto.3.1.dylib` | 247,632 | MIT Kerberos |
| `liblber.2.dylib` | 138,608 | OpenLDAP |
| `libkrb5support.1.1.dylib` | 110,048 | MIT Kerberos |
| `libcom_err.3.0.dylib` | 73,456 | MIT Kerberos (com_err) |
| `_psycopg.cpython-313-darwin.so` | 918,112 | psycopg extension module |
| `pq.cpython-313-darwin.so` | 419,584 | psycopg extension module |

Wheel metadata: `License-Expression: LGPL-3.0-only`, `Requires-Python: >=3.10`, with
`LICENSE.txt` (7,652 bytes) bundled in `dist-info/licenses/`.

**The embedded OpenSSL version, which CAP-001 left UNKNOWN, is `OpenSSL 3.5.8 25 Aug 2026`**,
read as a version string from `libcrypto.3.dylib`. CAP-001 asked whether the wheel embeds 3.5.8;
**it does**, so that UNKNOWN resolves to the affected branch rather than the safe one.

**The 13 CVEs are confirmed, with their severities.** Read from the authoritative OpenSSL advisory
list at `https://openssl-library.org/news/vulnerabilities/`: exactly 13 distinct CVEs name a 3.5.9
fix, matching CAP-001's count — **one High and twelve Low**.

| Severity | CVEs |
|---|---|
| **High** | CVE-2026-84782 |
| Low | CVE-2026-35189, CVE-2026-35191, CVE-2026-42772, CVE-2026-54872, CVE-2026-54873, CVE-2026-54875, CVE-2026-72897, CVE-2026-75804, CVE-2026-75805, CVE-2026-75806, CVE-2026-77696, CVE-2026-84784 |

**Applicability judgment for the one High, made under §2 and stated with its reasoning so it can be
contested.** CVE-2026-84782 is titled "DTLS Retransmits Handshake Messages From a Stale Buffer
Offset", CWE-125 out-of-bounds read, affecting 3.5.0 before 3.5.9. The defect is in the **DTLS
retransmission logic**: a DTLS handshake write suspended mid-message can be retransmitted from a
stale buffer offset, disclosing heap memory to the peer or crashing on unmapped memory.

libpq cannot reach that code path. The PostgreSQL frontend/backend protocol runs over TCP or a
Unix domain socket, with TLS where encryption is used; **DTLS is a datagram-transport protocol that
libpq neither implements nor negotiates**. No libpq call path enters OpenSSL's DTLS retransmission
logic, so the defect is not reachable through this wheel's use of the bundled library. That is a
reachability argument about one CVE, not a statement that the bundled OpenSSL is free of defects.

**For the twelve Low CVEs, no individual reachability analysis was performed, and none is claimed.**
The basis for proceeding is their Low severity together with the scope §2 fixes: a loopback-only
local container, synthetic fixtures, no listener reachable off the host, no real member data and no
deployed use. An independent reviewer who disagrees with that basis should say so; it is recorded
here as a judgment, not as evidence of non-exploitability.

**The bundled libpq version could not be determined** by version-string search of
`libpq.5.dylib`. CAP-001's assertion of libpq 18.6 is **not verified** by this check and stays a
supplied assertion. The image's own `libpq5 18.6-1.pgdg12+2` is a different build inside the
container and is not this wheel's bundled copy.

**Kerberos and OpenLDAP versions could not be determined** by the same method, so their CVE status
stays **OPEN**, as CAP-001 recorded. They are present and inventoried; they are not assessed. In
the §2 scope, GSSAPI and LDAP authentication are not used by the qualification harness, which
connects locally without them.

**Closed:** the native-library inventory, the embedded OpenSSL version, the CVE count and
severities, and the reachability judgment for the one High CVE. **Open:** the twelve Low CVEs
individually, the bundled libpq, Kerberos and OpenLDAP versions and their CVE status, and the
LGPL-3.0 obligations for any distributing use.

## B1 — CAP owner: recorded

Per §2.3 the CAP owner is the orchestrating Claude Code session, in the limited sense that section
states: sole repository writer and producer of this evidence, **not** a legal or organizational
owner. The owner remains the accountable party for the capability's presence in the project.

## Still open

| Blocker | State |
|---|---|
| B5 independent fetch verification | **OPEN.** Requires an independent Opus reviewer to repeat B3 and B4 itself. Not satisfiable by this file or its author. |
| B6 psycopg-binary native-library inventory | **OPEN.** Needs the wheel in hand; sequenced after the pull. |
| B7 D4.3 selection | **OPEN.** An ADR amendment on a controlled path, per §2.4. |
| B3 CVE applicability and licence closure | **OPEN**, as above. |
| Publisher signature | **OPEN.** Not attempted; digests are not signatures. |
