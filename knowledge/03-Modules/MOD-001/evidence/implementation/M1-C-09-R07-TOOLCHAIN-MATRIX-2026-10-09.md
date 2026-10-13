---
doc: M1-C-09-R07-TOOLCHAIN-MATRIX
status: IMPLEMENTED — LOCAL VERIFICATION ONLY, NOT INDEPENDENTLY REVIEWED, NO SCENARIO PROMOTION
module: MOD-001
requirement: GOV-01-R07
scenario_anchor: SCN-MOD001-127 (status UNCHANGED — still NOT EXECUTED)
subgoal: M1-C-09-R07-TOOLCHAIN-MATRIX
execution_role: IMPLEMENTATION
agent_model: claude-sonnet-5-5
date: 2026-10-09
base_commit: e481b814a80923849dddfe7a49319112aae7b023
---

# M1-C-09 — GOV-01-R07 toolchain matrix and real-config validator

## 1. Artifacts

| Path | Purpose |
|---|---|
| `mobile/TOOLCHAIN_MATRIX.md` | Pinned toolchain, `shared_module_version` per KMP module, `whitelabel_release_metadata` per branded app/store. |
| `mobile/shared/build.gradle.kts` | Pinned-version stub (Kotlin/Compose/AGP plugin versions, Gradle check, module `version`). No source sets. |
| `mobile/androidApp/build.gradle.kts` | Pinned-version stub plus two synthetic product flavors (the declared branded apps). No screens. |
| `tools/validate_toolchain_matrix.py` | Diffs the matrix against committed `mobile/**/build.gradle.kts`; fails closed. |
| `tools/tests/test_validate_toolchain_matrix.py` | 15 deterministic tests. |

## 2. Pins and official sources

Kotlin 2.2.20, Gradle 8.14, AGP 8.11.1, Xcode 16.4, Compose compiler plugin 2.2.20,
Compose Multiplatform 1.9.0.

- https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html
  — row for Kotlin 2.2.20: Gradle 7.6.3–8.14, AGP 7.3.1–8.11.1, Xcode 16.4.
- https://developer.android.com/build/releases/about-agp — AGP 8.11 requires
  Gradle 8.13 or newer. 8.14 satisfies both sources.
- https://kotlinlang.org/docs/multiplatform/compose-compatibility-and-versioning.html
  — no Kotlin column, so **no official Kotlin 2.2.20 ↔ Compose Multiplatform
  pairing was found**. The page states the latest Compose Multiplatform is always
  compatible with the latest Kotlin and requires at least Kotlin 2.1.0.
- https://github.com/JetBrains/compose-multiplatform/releases/tag/v1.9.0 —
  1.9.0 requires Kotlin 2.1 (a floor, which 2.2.20 satisfies).

**Disclosed limit:** Compose Multiplatform 1.9.0 is chosen because its stated
Kotlin floor is met; its exact co-qualification with 2.2.20 is not stated by an
official page I read. The compose compiler plugin equals the Kotlin version by
Kotlin 2.x design. Re-verify before MOD-006.

## 3. What the validator checks

`TOOLCHAIN_DRIFT`, `CONFIG_PIN_MISSING` (comment-only pins do not count),
`WHITELABEL_BRAND_MISSING`, `WHITELABEL_FIELD_MISSING`, `WHITELABEL_DRIFT`,
`SHARED_MODULE_VERSION_MISSING`, `SHARED_MODULE_VERSION_DRIFT`, `MATRIX_INVALID`
(unreadable input, missing pin or section, no config). Declared KMP modules are
build files using `kotlin("multiplatform")`; declared brands are `androidApp`
product flavors, matched on name and `applicationId`.

SCN-127 mapping: (a) `DriftTests` (matrix Gradle diverges; both stubs cited);
(b) `WhitelabelTests.test_missing_brand_row_denied`;
(c) `SharedModuleTests.test_missing_module_version_denied` (a second synthetic KMP
module is added in a temp root); companion positive `PositiveTests` (the fixture
copy and the current working tree both pass).

## 4. Verification run (local, 2026-10-09)

- `backend/.venv/bin/python -m pytest tools/tests/test_validate_toolchain_matrix.py -q` → 15 passed.
- `backend/.venv/bin/python -m ruff check` on the tool and test → all checks passed.
- `py_compile` on both → ok.
- `backend/.venv/bin/python tools/validate_toolchain_matrix.py` → `PASS`.

## 5. Limits — not claimed

- **No Gradle, Android, or iOS build was run.** The `.gradle.kts` stubs were never
  evaluated by Gradle. `androidApp` has no `compileSdk`, so it would not configure
  as-is; MOD-006 completes it.
- Xcode 16.4 is matrix-only; `mobile/iosApp/` has no committed config to diff.
  Apple store rows are not required (no iOS brand declaration exists).
- Brands, package IDs and versions are synthetic placeholders; no store listing exists.
- The validator does not check the pins' mutual compatibility (that is
  SCN-MOD001-051/099).
- Parent replay found a fail-open inventory case: adding a `mobile/ghost` row to
  `shared_module_version` with no matching Gradle module returns `[]` (PASS).
  The next mandatory C09 CI/checker increment must reject a matrix-declared
  module absent from real config. No SCN-127 disposition until fixed and replayed.
- The CI trigger row (path filter on `mobile/TOOLCHAIN_MATRIX.md` /
  `mobile/**/build.gradle.kts`) was **not** wired; no CI push, per instructions.
- SCN-MOD001-127 stays NOT EXECUTED. Independent review is still owed.
- `knowledge/**` status docs were not updated (outside this slice).

## 6. Operation checkpoint

The worker did not find the external workspace control path and did not call
`operation_budget.py` before completion. Parent located it afterward, but the
completed operation correctly rejected a late checkpoint. The guarded operation
record has exit 0 and durable changed-state hash; do not fabricate an in-flight
checkpoint. This is not SCN-127 assurance.
