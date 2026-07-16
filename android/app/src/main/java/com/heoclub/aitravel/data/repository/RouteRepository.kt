package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.DayRoutePlan
import com.heoclub.aitravel.data.model.DayRouteRequest
import com.heoclub.aitravel.data.model.OptimizeDayRouteRequest
import com.heoclub.aitravel.data.model.OptimizeDayRouteResponse
import com.heoclub.aitravel.data.model.RoutePlace
import com.heoclub.aitravel.data.remote.ApiService

interface RouteRepository {
    suspend fun calculateDayRoute(
        places: List<RoutePlace>,
        mode: String,
    ): DayRoutePlan

    suspend fun optimizeDayRoute(
        places: List<RoutePlace>,
        mode: String,
    ): OptimizeDayRouteResponse
}

class RemoteRouteRepository(
    private val apiService: ApiService,
) : RouteRepository {
    override suspend fun calculateDayRoute(
        places: List<RoutePlace>,
        mode: String,
    ): DayRoutePlan {
        return apiService.calculateDayRoute(
            DayRouteRequest(
                places = places,
                mode = mode,
            ),
        )
    }

    override suspend fun optimizeDayRoute(
        places: List<RoutePlace>,
        mode: String,
    ): OptimizeDayRouteResponse {
        return apiService.optimizeDayRoute(
            OptimizeDayRouteRequest(
                places = places,
                mode = mode,
            ),
        )
    }
}
