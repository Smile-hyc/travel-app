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
    val cards: List<AiCard> = emptyList(),
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

// ── AI Chat Cards ──

data class AiCardPlaceRef(
    val itemId: String,
    val note: String = "",
)

data class AiCardDay(
    val day_index: Int,
    val title: String = "",
    val place_refs: List<AiCardPlaceRef> = emptyList(),
)

data class AiLinkCardPayload(
    val action_type: String = "NAVIGATE_TO_CREATE_PLAN",
)

data class AiCard(
    val id: String = "",
    val type: String = "",           // "LINK" | "ITINERARY_OPTIMIZATION"
    val title: String? = null,
    val subtitle: String? = null,    // LINK only
    val payload: AiLinkCardPayload? = null,  // LINK only
    val days: List<AiCardDay>? = null,       // ITINERARY only
)

data class AiPlanGenerationRequest(
    val destination: String,
    val dateRange: String,
    val dayCount: Int,
    val preferences: List<String> = emptyList(),
    val freeText: String? = null,
    val arrivalStation: String? = null,
    val arrivalPoint: AiMapPointInput? = null,
    val arrivalDay: Int = 1,
    val arrivalTime: String? = null,
    val departureStation: String? = null,
    val departurePoint: AiMapPointInput? = null,
    val departureDay: Int? = null,
    val departureTime: String? = null,
    val hotelName: String? = null,
    val hotelPoint: AiMapPointInput? = null,
    val hotelStays: List<AiHotelStayInput> = emptyList(),
    val optimizationMode: String = "REQUIRED",
    val pace: String = "BALANCED",
    val transportPreference: String = "MIXED",
    val dailyStart: String = "09:00",
    val dailyEnd: String = "20:00",
    val clientRequestId: String? = null,
)

data class AiHotelStayInput(
    val name: String,
    val checkInDay: Int,
    val checkOutDay: Int,
    val mapPoint: AiMapPointInput? = null,
)

data class AiMapPointInput(
    val name: String,
    val address: String? = null,
    val latitude: Double,
    val longitude: Double,
    val adCode: String? = null,
    val provinceName: String? = null,
    val cityName: String? = null,
    val districtName: String? = null,
)

data class AiGeneratedPlace(
    val id: String,
    val source: String = "AMAP",
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
    val latitude: Double,
    val longitude: Double,
    val thumbnailUrl: String? = null,
    val imageUrls: List<String> = emptyList(),
    val phone: String? = null,
    val rating: String? = null,
    val costAverage: String? = null,
    val businessArea: String? = null,
    val openingHoursToday: String? = null,
    val openingHoursWeek: String? = null,
    val officialScenicGrade: String? = null,
    val experienceEvidenceCount: Int = 0,
    val officialReservationRequired: Boolean = false,
    val officialReservationNote: String? = null,
    val officialClosedDates: List<String> = emptyList(),
    val officialClosureWarning: String? = null,
    val officialOpeningHoursByDate: Map<String, String> = emptyMap(),
    val officialAccessNote: String? = null,
    val officialMaxDailyCapacity: Int? = null,
    val officialCapacityNote: String? = null,
    val officialTicketNote: String? = null,
    val crowdRisk: Double = 0.0,
    val contentUpdatedAt: String? = null,
    val scheduleVerified: Boolean = false,
    val suggestedStart: String,
    val suggestedEnd: String,
    val note: String,
    val mealType: String? = null,
)

data class AiGeneratedDay(
    val dayIndex: Int,
    val title: String,
    val summary: String,
    val places: List<AiGeneratedPlace> = emptyList(),
    val transfers: List<AiGeneratedTransfer> = emptyList(),
    val alternatives: List<AiPlanAlternative> = emptyList(),
    val weather: String? = null,
    val estimatedDistanceKm: Double = 0.0,
    val intensity: String = "适中",
)

data class AiPlanAlternative(
    val id: String,
    val sourcePoiId: String,
    val name: String,
    val category: String,
    val latitude: Double,
    val longitude: Double,
    val districtName: String? = null,
    val openingHoursWeek: String? = null,
    val officialReservationRequired: Boolean = false,
    val reason: String,
)

data class AiGeneratedTransfer(
    val originPlaceId: String,
    val destinationPlaceId: String,
    val mode: String,
    val modeLabel: String? = null,
    val distanceMeters: Int,
    val durationMinutes: Int,
    val verified: Boolean = true,
    val warning: String? = null,
    val polyline: List<RouteCoordinate> = emptyList(),
)

data class AiPlanQuality(
    val realPoiRatio: Double = 1.0,
    val duplicatePlaceCount: Int = 0,
    val totalPlaceCount: Int = 0,
    val usedFallback: Boolean = false,
    val dataSources: List<String> = emptyList(),
)

data class AiPlanGenerationResponse(
    val requestId: String,
    val title: String,
    val destination: String,
    val dateRange: String,
    val dayCount: Int,
    val transportPreference: String = "MIXED",
    val preferences: List<String> = emptyList(),
    val days: List<AiGeneratedDay> = emptyList(),
    val warnings: List<String> = emptyList(),
    val generatedAt: String,
    val model: String? = null,
    val quality: AiPlanQuality = AiPlanQuality(),
    val enrichmentBatchId: String? = null,
)

data class AiPlanProgressEvent(
    val sequence: Int,
    val type: String,
    val message: String,
    val dayIndex: Int? = null,
    val placeId: String? = null,
    val evidence: List<String> = emptyList(),
    val decision: String? = null,
    val createdAt: String,
)

data class AiPlanJobStatusResponse(
    val jobId: String,
    val status: String,
    val progress: Int,
    val stage: String,
    val completedDays: Int = 0,
    val totalDays: Int,
    val activeDayIndex: Int? = null,
    val partialDays: List<AiGeneratedDay> = emptyList(),
    val events: List<AiPlanProgressEvent> = emptyList(),
    val result: AiPlanGenerationResponse? = null,
    val error: String? = null,
    val createdAt: String,
    val updatedAt: String,
)
