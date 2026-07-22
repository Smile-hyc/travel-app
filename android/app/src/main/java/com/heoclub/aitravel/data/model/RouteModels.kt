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
    const val MIXED = "mixed"
    const val WALKING = "walking"
    const val DRIVING = "driving"
    const val CYCLING = "cycling"
    const val TRANSIT = "transit"

    val all = listOf(MIXED, WALKING, DRIVING, CYCLING, TRANSIT)

    fun label(mode: String, steps: List<RouteStep> = emptyList()): String {
        return when (mode) {
            MIXED -> "智能混合"
            WALKING -> "步行"
            DRIVING -> "驾车"
            CYCLING -> "骑行"
            TRANSIT -> transitLabel(steps)
            else -> "步行"
        }
    }

    private fun transitLabel(steps: List<RouteStep>): String {
        val instructions = steps.mapNotNull { it.instruction }.joinToString(" ")
        if (instructions.isBlank()) return "公共交通"
        val labels = buildList {
            if (listOf("地铁", "轨道交通", "轻轨").any(instructions::contains)) add("地铁")
            if (instructions.contains("有轨电车")) add("有轨电车")
            if (listOf("公交", "公共汽车", "巴士", "BRT", "快速公交").any {
                    instructions.contains(it, ignoreCase = true)
                }) add("公交")
            if (listOf("轮渡", "渡船", "客轮").any(instructions::contains)) add("轮渡")
            if (listOf("索道", "缆车").any(instructions::contains)) add("索道")
        }
        return labels.distinct().joinToString(" + ").ifBlank { "公共交通" }
    }
}
