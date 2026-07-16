package com.heoclub.aitravel.data.model

data class RouteCoordinate(
    val latitude: Double,
    val longitude: Double,
)

data class RoutePlace(
    val id: String,
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val address: String? = null,
    val cityName: String? = null,
    val adCode: String? = null,
    val cityCode: String? = null,
)

data class RouteStep(
    val instruction: String? = null,
    val distanceMeters: Int? = null,
    val durationSeconds: Int? = null,
    val polyline: List<RouteCoordinate> = emptyList(),
)

data class RouteSegmentRequest(
    val origin: RoutePlace,
    val destination: RoutePlace,
    val mode: String = RouteModes.WALKING,
)

data class RouteSegment(
    val originId: String,
    val destinationId: String,
    val originName: String,
    val destinationName: String,
    val mode: String,
    val distanceMeters: Int,
    val durationSeconds: Int,
    val polyline: List<RouteCoordinate> = emptyList(),
    val steps: List<RouteStep> = emptyList(),
    val warning: String? = null,
)

data class DayRouteRequest(
    val places: List<RoutePlace>,
    val mode: String = RouteModes.WALKING,
)

data class DayRoutePlan(
    val places: List<RoutePlace> = emptyList(),
    val segments: List<RouteSegment> = emptyList(),
    val totalDistanceMeters: Int = 0,
    val totalDurationSeconds: Int = 0,
    val mode: String = RouteModes.WALKING,
    val warning: String? = null,
)

data class OptimizeDayRouteRequest(
    val places: List<RoutePlace>,
    val mode: String = RouteModes.WALKING,
)

data class OptimizeDayRouteResponse(
    val originalPlaceIds: List<String>,
    val optimizedPlaceIds: List<String>,
    val optimizedPlaces: List<RoutePlace>,
    val route: DayRoutePlan,
    val changed: Boolean,
    val warning: String? = null,
)

object RouteModes {
    const val WALKING = "walking"
    const val DRIVING = "driving"
    const val CYCLING = "cycling"
    const val TRANSIT = "transit"

    val all = listOf(WALKING, DRIVING, CYCLING, TRANSIT)

    fun label(mode: String): String {
        return when (mode) {
            WALKING -> "步行"
            DRIVING -> "驾车"
            CYCLING -> "骑行"
            TRANSIT -> "公交"
            else -> "步行"
        }
    }
}
