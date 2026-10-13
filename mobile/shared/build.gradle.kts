// MOD-001 GOV-01-R07 (SCN-MOD001-127): pinned-version stub only. No application
// logic and no source sets; MOD-006 owns the real KMP module. The versions below
// are the "real committed config" tools/validate_toolchain_matrix.py diffs
// mobile/TOOLCHAIN_MATRIX.md against.
plugins {
    kotlin("multiplatform") version "2.2.20"
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.20"
    id("org.jetbrains.compose") version "1.9.0"
    id("com.android.library") version "8.11.1"
}

group = "app.veyro.synthetic"
version = "0.1.0-synthetic"

check(gradle.gradleVersion == "8.14") {
    "Gradle ${gradle.gradleVersion} does not match the pinned 8.14 (mobile/TOOLCHAIN_MATRIX.md)"
}
