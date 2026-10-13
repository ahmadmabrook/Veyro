---
doc: M1-C-06-WHEEL-TAG-VERSION-ARCHITECTURE
module: MOD-001
date: 2026-10-09
type: architecture decision (ARCHITECTURE_CRITICAL, bounded) — target-tag and
  version-selection reconciliation
requirement: GOV-01-R04 type-check CI stage; CAP-012 lock/install path
subgoal: M1-C-06-WHEEL-TAG-VERSION-ROOT-CAUSE
status: ROOT CAUSE PROVEN; corrected acquisition command and acceptance checks
  RECORDED — no lock generated, no capability approval, no scenario disposition
---

# M1-C-06 — Linux x86-64 / CPython 3.13 mypy wheel acquisition: target-tag root cause and version-selection contract

Status: **DECISION RECORDED. No wheel was downloaded, extracted, installed,
imported or executed; no mypy run of any kind; no lock or hash manifest
generated; no CAP-012 status, registry row, manifest binding or generator
change; no CI workflow; no remote action; no reviewer dispatched; no review
entitlement consumed or created; no scenario dispositioned; no MOD-001
certification credit.** Sole Veyro lease, operation
`336d4e46-5e45-4045-a679-82fb492522ec`, execution role
`ARCHITECTURE_CRITICAL`. Four governing baseline hashes re-verified this turn
(`backend/.venv/bin/python knowledge/00-System/verify_baselines.py`, 4/4 MATCH).
`REVIEW_IN_FLIGHT.md` read and left `CLEAR` — no review was dispatched, so no
claim was written. MOD-001 exit remains 0/8; gate-2 F01-F14 remain **14/14
CLOSED**; CAP-012 remains **QUALIFIED — NOT APPROVED**; SCN-MOD001-030/031 and
all 13 C06 scenarios remain NOT EXECUTED.

This record resolves the discrepancy recorded in
`M1-C-06-LINUX-CP313-WHEEL-ACQUISITION-BLOCK-2026-10-09.md` and **does not
re-open** any other part of
`M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md`. §1's additive stage-scoped
lock, §2's one-lock-per-stage convention, §4's platform/interpreter pinning,
§5's no-generator-change finding, §6's target-scope problem, §8's
architecture-versus-authorization separation, §9 Step B, §10's boundary and
§11.4's prohibitions all stand exactly as written.

## 0. Method and evidence basis

Everything below is derived from three classes of evidence, each named at the
point of use:

1. **Direct source reading of the pip that will run the command** — pip 26.1.1
   in `backend/.venv` (`backend/.venv/bin/python -m pip --version`;
   interpreter CPython 3.14.5, macOS arm64). Tag-selection logic read from
   `backend/.venv/lib/python3.14/site-packages/pip/_internal/utils/compatibility_tags.py`
   and `.../pip/_vendor/packaging/tags.py`; flag validation from
   `.../pip/_internal/cli/cmdoptions.py`; marker evaluation from
   `.../pip/_internal/metadata/importlib/_dists.py` and
   `.../pip/_vendor/packaging/markers.py`; constraint semantics from
   `.../pip/_internal/resolution/resolvelib/base.py` and `.../factory.py`.
2. **Local installed-distribution metadata** — `Requires-Dist` /
   `Requires-Python` read from the six `*.dist-info/METADATA` files already
   present in `backend/.venv`. No network, no execution of package code.
3. **Read-only PyPI JSON metadata** (`https://pypi.org/pypi/<name>/json`),
   fetched for `mypy`, `ast-serialize`, `librt`, `mypy-extensions`,
   `pathspec`, `typing-extensions` into `/tmp/m1c06-meta-<name>.json`. This is
   the same class of read-only reconciliation
   `M1-C-06-MYPY-LOCK-PLATFORM-RECONCILIATION-2026-10-09.md` already performed.
   **No `.whl` or `.tar.gz` file was requested or transferred.**

The pip tag computation below was executed by calling pip's own
`get_supported()` and `packaging.utils.parse_wheel_filename()` on
**filename strings from PyPI metadata** — no downloaded artifact was involved.
Per §3's standing rule, every digest in this record is **corroboration and a
falsifiable prediction only, never a generation input**; no hash here may be
transcribed into a governed lock.

## 1. Root cause — proven, not inferred

The failed command's `--platform manylinux_2_28_x86_64` is the sole cause, and
the mechanism is now exact.

**(a) pip performs no backward expansion of a PEP 600 `manylinux_x_y_arch`
platform string.** `compatibility_tags.py::_get_custom_platforms` (lines
99-111) expands only four prefixes — `macosx`, `ios`, `android`, and the
legacy `manylinux2014`/`manylinux2010` — and returns `[arch]` unchanged for
everything else. `manylinux_2_28_x86_64` partitions to `arch_prefix ==
"manylinux"`, which matches none of them, so it falls to the `else` branch.
Executed against pip's own code, `_expand_allowed_platforms` returns exactly
`['manylinux_2_28_x86_64']`. **A `--platform manylinux_2_28_x86_64` target
therefore accepts a wheel only if that wheel's own tag set literally contains
`manylinux_2_28_x86_64`.** `--platform` is not a glibc floor; it is a literal
tag-set membership test. (The same is true in the other direction:
`--platform manylinux_2_17_x86_64` expands to exactly
`['manylinux_2_17_x86_64']` and does **not** imply `manylinux2014_x86_64`.)

**(b) `ast-serialize` publishes no `manylinux_2_28_x86_64` wheel at any
version.** Across its 21 released versions, the complete set of x86-64 glibc
tag suffixes it ships is the single compressed pair
`manylinux_2_17_x86_64.manylinux2014_x86_64` (plus `musllinux_1_2_x86_64`,
which a manylinux target never matches). This holds for both the pinned
0.11.2 (56 wheels) and the current latest 0.12.1 (56 wheels).

**(c) Therefore the only ast-serialize version compatible with the 2_28 target
is 0.0.1**, whose sole wheel is `ast_serialize-0.0.1-py3-none-any.whl` — a
platform-independent wheel, which matches *any* platform target via
`py3-none-any`. That is precisely and completely pip's reported
`(from versions: 0.0.1)`. 0.0.1 does not satisfy mypy's
`ast-serialize<1.0.0,>=0.6.0`, so the resolve ends in
`No matching distribution found`.

**(d) This explains why the explicit-index retry behaved identically.** The
failure is a tag-compatibility rejection computed locally from index metadata,
not an index contents, mirror, or network problem. Adding
`--index-url https://pypi.org/simple` could not change it, and the observed
identical exit 1 corroborates the mechanism rather than merely co-occurring
with it.

**(e) Directory A staying empty is the correct consequence, not a second
fault.** pip resolves the whole closure before saving any file; a resolution
error leaves the destination untouched.

Mechanically demonstrated match/no-match for the 2_28 target, computed from
pip 26.1.1's own supported-tag list for `--python-version 3.13
--implementation cp --abi cp313` (45 tags):

| Candidate wheel | `manylinux_2_28_x86_64` target |
|---|---|
| `mypy-2.3.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | MATCH via `cp313-cp313-manylinux_2_28_x86_64` (pref idx 0) |
| `librt-0.15.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | MATCH via `cp313-cp313-manylinux_2_28_x86_64` (pref idx 0) |
| `ast_serialize-0.11.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | **NO MATCH** |
| `mypy_extensions-1.1.0-py3-none-any.whl` | MATCH via `py3-none-any` (idx 31) |
| `pathspec-1.1.1-py3-none-any.whl` | MATCH via `py3-none-any` (idx 31) |
| `typing_extensions-4.16.0-py3-none-any.whl` | MATCH via `py3-none-any` (idx 31) |

## 2. The minimum correct target tag is a single `manylinux_2_17_x86_64`

Computed from pip's own `get_supported()` against every published wheel of
each pinned version:

| Target | compiled candidates matched | tag-set size |
|---|---|---|
| `manylinux_2_28_x86_64` | mypy, librt only — **ast-serialize fails** | 45 |
| `manylinux_2_17_x86_64` | mypy, ast-serialize, librt — **all three** | 45 |
| `manylinux2014_x86_64` | all three, but pulls in `manylinux2010_x86_64` and `manylinux1_x86_64` | 103 |
| `manylinux_2_28_x86_64` + `manylinux_2_17_x86_64` (both) | all three | 74 |

**Multiple target tags are not needed, and this is the load-bearing finding.**
Adding `manylinux_2_28_x86_64` ahead of `manylinux_2_17_x86_64` changes which
*tag* is the best match for mypy and librt (`…_2_28_…` instead of `…_2_17_…`)
but **does not change which *file* is selected**, because one single published
file carries all three tags in its compressed tag set. Verified by selecting
across every published wheel of all six pinned versions: the two-tag target
and the single `manylinux_2_17_x86_64` target select the **identical six
files**, byte-identical digests. The second tag buys nothing and widens the
accepted tag set from 45 to 74.

`manylinux2014_x86_64` also resolves all three, but it is the only one of the
four options that *expands* — pip adds `manylinux2010_x86_64` and
`manylinux1_x86_64` — admitting two glibc baselines the target runner has no
need for. Rejected on CAPABILITY_POLICY's "no broader scope than the specific
gap requires" and `iac.md` control 2's least-privilege standard, consistent
with §2's reasoning for rejecting an all-tools lock.

**Decision: a single `--platform manylinux_2_17_x86_64`.** It is the only tag
common to all three compiled candidates, it is the narrowest of the four
options that resolves the closure, and it yields one uniform glibc floor
across all three compiled wheels — which matters because the generated lock
records name/version/hash and **cannot express a per-package platform
baseline** (§5's legibility shortfall). A mixed-baseline selection would be
expressible only in the `sha256sum` manifest, not in the lock.

**Runtime validity.** manylinux_2_17 requires glibc ≥ 2.17. Ubuntu 24.04
ships glibc 2.39, so these wheels are runtime-valid on the §4 runner, and
2_17 is the *lowest* floor of the four options, hence the most conservative.
Stated as a property of the manylinux specification and the Ubuntu release,
**not** as a verified observation of the GitHub runner image — the runner's
actual glibc is not inspected by this record and is not a *download*-time
property. §4's interpreter assertion, and ultimately an executed install,
remain the only things that observe the runner.

**Unique selection.** For five of six pinned packages exactly one published
wheel is compatible with the target, so selection is unambiguous. `mypy`
2.3.1 has two compatible wheels — the compiled `cp313-cp313-manylinux…` at
preference index 0 and the universal `mypy-2.3.1-py3-none-any.whl` at index
31 — so pip strictly prefers the compiled wheel. This answers the *selection*
half of §7 material unknown 5 (the universal wheel will not be chosen) without
touching the open question of whether it *could* substitute, which this record
does not reopen.

## 3. Name-set versus version-set — they are different problems with different answers

### 3.1 The name-set is correct and closed at six. No seventh package exists.

Read directly from the installed `mypy-2.3.1.dist-info/METADATA`, mypy 2.3.1's
complete non-extra `Requires-Dist` set is:

```text
typing_extensions>=4.6.0; python_version < "3.15"
typing_extensions>=4.14.0; python_version >= "3.15"
mypy_extensions>=1.0.0
pathspec>=1.0.0
tomli>=1.1.0; python_version < "3.11"
librt>=0.13.0; platform_python_implementation != "PyPy"
ast-serialize<1.0.0,>=0.6.0
```

Evaluated under a synthesized Linux/cp313 marker environment, the retained set
is `{typing-extensions, mypy-extensions, pathspec, librt, ast-serialize}` —
`tomli` is excluded (3.13 ≥ 3.11) and the 3.15 `typing_extensions` line is
excluded. Each of those five distributions' own installed `METADATA` carries
**zero** non-extra `Requires-Dist` (pathspec has three, all extras-gated:
`hyperscan`, `optional`, `re2`). The closure is therefore closed at exactly
the **six names already on record** — `mypy`, `ast-serialize`, `librt`,
`mypy-extensions`, `pathspec`, `typing-extensions` — with no seventh package
and no sdist-only member. **§7 material unknown 3 is answered, by metadata
reading rather than by the download.**

### 3.2 A correction to §3's stated rationale for omitting `--no-deps`

§3 justifies resolving dependencies rather than passing `--no-deps` "precisely
so that a 3.13/Linux environment-marker difference cannot hide a seventh
package." **The mechanism does not provide that property**, and a future
reader must not rely on it for a different package set.

pip evaluates `Requires-Dist` markers as `req.marker.evaluate({"extra": …})`
(`metadata/importlib/_dists.py` lines 224-235). `packaging.markers.Marker.evaluate`
builds `current_environment` from `default_environment()` — the **running**
interpreter — and then overrides only the keys explicitly passed. pip passes
only `extra`. Therefore `python_version`, `python_full_version`,
`platform_python_implementation`, `sys_platform` and `platform_machine` are
all taken from the macOS / CPython 3.14.5 / arm64 host, **not** from
`--python-version 3.13 --implementation cp --platform manylinux_2_17_x86_64
--abi cp313`. Those four flags affect **wheel tag compatibility only**. A
cross-target `pip download` consequently cannot detect a target-environment
marker difference at all.

For *this* closure the outcome is nonetheless correct, and that was verified
rather than assumed: evaluating all seven `Requires-Dist` lines under the real
host environment (`python_version='3.14'`,
`platform_python_implementation='CPython'`, `sys_platform='darwin'`,
`platform_machine='arm64'`) and under a synthesized target environment
(`'3.13'`, `'CPython'`, `'linux'`, `'x86_64'`) produces the **identical**
five-name result. Both markers are insensitive to the difference: `3.14 < 3.11`
and `3.13 < 3.11` are both false, and `CPython != "PyPy"` is true in both. The
name-set is right for a reason this record states explicitly, instead of being
right for a reason §3 credited to the wrong mechanism.

### 3.3 The version-set does drift, in two packages, and current PyPI selection is correct

| Package | Precedent pin (`requirements-dev.lock.txt`, CAP-012 row) | PyPI latest today | Unconstrained resolve today |
|---|---|---|---|
| mypy | 2.3.1 | 2.4.0 | 2.3.1 — explicitly pinned on the command line |
| ast-serialize | 0.11.2 | **0.12.1** | **0.12.1 — drift** |
| librt | 0.15.0 | **0.16.0** | **0.16.0 — drift** |
| mypy-extensions | 1.1.0 | 1.1.0 | 1.1.0 |
| pathspec | 1.1.1 | 1.1.1 | 1.1.1 |
| typing-extensions | 4.16.0 | 4.16.0 | 4.16.0 |

**No requirement that current PyPI selects historical versions by default is
asserted anywhere in this record, and none exists.** pip correctly selects the
newest version satisfying an unconstrained specifier. `librt 0.16.0` was the
*right* answer to the command as written (`librt>=0.13.0`), not a resolver
fault; `librt 0.15.0` is simply what was newest when
`backend/requirements-dev.lock.txt` was generated. The observed-0.16.0
divergence is a time effect, and the precedent six-version set is not
reproducible from an unconstrained command at any later date.

**The failure masked a second drift.** Because ast-serialize never resolved,
the block record could only observe the librt discrepancy. With the tag
corrected, an unconstrained resolve would also move ast-serialize 0.11.2 →
0.12.1. Two of six pins drift, not one. The remaining three transitives happen
to be at PyPI-latest today, so they show no drift — a time-dependent
coincidence, not a property to rely on.

### 3.4 Freeze the version-set with a constraints file — versions only, no hashes

**Decision: pass exact `==` pins for the five transitive packages through a
pip constraints file (`-c`), keeping `mypy==2.3.1` as the sole requirement on
the command line.**

Why freeze at all, rather than accept the resolver's current selection:

1. **CAP-012's registry row names its closure by exact version** — "ast-serialize
   0.11.2, librt 0.15.0, mypy_extensions 1.1.0, pathspec 1.1.1,
   typing_extensions 4.16.0". A Linux lock carrying 0.12.1/0.16.0 would make
   that row's own closure statement false for the artifact the stage installs,
   forcing a registry edit that §9's hard prohibitions and §11.4(3) forbid and
   that this operation is barred from making.
2. **§2's drift-detection convention only has value if a fresh lock starts
   drift-free.** §2 discloses lock proliferation's cost and relies on the
   mitigation that "every lock's versions are derived from the same
   `backend/pyproject.toml` / `requirements-dev.txt` intent, so drift is
   mechanically detectable by comparing `name==version` sets." A new lock born
   two versions apart from its sibling makes that comparison report drift on
   day one and defeats the mitigation.
3. **§3's two-independent-acquisitions control is not time-robust without
   pins.** If a new librt or ast-serialize release lands between acquisition A
   and acquisition B, directory B legitimately differs and `check` fails —
   indistinguishable from the non-reproducibility the control exists to detect.
   Exact pins make A and B compare only what the control is actually about.

Why a **constraints file** specifically, rather than naming all six packages as
requirements on the command line:

- pip's `Constraint` (`resolution/resolvelib/base.py`) is a pure filter:
  `specifier` / `hashes` / `links`, applied via
  `Constraint.is_satisfied_by(candidate)` during candidate selection
  (`factory.py` line 521), and looked up **by project name**. A constraint for
  a package that is never required is never consulted. **A constraints file
  cannot add a requirement to the closure.**
- Therefore **§3's closure-discovery control survives exactly**: `mypy==2.3.1`
  remains the only requirement, the closure is still discovered rather than
  declared, and a hypothetical seventh package would still resolve
  *unconstrained* and still appear as a new, visible name. Naming all six as
  requirements would instead conflate "what was requested" with "what was
  discovered" — losing the very distinction §3 built the control around.
- The failure mode also improves. Under §3 as written, a version divergence is
  something a human must notice in the materialized filenames and then stop on.
  Under exact constraints, a version that is no longer obtainable for the
  target becomes a **hard pip resolution error** — loud, non-silent, and
  fail-closed by construction rather than by vigilance. In particular, the
  silent-downgrade hazard (a future librt whose newest release drops the
  `manylinux_2_17_x86_64` tag, causing a single-tag target to quietly select an
  older version) cannot occur: with `librt==0.15.0` pinned, a tag mismatch is a
  resolution failure, not a downgrade.

**The constraints file carries versions only. It must contain no `--hash`
lines.** pip's `Constraint` does accept `hashes` and `hash_options`, so hashes
placed in a constraints file become a **selection input** to the resolver.
That would violate §3's standing rule that "metadata is a check input, never a
generation input" and would route PyPI digests into the artifact-selection
path the generated lock depends on. Versions are already independently
recorded in `requirements-dev.lock.txt` and in CAP-012's registry row;
digests are not, and must continue to be derived only by `hashlib.sha256` over
real downloaded bytes inside `tools/generate_requirements_lock.py`.

Exact content for the constraints file (five lines, no hashes, no extras, no
markers, no editable entries — all of which pip's
`check_invalid_constraint_type` would reject or which would exceed this
decision's scope):

```text
ast-serialize==0.11.2
librt==0.15.0
mypy-extensions==1.1.0
pathspec==1.1.1
typing-extensions==4.16.0
```

## 4. The declined flag-combination prediction is now answered by observation

§11.3 explicitly declined to predict whether pip accepts
`--platform` / `--python-version` / `--implementation` / `--abi` **together
with** dependency resolution (no `--no-deps`). It does, and this is settled by
both source and observation:

- `cli/cmdoptions.py::check_dist_restriction` raises `CommandError` when any of
  those four options is set **unless** either `--no-deps` is set **or**
  `--only-binary=:all:` is set with no conflicting `--no-binary`. The failed
  command carried `--only-binary=:all:`, so the invocation is legal.
- The observed failure corroborates it: pip proceeded past argument validation,
  resolved mypy 2.3.1's metadata and its dependency specifiers, and failed
  *inside* resolution on `ast-serialize`. An argument-validation rejection
  would have produced a `CommandError` before any candidate was considered.

So §11.3's stop-and-record condition for that specific risk does not fire, and
`--no-deps` must still **not** be added — it would discard the closure
discovery §3 depends on.

## 5. Exact, reviewable A/B acquisition command

Not executed by this record. Three distinct paths are used so that the two
download destinations stay pure and empty for the generator's
"every wheel appears exactly once" guard, and so that the constraints file —
a file this session authors — never shares a directory with untrusted
downloaded content:

```bash
# --- fresh paths, all outside the repository tree ---
CDIR="$(mktemp -d /tmp/m1c06-typecheck-constraints.XXXXXX)"   # inputs only
DIR_A="$(mktemp -d /tmp/m1c06-typecheck-a.XXXXXX)"            # download A, must stay pure
DIR_B="$(mktemp -d /tmp/m1c06-typecheck-b.XXXXXX)"            # download B, must stay pure

cat > "$CDIR/typecheck-linux-cp313.constraints.txt" <<'EOF'
ast-serialize==0.11.2
librt==0.15.0
mypy-extensions==1.1.0
pathspec==1.1.1
typing-extensions==4.16.0
EOF

# --- acquisition A (then identically for B with --dest "$DIR_B") ---
env -u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL -u PIP_FIND_LINKS \
    -u PIP_NO_INDEX -u PIP_TARGET -u PIP_PREFIX -u PIP_CONSTRAINT \
    PIP_CONFIG_FILE=/dev/null \
  backend/.venv/bin/python -m pip download \
    --only-binary=:all: \
    --platform manylinux_2_17_x86_64 \
    --python-version 3.13 --implementation cp --abi cp313 \
    --index-url https://pypi.org/simple \
    --no-cache-dir --no-input --disable-pip-version-check \
    -c "$CDIR/typecheck-linux-cp313.constraints.txt" \
    --dest "$DIR_A" \
    mypy==2.3.1
```

Exactly four things changed relative to the failed command: the platform tag
(`manylinux_2_28_x86_64` → `manylinux_2_17_x86_64`), the added constraints
file, the explicit index plus cleared `PIP_*`/`PIP_CONFIG_FILE` hardening
already required by §4 for the install step, and the determinism flags. `mypy`
remains the sole requirement, `--no-deps` is **not** added, and
`--only-binary=:all:` is retained (both required — see §4 above).

Generator invocation is unchanged from §11.3's hardening, with the wheel
directory passed **as an argument** and the interpreter never launched from
inside it:

```bash
backend/.venv/bin/python -I tools/generate_requirements_lock.py \
  generate "$DIR_A" backend/requirements-typecheck-linux-x86_64-cp313.lock.txt
backend/.venv/bin/python -I tools/generate_requirements_lock.py \
  check    "$DIR_B" backend/requirements-typecheck-linux-x86_64-cp313.lock.txt
```

## 6. Expected acceptance checks, to be run before any lock generation

These are **predictions from read-only metadata, stated so they can be
falsified by the download.** Per §3's observe-never-predict rule, a mismatch
is a stop-and-record condition returning to this record, and **no digest below
may be transcribed into the generated lock.**

**AC-1 — exit status.** Both acquisitions exit 0.

**AC-2 — materialized filenames.** Each of `$DIR_A` and `$DIR_B` contains
**exactly these six files and nothing else**:

| # | Expected filename | Expected SHA-256 (corroboration only) |
|---|---|---|
| 1 | `mypy-2.3.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `1c80fbc405ed8020f5ff3802dc18cf060197bcdd3fbdd6a26ef2fd34dfdd5226` |
| 2 | `ast_serialize-0.11.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | `a7004ba572f09be34342ccb98dcd4bad5707d3d81adc8cb4c3f685d2a2c51bbc` |
| 3 | `librt-0.15.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl` | `234d8d394721fa0d786af15ebf1f3fb7f3ed82fd1cd0cde45c2f247b5d4281d2` |
| 4 | `mypy_extensions-1.1.0-py3-none-any.whl` | `1be4cccdb0f2482337c4743e60421de3a356cd97508abadd57d47403e94f5505` |
| 5 | `pathspec-1.1.1-py3-none-any.whl` | `a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189` |
| 6 | `typing_extensions-4.16.0-py3-none-any.whl` | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` |

Rows 1-3 are the three Linux candidates
`M1-C-06-MYPY-LOCK-PLATFORM-RECONCILIATION-2026-10-09.md` already enumerated,
with digests unchanged from that record — an independent second agreement.
Rows 4-6 are platform-independent and their digests are **identical to lines
10, 20 and 34 of the existing `backend/requirements-dev.lock.txt`**, which
yields a useful review property: the new Linux lock must agree with the
existing macOS lock on exactly three of six lines, and differ on exactly
three (`mypy`, `ast-serialize`, `librt`). No `.whl` is yanked.

**AC-3 — no `.tar.gz` and no seventh package.** `--only-binary=:all:` makes an
sdist arrival impossible; any seventh name is a §3 stop condition (and per
§3.1 above, none is expected).

**AC-4 — name-set and version-set both match.** Parsed `name==version` set
equals the six rows above. The name-set must equal CAP-012's recorded closure;
the version-set must equal `requirements-dev.lock.txt`'s mypy-closure pins.
These are checked as **two separate assertions**, per §3.3.

**AC-5 — A and B agree.** `sha256sum *.whl` manifests from both directories,
sorted, are byte-identical to each other, and each line agrees with AC-2.

**AC-6 — generator outcomes.** `generate` against `$DIR_A` writes six entries
to `backend/requirements-typecheck-linux-x86_64-cp313.lock.txt`; `check`
against `$DIR_B` exits 0.

**AC-7 — nothing else moved.** `backend/requirements-dev.lock.txt`
byte-unchanged; `tools/generate_requirements_lock.py` byte-unchanged; no file
inside `$DIR_A`/`$DIR_B` extracted, imported, installed or executed; no
`pip install`; no mypy run.

**AC-8 — negative control for the root cause (optional, zero-download).** Pip's
tag computation can be re-derived locally with no network and no download, to
re-confirm that `ast_serialize-0.11.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`
is incompatible with a `manylinux_2_28_x86_64` target and compatible with a
`manylinux_2_17_x86_64` one. This is the mechanical restatement of §1 and is
cheap enough to include as evidence.

## 7. Narrow correction required to the pre-existing decision record

**Yes — two items, both narrow, both aimed only at preventing a stale command
from reading as live authorization.** Recorded here and, per the instruction
bounding this operation's tracked writes, applied to
`M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md` as an additive §12 pointer
that marks the affected text superseded in place rather than rewriting it —
the same convention §11 itself used.

1. **§3's compressed-tag sentence is factually wrong and is the proximate
   cause of the failed command.** It states that `manylinux_2_17_x86_64`,
   `manylinux2014_x86_64` and `manylinux_2_28_x86_64` "all resolve to the same
   two files, which removes most of the fragility in the `--platform` choice."
   That holds for mypy and librt and is **false for ast-serialize**, which
   carries no `manylinux_2_28_x86_64` tag at any version. The three tags are
   not interchangeable, and the `--platform` choice is precisely where the
   fragility lives. §3's accompanying duty-to-check sentence was correct and is
   what caught this.
2. **The `--platform manylinux_2_28_x86_64` command shape in §3, §11.3(1) and
   §11.5 is known-failing and must not be re-run.** It is superseded by §5 of
   this record. §11.5's "smallest next action" otherwise stands unchanged in
   sequence and outputs; only its command text and its unconstrained
   version-resolution assumption are corrected.

Additionally recorded, as a rationale correction rather than a decision change:
§3's basis for omitting `--no-deps` (§3.2 above) is not the property pip
provides, though its conclusion — resolve rather than `--no-deps` — remains
correct, and §7 material unknown 3 is now answered from metadata.

Nothing else in that record is amended. §4's `manylinux_2_28`-independent
interpreter/platform assertions, §9 Step B's ten requirements, and §11.4's
eight prohibitions are untouched.

## 8. Technical question for the orchestrator

Not an owner decision and not a blocker — a scope question about tracked
artifacts, raised because this operation's tracked writes are capped at two
files and cannot settle it:

> Should `typecheck-linux-cp313.constraints.txt` become a **committed**
> artifact (e.g. `backend/`-local, alongside the new lock) so a future
> reviewer can reproduce the acquisition from the repository alone, or is it
> sufficient that its exact five-line content is recorded verbatim in §3.4 of
> this record and its effect is observable in the generated lock's
> `name==version` set?

Recommendation: committed eventually, for the same reproducibility reason §3
requires a committed `sha256sum` manifest; but the lock-generation operation
can proceed with a scratch-path constraints file without blocking, since the
content is fully specified here. Either way it is a *new* tracked file and
therefore the lock-generation operation's scope, not this one's.

## 9. Next legal action

One bounded in-session operation performing **§3 / §9 Step A as corrected by
§5 and §6 of this record**: write the §3.4 constraints file to a fresh
out-of-repository input directory; two `pip download` runs per §5 into two
fresh empty out-of-repository directories A and B; evaluate AC-1 through AC-5;
only if all pass, `generate` against A to
`backend/requirements-typecheck-linux-x86_64-cp313.lock.txt` and `check`
against B (AC-6); two `sha256sum` manifests diffed against each other and
against §6's table; AC-7 re-verified; all observations recorded in a new dated
evidence file.

**No install. No mypy run. No workflow authored. No registry, manifest, plan,
or `requirements-dev.lock.txt` change.** Any divergence from §6 stops the
operation and returns to this record rather than being locked in. §9 Step B
(the `veyro-infra-sre-engineer` workflow authoring) still follows Step A and is
unchanged.

## 10. Boundary — what is explicitly not claimed

No PASS of any kind; no scenario executed, promoted or dispositioned.
SCN-MOD001-030 and SCN-MOD001-031 and all 13 C06 scenarios remain NOT
EXECUTED. MOD-001 exit remains 0/8; gate-2 F01-F14 remain 14/14 CLOSED; the
P2-4 approval/assurance hold is preserved unchanged.

No APPROVED of any kind. CAP-012 remains **QUALIFIED — NOT APPROVED**,
`lifecycle_status` not ACTIVE, no reliance of any kind permitted;
`validate_capabilities.py` is still expected to report
`CAPABILITY_NOT_APPROVED`, which is the intended fail-closed hold. §8 of the
architecture record stands in full, including this worker's structural
disqualification from being CAP-012's independent reviewer. CAP-008, CAP-010
and CAP-011 are untouched. No capability registry row, manifest binding,
`lifecycle_status`, `approved_by` or `approved_date` is created or altered.

No GOV-01-R03 or GOV-01-R04 acceptance criterion is closed; the
non-bypassable blocking-gate criterion specifically is not addressed. The
C2/N5 same-name candidate-spoof residual stays open and untouched. §6's
target-scope problem and §7's material unknowns 1, 2, 4, 6 and 7 are untouched
and remain open; unknowns 3 and (for selection only) 5 are answered above.

No review entitlement consumed or created; `REVIEW_IN_FLIGHT.md` left `CLEAR`;
no reviewer dispatched. No plan operation incremented. No generator, workflow,
`pyproject.toml`, `requirements-dev.txt`, `requirements-dev.lock.txt` or
harness file modified. No `uses:` line, required status context or
branch-protection change. The single writer lease is preserved.

The four owner-reserved absolute restrictions are untouched and not
implicated: this operation performed read-only HTTPS metadata requests to
PyPI only — no spend or paid service, no real member data, no Production
action, no deploy, and no remote mutation of any kind.
