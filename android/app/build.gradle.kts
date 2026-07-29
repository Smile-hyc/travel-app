plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

import java.util.Properties
import java.io.File

fun Properties.loadIfExists(file: File) {
    if (file.exists()) {
        file.inputStream().use(::load)
    }
}

val localProperties = Properties().apply {
    loadIfExists(rootProject.file("local.properties"))
}
val backendEnvProperties = Properties().apply {
    loadIfExists(rootProject.file("../backend/.env"))
}

fun localConfigValue(key: String, fallback: String = ""): String {
    return localProperties.getProperty(key)
        ?: backendEnvProperties.getProperty(key)
        ?: providers.gradleProperty(key).orNull
        ?: providers.environmentVariable(key).orNull
        ?: fallback
}

val localDeviceApiBaseUrl = localConfigValue(
    key = "LOCAL_DEVICE_API_BASE_URL",
    fallback = providers.gradleProperty("AI_TRAVEL_API_BASE_URL")
        .orElse("http://127.0.0.1:8000/")
        .get(),
)
val releaseApiBaseUrl = localConfigValue(
    key = "API_BASE_URL",
    fallback = "http://152.136.27.117:8020/",
)
val amapAndroidKey = localConfigValue(
    key = "AMAP_ANDROID_KEY",
    fallback = "",
)

android {
    namespace = "com.heoclub.aitravel"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.heoclub.aitravel"
        minSdk = 28
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        manifestPlaceholders["AMAP_ANDROID_KEY"] = amapAndroidKey

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    val keystoreProperties = Properties().apply {
        loadIfExists(rootProject.file("keystore.properties"))
    }

    signingConfigs {
        create("release") {
            storeFile = file("travel-app-release.jks")
            storePassword = keystoreProperties.getProperty("KEYSTORE_PASSWORD") ?: ""
            keyAlias = keystoreProperties.getProperty("KEY_ALIAS") ?: ""
            keyPassword = keystoreProperties.getProperty("KEY_PASSWORD") ?: ""
        }
    }

    buildTypes {
        debug {
            // A USB-connected device reaches the host through `adb reverse`.
            // Keep Debug independent from the shared/cloud server.
            buildConfigField("String", "API_BASE_URL", "\"$localDeviceApiBaseUrl\"")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiBaseUrl\"")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
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

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
}

val validateAmapAndroidKey by tasks.registering {
    group = "verification"
    description = "Checks that an AMap Android SDK key is configured before packaging the app."

    doLast {
        check(amapAndroidKey.isNotBlank()) {
            "AMAP_ANDROID_KEY is missing. Add the Android-platform key to " +
                "android/local.properties (do not use AMAP_WEB_SERVICE_KEY). " +
                "The key must be bound to package com.heoclub.aitravel and this build's signing SHA-1."
        }
    }
}

tasks.configureEach {
    val packagesApp = name.startsWith("package", ignoreCase = true) &&
        !name.endsWith("Resources", ignoreCase = true) &&
        !name.endsWith("Assets", ignoreCase = true)
    if (name.startsWith("assemble", ignoreCase = true) ||
        name.startsWith("bundle", ignoreCase = true) ||
        packagesApp ||
        name.startsWith("install", ignoreCase = true)
    ) {
        dependsOn(validateAmapAndroidKey)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)
    implementation(libs.okhttp.logging)
    implementation(libs.amap.map.sdk)
    implementation(libs.coil.compose)

    debugImplementation(libs.androidx.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
