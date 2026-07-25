package com.heoclub.aitravel.ui.createplan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.AiPlanGenerationRequest
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.AiGeneratedDay
import com.heoclub.aitravel.data.model.AiPlanProgressEvent
import com.heoclub.aitravel.data.model.AiGeneratedPlace
import com.heoclub.aitravel.data.model.AiHotelStayInput
import com.heoclub.aitravel.data.model.AiMapPointInput
import com.heoclub.aitravel.data.model.AiPlanQuality
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Instant
import java.util.UUID

data class AiPlanDraftInput(
    val destination: String,
    val dateRange: String,
    val dayCount: Int,
    val preferences: List<String>,
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
)

internal fun canonicalPlanningMode(value: String?): String =
    if (value?.uppercase() == "FAST") "FAST" else "REQUIRED"

sealed interface AiPlanGenerationUiState {
    data class Loading(
        val progress: Int = 0,
        val stage: String = "正在创建智能规划任务",
        val completedDays: Int = 0,
        val totalDays: Int = 0,
        val activeDayIndex: Int? = null,
        val partialDays: List<AiGeneratedDay> = emptyList(),
        val events: List<AiPlanProgressEvent> = emptyList(),
    ) : AiPlanGenerationUiState

    data class Ready(
        val result: AiPlanGenerationResponse,
        val visibleDayCount: Int,
        val savedPlanId: String,
    ) : AiPlanGenerationUiState

    data class Error(
        val message: String,
        val completedDays: Int = 0,
        val totalDays: Int = 0,
        val partialDays: List<AiGeneratedDay> = emptyList(),
        val events: List<AiPlanProgressEvent> = emptyList(),
    ) : AiPlanGenerationUiState
}

class AiPlanGenerationViewModel(
    private val input: AiPlanDraftInput,
    private val aiRepository: AiRepository,
    private val travelPlanRepository: TravelPlanRepository,
    private val exploreRepository: ExploreRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow<AiPlanGenerationUiState>(AiPlanGenerationUiState.Loading())
    val uiState: StateFlow<AiPlanGenerationUiState> = _uiState.asStateFlow()

    private var generationJob: Job? = null
    private var enrichmentJob: Job? = null
    private var activeJobId: String? = null

    init {
        generate()
    }

    fun retry() {
        generate()
    }

    fun cancel() {
        generationJob?.cancel()
        enrichmentJob?.cancel()
        activeJobId = null
    }

    fun useCurrentDraftWithoutAi(): Boolean {
        val state = _uiState.value
        val partialDays = when (state) {
            is AiPlanGenerationUiState.Loading -> state.partialDays
            is AiPlanGenerationUiState.Error -> state.partialDays
            else -> return false
        }
        val completedDays = when (state) {
            is AiPlanGenerationUiState.Loading -> state.completedDays
            is AiPlanGenerationUiState.Error -> state.completedDays
            else -> 0
        }
        val days = partialDays
            .sortedBy { it.dayIndex }
            .filter { it.places.isNotEmpty() }
        if (days.isEmpty() || completedDays < input.dayCount) return false

        generationJob?.cancel()
        generationJob = null
        activeJobId = null
        val allPlaces = days.flatMap { it.places }
        val result = AiPlanGenerationResponse(
            requestId = UUID.randomUUID().toString(),
            title = "${input.destination.trim().trimEnd('市')} ${input.dayCount} 日约束行程",
            destination = input.destination.trim(),
            dateRange = input.dateRange,
            dayCount = input.dayCount,
            transportPreference = input.transportPreference,
            preferences = input.preferences,
            days = days,
            warnings = listOf("已使用当前方案，行程已结合天气、开放时间与实际通勤安排。"),
            generatedAt = Instant.now().toString(),
            model = null,
            quality = AiPlanQuality(
                realPoiRatio = 1.0,
                duplicatePlaceCount = allPlaces.size - allPlaces.distinctBy { it.sourcePoiId }.size,
                totalPlaceCount = allPlaces.size,
                usedFallback = true,
                dataSources = listOf("AMAP"),
            ),
        )
        upsertGeneratedPlaces(days)
        val plan = travelPlanRepository.importGeneratedPlan(result)
        _uiState.value = AiPlanGenerationUiState.Ready(
            result = result,
            visibleDayCount = days.size,
            savedPlanId = plan.id,
        )
        prepareAndObserveEnrichment(days)
        return true
    }

    private fun generate() {
        generationJob?.cancel()
        generationJob = viewModelScope.launch {
            _uiState.value = AiPlanGenerationUiState.Loading(totalDays = input.dayCount)
            val request = AiPlanGenerationRequest(
                destination = input.destination,
                dateRange = input.dateRange,
                dayCount = input.dayCount,
                preferences = input.preferences,
                freeText = input.freeText,
                arrivalStation = input.arrivalStation,
                arrivalPoint = input.arrivalPoint,
                arrivalDay = input.arrivalDay,
                arrivalTime = input.arrivalTime,
                departureStation = input.departureStation,
                departurePoint = input.departurePoint,
                departureDay = input.departureDay,
                departureTime = input.departureTime,
                hotelName = input.hotelName,
                hotelPoint = input.hotelPoint,
                hotelStays = input.hotelStays,
                optimizationMode = canonicalPlanningMode(input.optimizationMode),
                pace = input.pace,
                transportPreference = input.transportPreference,
                dailyStart = input.dailyStart,
                dailyEnd = input.dailyEnd,
                clientRequestId = UUID.randomUUID().toString(),
            )
            var result: AiPlanGenerationResponse? = null
            var latestPartialDays: List<AiGeneratedDay> = emptyList()
            var latestCompletedDays = 0
            var latestTotalDays = input.dayCount
            var latestEvents: List<AiPlanProgressEvent> = emptyList()
            try {
                aiRepository.streamPlan(request).collect { snapshot ->
                    activeJobId = snapshot.jobId
                    latestPartialDays = snapshot.partialDays
                    latestCompletedDays = snapshot.completedDays
                    latestTotalDays = snapshot.totalDays
                    latestEvents = snapshot.events
                    when (snapshot.status) {
                        "COMPLETED" -> result = snapshot.result
                        "FAILED" -> _uiState.value = AiPlanGenerationUiState.Error(
                            message = snapshot.error ?: "智能规划任务失败，请调整条件后重试。",
                            completedDays = snapshot.completedDays,
                            totalDays = snapshot.totalDays,
                            partialDays = snapshot.partialDays,
                            events = snapshot.events,
                        )
                        "CANCELLED" -> _uiState.value = AiPlanGenerationUiState.Error("智能规划已取消。")
                        else -> {
                            upsertGeneratedPlaces(snapshot.partialDays)
                            _uiState.value = AiPlanGenerationUiState.Loading(
                                progress = snapshot.progress,
                                stage = snapshot.stage,
                                completedDays = snapshot.completedDays,
                                totalDays = snapshot.totalDays,
                                activeDayIndex = snapshot.activeDayIndex,
                                partialDays = snapshot.partialDays,
                                events = snapshot.events,
                            )
                        }
                    }
                }
            } catch (_: CancellationException) {
                return@launch
            } catch (error: Exception) {
                _uiState.value = AiPlanGenerationUiState.Error(
                    message = error.message ?: "智能规划流中断，请检查后端连接后重试。",
                    completedDays = latestCompletedDays,
                    totalDays = latestTotalDays,
                    partialDays = latestPartialDays,
                    events = latestEvents,
                )
                return@launch
            }
            activeJobId = null
            val completedResult = result
            if (completedResult == null) {
                if (_uiState.value !is AiPlanGenerationUiState.Error) {
                    _uiState.value = AiPlanGenerationUiState.Error(
                        message = "规划流已结束，但没有返回可用行程。",
                        completedDays = latestCompletedDays,
                        totalDays = latestTotalDays,
                        partialDays = latestPartialDays,
                        events = latestEvents,
                    )
                }
                return@launch
            }
            upsertGeneratedPlaces(completedResult.days)

            if (completedResult.days.isEmpty()) {
                _uiState.value = AiPlanGenerationUiState.Error(
                    message = "没有生成可用的每日行程，请调整目的地或天数后重试。",
                    completedDays = latestCompletedDays,
                    totalDays = latestTotalDays,
                    partialDays = latestPartialDays,
                    events = latestEvents,
                )
                return@launch
            }

            val plan = travelPlanRepository.importGeneratedPlan(completedResult)
            _uiState.value = AiPlanGenerationUiState.Ready(
                result = completedResult,
                visibleDayCount = completedResult.days.size,
                savedPlanId = plan.id,
            )
            completedResult.enrichmentBatchId?.let(::observeEnrichment)
        }
    }

    private fun prepareAndObserveEnrichment(days: List<AiGeneratedDay>) {
        enrichmentJob?.cancel()
        enrichmentJob = viewModelScope.launch {
            runCatching {
                val places = days.flatMap { it.places }.map { it.toPlaceSummary() }
                exploreRepository.preparePlaceEnrichment(places).batchId
            }.onSuccess(::observeEnrichment)
        }
    }

    private fun observeEnrichment(batchId: String) {
        enrichmentJob?.cancel()
        enrichmentJob = viewModelScope.launch {
            runCatching {
                exploreRepository.streamPlaceEnrichment(batchId).collect { /* Repository merges by POI ID. */ }
            }
        }
    }

    private fun upsertGeneratedPlaces(days: List<AiGeneratedDay>) {
        days.flatMap { it.places }.forEach { place ->
            exploreRepository.upsertPlace(place.toPlaceSummary())
        }
    }

    private fun AiGeneratedPlace.toPlaceSummary(): PlaceSummary {
        return PlaceSummary(
            id = id,
            source = source,
            sourcePoiId = sourcePoiId,
            name = name,
            category = category,
            categoryCode = categoryCode,
            typeName = typeName,
            typeCode = typeCode,
            address = address,
            provinceName = provinceName,
            cityName = cityName,
            districtName = districtName,
            adCode = adCode,
            cityCode = cityCode,
            latitude = latitude,
            longitude = longitude,
            phone = phone,
            rating = rating,
            costAverage = costAverage,
            coverImageUrl = thumbnailUrl,
            imageUrls = imageUrls,
            businessArea = businessArea,
            openingHoursToday = openingHoursToday,
            openingHoursWeek = openingHoursWeek,
        )
    }

    class Factory(
        private val input: AiPlanDraftInput,
        private val aiRepository: AiRepository,
        private val travelPlanRepository: TravelPlanRepository,
        private val exploreRepository: ExploreRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(AiPlanGenerationViewModel::class.java)) {
                return AiPlanGenerationViewModel(input, aiRepository, travelPlanRepository, exploreRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
