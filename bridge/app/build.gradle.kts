import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// The DJI app key comes from local.properties (git-ignored) or the environment, never the repo.
val localProps = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val djiApiKey: String = localProps.getProperty("DJI_API_KEY") ?: System.getenv("DJI_API_KEY") ?: ""

android {
    namespace = "ca.bcit.drone3pov.bridge"
    // DJI support recommends compileSdk 33 for MSDK 4.18.
    compileSdk = 33

    defaultConfig {
        applicationId = "ca.bcit.drone3pov.bridge"
        minSdk = 24
        // MSDK v4 predates Android 12's background and USB changes. Sideloaded, so 30 is fine.
        targetSdk = 30
        versionCode = 1
        versionName = "0.1.0"
        manifestPlaceholders["DJI_API_KEY"] = djiApiKey
        ndk { abiFilters += listOf("armeabi-v7a", "arm64-v8a") }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    packaging {
        // MSDK v4 loads its native libraries itself and breaks if they are compressed or stripped.
        jniLibs {
            useLegacyPackaging = true
            keepDebugSymbols += setOf(
                "*/*/libdjivideo.so",
                "*/*/libSDKRelativeJNI.so",
                "*/*/libFlyForbid.so",
                "*/*/libduml_vision_bokeh.so",
                "*/*/libyuv2.so",
                "*/*/libGroudStation.so",
                "*/*/libFRCorkscrew.so",
                "*/*/libUpgradeVerify.so",
                "*/*/libFR.so",
                "*/*/libDJIFlySafeCore.so",
                "*/*/libdjifs_jni.so",
                "*/*/libsfjni.so",
                "*/*/libDJICommonJNI.so",
                "*/*/libDJICSDKCommon.so",
                "*/*/libDJIUpgradeCore.so",
                "*/*/libDJIUpgradeJNI.so",
                "*/*/libDJIWaypointV2Core.so",
                "*/*/libDJIMOP.so",
                "*/*/libDJISDKLOGJNI.so",
            )
        }
        resources { excludes += setOf("META-INF/rxjava.properties", "META-INF/proguard/okhttp3.pro") }
    }

    lint {
        disable += "ExpiredTargetSdkVersion"
    }
}

dependencies {
    implementation("com.dji:dji-sdk:4.18")
    compileOnly("com.dji:dji-sdk-provided:4.18")
    implementation("org.nanohttpd:nanohttpd:2.3.1")

    testImplementation("junit:junit:4.13.2")
}
