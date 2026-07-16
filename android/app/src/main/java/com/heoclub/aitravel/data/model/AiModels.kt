package com.heoclub.aitravel.data.model

data class AiHistoryMessage(
    val role: String,
    val content: String,
)

data class AiPlaceContext(
    val itemId: String,
    val sourcePoiId: String? = null,
    val name: String,
    val category: String? = null,
    val typeName: String? = null,
    val address: String? = null,
    val cityName: String? = null,
    val districtName: String? = null,
    val imageUrl: String? = null,
    val dayIndex: Int? = null,
    val visitOrder: Int? = null,
    val suggestedStart: String? = null,
    val suggestedEnd: String? = null,
)

data class AiDayContext(
    val dayIndex: Int,
    val title: String? = null,
    val places: List<AiPlaceContext> = emptyList(),
)

data class AiWeatherContext(
    val city: String? = null,
    val text: String? = null,
    val weather: String? = null,
    val dayTemp: String? = null,
    val nightTemp: String? = null,
    val reportTime: String? = null,
)

data class AiRouteSummary(
    val dayIndex: Int,
    val mode: String? = null,
    val placeCount: Int = 0,
    val totalDistanceMeters: Int? = null,
    val totalDurationSeconds: Int? = null,
    val warnings: List<String> = emptyList(),
)

data class AiPlanContext(
    val id: String? = null,
    val title: String? = null,
    val destination: String? = null,
    val dateRange: String? = null,
    val revision: Long? = null,
    val updatedAt: Long? = null,
    val days: List<AiDayContext> = emptyList(),
    val unplannedPlaces: List<AiPlaceContext> = emptyList(),
    val weather: AiWeatherContext? = null,
    val routeSummaries: List<AiRouteSummary> = emptyList(),
)

data class AiChatRequest(
    val conversationId: String? = null,
    val planId: String? = null,
    val message: String,
    val history: List<AiHistoryMessage> = emptyList(),
    val context: AiPlanContext? = null,
)

data class AiChatResponse(
    val conversationId: String,
    val messageId: String? = null,
    val message: String,
    val quickReplies: List<String> = emptyList(),
    val referencedPlaceItemIds: List<String> = emptyList(),
    val actionSetId: String? = null,
    val planRevision: Long? = null,
    val suggestedActions: List<AiSuggestedAction> = emptyList(),
    val actionWarnings: List<String> = emptyList(),
    val createdAt: String? = null,
    val model: String? = null,
)

data class AiSuggestedAction(
    val id: String,
    val type: String,
    val placeItemId: String,
    val fromDayIndex: Int? = null,
    val toDayIndex: Int? = null,
    val fromPosition: Int? = null,
    val toPosition: Int? = null,
    val reason: String? = null,
    val requiresRouteRefresh: Boolean = true,
    val affectedDayIndexes: List<Int> = emptyList(),
)
