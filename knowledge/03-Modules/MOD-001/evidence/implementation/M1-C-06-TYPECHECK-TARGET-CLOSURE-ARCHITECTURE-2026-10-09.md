# M1-C-06 — Typecheck Target Closure Architecture (backend/app under strict mypy)

Date: 2026-10-09
Operation: M1-C-06 (guarded Opus ARCHITECTURE_CRITICAL, write-first recovery after
the prior subgoal `M1-C-06-TYPECHECK-TARGET-CLOSURE-ARCHITECTURE` soft-stopped with
no file written).
Scope: architecture decision only. No mypy was run against any Veyro path in this
call, no synthetic probe was executed, no code/test/workflow/lock/registry edit was
made, and no capability or scenario disposition was changed.

> **CORRECTION NOTICE — 2026-10-09, later guarded Opus ARCHITECTURE_CRITICAL call
> (subgoal `M1-C-06-DECISION-CONTRADICTION-CORRECTION`).** §§2–6 below are retained
> verbatim as history. The **Option B selection in §3 is SUPERSEDED**, and the §5
> scope-requalification requirement it induced is **moot**, because §3 rested on four
> factual errors now corrected in **§8**. The governing decision is **§9 (Option A —
> keep the exact `backend/app` directory target)**, with one named residual marked
> **DECISION_BLOCKED** in §10 and the next substep restated in §7. This record is
> architecture, not approval: **CAP-012 remains QUALIFIED NOT APPROVED**, no mypy has
> run against any Veyro source, no CI live run has occurred, and no scenario or gate is
> PASS. No file other than this record was edited by the correcting call.

## 1. Governance state preserved (unchanged by this record)

- **CAP-012 remains QUALIFIED NOT APPROVED.** No real Veyro file may be typechecked
  under the gate until CAP-012 reaches `APPROVED`, which requires a **fresh,
  independent, qualified Opus `veyro-security-reviewer` determination** evaluating the
  Sonnet-produced qualification evidence in a fresh context — *not* an owner sign-off
  (corrected; see §8 item 4 and `CAPABILITY_POLICY.md` "Model-routing interaction").
  (`knowledge/00-System/CAPABILITY_REGISTRY.md`, CAP-012 row;
  `M1-C-06-QUALIFIED-CAP-DRAFT-2026-10-09.md`.)
- **R04 gate-2 closure is NOT claimed or advanced** by this decision.
- **SCN-070 remains capped**; no scenario is marked PASS.
- All prior synthetic evidence (`M1-C-06-MYPY-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
  `M1-C-06-SYNTHETIC-TYPECHECK-CI-AUTHORING-2026-10-09.md`) is **synthetic-fixture
  output only** and is explicitly *not* real-code gate evidence.

## 2. Verified target inventory (re-verified this call, `find backend/app -name '*.py'`)

23 `.py` files, partitioned exactly:

- **10 non-test files**: `app/__init__.py`, `app/modules/__init__.py`,
  `app/modules/_shared/__init__.py`, `app/modules/_shared/tenant_context.py`, and the
  six module packages' `__init__.py` (`access`, `booking`, `ledger`, `membership`,
  `payment`, `pos`).
- **13 test-tree files**: `app/modules/conftest.py`, six `*/tests/__init__.py`, and six
  `*/tests/test_scaffold_live.py`.

Carried forward from the prior call (not re-inspected here, per the no-repeat
constraint): `app/modules/conftest.py` imports `psycopg`, `pytest`,
`tests.harness.postgres`, and `tests.harness.tenant_context`; the nested
`test_scaffold_live.py` files also import the harness. The `tests.harness.*` package
lives **outside** the `backend/app` package root — that is the origin of the
"outside-package" error observed in the Stage-5 disposable probe (2 errors, 8 source
files checked), versus the explicit production-only list which returned success.

## 3. Decision — Option B selected: explicitly narrowed target + dynamic fail-closed inventory guard — **SUPERSEDED, see §8/§9**

> Retained verbatim as history. Rationale items 2, 3 and 4 below are factually wrong;
> see §8. The governing decision is §9.

**Selected:** narrow the strict-mypy target from the directory `backend/app` to the
non-test production file set, enforced by a **dynamic, fail-closed inventory guard**
that re-enumerates `backend/app/**/*.py` at gate time and exits non-zero if any file is
neither typechecked nor matched by a declared, reviewed exclusion manifest. Flag
**CAP-012 scope requalification** (see §5).

**Rejected:** Option A (keep the directory target and resolve every imported
package/harness transitive without suppression). Rationale:

1. **External code boundary.** A directory target pulls `conftest.py` and the six
   nested scaffold tests into the closure, and through them `psycopg` and `pytest`.
   Resolving those without suppression means admitting third-party type surfaces into
   a gate whose R04 purpose is to constrain *Veyro* code. Suppression would make the
   gate non-fail-closed; non-suppression enlarges the trusted surface.
2. **Outside-package harness.** `tests.harness.*` is not reachable as a package member
   of `backend/app`; making it resolvable requires either a path/namespace
   reconfiguration or a second package root — an architectural change to the test
   layout, not a gate-configuration change.
3. **Linux lock implication.** The current Linux cp313 additive mypy-only six-wheel
   lock is A/B verified but **does not pin `psycopg`, `pytest`, or their closure**
   (`M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION-2026-10-09.md`;
   `M1-C-06-MYPY-CI-LOCK-ARCHITECTURE-2026-10-09.md`). Option A therefore requires a
   new, unverified lock expansion, re-entering the acquisition problem already recorded
   as blocked in `M1-C-06-LINUX-CP313-WHEEL-ACQUISITION-BLOCK-2026-10-09.md`. Option B
   requires **no lock change at all**.
4. **Non-vacuity is preserved without it.** Narrowing still typechecks 10 real files,
   four of which carry content beyond package markers' trivial surface
   (`_shared/tenant_context.py` in particular). The gate is not vacuous.

**Why the guard, not the list, is the fail-closed element.** The prior call's
disposable drift probe demonstrated that a *frozen* explicit list silently misses a
newly added production file — which is the one real defect of Option B. The guard
neutralizes exactly that: the list is an output of enumeration plus an explicit
exclusion manifest, never a hand-maintained constant, and an unclassified file is a
hard failure rather than a silent omission.

## 4. Pins that this record does not invent

No psycopg/pytest/closure pin is asserted here. If Option A is ever revisited, the
**deterministic acquisition/verification method** is the one already recorded in
`M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION-2026-10-09.md` and
`M1-C-06-UPSTREAM-PROVENANCE-PINS-2026-10-09.md`: resolve the exact cp313
manylinux wheel tags from the upstream index metadata, take sha256 values from that
metadata rather than transcribing them, A/B verify the additive lock in the trusted CI
runner, and only then extend the lock. Hand-written hashes are not acceptable.

## 5. CAP-012 scope requalification (required, not performed here) — **MOOT, see §9**

> Retained as history. §9 keeps the declared `backend/app` target unchanged, so the
> scope deviation this section was raised to cover no longer exists. CAP-012 still
> needs its ordinary independent Opus approval (§8 item 4) — that is unrelated to
> scope requalification.

CAP-012's declared intended target is **exactly `backend/app` under strict mypy**.
Option B makes the effective target a dynamically-derived subset of that directory.
That is a material deviation from the declared capability scope and therefore requires
**scope requalification of CAP-012 before any approval**, with the narrowed target and
the guard's exclusion manifest named explicitly in the qualification record. This
record flags that requirement; it does not satisfy it. CAP-012 stays QUALIFIED NOT
APPROVED.

## 6. Remaining empirical unknowns (all untested — no Veyro-path mypy has ever run)

1. Whether the 10 non-test files are clean under strict mypy from the real repo root —
   never executed; the "success in five" result came from a disposable synthetic copy,
   not these paths.
2. Whether any *non-test* file transitively imports `tests.harness.*` or `psycopg`
   (i.e. whether the external boundary survives narrowing at all) — unverified.
3. The concrete strict-mode error classes `_shared/tenant_context.py` will produce.
4. Whether `follow_imports` default behaviour on Linux cp313 under the locked mypy
   matches the locally observed darwin behaviour.
5. Whether the exclusion manifest can be expressed without any per-file
   `type: ignore` — required for fail-closed status.

## 7. Next bounded substep (one, Sonnet tier) — **SUPERSEDED, see §11**

> Retained as history. The inventory-guard script described here exists only to serve
> Option B's narrowed file list; §9 keeps the directory target, so the guard is not the
> next substep. §11 states the corrected substep.

Author — do **not** run against Veyro paths, do **not** wire into any workflow — a
standalone inventory-guard script plus its unit test over synthetic fixtures only:
enumerate `backend/app/**/*.py`, partition each path against a declared exclusion
manifest, print the resulting typecheck file list, and exit non-zero on any
unclassified path or on an empty typecheck list. Deliverable is the script, its
synthetic-fixture test, and the drift-detection assertion. Out of scope for that
substep: mypy invocation on Veyro paths, lock edits, CI workflow edits, CAP-012
approval, scenario disposition.

## 8. Factual corrections to §§1–3 (2026-10-09 correcting call)

1. **"Four of [the 10 non-test files] carry content beyond package markers" (§3
   rationale 4) is false.** An AST inventory of the 10 non-test `backend/app` files
   shows **9 empty `__init__.py` package markers** and exactly **one** file containing
   any import or statement: `app/modules/_shared/tenant_context.py`. Combined with
   CAP-012's own Stage-5 finding that *a vacuous package (only an empty `__init__.py`)
   exits 0* (`CAPABILITY_REGISTRY.md`, CAP-012 scope cell), Option B's effective gate
   would typecheck **one meaningful file** while excluding the 13 test-tree files that
   sit inside CAP-012's declared `backend/app` target. §3's non-vacuity claim does not
   hold.
2. **"`tests.harness.*` is not reachable … requires an architectural change to the
   test layout" (§2 closing sentence, §3 rationale 2) overstates the evidence.** The
   prior disposable mypy directory probe **successfully followed an outside-package
   `outside_pkg/harness` import and reported that file's type error**. That
   demonstrates such imports are followed and their errors surfaced — it does **not**
   establish that `tests.harness` is unresolvable, nor that any layout change is
   required. What actually remains open is narrower and is isolated in §10.
3. **"Option B requires no lock change at all" (§3 rationale 3) is an unsupported
   unconditional.** §6 unknown 2 of this same record concedes that whether any
   *non-test* file transitively imports `tests.harness.*` or `psycopg` is unverified —
   and item 1 above shows the single content-bearing non-test file does carry imports
   whose targets have not been enumerated. A lock-neutrality claim cannot be stated
   unconditionally while its own premise is untested.
4. **"approved by the owner" (§1) names the wrong authority.** Per
   `CAPABILITY_POLICY.md` "Model-routing interaction" (binding operating model), a
   capability may read `APPROVED` only on a **fresh, independent, qualified Opus
   `veyro-security-reviewer` determination** that evaluates the Sonnet-produced
   evidence in a fresh context without re-running the tests, recorded in `approved_by`
   / `approved_date`. Owner approval is a separate axis (owner-reserved restrictions)
   and is not a substitute. §1 is corrected in place.

## 9. Corrected decision — Option A: keep the exact `backend/app` directory target (23 files)

**Selected.** The R04 type-check gate keeps CAP-012's declared target verbatim: the
single directory `backend/app`, all 23 `.py` files, invoked exactly as the registry
already declares — cwd `backend`, cleared environment with no `MYPYPATH`/`MYPY_*`,
`--config-file pyproject.toml --cache-dir=/dev/null --no-color-output app`, with `app`
`realpath`-checked to equal `backend/app`, and `[tool.mypy]` key set equal to exactly
`python_version` and `strict`. **Errors arising from followed imports are accepted as
fail-closed gate failures to be fixed in Veyro code or resolved by locked
dependencies — never suppressed.** No `type: ignore`, no `ignore_missing_imports`, no
`exclude`, `files`, `follow_imports`, `ignore_errors` or per-module override is
introduced; each of those independently fails CAP-012's wrapper by its declared
key-set rule.

Grounds, after §8:

1. **Minimum governance surface.** Option B simultaneously breaks three declared
   CAP-012 invariants — the single `realpath`-checked directory target, the frozen
   two-key config, and the pass condition `N` = expected `.py` count under
   `backend/app` (23). It would require redesigning the wrapper contract *and* a scope
   requalification (§5) before CAP-012 has had its first independent approval at all.
   Option A requires neither: the capability's declared scope and the gate's effective
   scope stay identical.
2. **The gate stays non-vacuous on the real tree.** 23 files versus one meaningful
   file (§8 item 1). A gate that passes because nine of its ten inputs are empty files
   is not an enforcement mechanism.
3. **Fail-closed is preserved by construction, not by an added guard.** Option B needed
   a dynamic inventory guard plus a reviewed exclusion manifest purely to re-create the
   drift resistance a directory target has inherently. Removing the guard removes a
   whole component — and with it §6 unknown 5 (whether the manifest could be expressed
   without per-file `type: ignore`), which is now moot.
4. **Third-party closure is a lock problem, handled additively and deterministically.**
   `psycopg` and `pytest` enter the closure through `app/modules/conftest.py` and the
   six nested `test_scaffold_live.py`. The resolution route is a **deterministic,
   A/B-verified, additive Linux cp313 lock expansion covering the real third-party
   imports only**, using the method already recorded in §4 — resolve exact cp313
   manylinux wheel tags and sha256 values from upstream index metadata rather than
   transcribing them, A/B verify in the trusted CI runner, then extend the lock. **No
   pin is invented, asserted or assumed here**. The earlier six-wheel acquisition
   block was resolved by the corrected tag/version route and A/B-verified lock in
   `M1-C-06-LINUX-CP313-TYPECHECK-LOCK-ACQUISITION-2026-10-09.md`; acquisition of
   additional imported-package wheels remains unperformed. Accepting that work is
   strictly cheaper than narrowing the gate to one file and re-opening capability scope.

Unchanged by this decision: CAP-012 stays **QUALIFIED NOT APPROVED**; R04 gate-2
closure is not claimed or advanced; SCN-070 stays capped; no mypy has run against any
Veyro path; no CI live run has occurred.

## 10. Residual — `DECISION_BLOCKED` on one named implementation fact

§9 fixes the route. One implementation-level fact must be checked before the gate can
be wired, and this record asserts no preference on its outcome.

**DECISION_BLOCKED — exact fact to check:** under cwd `backend`, no `MYPYPATH`/`MYPY_*`,
`[tool.mypy]` restricted to `{python_version, strict}`, and the single directory target
`app`, does mypy resolve `tests.harness.postgres` / `tests.harness.tenant_context`
(imported by `app/modules/conftest.py` and the six nested `test_scaffold_live.py`) via
the implicit source root obtained by walking up past `app/__init__.py`, or does it emit
an unresolved-import error that cannot be cleared without a forbidden config key
(`mypy_path`), a forbidden environment variable (`MYPYPATH`), or relocating the
harness?

**Minimum deterministic probe (synthetic only, not performed here).** In a disposable
OS-temp tree with no Veyro file read or typechecked, build the *synthetic analogue of
the real nested `backend/app` layout* that CAP-012's registry row already lists as a
remaining dependency: `<root>/app/__init__.py`, `app/modules/__init__.py`,
`app/modules/_shared/__init__.py`, six module packages each with `__init__.py`,
`tests/__init__.py` and one test module, an `app/modules/conftest.py` importing
`tests.harness.<mod>`, and a sibling `<root>/tests/harness/` whose module carries one
deliberate type error. Run the exact CAP-012 CLI from cwd `<root>` in **two variants
only** — A: `<root>/tests/__init__.py` present; B: absent — and record for each (i) rc,
(ii) the reported `N source files`, (iii) whether the harness defect surfaces as a
*followed-import type error* or as an *unresolved-import error*. No third-party package
is installed, no lock is touched, no Veyro path is passed, tree removed afterwards.

**Branch consequences, decided in advance so the probe is dispositive:**
- *Resolves (either variant):* harness type errors are ordinary Veyro-code failures,
  routed to `veyro-test-author` / `veyro-critical-engineer` by slice; record the
  actual reported `N` and compare it to the 23 direct target files without assuming
  followed imports contribute to that count; no config or layout change.
- *Does not resolve:* the only two admissible responses are (a) relocating
  `backend/tests/harness` inside a single source root — a test-layout change needing
  its own recorded decision, not a gate-configuration tweak — or (b) accepting the
  unresolved-import error as a standing fail-closed blocker. Clearing it with
  `mypy_path`/`MYPYPATH` or any suppression is **not** admissible.

Also still open from §6 and unaffected: whether `_shared/tenant_context.py` and the
real 23-file tree are clean under strict mypy (never executed), the concrete strict-mode
error classes it produces, and whether Linux cp313 followed-import behaviour under the
locked mypy matches the locally observed darwin behaviour.

## 11. Corrected next bounded substep (one, Sonnet tier)

Author and execute the **§10 two-variant synthetic nested-layout drill** — the probe
specified above, in a disposable OS-temp tree, against synthetic fixtures only, which
is permitted solely as CAP-012 qualification-drill work (`CAPABILITY_POLICY.md`: drills
are the only context in which an unapproved capability may be touched, and only against
synthetic fixtures). Deliverable: the fixture generator, the recorded A/B rc / `N source
files` / error-class results for both variants, and a written statement of which §10
branch holds.

Explicitly out of scope for that substep: any mypy invocation on a Veyro path, any
`backend/pyproject.toml` or lock edit, any CI workflow edit or live CI run, any
wheel acquisition or download, CAP-012 approval or registry change, and any scenario or
gate disposition.
