// The Kairu phone app (Phase D, PHONE.md). Built on GitHub's machines (.github/workflows/phone.yml), never on the PC.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "KairuPhone"
include(":app")
