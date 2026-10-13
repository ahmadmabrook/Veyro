---
doc: MOBILE_TOOLCHAIN_MATRIX
status: LIVE — synthetic pins authored before MOD-006; no real Android/iOS build has been run
module: MOD-001
requirement: GOV-01-R07
scenario: SCN-MOD001-127
created: 2026-10-09
---

# Mobile toolchain compatibility matrix

Authoritative target MOD-006 inherits. `tools/validate_toolchain_matrix.py`
checks this file against the committed `mobile/**/build.gradle.kts`; a
mismatch is a defect. Sources: Kotlin Multiplatform compatibility guide
(https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html)
and AGP release notes (https://developer.android.com/build/releases/about-agp).
Kotlin 2.2.20 supports Gradle 7.6.3–8.14, AGP 7.3.1–8.11.1 and Xcode 16.4;
AGP 8.11 requires Gradle 8.13 or newer. Xcode has no committed config yet
(`mobile/iosApp/` is empty), so its pin is matrix-only.

## toolchain_pins

| component | version |
|---|---|
| kotlin | 2.2.20 |
| compose_compiler_plugin | 2.2.20 |
| compose_multiplatform | 1.9.0 |
| gradle | 8.14 |
| agp | 8.11.1 |
| xcode | 16.4 |

## shared_module_version

| module | shared_module_version |
|---|---|
| mobile/shared | 0.1.0-synthetic |

## whitelabel_release_metadata

All rows are synthetic; no store listing exists.

| brand | store | bundle_package_id | release_version | min_supported_version | store_status |
|---|---|---|---|---|---|
| syntheticBrandA | google_play | app.veyro.synthetic.branda | 0.1.0-synthetic | 0.1.0-synthetic | NOT_PUBLISHED_SYNTHETIC |
| syntheticBrandB | google_play | app.veyro.synthetic.brandb | 0.1.0-synthetic | 0.1.0-synthetic | NOT_PUBLISHED_SYNTHETIC |
