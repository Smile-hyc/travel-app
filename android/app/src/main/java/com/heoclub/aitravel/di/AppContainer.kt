package com.heoclub.aitravel.di

import android.content.Context
import com.heoclub.aitravel.data.local.TokenStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import com.heoclub.aitravel.data.location.CurrentLocationRepository
import com.heoclub.aitravel.data.remote.RetrofitClient
import com.heoclub.aitravel.data.repository.AuthRepository
import com.heoclub.aitravel.data.repository.DefaultHealthRepository
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.AiConversationHistoryStore
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.HealthRepository
import com.heoclub.aitravel.data.repository.CloudTravelPlanRepository
import com.heoclub.aitravel.data.repository.FootprintRepository
import com.heoclub.aitravel.data.repository.JournalRepository
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
    val tokenStore = TokenStore(context)

    private val apiClient = RetrofitClient.create(
        baseUrl = apiBaseUrl,
        isDebug = isDebug,
        tokenStore = tokenStore,
    )
    private val apiService = apiClient.apiService

    val authRepository = AuthRepository(apiService, tokenStore)
    val healthRepository: HealthRepository = DefaultHealthRepository(apiService)
    val currentLocationRepository = CurrentLocationRepository(context)
    val travelPlanRepository: TravelPlanRepository = CloudTravelPlanRepository(
        apiService = apiService,
        scope = CoroutineScope(Dispatchers.IO),
    )
    val aiConversationHistoryStore = AiConversationHistoryStore(context)
    val footprintRepository = FootprintRepository(apiService)
    val journalRepository = JournalRepository(apiService)
    val exploreRepository: ExploreRepository = RemoteExploreRepository(apiService)
    val routeRepository: RouteRepository = RemoteRouteRepository(apiService)
    val aiRepository: AiRepository = RemoteAiRepository(
        apiService = apiService,
        okHttpClient = apiClient.okHttpClient,
        apiBaseUrl = apiBaseUrl,
    )
}
