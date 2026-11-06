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

**Updated later the same day, after the B3 and B6 continuation passes.** Three of those four grounds
have since been produced, and this section is left standing rather than rewritten so the sequence is
visible. Current state: the bundled libpq, OpenSSL and Kerberos **versions are established**; all
twelve Low CVEs are **positioned**, two of them REACHABLE; and the bookworm CVE applicability is
**measured**, extended to the PGDG and Go groups. **The licence-closure ground did not survive
contact with the artifact**: it is not merely unproduced, it is **not obtainable from this SBOM at
all**, because `licenseConcluded` is `NOASSERTION` on every package and the declared fields are
unions of licence texts rather than grants. That changes what "unmet" means for this limb — it
cannot be closed from the SBOM's own licence fields, which are `NOASSERTION` throughout. An earlier
revision escalated that to "no further evidence pass can move it", which was wrong and is withdrawn:
two routes remained, and **the first was then executed**. Enumerating the declared space gives 46
distinct SPDX identifiers, all free-software or free-documentation licences that condition
distribution rather than execution. That produced a sound finding on the **use** question and
verified notice retention in the image, but it is **not** what condition 1 names: §2's own gloss is
"exact package licence closure", a per-package determination. A per-package pass over the image's
own 141 `copyright` files was then performed as well, giving 126 CLOSED, 3 NOT CLOSED and 12
NEEDS-READING, with 57 SBOM names undetermined. **The limb therefore stays OPEN**, bounded to
nameable packages. An earlier revision called the scoping of condition 1 an owner question at this
point; it was not reached, because the work was done instead. See "Route 1 executed" and "The
per-package pass" below.

**Whether condition 1 as a whole is now met is a separate judgment, and this file does not make it.**
That assessment has to run limb by limb across B2, B3, B4 and B6 and carry its own review, because it
is what would make the delegated pre-pull decision exercisable and, through §3 and §4, eventually
unlock S1 product code. It is not decided here and must not be read out of these findings.

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

## B3 continued — bookworm CVE applicability and licence closure: EVIDENCED, still OPEN

Produced 2026-11-06 by a delegated evidence pass over the pinned image's own SPDX SBOM plus OSV,
then re-checked first-hand by the orchestrating session on the raw artifacts. It **closes neither
part of B3**, and §2 condition 1 stays unmet. What it does is replace two CAP-001 assertions with
measurements, and both measurements are worse than the assertions.

### What was fetched, and that it is the right bytes

The attestation manifest `sha256:865d14b614365066d4523d6f144602ef0ac2e6c3d3b6d1c382e2cceb60d2e56c`
carries the SPDX SBOM as layer 0, digest
`sha256:1166fb99b1c4ecbe844f5597939f1d0d74a3332fe804938e23b9bae220ba7cea`, size 5,933,891. The bytes
received are 5,933,891 and their recomputed SHA-256 equals that digest. Verified twice, independently.

The document is an in-toto envelope whose `predicate` is the SPDX document. It holds **204 SPDX
packages**: one root entry named `sbom`, **199 `pkg:deb`** entries and **4 `pkg:golang`** entries.
All 199 Debian entries carry a name and a version; none is unresolvable.

### CVE applicability: 154 open entries, against CAP-001's 140 on the same OSV basis

The SBOM carries no source-package field and OSV's Debian data is keyed by source package, so the
binary-to-source mapping was done against current Debian bookworm, updates and security indexes.
**That mapping is this pass's own method, not SBOM data**, and it is where the pass is weakest:

| Mapping outcome | Count |
|---|---|
| Exact version found in an index | 149 |
| Not in any index; queried by its own binary name as a fallback | 39 |
| Name found, version differs | 5 |
| PGDG packages, not Debian, **not queried** | 6 |

89 distinct source/version pairs were queried. The result is **154 distinct OSV Debian entries, each
mapping to one distinct upstream CVE**. Recounted first-hand from the raw OSV data: 154.

**The comparison with CAP-001 needs its bases stated, or it misleads.** CAP-001 §4 records two
different numbers: its OSV querybatch gave **140 unique source/CVE pairs**, and only *after*
adjudication against the Debian Security Tracker current feed did that become "**139 OPEN, 1
UNDETERMINED** for bookworm", with 85 unassigned urgency, 53 unimportant, 1 low.

This pass finds **154**, raw and unadjudicated, under its own definition of open (OSV lists no
bookworm fix at or below the installed version). So:

- Against CAP-001's **directly comparable** OSV figure of 140, this pass exceeds it by **14**.
- Against its tracker-adjudicated 139 the gap is 15, but that comparison mixes bases and should not
  be the headline. The 1 UNDETERMINED entry is not identified here either.
- The `unimportant` count (53) and the `low` count (1) match CAP-001 exactly; the entire excess sits
  in "not yet assigned" (100 against 85).

No method was adjusted to close the gap. CAP-001 records 105 binary-to-source mappings and that 42
of its package pages lacked a source link, against 193 non-PGDG rows resolved to 89 distinct pairs
here, so its mapping was probably less complete. **The higher number is the one to plan against**,
and which specific entries CAP-001 missed is not established, because the Debian Security Tracker
was not queried in this pass.

Two counting details, stated so the arithmetic is reproducible. Counting one urgency per entry gives
53 + 100 + 1 = 154. Counting distinct urgency values per entry gives 156, because **two entries carry
two different urgency values across their affected ranges**. Neither count is wrong; they answer
different questions.

### Severity, and what OSV does not supply

Four of the 154 entries carry **no `severity` field at all** and are recorded as NO_SEVERITY_GIVEN;
none is inferred. The other 150 carry only a CVSS vector string — 122 v3, 28 v4 — and **no numeric
score**, so no score is derived. "Not yet assigned" is Debian stating that no urgency has been
decided; it is not a severity rating and is not treated as one.

**Fix status: 146 with no bookworm fix listed, 8 with one — independently reproduced.** The first
cross-check attempted by the orchestrating session produced a different shape (81/73) and **that
cross-check was wrong, not the pass**: a single OSV Debian record lists many source packages across
Debian:12, :13 and :14 — `DEBIAN-CVE-2011-3389` names nine packages including `asterisk` on
Debian:14 — so a naive "does any affected range carry a fixed event" test counts fixes for packages
that are not in this image at all. Rerun scoped to Debian:12 *and* to the source package actually
matched for each queried pair, the split reproduces exactly at **146 / 8**. All eight, named because
they are the only entries in the set with a fix available:

| Entry | Source package | Fixed in |
|---|---|---|
| `DEBIAN-CVE-2026-84782` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-35189` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-54872` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-75805` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-75806` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-77696` | `openssl` | `3.0.22-1~deb12u2` |
| `DEBIAN-CVE-2026-109518` | `apt` | `2.6.2` |
| `DEBIAN-CVE-2026-107161` | `cyrus-sasl2` | `2.1.28+dfsg-10+deb12u1` |

**Two things about that table must not be blurred.** First, these are the **image's own Debian
packages** — its system `openssl` at `3.0.22-1~deb12u1` — and **not** the OpenSSL 3.5.8 bundled
inside the `psycopg-binary` wheel, which is B6's subject. The CVE identifiers overlap because the
same upstream flaws affect both, but they are different artifacts at different versions, and a fix
being available for one says nothing about the other.

Second, `CVE-2026-84782` is the **High** severity entry, and a bookworm fix for it exists in
`3.0.22-1~deb12u2`, which the pinned digest predates. That is the concrete cost of the position D2
records — the pinned digest is an older bookworm build and carries no package update published
since the pin. It is recorded here so the trade-off is visible rather than implied.

### Licence closure: not closed, and CAP-001's figure is inaccurate as written

Counted first-hand over all 204 SPDX packages:

- `licenseConcluded` is `NOASSERTION` on **all 204**. Not one package has a concluded licence.
- `licenseDeclared` is literally `NOASSERTION` on **exactly 1** package — the root `sbom` entry.
- `licenseDeclared` is **absent entirely** on **16** others: `base-files`,
  `debian-archive-keyring`, `libcrypt1`, `libnss-wrapper`, `libsemanage-common`, `libsemanage2`,
  `libsemanage`, `libxcrypt`, `libxslt1.1`, `libxslt`, `nss-wrapper`, `tzdata`, and the 4 Go modules.

So 17 packages have no declared licence, but only by unioning the one literal `NOASSERTION` with the
sixteen absent fields. **CAP-001's wording, that "17 `licenseDeclared` fields are NOASSERTION", is not
accurate as written.** The remaining **187** packages carry a named declared licence
(187 + 16 absent + 1 literal = 204); whether those strings are correct or acceptable was not
assessed.
Licence closure is therefore **still OPEN**: a package set in which nothing has a concluded licence is
not a closed licence set.

### What this pass does not establish

- **The PostgreSQL packages themselves are unassessed.** The six PGDG entries — `libpq5`,
  `postgresql-17`, `postgresql-18`, `postgresql-client-17`, `postgresql-client-common`,
  `postgresql-common` — are not Debian packages and were not queried. Their CVE status is **UNKNOWN**.
  This is the most consequential gap in the pass: it covers the base OS and not the database.
- The 4 Go modules (Go stdlib 1.24.6, `gosu`, `moby/sys/user`, `golang.org/x/sys`) were not assessed.
  **UNKNOWN.**
- **154 is a lower bound, not a total**, for three reasons, strongest first. (a) The SBOM carries
  package data **only from Debian `dpkg` metadata**, so anything in the image not installed through
  `dpkg` does not appear in it at all and was never queried. In a PostgreSQL image that is the
  largest single reason the figure is a floor. (b) The version queried is the SBOM's version, which
  is **not necessarily the source-package version** for binNMU or epoch cases — a caveat that
  attaches to all 199 rows, including the 149 the table calls exact, not only to the two noted
  below. (c) Any of the 39 fallback-mapped names that is not a real source name returns zero results
  silently; this is the weakest of the three, since 28 of the 39 returned zero and most are genuine
  Debian source names that did resolve (`glibc` returned 24, `gnutls28` 7, `openldap` 6, `krb5` 6,
  `zlib` 4).
- **Absence of an entry is not evidence that a CVE does not apply.** OSV's Debian:12 completeness for
  this package set is UNKNOWN, and nothing here licenses reading a missing id as a clean result.
- `openssl` and `libssl3` fell into "name found, version differs", so their results may not
  correspond to the versions actually installed in the image. That bears directly on the OpenSSL
  question and is not glossed.
- "Open" here means OSV lists no bookworm fix at or below the installed version. It says nothing
  about reachability or exploitability in this image.
- Mapping used **today's** Debian indexes, not the image's build-time ones. **The OSV feed is moving
  under this pass, not settled.** Recomputed first-hand: the latest `modified` timestamp in the set
  is `2026-11-06T16:00:08Z`, **84 of the 154 entries** were modified after 2026-10-23, and **25 were
  modified on 2026-11-06 — the day of this pass**. An earlier revision of this section said "some
  entries were modified as recently as 2026-10-23", which was wrong by two weeks and understated the
  volatility in the direction that flatters the result; it was copied from the delegated report
  without being re-checked, in a section that claims a first-hand re-check. A re-run on another day
  should be expected to give a different count.
- Not checked at all: the linux/amd64 member, the SLSA provenance blob, publisher signatures, and the
  Debian Security Tracker cross-check.

### Effect on B3 and on condition 1

**B3's CVE applicability is evidenced and not closed.** B3's package licence closure is **not closed**.
Both remain as the "Still open" table records them, and §2 condition 1 — which names "licence closure
and CVE applicability" by name — stays **unmet**. Nothing here closes a blocker, activates a
capability, grants Ready, or retroactively authorizes the pull.

What would close it: the six PGDG packages and the four Go modules assessed on their own terms; the
dpkg-only scope of the SBOM addressed, since anything outside `dpkg` was never queried; the 39
fallback mappings resolved to real source names; the SBOM-version-versus-source-version question
settled for all 199 rows rather than the two noted above; and either a declared-licence enumeration
the project is willing to call closed for a non-distributing loopback-only use, or an explicit
scoped acceptance recorded as such. Under `INTERNAL_CAP_MODE = UNMETERED` none of that has a budget
ceiling.

**One engineering option this pass makes visible, recorded not taken.** Six of the eight fixable
entries are the image's system `openssl`, and they include the single High. D2 of the drafted
ADR-0006 already provides the route — move to a newer digest only under a change to that ADR
carrying a fresh CVE assessment of that digest — so selecting a newer bookworm build would retire
those six, at the cost of a full re-assessment and of discarding the only assessment that currently
exists. That is a decision for the D4.3 selection, not for this evidence file, and nothing here
selects it.

## B3 continued (2) — PGDG packages, Go modules, and why licence closure is not obtainable

Produced 2026-11-06, closing the two groups the first B3 pass could not query and settling the
licence limb. Delegated for the network work, re-verified first-hand for every figure asserted below.

### A fact about the image that its tag does not advertise

Read from the SBOM's own `versionInfo`:

| Package | Version |
|---|---|
| `postgresql-17`, `postgresql-client-17` | `17.11-1.pgdg12+2` |
| **`postgresql-18`** | **`18.6-1.pgdg12+2`** |
| **`libpq5`** | **`18.6-1.pgdg12+2`** |
| `postgresql-common`, `postgresql-client-common` | `293.pgdg12+1` |

The pinned image is named for PostgreSQL 17 and runs 17.11, but it **also contains the
`postgresql-18` package at 18.6**, and its client library `libpq5` is **18.6**, not 17.x. Any
assessment of this image therefore has to cover PostgreSQL 18 as well as 17; the earlier pass's
framing as "PostgreSQL 17.11" understated what is installed. The wheel's own bundled libpq is also
18.6, which is consistent.

### PostgreSQL advisory status

- **17.11 and 18.6 are the latest in their series.** The project's release-notes index shows both,
  dated 2026-08-13; notes for 17.12 and 18.7 return 404.
- **No listed advisory affects them.** The project's security page carries 76 CVE rows, and none
  lists 17 or 18 as affected with a fixed-in version above 17.11 or 18.6.
- **libpq and the client tools share the server's single advisory stream**, so there is no separate
  libpq list to check; at 18.6 and 17.11 they are at or above every fixed-in version.
- **A minor release lands 2026-11-12**, six days after this pass. Anything fixed there is not yet
  public, so this status has a known expiry.

**OSV has no PGDG coverage, and the empty results prove nothing.** Roughly twenty queries across
`Debian:12`, `Debian`, `Ubuntu`, purl and GIT forms using the PGDG names and versions all returned
empty. That the endpoint works was established by controls: `postgresql-17` on `Debian:13` returned
46 advisories, `postgresql-15` on `Debian:12` returned 40, and Bitnami `postgresql` 17.9.0 returned
35 while 17.11.0 and 18.6.0 returned none. **Debian 12 simply does not ship PostgreSQL 17 or 18**, so
the PGDG packages sit outside the dataset the first B3 pass used. The PostgreSQL status above rests
on **one primary source**, the project's own page, with no second source to cross-check it.

`postgresql-common` at `293.pgdg12+1`: the Debian security tracker shows no open issues for the
Debian package and three resolved ones. Whether the PGDG build corresponds to Debian's package was
not established, so that status is inherited, not verified.

### Go modules — one module is affected, and the stdlib advisory set is large

| Module | Version | Finding |
|---|---|---|
| Go standard library | 1.24.6 | **59 advisories** returned by OSV (`GO-2025-4006` … `GO-2026-6809`), and 1.24.6 falls inside every one of their ranges. **Symbol-level reachability is NOT ASSESSED** — that needs the built binary and a call-graph tool such as `govulncheck`, which is not available here and which the no-install rule forbids obtaining. |
| `github.com/moby/sys/user` | 0.1.0 | **AFFECTED** by `GHSA-mjcv-p78q-w5fw` / `GO-2026-6686` / `CVE-2026-61801`, fixed in 0.4.1. Unbounded parsing of `passwd`/`group` files can exhaust memory — availability only, rated MODERATE, `AV:L`. **gosu 1.19 source calls `user.GetExecUserPath`, one of the advisory's affected functions** — read from source at git ref `1.19`; **the gosu binary in the image was not inspected**, so what is actually linked is not verified. Whether anything in this scope can alter those files at run time is **NOT ASSESSED**. |
| `golang.org/x/sys` | 0.1.0 | `GO-2026-5024` / `CVE-2026-39824`, fixed in 0.44.0. The affected symbol exists only on Windows and gosu uses `x/sys/unix`; the binary was not checked. |
| `gosu` | 1.19.0 | OSV returned nothing. Its coverage of this module is **unestablished**, so that is not a clean result. |

gosu's source imports only `os`, `os/exec`, `runtime`, `syscall`, `moby/sys/user` and `x/sys/unix`,
and calls none of the `os` symbols named in four of the stdlib advisories. That narrows four of
fifty-nine and leaves the rest unassessed.

### Licence closure is not obtainable from this SBOM, and that is a finding rather than unfinished work

Counted first-hand over all 204 SPDX packages:

- `licenseConcluded` is `NOASSERTION` on **all 204**. The generator made no determination anywhere.
- Of the 188 packages with a `licenseDeclared` value, **166 carry an OR-union** rather than a single
  licence, across **55 distinct union strings**; only **21** declare a single real licence, from 6
  distinct values — a twenty-second single-valued entry is the root `sbom` package, whose value is
  literally `NOASSERTION`, which is a non-declaration and is not counted as one of the distinct
  values.
- Those unions are not disjunctive grants. The twelve GnuPG packages declare
  `BSD-3-Clause OR CC0-1.0 OR GPL-3.0-only OR GPL-3.0-or-later OR LGPL-2.1-only OR LGPL-2.1-or-later OR LGPL-3.0-only OR LGPL-3.0-or-later`.
  GnuPG is GPL-3.0-or-later; **no one may take it under CC0-1.0.** The field is a union of every
  licence text appearing in the package's `debian/copyright`, not a choice.
- Even the single-licence declarations are unreliable: the whole Kerberos family — `krb5`,
  `libkrb5-3`, `libgssapi-krb5-2`, `libk5crypto3`, `libkrb5support0` — declares `GPL-2.0-only`, which
  is surprising for MIT Kerberos and suggests the field reflects packaging copyright text rather than
  upstream licensing.

**So licence closure cannot be established by reading this artifact** — that claim is about this
SBOM, and it is as far as the evidence reaches. It does **not** follow that no further pass could
move the limb, and an earlier revision of this section said exactly that; the claim is withdrawn. Two
routes remain open and are named rather than foreclosed:

1. **Enumerate the declared space.** It is bounded: 55 distinct union strings plus 6 distinct single
   values, about **61 strings in total**, not 204 judgments. The question condition 1 poses for *this*
   scope — licence closure for loopback-only synthetic qualification — is whether any term restricts
   **use** rather than conveyance, and that is answerable by reading 61 strings.
2. **Read Debian's own `copyright` files.** The pinned image is already on disk and carries
   machine-readable DEP-5 `debian/copyright` for its packages. That is a further evidence source
   reachable without any new fetch, and this file does not pretend otherwise.

The residual-work figure in an earlier revision was also wrong by roughly a factor of two: it said
"199 source packages", but the 199 are `pkg:deb` **binary** entries, which this file's own earlier
section resolves to **89 distinct source packages**. Overstating the remaining work is what made
stopping look reasonable, so the corrected figure is stated here.

What remains true is narrower and still substantial: the SBOM's own licence fields cannot establish
closure, because `licenseConcluded` is `NOASSERTION` throughout — the generator declined that
judgment — and the declared field is a union of texts rather than a grant.

### Route 1 executed — the declared space enumerated; the use question answered, the limb still open

Route 1 above was then taken rather than left as a possibility. Splitting all 188 declared values on
`OR` and `AND` yields **46 distinct SPDX licence identifiers** — a smaller and far more tractable set
than either 204 packages or 61 strings:

`Apache-2.0`, `Artistic-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `BSD-4-Clause`, `BSD-4-Clause-UC`,
`BSL-1.0`, `Beerware`, `CC-BY-3.0`, `CC0-1.0`, `FSFAP`, `FSFUL`, `FSFULLR`, `GFDL-1.2-only`,
`GFDL-1.2-or-later`, `GFDL-1.3-only`, `GPL-1.0-only`, `GPL-1.0-or-later`, `GPL-2.0-only`,
`GPL-2.0-or-later`, `GPL-3.0-only`, `GPL-3.0-or-later`, `ISC`, `Kazlib`, `LGPL-2.0-only`,
`LGPL-2.0-or-later`, `LGPL-2.1-only`, `LGPL-2.1-or-later`, `LGPL-3.0-only`, `LGPL-3.0-or-later`,
`Latex2e`, `MIT`, `MIT-CMU`, `MPL-1.1`, `MS-PL`, `OpenSSL`, `PostgreSQL`, `RSA-MD`, `SMAIL-GPL`,
`Sleepycat`, `Spencer-86`, `TCL`, `X11`, `Zlib`, `libutil-David-Nugent`, and `NOASSERTION` (the root
`sbom` entry, which is not software).

**Of the 46, forty-five are recognised free-software or free-documentation licences** (the
forty-sixth is `NOASSERTION`, the root `sbom` entry, which is not software). None is proprietary,
none carries a non-commercial term, and none imposes a field-of-use restriction.

**A first attempt at the next step was wrong, and the correction matters.** An earlier revision of
this section claimed the conditions "attach to copying, distribution, modification or public
conveyance, not to execution", and that the permissive identifiers "say nothing about running the
software". That is **false on the licence texts** for about fourteen of them, and an independent
review caught it. Several expressly grant *use* and condition that grant:

- `RSA-MD` (declared by `cyrus-sasl2`, `libsasl2-2`, `libsasl2-modules-db`) licenses copying **and
  use** provided the software is identified in material referencing it, and requires its notices be
  retained in any copy of any part.
- `Beerware` (11 entries) conditions the whole grant on retaining its notice.
- `libutil-David-Nugent` permits "other use" provided its notation is included.
- `Spencer-86` grants use for any purpose **subject to restrictions**, including not
  misrepresenting the software's origin.
- `MIT`, `ISC`, `X11`, `MIT-CMU`, `PostgreSQL`, `TCL`, `BSL-1.0`, `Zlib`, `Kazlib` all grant use
  subject to notices appearing in or being retained in all copies; `BSL-1.0` names execution
  expressly, and `MIT-CMU` binds the recipient by the act of obtaining or using.
- The `OpenSSL`/SSLeay text makes the software free for use **as long as its conditions are adhered
  to**.

There is also a **third category the two-way taxonomy omitted**: `BSD-4-Clause`,
`BSD-4-Clause-UC`, `OpenSSL` and `X11`/`MIT-CMU` carry advertising and name-use clauses, which
attach to advertising rather than to use or conveyance and can trigger without either.

So the accurate statement is narrower in form and stronger in evidence. **No identifier in the set
conditions the act of execution as such.** What several of them do condition on a *copy held and
run* is **notice retention and non-misrepresentation** — and that is a question of fact about the
artifact, which the earlier revision never checked.

**That fact is now checked, by static inspection of the pinned image.** `docker save` was used to
export the image's layers to a file; no container was created and none was run. Walking all 14
layers:

- **141 packages carry `/usr/share/doc/<pkg>/copyright`** directly.
- **Zero whiteout entries** exist anywhere under `usr/share/doc`, so nothing was deleted by a later
  layer.
- **`/usr/share/common-licenses/` is present** with 17 licence texts, including `Apache-2.0`,
  `GPL-1`, `GPL-2`, `GPL-3`, `LGPL-2`, `LGPL-2.1`, `LGPL-3`, `GFDL-1.2`, `GFDL-1.3`, `MPL-1.1`,
  `MPL-2.0`, `BSD`, `Artistic` and `CC0-1.0`.
- The three binary packages without a direct file resolve by symlink, which is standard Debian
  practice: `libgcc-s1` → `gcc-12-base` and `libstdc++6` → `gcc-12-base` (both of which carry a
  copyright file), and `libncursesw6` → `libtinfo6`.
- The ~57 SBOM entries with no doc directory are **source-package** names, which have no doc
  directory by construction. Spot-checked for twelve of them — `glibc`, `acl`, `attr`, `krb5`,
  `openldap`, `zlib`, `pam`, `systemd`, `sqlite3`, `libzstd`, `libselinux`, `gmp` — whose binary
  packages (`libc6`, `libacl1`, `libattr1`, `libkrb5-3`, `libldap-2.5-0`, `zlib1g`, `libpam0g`,
  `libsystemd0`, `libsqlite3-0`, `libzstd1`, `libselinux1`, `libgmp10`) all carry notices.

**So the notice-retention and non-misrepresentation conditions are satisfied by the image as
pinned**, and running it breaches no condition in the set. The remaining bullets record how each
licence family reaches that result:

- The GPL family says so explicitly. GPL-2.0 §0 provides that activities other than copying,
  distribution and modification fall outside the licence's scope and that running the program is not
  restricted; GPL-3.0 §2 affirms unlimited permission to run the unmodified program. The LGPL
  versions inherit this through their GPL base.
- The permissive identifiers — `MIT`, `X11`, `ISC`, `BSD-*`, `Apache-2.0`, `Zlib`, `BSL-1.0`,
  `MS-PL`, `PostgreSQL`, `TCL`, `OpenSSL`, `Beerware`, `Kazlib`, `Spencer-86`, `RSA-MD`, `FSF*`,
  `Latex2e`, `libutil-David-Nugent`, `MIT-CMU` — impose **notice retention**, several of them on a
  held copy and not only on redistribution, as set out above. Those duties are satisfied here
  because the notices are retained; **it is the retention that discharges them, not the absence of
  an obligation.**
- No patent or anti-circumvention term in the set bites on a local non-distributing use:
  `Apache-2.0` §3, `MS-PL` §3(A), `MPL-1.1` §8.2 and `GPL-3.0` §3 and §11 are licensor-side grants
  or waivers, or defensive terminations conditioned on litigation or on conveying.
- `Sleepycat` conditions **redistribution** on source availability. `MPL-1.1` and `Artistic-2.0`
  likewise attach to distribution and modification. `CC0-1.0` waives rights outright. `CC-BY-3.0`
  requires attribution when distributing or publicly performing. The `GFDL` identifiers govern
  documentation, on distribution.

**Why the conclusion holds whatever the unions mean.** An earlier revision argued the unions are
disjunctive — "the true licence is *some member*" — which contradicts this file's own analysis two
sections above, that a union lists every text appearing in `debian/copyright` and is **not a choice**.
The conjunctive reading is the right one and it is also the stronger one here: if every member
governs its own files, then every member's conditions apply, and since no member conditions
execution and the notice duties of all of them are satisfied by the retained notices, the result is
the same. The Kerberos family's surprising `GPL-2.0-only` declaration is a case in point — right or
wrong, both it and MIT Kerberos's actual terms sit inside this set, and neither restricts running
the software. Note also that **no declared value contains `AND`, `WITH`, parentheses or a `+`
suffix**, so splitting on `OR`/`AND` discarded no conjunction; the `AND` half of the split was
vacuous.

**What is established, stated at exactly its strength.** For a local, non-distributing qualification
use in which nothing is conveyed: no licence in the set conditions execution as such, and the
conditions that do attach to a held and running copy — notice retention and non-misrepresentation —
are satisfied by the image as pinned. **Running this image breaches no term in the set.**

**What is NOT established, and it is the thing condition 1 names.** §2's own gloss on this item, in
its acceptance paragraph, is "**exact** package licence closure" — a per-package determination.
This pass does not make one, and `licenseConcluded` remains `NOASSERTION` on all 204. An earlier
revision of this section claimed the limb was therefore "closed for the authorized scope" and that
this was "the determination condition 1 asks for". **That claim is withdrawn.** Reading §2's
scope framing back into condition 1 to redefine "licence closure" as a use-only, set-level property
is a narrowing, and it is open to the same objection this file already sustains elsewhere against
substituting a weaker test — that the colon-list states what the closing evidence must cover and the
clause is headed "Conditions, none waived". Having rejected that move once, this file does not get to
make it here.

**So the licence limb remained OPEN for condition 1 at that point**, and the next step was taken
rather than escalated — see below. An earlier revision of this paragraph said the remaining work
would be disproportionate and that scoping condition 1 was therefore an owner question. That was
premature: the work turned out to be bounded and was done.

### The per-package pass — 126 of 141 closed formally, 15 not, and 57 entries undetermined

The image's own `copyright` files, extracted above, were then parsed per package. Of the 141:

| Outcome | Count | Meaning |
|---|---|---|
| **CLOSED** | **126** | 118 DEP-5 files where every `Files:` stanza carries a `License:` and every short-name is defined in the file or is a `common-licenses` name, plus 8 free-form files read in full. |
| **NOT CLOSED** | **3** | `base-passwd` and `libldap-2.5-0` reference a bare `public-domain` label that is never defined and is not a `common-licenses` name. `libllvm19` references `BSD-3-Clause` and `BSD-3-clause` without defining either — and `BSD-3-clause` does **not** resolve to `common-licenses/BSD`, which is a different text — with a `Files:` stanza reported to carry no `License:` at all. |
| **NEEDS-READING** | **12** | The primary licence is identified in each, but component notices were not verified line by line, or some files are stated to carry no licence. Named: `gcc-12-base` (covers the whole gcc tree and never states what governs the files this package installs); `libc6`, `libc-bin`, `libc-l10n` and `locales` (one byte-identical file whose header says glibc 2.23 while the SBOM says 2.36, so the header is **stale**); `libcrypt1` (testsuite files stated to have no licence, asserted not installed, unverified); `libgcrypt20` and `libgnutls30`; and `libgssapi-krb5-2`, `libk5crypto3`, `libkrb5-3`, `libkrb5support0` (one identical 1374-line aggregate of component notices, not read in full). |

**A refinement from re-checking the three NOT CLOSED cases first-hand.** Most of `libldap-2.5-0`'s
apparently-undefined names are DEP-5 **conjunctions** — `OpenLDAP-2.8 and BSD-3-clause`,
`OpenLDAP-2.8 and UMich and F5` and so on — whose components are each defined in the file, so they
resolve by decomposition. Its real gap is the same single one as `base-passwd`'s: the bare
`public-domain` label, which is a Debian convention asserting that no copyright is claimed rather
than a missing licence text. `libllvm19`'s case-variant gap is the substantive one of the three.

**What "CLOSED" means here, stated because it is weaker than it sounds.** It is a **formal
self-consistency** test: the copyright file internally resolves. It is **not** a determination that
the stated licences are correct, complete, or correctly matched to the shipped files. Of the 126,
twenty-five carry hedged local labels such as `probably-PD`, `none`, `permissive`, `FreeSoftware` or
`MIT-like` — each defined in its own file, but each a packager's characterisation — and five pass
only on a case-insensitive match, among them `postgresql-17`, `postgresql-client-17` and `libpq5`.

**Coverage, and what is simply not determined.** The SBOM has 199 `pkg:deb` entries but **198
distinct names** — `e2fsprogs` appears twice. All 141 files matched a purl. **57 names have no
copyright file and are not determined by this pass**: `libgcc-s1`, `libncursesw6` and `libstdc++6`,
whose doc directories are symlinks (resolved earlier in this file), plus about 54 source-package
names. Only copyright **declarations** were read; no installed file contents were examined.

**The use question, now much better evidenced — and who did what.** The lexical scan across all 141
files plus the texts of about 35 locally-defined licences was performed by the delegated pass, not by
the orchestrating session, and found **no term restricting use or execution**. The orchestrating
session independently reproduced the licence-value counts, the three NOT CLOSED cases and the
conjunction refinement, but **did not re-run the full scan**; that attribution is stated because an
earlier section of this file records a claim of first-hand verification that the stated command
disproved. The nearest items the scan did surface are recorded rather than omitted, because they are
the ones a reader would want to check:

- **RSA MD4/MD5 grants** (`libsasl2-2`, `libsasl2-modules-db`, the krb5 family) condition the grant
  of copying and use on identification — an attribution condition, satisfied by the retained
  notices, not an execution restriction.
- **Acceptance-by-use wording** in `Ms-PL` (`libdb5.3`) and the Unicode data-files notice (the perl
  packages).
- **Export-control notices** in the krb5 family, the e2fsprogs family and `libsasl2`. These are not
  licence conditions on use; they are statutory notices about export, and they are recorded here
  because they are a constraint class the licence analysis would otherwise hide. They bear on
  distribution and transfer, not on running the image locally.
- **Trademark-use terms** in the krb5 family only.
- **`Sleepycat`** (`libdb5.3`, read in full): a source-availability condition on redistribution.
- **Not read:** `libidn2-0` points at an external Unicode "Terms of Use" URL that is not contained in
  the file.

**Effect on the limb: still OPEN, but now precisely bounded rather than open-ended.** What blocks it
is nameable: 3 packages formally unresolved, 12 whose aggregate notices were not read line by line,
57 SBOM entries undetermined, and a notion of "closed" that is self-consistency rather than
correctness. That is a materially better position than the earlier "not obtainable" and the later
"closed for the authorized scope", both of which were wrong in opposite directions. **Whether this
suffices for condition 1's "exact package licence closure" is the judgment the separate condition-1
assessment has to make, on this evidence, and it is not made here.**

**What this does NOT establish, and the limits are the point.**

- **Nothing about distribution.** The moment any Veyro artifact embedding this image is conveyed,
  81 of the 204 packages' GPL-3/AGPL/LGPL-3-class terms and `Sleepycat`'s source-availability
  condition become live, along with the attribution duties of every permissive licence in the set.
  That is a different question on different facts and stays reserved to the owner under DC-16
  `production-promotion`.
- **It is not a per-package licence determination.** `licenseConcluded` is still `NOASSERTION` on all
  204, and this pass does not conclude any package's licence. It establishes a property of the
  *whole candidate set*, which is weaker than closure in the general case and sufficient only for the
  use question.
- **It rests on the declared fields being a superset of the truth.** If a package's real licence is
  something that appears in **no** declared string — which the SBOM gives no way to detect — this
  argument does not reach it. The `dpkg`-only scope recorded above bounds it the same way.
- **It is a licence-terms reading, not legal advice**, performed by the orchestrating session and not
  by counsel. It is recorded as an engineering determination about this scope and nothing wider.

For the authorized scope the distribution question is not triggered, because nothing is conveyed:
the same position B6 already records for its LGPL-3.0 limb. **But the exposure if that ever changes
is now quantified: 81 of the 204 packages declare GPL-3.0-, AGPL- or LGPL-3.0-class terms**, among
them `bash`, `coreutils`, `gnupg`, `gnutls28`, `gcc-12` and `cyrus-sasl2`. Any distributed Veyro
artifact embedding this image is a different question entirely and is reserved to the owner under
DC-16 `production-promotion`.

### Effect on B3 and on condition 1 — what this does and does not move

**Closed by this pass:** the PGDG group is assessed, with no listed PostgreSQL advisory affecting
17.11 or 18.6 on the project's own table; the Go modules are assessed by version; and the licence
limb is now understood well enough to say it is not closeable from this artifact.

**Left standing, and corrected here.** That last clause is wrong twice over. Route 1 *was* executed
from that very artifact — the enumeration is the SBOM's own declared fields — so the limb was
partly addressable from it. And an earlier revision then over-corrected, declaring the limb closed;
that is withdrawn too. The accurate position is the next item.

**Advanced but NOT closed:**

1. **Licence closure.** Route 1 answered the **use** question: the declared space enumerates to 45
   real SPDX identifiers, none conditioning execution as such, and the notice-retention and
   non-misrepresentation duties that several of them do impose on a held copy are **verified
   satisfied** by the pinned image — 141 packages carrying `copyright`, zero whiteouts, 17
   `common-licenses` texts, three symlinks resolving to present files. Running the image breaches no
   term in the set. **That is not condition 1's "exact package licence closure"**, which is
   per-package and which this pass does not perform; `licenseConcluded` stays `NOASSERTION` on all
   204. A **per-package pass** over the image's own 141 `copyright` files was then performed rather
   than escalated, giving **126 CLOSED, 3 NOT CLOSED, 12 NEEDS-READING**, with **57** SBOM names
   undetermined for want of a copyright file, and no use or execution restriction found anywhere in
   the 141 files or the ~35 local licence texts. So the limb **remains OPEN** — but bounded to
   nameable packages rather than open-ended. Whether that satisfies condition 1 is for the separate
   condition-1 assessment. A distributing use is a different matter entirely, reserved under DC-16
   `production-promotion`.

**Still OPEN:**

1. **Reachability for 59 Go stdlib advisories**, and for the one affected `moby/sys/user` function
   that gosu's source calls.
2. **The single-source basis** of the PostgreSQL status, with a release six days out.
3. **The dpkg-only scope** of the SBOM, which no amount of OSV querying addresses.
4. **OpenLDAP's bundled version** and the six inferred sibling libraries, from B6.
5. **Two REACHABLE Low CVEs** in the bundled OpenSSL, held only by a scope argument.

Nothing here closes a blocker, activates a capability, grants Ready, or retroactively authorizes the
pull.

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

## B6 continued — bundled versions established; two of the four Low CVEs are REACHABLE

Produced 2026-11-06 by a delegated static-inspection pass over the wheel already on disk, with every
headline claim re-verified first-hand by the orchestrating session. Nothing was executed, nothing was
installed, and no extracted object was placed on an import path. **This pass does not close B6
favourably.** It establishes the versions CAP-001 asserted, and it finds that two of the four
previously unargued Low CVEs are reachable — one of them in a default configuration.

### Bundled library versions — CAP-001's three assertions are matched, with one still an inference

Twelve shared objects were extracted from the wheel (hash re-checked first: 4,772,031 bytes, SHA-256
`373704aea331d3f3e3402c125a1543f5875e2986ebb54f97d1647942161f803f`).

| Library | Version | How established | Class |
|---|---|---|---|
| libpq | **18.6** | `_PQlibVersion` disassembles to `mov w0, #0xbf26` / `movk w0, #0x2, lsl #16` = `0x2bf26` = 180006 = 18.6. **Re-derived first-hand**, not taken from the delegated report. | VERIFIED |
| OpenSSL | **3.5.8** | `libcrypto.3.dylib` carries the banner string `OpenSSL 3.5.8`. Re-read first-hand. | VERIFIED |
| MIT Kerberos | **1.22.2** | `libkrb5.3.3.dylib` carries `KRB5_BRAND: krb5-1.22.2-final 1.22.2`. Re-read first-hand. | VERIFIED |
| OpenLDAP | 2.6.14 | **No banner string exists in `libldap.2.dylib`** — confirmed first-hand. The figure rests on reading a `mov w8, #0x5086` (= 20614) near the vendor-name string in `_ldap_get_option` as the API-info vendor version, a reading the delegate did not check against OpenLDAP source. | **INFERENCE, not verified** |
| libssl, libgssapi_krb5, libk5crypto, libkrb5support, libcom_err, liblber | — | No banner of their own. Assumed to come from the same builds as their siblings, on linkage and a shared build prefix. | **INFERRED ONLY** |

So **CAP-001's libpq 18.6, Kerberos 1.22.2 and OpenLDAP 2.6.14 are matched by the artifacts**, and the
first two plus OpenSSL are now first-hand VERIFIED rather than supplied assertions. The OpenLDAP
figure is an inference and is recorded as one. The six sibling libraries' versions stay UNKNOWN.

### The four previously unargued Low CVEs, now positioned — and two are reachable

All four are against the **OpenSSL 3.5.8 bundled in this wheel**, never the image's system openssl
3.0.22. Three of the four identifiers also appear against the image's package; those are a different
artifact at a different version and nothing here transfers between them.

| CVE | Flaw | Verdict | Basis |
|---|---|---|---|
| `CVE-2026-35189` | Excess heap growth from a certificate carrying many relative CRL distribution points, during X.509 extension caching in a TLS handshake | **REACHABLE** | libpq imports `_SSL_connect`, `_SSL_set_verify`, `_SSL_get1_peer_certificate` and `_X509_get_ext_d2i`; the chain-verification entry point `_X509_verify_cert` is imported by **`libssl.3.dylib`**, which libpq loads in-process. All by exact-match `nm -u`. The input is the server certificate libpq's own handshake receives. |
| `CVE-2026-54872` | Timing leak in ECDSA/SM2 signing on non-NIST generic curves such as Brainpool | **REACHABLE, conditional** | libpq imports `_SSL_use_PrivateKey_file` and `_ENGINE_load_private_key`; `libssl.3.dylib` contains **12** occurrences of `brainpool`. Both confirmed first-hand. Live only where a client certificate and key on such a curve are configured. |
| `CVE-2026-54875` | SM2 timing leak on ARM64 and RISC-V; this wheel is arm64 | **NOT REACHABLE THROUGH THE TLS PATH** — a narrower claim than "not reachable" | **The vulnerable code ships.** `libcrypto.3.dylib` exports **109 SM-family symbols**, among them `_EC_GFp_sm2p256_method`, `_EVP_sm3` and `_EVP_sm4_cbc`. What is absent is any way for TLS to select it: `libssl.3.dylib` carries **no `sm2sig_sm3` signature algorithm** — while it does carry the brainpool sigalgs, 12 occurrences — and libpq imports no `_EVP_PKEY_sign`, `_EVP_DigestSign` or `_EVP_DigestSignInit`. All by exact-match `nm`/`strings`. |
| `CVE-2026-77696` | Timing leak in SM2 signature generation, all platforms | **NOT REACHABLE THROUGH THE TLS PATH** | Same evidence as above, and subject to the same narrowing: the code is present in libcrypto and only the TLS selection path is shown absent. |

**A fabricated verification, retracted — recorded because this file's standing claim is that every
finding was produced first-hand by the stated command.** An earlier revision of this section asserted
that libpq imports `_X509_verify_cert` "directly … confirmed first-hand by `nm -u`", and presented
that as a *correction* to the delegated report, which had attributed the symbol to libssl. **The
delegate was right and the correction was false.** libpq's only matching undefined symbol is
`_X509_verify_cert_error_string`, an error-code-to-string accessor that verifies no chain and
populates no extension cache; `_X509_verify_cert` itself is imported by `libssl.3.dylib`.

The cause was a method error worth naming: the check tested `symbol in nm_output` as a **substring**,
so the longer `_X509_verify_cert_error_string` satisfied a test for `_X509_verify_cert`. Every symbol
claim in this section has since been re-run with **exact line matching**, which is the only form this
file should ever rely on. `CVE-2026-35189`'s REACHABLE verdict survives on the corrected basis —
libpq's own `_SSL_connect`, `_SSL_get1_peer_certificate` and `_X509_get_ext_d2i`, plus libssl's
`_X509_verify_cert` in the same process — so the direction does not change, only the stated
integration point, which is the fact a mitigation would be scoped against.

**A second understatement, also corrected.** That revision rested the two SM2 verdicts on the absence
of SM2 strings from **libssl**, which is not where SM2 lives, and dropped the delegate's disclosure
that `libcrypto` ships the SM2 implementation in full. The load-bearing argument is the delegate's,
not the one published: TLS cannot select SM2 because libssl carries no `sm2sig_sm3` entry. Both
verdicts are now stated as "not reachable through the TLS path", with the code's presence disclosed.

### What the reachability verdicts do and do not rest on

- `nm -u` lists **imports, not runtime calls**. A symbol being imported does not prove the path
  executes; a symbol being absent is the stronger half of the argument. **Absence must be established
  by exact line matching**, never by substring: a substring test produced a false positive in an
  earlier revision of this section, as recorded above.
- **The two SM2 verdicts are about the TLS path only.** The SM2 implementation is present in the
  bundled `libcrypto`, so any route into libcrypto that does not go through libssl's signature-algorithm
  selection is outside what the evidence covers.
- That the extension cache is populated inside `X509_verify_cert` comes from OpenSSL internals
  knowledge, **not from a symbol in this artifact**. It is the weakest link in the REACHABLE verdict
  for `CVE-2026-35189`, and the verdict is adverse to this project, so it is not softened on that
  account.
- The two NOT REACHABLE verdicts **do not cover** a runtime OpenSSL engine, provider or config file —
  libpq does import `_ENGINE_by_id` — nor other code in the same process calling libcrypto directly.
- Whether either REACHABLE finding is practically exploitable is **NOT ASSESSED**, and no such claim
  is made in either direction.

### Why this is tolerable for the authorized scope — a scope argument, not a safety claim

Stated as a scope argument on purpose, because the reachability question has now been answered
against the project and must not be re-answered by reasoning:

- `CVE-2026-35189`'s input is a **server certificate**. In the authorized scope libpq connects only
  to this project's own container over loopback, so the certificate is not attacker-supplied. The
  `postgres` image also defaults to SSL off, so a TLS handshake may not occur at all — but that is
  configuration, not architecture, and is not relied on as the primary argument.
- `CVE-2026-54872` needs a client certificate and key on a Brainpool or other generic curve. None is
  configured, and none is to be configured in this scope.
- **Both arguments fail the moment the scope changes.** For any deployed use in which libpq connects
  to a server whose certificate is not fully trusted, `CVE-2026-35189` is **live and unmitigated**.
  That is a real input to the DC-16 `production-promotion` decision, which is reserved to the owner,
  and it is recorded here so that decision is not made without it.

### Effect on B6

The **bundled-library-versions** item is **closed** for libpq, OpenSSL and Kerberos and remains open
for OpenLDAP and the six inferred siblings. The **twelve Low CVEs** now all carry a position: eight
argued structurally unreachable earlier, two more NOT REACHABLE here, and **two REACHABLE**. B6's CVE
status is therefore evidenced in full, with an adverse finding, rather than closed clean. Nothing
here closes a blocker, activates a capability or grants Ready.

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
| B6 remaining: twelve Low CVEs individually | **ALL TWELVE NOW POSITIONED, with an adverse result.** Eight argued structurally unreachable earlier. `CVE-2026-54875` and `CVE-2026-77696` are **not reachable through the TLS path** — a narrower claim than "not reachable", because `libcrypto` ships the SM2 code (109 exported SM-family symbols) and what is absent is libssl's `sm2sig_sm3` selection entry. And **two REACHABLE**: `CVE-2026-35189` in a default TLS handshake, via libpq's `_SSL_connect`, `_SSL_get1_peer_certificate` and `_X509_get_ext_d2i` plus libssl's in-process `_X509_verify_cert`; and `CVE-2026-54872` conditionally, where a client key on a generic curve is configured. The two REACHABLE findings are held only by a scope argument, which fails if the scope changes. See "B6 continued", including the retraction of a substring-matching false positive that earlier mis-attributed `_X509_verify_cert` to libpq. |
| B6 remaining: bundled libpq, Kerberos, OpenLDAP versions | **PARTLY CLOSED.** libpq **18.6** VERIFIED first-hand (`_PQlibVersion` → `0x2bf26` = 180006), OpenSSL **3.5.8** and MIT Kerberos **1.22.2** VERIFIED from their own banner strings — so CAP-001's assertions are matched. **Still OPEN:** OpenLDAP 2.6.14 is an inference from a disassembly reading, as `libldap` carries no banner; and six sibling libraries have no version of their own. |
| B6 remaining: LGPL-3.0 obligations for a distributing use | **OPEN.** Not triggered by the loopback-only scope; not assessed for any other use. |
| B7 D4.3 selection | **CLOSED** by `ADR-0006-mod004-d43-driver-selection.md`, published `eb4c8e4` with exact-SHA push CI run `42286985330` `success`. Its `Review: VR-ADR0006-20261106-003 APPROVED` is a **document-assigned label**: the reviewed bytes are hash-verifiable, while the review's performance and performer leave no `*.evidence.json` and are asserted, as that ADR itself states. That closes B7 and nothing else. |
| B3 CVE applicability | **OPEN**, but now measured rather than asserted and materially extended. **154** distinct open bookworm CVEs against the image's own SBOM, against CAP-001's **140** on the same OSV basis. The PGDG group is now assessed: the image contains `postgresql-17`/`-client-17` at 17.11, **`postgresql-18` at 18.6** and `libpq5` at **18.6**, and no row of the PostgreSQL project's 76-CVE security page lists 17 or 18 as affected above those versions — on a single primary source, with a minor release due 2026-11-12. The four Go modules are assessed: **59 stdlib advisories apply to 1.24.6** with reachability NOT ASSESSED, and `moby/sys/user` 0.1.0 is **AFFECTED** by `CVE-2026-61801` in a function gosu actually calls. Still a lower bound: the SBOM carries only `dpkg` metadata. See "B3 continued" and "B3 continued (2)". |
| B3 package licence closure | **OPEN — advanced substantially, precisely bounded, not closed.** The 188 declared SBOM values split into 46 identifiers, **45** real licences (the 46th is `NOASSERTION`); none is proprietary, non-commercial or field-of-use restricted, and **none conditions execution as such**. About fourteen condition a *held copy* on notice retention or non-misrepresentation; those duties are **verified satisfied** by the pinned image — 141 `copyright` files, 0 whiteouts under `usr/share/doc`, 17 `common-licenses` texts, 3 doc-dir symlinks resolving to present files. A **per-package pass** over those 141 files then found **126 CLOSED, 3 NOT CLOSED** (`base-passwd`, `libldap-2.5-0` on a bare undefined `public-domain` label; `libllvm19` on undefined `BSD-3-Clause`/`BSD-3-clause`, which do not resolve to `common-licenses/BSD`) **and 12 NEEDS-READING**, all named in "The per-package pass". A lexical scan of all 141 files plus ~35 local licence texts found **no use or execution restriction**; export-control notices (krb5, e2fsprogs, `libsasl2`), trademark terms (krb5) and `Sleepycat`'s redistribution condition are recorded as the nearest items. **Still not closed**, because "CLOSED" there is formal self-consistency rather than correctness, 15 of 141 are unresolved, and **57 of the 198 distinct SBOM names have no copyright file and are undetermined**. Whether this satisfies condition 1's "exact package licence closure" is for the separate condition-1 assessment, on this evidence. A distributing use is a different question, reserved under DC-16 `production-promotion`. A licence-terms reading by this session, not legal advice. |
| Publisher signature | **OPEN.** Not attempted; digests are not signatures, and an anonymous registry token authenticates nothing about the publisher. |

**Correction.** An earlier revision of this file headed B6 "VERIFIED" while this table still said
"OPEN. Needs the wheel in hand; sequenced after the pull." Both could not be true, and the
contradiction mattered because §2 condition 1 turns on whether B6 is closed. The independent B5
reviewer found it. The inventory is closed; the named remaining items are not, and they are now
listed as themselves instead of being folded into a single misleading row.
