package com.heoclub.aitravel

import android.app.Application
import com.amap.api.location.AMapLocationClient
import com.amap.api.maps.MapsInitializer
import com.heoclub.aitravel.di.AppContainer

class AiTravelApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        MapsInitializer.updatePrivacyShow(this, true, true)
        MapsInitializer.updatePrivacyAgree(this, true)
        AMapLocationClient.updatePrivacyShow(this, true, true)
        AMapLocationClient.updatePrivacyAgree(this, true)
        container = AppContainer(
            context = this,
            apiBaseUrl = BuildConfig.API_BASE_URL,
            isDebug = BuildConfig.DEBUG,
        )
    }
}
