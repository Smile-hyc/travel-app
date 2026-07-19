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
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

data class AiPlanDraftInput(
    val destination: String,
    val dateRange: String,
    val dayCount: Int,
    val preferences: List<String>,
    val freeText: String? = null,
    val arrivalStation: String? = null,
    val arrivalDay: Int = 1,
    val arrivalTime: String? = null,
    val departureStation: String? = null,
    val departureDay: Int? = null,
    val departureTime: String? = null,
    val hotelName: String? = null,
    val hotelStays: List<AiHotelStayInput> = emptyList(),
    val pace: String = "BALANCED",
    val transportPreference: String = "MIXED",
    val dailyStart: String = "09:00",
    val dailyEnd: String = "20:00",
)

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

    data class Error(val message: String) : AiPlanGenerationUiState
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
    private var activeJobId: String? = null

    init {
        generate()
    }

    fun retry() {
        generate()
    }

    fun cancel() {
        generationJob?.cancel()
        activeJobId = null
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
                arrivalDay = input.arrivalDay,
                arrivalTime = input.arrivalTime,
                departureStation = input.departureStation,
                departureDay = input.departureDay,
                departureTime = input.departureTime,
                hotelName = input.hotelName,
                hotelStays = input.hotelStays,
                pace = input.pace,
                transportPreference = input.transportPreference,
                dailyStart = input.dailyStart,
                dailyEnd = input.dailyEnd,
                clientRequestId = UUID.randomUUID().toString(),
            )
            var result: AiPlanGenerationResponse? = null
            try {
                aiRepository.streamPlan(request).collect { snapshot ->
                    activeJobId = snapshot.jobId
                    when (snapshot.status) {
                        "COMPLETED" -> result = snapshot.result
                        "FAILED" -> _uiState.value = AiPlanGenerationUiState.Error(
                            snapshot.error ?: "智能规划任务失败，请调整条件后重试。",
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
            } catch (error: Exception) {
                _uiState.value = AiPlanGenerationUiState.Error(
                    error.message ?: "智能规划流中断，请检查后端连接后重试。",
                )
                return@launch
            }
            activeJobId = null
            val completedResult = result
            if (completedResult == null) {
                if (_uiState.value !is AiPlanGenerationUiState.Error) {
                    _uiState.value = AiPlanGenerationUiState.Error("规划流已结束，但没有返回可用行程。")
                }
                return@launch
            }
            upsertGeneratedPlaces(completedResult.days)

            if (completedResult.days.isEmpty()) {
                _uiState.value = AiPlanGenerationUiState.Error(
                    "没有生成可用的每日行程，请调整目的地或天数后重试。",
                )
                return@launch
            }

            val plan = travelPlanRepository.importGeneratedPlan(completedResult)
            _uiState.value = AiPlanGenerationUiState.Ready(
                result = completedResult,
                visibleDayCount = completedResult.days.size,
                savedPlanId = plan.id,
            )
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
