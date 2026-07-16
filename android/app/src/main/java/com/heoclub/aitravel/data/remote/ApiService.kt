package com.heoclub.aitravel.data.remote

import com.heoclub.aitravel.data.model.HealthResponse
import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiChatResponse
import com.heoclub.aitravel.data.model.CitySearchResult
import com.heoclub.aitravel.data.model.DayRoutePlan
import com.heoclub.aitravel.data.model.DayRouteRequest
import com.heoclub.aitravel.data.model.ExploreWeather
import com.heoclub.aitravel.data.model.OptimizeDayRouteRequest
import com.heoclub.aitravel.data.model.OptimizeDayRouteResponse
import com.heoclub.aitravel.data.model.PaginatedPlaces
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.RouteSegment
import com.heoclub.aitravel.data.model.RouteSegmentRequest
import retrofit2.http.GET
import retrofit2.http.Body
import retrofit2.http.POST
import retrofit2.http.Query

interface ApiService {
    @GET("api/health")
    suspend fun getHealth(): HealthResponse

    @GET("api/explore/pois/search")
    suspend fun searchPois(
        @Query("adcode") adcode: String,
        @Query("category") category: String,
        @Query("keyword") keyword: String? = null,
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 20,
        @Query("city_limit") cityLimit: Boolean = true,
    ): PaginatedPlaces

    @GET("api/explore/cities/search")
    suspend fun searchCities(
        @Query("keyword") keyword: String,
        @Query("limit") limit: Int = 12,
    ): List<CitySearchResult>

    @GET("api/explore/input-tips")
    suspend fun getInputTips(
        @Query("keyword") keyword: String,
        @Query("adcode") adcode: String? = null,
        @Query("city_limit") cityLimit: Boolean = true,
        @Query("category") category: String? = null,
    ): List<PlaceSuggestion>

    @GET("api/explore/weather")
    suspend fun getExploreWeather(
        @Query("adcode") adcode: String,
    ): ExploreWeather

    @POST("api/routes/segment")
    suspend fun calculateRouteSegment(
        @Body request: RouteSegmentRequest,
    ): RouteSegment

    @POST("api/routes/day/calculate")
    suspend fun calculateDayRoute(
        @Body request: DayRouteRequest,
    ): DayRoutePlan

    @POST("api/routes/day/optimize")
    suspend fun optimizeDayRoute(
        @Body request: OptimizeDayRouteRequest,
    ): OptimizeDayRouteResponse

    @POST("api/ai/chat")
    suspend fun chatWithAi(
        @Body request: AiChatRequest,
    ): AiChatResponse
}
