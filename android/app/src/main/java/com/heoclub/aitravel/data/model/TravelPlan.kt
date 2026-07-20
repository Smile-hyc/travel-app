package com.heoclub.aitravel.data.model

data class TravelPlan(
    val id: String,
    val title: String,
    val destination: String,
    val dateRange: String,
    val dayCount: Int,
    val preferences: List<String>,
    val createdAt: Long,
    val revision: Long = 1L,
    val updatedAt: Long = createdAt,
    val days: List<PlanDay> = List(dayCount.coerceAtLeast(1)) { index ->
        PlanDay(
            id = "day-${index + 1}",
            dayIndex = index + 1,
            title = "DAY ${index + 1}",
        )
    },
    val unplannedItems: List<PlanItem> = emptyList(),
) {
    val placeCount: Int
        get() = days.orEmpty().sumOf { it.items.orEmpty().size } + unplannedItems.orEmpty().size
}

data class PlanDay(
    val id: String,
    val dayIndex: Int,
    val title: String,
    val items: List<PlanItem> = emptyList(),
)

data class PlanItem(
    val id: String,
    val source: String,
    val sourcePoiId: String,
    val name: String,
    val category: String,
    val categoryCode: String,
    val typeName: String? = null,
    val typeCode: String? = null,
    val address: String? = null,
    val provinceName: String? = null,
    val cityName: String? = null,
    val districtName: String? = null,
    val adCode: String? = null,
    val cityCode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val dayId: String,
    val dayIndex: Int,
    val visitOrder: Int,
    val note: String? = null,
    val mealType: String? = null,
    val suggestedStart: String? = null,
    val suggestedEnd: String? = null,
    val transportModeToNext: String = "walking",
    val thumbnailUrl: String? = null,
    val imageUrls: List<String> = emptyList(),
    val phone: String? = null,
    val rating: String? = null,
    val costAverage: String? = null,
    val businessArea: String? = null,
    val openingHoursToday: String? = null,
    val openingHoursWeek: String? = null,
    val scheduleVerified: Boolean = false,
)
