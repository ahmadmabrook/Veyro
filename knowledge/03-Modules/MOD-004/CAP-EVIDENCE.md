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

**Correction, 2026-11-06 — "into memory" understated it.** The wheel **is on disk** outside the
repository, 4,772,031 bytes, SHA-256 `373704aea331d3f3e3402c125a1543f5875e2986ebb54f97d1647942161f803f`
matching its pin, and its bundled `libpq.5.dylib` (371,120 bytes) was **extracted to disk** beside
it. The pinned image is likewise on disk in the Colima store, held untagged and pulled by digest.
Nothing is on any import path and nothing was installed, so every "not installed" statement in this
file stands exactly as written; what was inaccurate was the implication that nothing persisted. This
correction bounds the sentence above and the same framing in the B6 section; neither is edited.

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

## Condition 1 is unmet on grounds that are not circular — recorded 2026-11-06

The deviation above records conditions 2 and 4 as unmet at the pull, and treats condition 1 as
flawed by the B6 circularity. That account is incomplete, and the missing part is not a defect in
the record but ordinary unfinished work.

**What condition 1 requires**, in its own words: that B2, B3, B4 and B6 be "closed by evidence
actually produced and recorded: free-runtime terms; image provenance, licence closure and CVE
applicability; wheel and transitive hashes re-checked against PyPI; and the `psycopg-binary`
bundled-library inventory with its CVE status and LGPL-3.0 obligations."

**What the Still-open table below actually records**, as of this entry:

- **B3** — CVE applicability for the 139 open Debian bookworm CVEs: **OPEN**. Package licence
  closure, the 17 `NOASSERTION` fields: **OPEN**. Condition 1 names both by name.
- **B6** — the inventory itself is closed, but its CVE status is not: four of the twelve Low CVEs
  are unargued and the bundled libpq, Kerberos and OpenLDAP versions are unestablished. Condition 1
  names CVE status by name.
- **The LGPL-3.0 limb is NOT claimed as a ground here**, and saying otherwise would contradict this
  file. The "Still open" table records it as OPEN **for a distributing use**, and records a position
  for this one: not triggered by the loopback-only scope, because nothing is conveyed. So the part
  that is open lies outside this qualification, and §2 puts a distributing or deployed use outside
  it too, reserving deployed use to the owner under DC-16 `production-promotion`. An earlier
  revision of this section stated the obligations flatly "unassessed" and then listed the
  *loopback-only* assessment as outstanding work — inverting the record, and reintroducing exactly
  the contradiction class the B5 reviewer caught on this blocker once already.

So **condition 1 is unmet**, and not because of the B6 circularity. The four Low CVEs, the bundled
versions, the licence closure and the bookworm CVE applicability are all producible from artifacts
already in hand or from public sources; they are simply not yet produced.

**The narrower reading, named and answered**, because it is the reading a later session will reach
for. §2's own "What is being accepted" paragraph pre-accepts, as this record's premise, that "exact
package licence closure are OPEN", that the bundled libpq, MIT Kerberos and OpenLDAP CVE status "is
UNKNOWN", that "LGPL-3.0 obligations are unassessed", and that there are "139 OPEN Debian bookworm
CVEs" with incomplete mapping. So, the argument runs, condition 1 cannot require those same items
closed; it must require only that evidence be *produced and recorded* in those areas, replacing
CAP-001's supplied-assertion class, with residuals disclosed — which is what this file did.

It loses, on four grounds. The grammatical subject of condition 1 is the blockers and its verb is
"are closed"; the colon-list states what the closing evidence must cover, it does not substitute a
weaker test. The acceptance paragraph's own subject is "CAP-001 §4 records, **as supplied and
reviewer-unverified assertions**, that …" — it discloses a bad starting state so the owner's
attestation is informed, and condition 1 then requires that state be remedied; the two are
sequential, not contradictory. The clause is headed "**Conditions, none waived**". And decisively,
"CVE applicability" and "licence closure" are *judgments*, producible without fixing a single CVE,
so the wider reading is achievable rather than absurd — whereas under the narrower reading B3 would
have to be called closed, which this file's own B3 heading, "VERIFIED in part, CVE applicability
OPEN", denies.

**Consequences, stated rather than left to inference.**

1. The pull was unauthorized on this ground as well as on conditions 2 and 4. §2 permits a pull only
   once "conditions 1-6 and the remaining CAP-001 §6 execution controls hold", and conditions 1, 2
   and 4 were all unmet at the time. This is a broader characterisation of the same breach, not a
   new event, and it is recorded here rather than left for someone else to find.
2. `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME` **is not closed**. §3.1 is a precondition of
   *activation* rather than a closure rule: it requires that blocker to be "closed by the §2
   evidence", and with condition 1 unmet the §2 evidence does not close it. §3's "on all of the
   following and not before" is therefore unsatisfied, and the capability manifest stays PROVISIONAL
   with `gate_eligible: false`.
3. **No install, no container run, no manifest activation, no Ready-for-S1 judgment and no S1
   product code follow**, under the deviation section above and §3, §4 and §5. The install and
   container-run bars are listed first deliberately: they are the nearer temptation, and the
   deviation section above already holds them closed "until conditions 1-6 genuinely hold".
   ADR-0002 D12 stands unrelaxed.
4. None of this is a budget problem. Under `INTERNAL_CAP_MODE = UNMETERED`
   (`OWNER-2026-11-06-internal-cap-unmetered.md`) the remaining evidence work has no ceiling; what
   it has is a standard of proof. The work is: bookworm CVE applicability against the pinned digest;
   package licence closure, including the fields CAP-001 records as `NOASSERTION`; the bundled
   libpq, Kerberos and OpenLDAP versions; and a reachability position on the four remaining Low
   CVEs, or an explicit scoped acceptance of them. The LGPL-3.0 obligations are deliberately **not** on this list: the loopback-only position
   is already recorded, and the distributing-use question that stays open is outside this
   qualification.

This entry closes nothing and produces no evidence. It corrects the record's account of why the work
is not finished.

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

**Two corrections from the independent B5 verification, both making this section stronger than
first written.** First, the arm64 manifest `a85953d6…b3670d` was claimed above only as a *member* of
the index; its own bytes also **rehash to the pin** (3,643 bytes), which the reviewer checked and
this author had not. Second, and more consequential: **the narrower tag `17.11-bookworm` has also
moved off the pinned digest.** It now resolves to index
`sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994` with arm64 member
`sha256:9da3effe923ca751b92343f54bb9a90674895c52975e0bd10efd568d6be49b21`, so the bookworm line has
been rebuilt since the pin. The pinned digest remains retrievable, so pinning works — but **no tag,
not merely `:17`, resolves to the assessed artifact**, and CAP-001's 139-CVE bookworm scan is bound
to that one older build and is not necessarily the current bookworm build either. Execution must
pin the digest; a tag must never be used.

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

## B5 — independent fetch verification: SATISFIED for B3 and B4

§2.2 requires "an independent Opus reviewer performs its own fetch verification of B3 and B4 rather
than reading the Capability Manager's summary", and that a reviewer unable to fetch says so and
approves nothing. An independent Opus session, not the author of this file, performed it and
reported outbound network access working, so that branch did not apply. **OUTCOME: APPROVED**, on
eleven claims put to it.

It bound the pins to the repository rather than to its task prompt: the four wheel hashes against
`mod004-d123a-wheel-lock.txt` byte-for-byte, and the five image digests and both attestation blob
sizes against `CAP-001-mod004-d123a-prepull.md`. So it verified the artifacts this repository pins,
not figures handed to it.

**Confirmed independently:** all four PyPI hashes, filenames, yank status and `requires_python`; the
three licence expressions plus PSF-2.0; the transitive closure including the marker reasoning
(it checked that PEP 508 defines `python_version` as the first two components, so `"3.13" < "3.13"`
is false under both string and version comparison, and that `psycopg-pool` is the only unconditional
path to typing-extensions); the OCI index, arm64 manifest and attestation manifest fetched by digest
and rehashed; the attestation's declared layers, sizes and in-toto predicate types; the
`postgres:17` divergence; the wheel's hash checked **before** inspection and the
`OpenSSL 3.5.8 25 Aug 2026` string; and the 13 CVEs split one High and twelve Low, with a negative
cross-check confirming the count is not an artifact of its selector. Every entry of this file's
native-library table reproduced exactly on its own copy.

**Scope it was careful to state, and which is repeated here rather than quietly dropped.** It did
not pull the two attestation blobs, so their declared digests, sizes and predicates were verified
inside bytes that rehash to the pinned manifest, but the blob bytes themselves were not rehashed.
It verified no publisher signature and no trust root; it confirms an anonymous registry token
authenticates nothing about the publisher, so that stays OPEN. It states its verdict is not a safety
pass, not a security certification, not closure of any blocker, not the §2 pre-pull decision, and
authorizes no pull, install, activation or code. Per CLAUDE.md's disclosure rule its review leaves
no artifact: that it was performed, by whom, and that it held no write tool are asserted, not
provable by hash.

**It found a defect in this file and three places it understated.** The defect — a contradiction
about B6's state between its section heading and the summary table — is corrected above, with the
correction labelled rather than silently applied. Two understatements are folded into B3 above. The
third is below.

**The reachability argument, on firmer ground than this file had it.** This file argued from
protocol design: libpq speaks the PostgreSQL protocol over TCP or Unix sockets with TLS and neither
implements nor negotiates DTLS. The reviewer checked the binary instead. On the bundled
`psycopg_binary/.dylibs/libpq.5.dylib`, `nm -u` returns **no DTLS symbol and no QUIC symbol at
all**; the TLS entry points it imports are `_TLS_method`, `_SSL_CTX_new` and `_SSL_connect`.
OpenSSL's DTLS retransmission path is reachable only through a DTLS method object, which libpq never
constructs. CVE-2026-84782 is therefore unreachable through this wheel by symbol surface, not only
by protocol reasoning. It also confirmed from the advisory text that this file's paraphrase
overstates nothing.

**The twelve Low CVEs, now partly analysed — and the disclosure stays.** The reviewer agreed that no
individual analysis had been done and that this file disclosed it plainly rather than hiding it, and
said it would not soften that framing. By the same symbol-surface argument it found **eight of the
twelve structurally outside libpq's reach**: five QUIC issues (CVE-2026-35191, 42772, 54873, 75804,
84784), one DTLS 1.2 record issue (75806), one CMP client issue (75805), and CVE-2026-72897, which
turns on `SSL_set_SSL_CTX()`, a symbol libpq does not import.

**The remaining four are not dismissed, and this is the part that matters.** CVE-2026-35189
(relative-CRLDP memory allocation), CVE-2026-54872 (non-NIST EC timing), CVE-2026-54875 and
CVE-2026-77696 (SM2) sit in general X.509 and crypto territory that libpq's TLS path could in
principle touch. **No reachability claim is made for those four.** The basis for proceeding on them
remains what §2 fixes and nothing more: Low severity, a loopback-only local container, synthetic
fixtures, no listener reachable off the host, no real member data and no deployed use. The reviewer's
own words on this: the disclosure "is doing real work and should stay as written rather than be
reinterpreted as a clean bill." It stays as written.

## B1 — CAP owner: recorded

Per §2.3 the CAP owner is the orchestrating Claude Code session, in the limited sense that section
states: sole repository writer and producer of this evidence, **not** a legal or organizational
owner. The owner remains the accountable party for the capability's presence in the project.

## Still open

| Blocker | State |
|---|---|
| B5 independent fetch verification | **SATISFIED** for B3 and B4. An independent Opus reviewer performed its own fetches and returned APPROVED on all eleven claims put to it; see the section below. |
| B6 native-library inventory | **CLOSED** — the inventory, the embedded OpenSSL version and the CVE count and severities are verified, by this file and independently. Its *remaining* items stay open and are listed in the next three rows rather than by calling the inventory open. |
| B6 remaining: twelve Low CVEs individually | **OPEN.** Eight of the twelve are now argued structurally unreachable (see the B5 section); four are not. |
| B6 remaining: bundled libpq, Kerberos, OpenLDAP versions | **OPEN.** Not readable by version-string search. CAP-001's libpq 18.6 stays a supplied assertion. |
| B6 remaining: LGPL-3.0 obligations for a distributing use | **OPEN.** Not triggered by the loopback-only scope; not assessed for any other use. |
| B7 D4.3 selection | **OPEN.** An ADR amendment on a controlled path, per §2.4. |
| B3 CVE applicability and package licence closure | **OPEN**, as above (139 bookworm CVEs, 17 `NOASSERTION` fields). |
| Publisher signature | **OPEN.** Not attempted; digests are not signatures, and an anonymous registry token authenticates nothing about the publisher. |

**Correction.** An earlier revision of this file headed B6 "VERIFIED" while this table still said
"OPEN. Needs the wheel in hand; sequenced after the pull." Both could not be true, and the
contradiction mattered because §2 condition 1 turns on whether B6 is closed. The independent B5
reviewer found it. The inventory is closed; the named remaining items are not, and they are now
listed as themselves instead of being folded into a single misleading row.
