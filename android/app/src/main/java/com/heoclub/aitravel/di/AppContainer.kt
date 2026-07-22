package com.heoclub.aitravel.di

import android.content.Context
import com.heoclub.aitravel.data.location.CurrentLocationRepository
import com.heoclub.aitravel.data.remote.RetrofitClient
import com.heoclub.aitravel.data.repository.DefaultHealthRepository
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.HealthRepository
import com.heoclub.aitravel.data.repository.PersistentTravelPlanRepository
import com.heoclub.aitravel.data.repository.RemoteAiRepository
import com.heoclub.aitravel.data.repository.RemoteExploreRepository
import com.heoclub.aitravel.data.repository.RemoteRouteRepository
import com.heoclub.aitravel.data.repository.RouteRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository

class AppContainer(
    context: Context,
    apiBaseUrl: String,
    isDebug: Boolean,
) {
    private val apiClient = RetrofitClient.create(
        baseUrl = apiBaseUrl,
        isDebug = isDebug,
    )
    private val apiService = apiClient.apiService

    val healthRepository: HealthRepository = DefaultHealthRepository(apiService)
    val currentLocationRepository = CurrentLocationRepository(context)
    val travelPlanRepository: TravelPlanRepository = PersistentTravelPlanRepository(context)
    val exploreRepository: ExploreRepository = RemoteExploreRepository(apiService)
    val routeRepository: RouteRepository = RemoteRouteRepository(apiService)
    val aiRepository: AiRepository = RemoteAiRepository(
        apiService = apiService,
        okHttpClient = apiClient.okHttpClient,
        apiBaseUrl = apiBaseUrl,
    )
}
