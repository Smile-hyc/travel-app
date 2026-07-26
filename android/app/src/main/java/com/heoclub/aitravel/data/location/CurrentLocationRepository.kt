package com.heoclub.aitravel.data.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.amap.api.location.AMapLocation
import com.amap.api.location.AMapLocationClient
import com.amap.api.location.AMapLocationClientOption
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

data class CurrentLocation(
    val latitude: Double,
    val longitude: Double,
    val cityName: String,
    val provinceName: String,
    val districtName: String,
    val adCode: String,
    val address: String,
    val accuracyMeters: Float,
    val updateSequence: Long,
)

data class CurrentLocationUiState(
    val location: CurrentLocation? = null,
    val isLocating: Boolean = false,
    val errorMessage: String? = null,
)

class CurrentLocationRepository(context: Context) {
    private val applicationContext = context.applicationContext
    private val _state = MutableStateFlow(CurrentLocationUiState())
    val state: StateFlow<CurrentLocationUiState> = _state.asStateFlow()

    private var locationClient: AMapLocationClient? = null
    private var updateSequence = 0L

    fun refreshLocation() {
        if (!hasLocationPermission()) {
            reportPermissionDenied()
            return
        }
        if (!hasAmapAndroidKey()) {
            finishWithError(
                "未配置高德 Android Key，请在 android/local.properties 中设置 AMAP_ANDROID_KEY",
            )
            return
        }
        if (_state.value.isLocating) return

        _state.value = _state.value.copy(isLocating = true, errorMessage = null)
        val client = runCatching { obtainClient() }
            .getOrElse { throwable ->
                _state.value = _state.value.copy(
                    isLocating = false,
                    errorMessage = throwable.message?.takeIf(String::isNotBlank)
                        ?: "定位服务初始化失败",
                )
                return
            }

        client.stopLocation()
        client.setLocationOption(
            AMapLocationClientOption().apply {
                locationMode = AMapLocationClientOption.AMapLocationMode.Hight_Accuracy
                isOnceLocation = true
                isOnceLocationLatest = true
                isNeedAddress = true
                isLocationCacheEnable = true
                httpTimeOut = 15_000L
            },
        )
        client.startLocation()
    }

    fun reportPermissionDenied() {
        _state.value = _state.value.copy(
            isLocating = false,
            errorMessage = "未获得定位权限",
        )
    }

    private fun obtainClient(): AMapLocationClient {
        return locationClient ?: AMapLocationClient(applicationContext).apply {
            setLocationListener(::handleLocationResult)
        }.also { locationClient = it }
    }

    private fun handleLocationResult(location: AMapLocation?) {
        if (location == null) {
            finishWithError("未获取到定位结果")
            return
        }
        if (location.errorCode != AMapLocation.LOCATION_SUCCESS) {
            val detail = location.errorInfo.orEmpty().trim()
            finishWithError(
                when {
                    location.errorCode == AMAP_KEY_ERROR_CODE ->
                        "定位失败：高德 Android Key 校验失败，请检查包名和签名 SHA-1 绑定"
                    detail.isBlank() -> "定位失败（${location.errorCode}）"
                    else -> "定位失败：$detail"
                },
            )
            return
        }

        updateSequence += 1
        val province = location.province.orEmpty().trim()
        val district = location.district.orEmpty().trim()
        val city = location.city.orEmpty().trim()
            .ifBlank { district }
            .ifBlank { province }
            .ifBlank { "当前位置" }
        _state.value = CurrentLocationUiState(
            location = CurrentLocation(
                latitude = location.latitude,
                longitude = location.longitude,
                cityName = city,
                provinceName = province,
                districtName = district,
                adCode = location.adCode.orEmpty().trim(),
                address = location.address.orEmpty().trim(),
                accuracyMeters = location.accuracy,
                updateSequence = updateSequence,
            ),
            isLocating = false,
            errorMessage = null,
        )
        locationClient?.stopLocation()
    }

    private fun finishWithError(message: String) {
        _state.value = _state.value.copy(
            isLocating = false,
            errorMessage = message,
        )
        locationClient?.stopLocation()
    }

    private fun hasLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            applicationContext,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(
                applicationContext,
                Manifest.permission.ACCESS_COARSE_LOCATION,
            ) == PackageManager.PERMISSION_GRANTED
    }

    private fun hasAmapAndroidKey(): Boolean {
        val applicationInfo = runCatching {
            applicationContext.packageManager.getApplicationInfo(
                applicationContext.packageName,
                PackageManager.GET_META_DATA,
            )
        }.getOrNull()
        return applicationInfo?.metaData
            ?.getString(AMAP_KEY_METADATA_NAME)
            .orEmpty()
            .isNotBlank()
    }

    private companion object {
        const val AMAP_KEY_METADATA_NAME = "com.amap.api.v2.apikey"
        const val AMAP_KEY_ERROR_CODE = 7
    }
}
