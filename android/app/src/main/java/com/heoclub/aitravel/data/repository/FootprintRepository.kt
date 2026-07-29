package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.UserFootprintCreateRequest
import com.heoclub.aitravel.data.model.UserFootprintResponse
import com.heoclub.aitravel.data.remote.ApiService

class FootprintRepository(
    private val apiService: ApiService,
) {
    suspend fun getFootprints(): Result<List<UserFootprintResponse>> = runCatching {
        apiService.getUserFootprints()
    }

    suspend fun addFootprint(
        cityName: String,
        provinceName: String = "",
        latitude: Double? = null,
        longitude: Double? = null,
    ): Result<UserFootprintResponse> = runCatching {
        apiService.addUserFootprint(
            UserFootprintCreateRequest(
                cityName = cityName,
                provinceName = provinceName,
                latitude = latitude,
                longitude = longitude,
            ),
        )
    }
}
