plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Each GitHub build gets a higher number, so `kairu phone install` can update the app in place.
val buildNumber = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
// The owner's signing key, from the repository's secrets (PHONE.md). Without it, the cached debug key signs.
val keystorePath: String? = System.getenv("KAIRU_KEYSTORE_FILE")

android {
    namespace = "com.kairu.phone"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.kairu.phone"
        minSdk = 29
        targetSdk = 35
        versionCode = buildNumber
        versionName = "0.1.$buildNumber"
    }

    signingConfigs {
        if (keystorePath != null) {
            create("owner") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("KAIRU_KEYSTORE_PASSWORD")
                keyAlias = "kairu"
                keyPassword = System.getenv("KAIRU_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (keystorePath != null) signingConfigs.getByName("owner") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "META-INF/versions/9/OSGI-INF/MANIFEST.MF"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    // D2: approving a High request with the fingerprint (BiometricPrompt needs a FragmentActivity)
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    // Kairu Link's Ed25519, X25519 and Poly1305 (the same algorithms as the PC's libsodium; PHONE.md)
    implementation("org.bouncycastle:bcprov-jdk18on:1.79")
    // Scanning the pairing QR code that `kairu device pair` shows
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")  // the real org.json on the JVM, for the Link tests
}
