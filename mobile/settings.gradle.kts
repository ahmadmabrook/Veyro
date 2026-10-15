pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "veyro-mobile"

include(":shared")
include(":androidApp")

project(":shared").projectDir = file("shared")
project(":androidApp").projectDir = file("androidApp")
