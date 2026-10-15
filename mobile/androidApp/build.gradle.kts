// MOD-001 GOV-01-R07 (SCN-MOD001-127): pinned-version stub only, native adapters
// only and no screens. Each product flavor is one synthetic branded app whose
// package ID must have a whitelabel_release_metadata row in
// mobile/TOOLCHAIN_MATRIX.md.
plugins {
    id("com.android.application") version "8.11.1"
    kotlin("android") version "2.2.20"
}

check(gradle.gradleVersion == "8.14") {
    "Gradle ${gradle.gradleVersion} does not match the pinned 8.14 (mobile/TOOLCHAIN_MATRIX.md)"
}

android {
    compileSdk = 36
    namespace = "app.veyro.synthetic.androidapp"
    flavorDimensions += "brand"
    productFlavors {
        create("syntheticBrandA") {
            dimension = "brand"
            applicationId = "app.veyro.synthetic.branda"
        }
        create("syntheticBrandB") {
            dimension = "brand"
            applicationId = "app.veyro.synthetic.brandb"
        }
    }
}

dependencyLocking {
    lockAllConfigurations()
}

// Lock the resolved plugin buildscript classpath separately from project dependencies.
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
