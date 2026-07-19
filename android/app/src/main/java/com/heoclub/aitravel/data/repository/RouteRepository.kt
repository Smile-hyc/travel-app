package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.DayRoutePlan
import com.heoclub.aitravel.data.model.DayRouteRequest
import com.heoclub.aitravel.data.model.OptimizeDayRouteRequest
import com.heoclub.aitravel.data.model.OptimizeDayRouteResponse
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.RoutePlace
import com.heoclub.aitravel.data.model.RouteSegmentRequest
import com.heoclub.aitravel.data.model.RouteModes
import com.heoclub.aitravel.data.remote.ApiService

interface RouteRepository {
    suspend fun calculateDayRoute(
        places: List<RoutePlace>,
        mode: String,
    ): DayRoutePlan

    suspend fun calculateMixedDayRoute(items: List<PlanItem>): DayRoutePlan

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

    override suspend fun calculateMixedDayRoute(items: List<PlanItem>): DayRoutePlan {
        val ordered = items.sortedBy { it.visitOrder }.filter { it.latitude != null && it.longitude != null }
        val places = ordered.mapNotNull { it.toRoutePlace() }
        val segments = mutableListOf<com.heoclub.aitravel.data.model.RouteSegment>()
        for ((origin, destination) in ordered.zipWithNext()) {
            val mode = origin.transportModeToNext.takeIf(RouteModes.all::contains)
                ?.takeUnless { it == RouteModes.MIXED }
                ?: RouteModes.WALKING
            segments += apiService.calculateRouteSegment(
                RouteSegmentRequest(
                    origin = requireNotNull(origin.toRoutePlace()),
                    destination = requireNotNull(destination.toRoutePlace()),
                    mode = mode,
                ),
            )
        }
        return DayRoutePlan(
            places = places,
            segments = segments,
            totalDistanceMeters = segments.sumOf { it.distanceMeters },
            totalDurationSeconds = segments.sumOf { it.durationSeconds },
            mode = RouteModes.MIXED,
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
