package com.heoclub.aitravel.ui.assistant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiDayContext
import com.heoclub.aitravel.data.model.AiHistoryMessage
import com.heoclub.aitravel.data.model.AiPlaceContext
import com.heoclub.aitravel.data.model.AiPlanContext
import com.heoclub.aitravel.data.model.AiCard
import com.heoclub.aitravel.data.model.AiSuggestedAction
import com.heoclub.aitravel.data.model.AiGeneratedDay
import com.heoclub.aitravel.data.model.AiGeneratedPlace
import com.heoclub.aitravel.data.model.AiPlanGenerationRequest
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.AiRecommendedPlace
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.AiConversationHistoryStore
import com.heoclub.aitravel.data.repository.AiConversationMessageRecord
import com.heoclub.aitravel.data.repository.AiConversationRecord
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import android.util.Log
import java.util.UUID

data class ChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val text: String,
    val fromUser: Boolean,
    val recommendedPlaces: List<AiRecommendedPlace> = emptyList(),
    val retrievalCity: String? = null,
    val offerPlan: Boolean = false,
    val originalQuestion: String? = null,
)

data class AiActionCardUi(
    val action: AiSuggestedAction,
    val placeName: String,
    val summary: String,
    val reason: String?,
    val selected: Boolean = true,
)

data class AiActionSetUi(
    val actionSetId: String,
    val planRevision: Long?,
    val cards: List<AiActionCardUi>,
    val warnings: List<String> = emptyList(),
)

data class AiAssistantUiState(
    val currentPlan: TravelPlan? = null,
    val messages: List<ChatMessage> = emptyList(),
    val quickReplies: List<String> = defaultQuickReplies,
    val isSending: Boolean = false,
    val isStreaming: Boolean = false,
    val streamingText: String = "",
    val isApplyingActions: Boolean = false,
    val errorMessage: String? = null,
    val actionSet: AiActionSetUi? = null,
    val actionMessage: String? = null,
    val actionWarnings: List<String> = emptyList(),
    val undoToken: String? = null,
    val cards: List<AiCard> = emptyList(),
    val generatedPlan: AiPlanGenerationResponse? = null,
    val generatedPlanExpanded: Boolean = false,
    val isGeneratingPlan: Boolean = false,
    val generationProgress: Int = 0,
    val generationStage: String? = null,
    val planningError: String? = null,
    val savedGeneratedPlanId: String? = null,
    val planSetupRequest: String? = null,
    val conversationHistories: List<AiConversationRecord> = emptyList(),
    val activeConversationId: String? = null,
)

private val defaultQuickReplies = listOf(
    "帮我看看 DAY 1 会不会太赶",
    "待规划地点应该放到哪一天",
    "帮我优化一下当天顺序",
)

class AiAssistantViewModel(
    private val initialQuestion: String?,
    private val planId: String?,
    private val travelPlanRepository: TravelPlanRepository,
    private val aiRepository: AiRepository,
    private val exploreRepository: ExploreRepository,
    private val conversationHistoryStore: AiConversationHistoryStore,
    private val onNavigateToCreatePlan: () -> Unit = {},
    private val onNavigateToPlaceDetail: (String) -> Unit = {},
    private val onNavigateToPlanDetail: (String) -> Unit = {},
) : ViewModel() {
    private var conversationId: String? = null
    private var lastFailedInput: String? = null
    private var activePlanId: String? = planId
    private var activeHistoryId: String = UUID.randomUUID().toString()
    private var historyReady = false

    private val _uiState = MutableStateFlow(
        AiAssistantUiState(
            currentPlan = planId?.let(travelPlanRepository::getPlan),
            messages = listOf(buildGreeting(planId?.let(travelPlanRepository::getPlan))),
        ),
    )
    val uiState: StateFlow<AiAssistantUiState> = _uiState.asStateFlow()

    init {
        restoreConversationHistory()
        observeConversationPersistence()
        observePlanChanges()
        if (!initialQuestion.isNullOrBlank()) {
            startNewConversation()
            sendMessage(initialQuestion)
        }
    }

    fun startNewConversation() {
        historyReady = false
        activeHistoryId = UUID.randomUUID().toString()
        conversationId = null
        activePlanId = planId
        val currentPlan = planId?.let(travelPlanRepository::getPlan)
        _uiState.update { state ->
            AiAssistantUiState(
                currentPlan = currentPlan,
                messages = listOf(buildGreeting(currentPlan)),
                conversationHistories = state.conversationHistories,
                activeConversationId = activeHistoryId,
            )
        }
        historyReady = true
    }

    fun openConversation(conversationIdToOpen: String) {
        val record = conversationHistoryStore.loadAll().firstOrNull { it.id == conversationIdToOpen } ?: return
        historyReady = false
        activeHistoryId = record.id
        conversationId = record.remoteConversationId
        activePlanId = record.planId
        val restoredMessages = record.messages.map { it.toChatMessage() }
        restoredMessages.flatMap { it.recommendedPlaces }.forEach { exploreRepository.upsertPlace(it.toPlaceSummary()) }
        _uiState.update {
            AiAssistantUiState(
                currentPlan = activePlanId?.let(travelPlanRepository::getPlan),
                messages = restoredMessages.ifEmpty { listOf(buildGreeting(null)) },
                conversationHistories = conversationHistoryStore.loadAll(),
                activeConversationId = activeHistoryId,
            )
        }
        historyReady = true
    }

    fun deleteConversation(conversationIdToDelete: String) {
        conversationHistoryStore.delete(conversationIdToDelete)
        if (conversationIdToDelete == activeHistoryId) {
            startNewConversation()
        }
        _uiState.update {
            it.copy(conversationHistories = conversationHistoryStore.loadAll())
        }
    }

    fun sendMessage(input: String) {
        val cleanInput = input.trim()
        if (cleanInput.isBlank() || _uiState.value.isSending) return

        val history = buildHistory(_uiState.value.messages)
        _uiState.update { state ->
            state.copy(
                messages = state.messages + ChatMessage(text = cleanInput, fromUser = true),
                isSending = true,
                errorMessage = null,
                actionMessage = null,
                actionSet = null,
                planSetupRequest = null,
            )
        }

        viewModelScope.launch {
            val currentPlan = activePlanId?.let(travelPlanRepository::getPlan)
            val request = AiChatRequest(
                conversationId = conversationId,
                planId = activePlanId,
                message = cleanInput,
                history = history,
                context = buildPlanContext(currentPlan),
            )

            _uiState.update { it.copy(isStreaming = true, streamingText = "") }

            aiRepository.chatStream(
                request = request,
                onChunk = { chunk ->
                    _uiState.update { it.copy(streamingText = it.streamingText + chunk) }
                },
                onDone = { response ->
                    Log.e("AiAssistant", "Stream done: cards=${response.cards.size}, actions=${response.suggestedActions.size}, textLen=${response.message.length}")
                    conversationId = response.conversationId
                    lastFailedInput = null
                    val latestPlan = activePlanId?.let(travelPlanRepository::getPlan)
                    val actionSet = buildActionSet(
                        plan = latestPlan,
                        actionSetId = response.actionSetId,
                        planRevision = response.planRevision,
                        actions = response.suggestedActions,
                        warnings = response.actionWarnings,
                    )
                    val staleWarning = if (
                        actionSet != null &&
                        latestPlan != null &&
                        response.planRevision != null &&
                        response.planRevision != latestPlan.revision
                    ) {
                        "AI 建议基于旧版本计划生成，请重新发送需求生成新建议。"
                    } else {
                        null
                    }

                    val responseCards = if (staleWarning == null) response.cards else emptyList()
                    val shouldOfferPlanSetup = activePlanId == null && isExplicitPlanCreationRequest(cleanInput)
                    val setupRequest = buildPlanningHandoff(cleanInput, response.retrievalCity, response.recommendedPlaces)
                    upsertRecommendedPlaces(response.recommendedPlaces)

                    _uiState.update { state ->
                        state.copy(
                            currentPlan = latestPlan,
                            messages = state.messages + ChatMessage(
                                text = response.message,
                                fromUser = false,
                                recommendedPlaces = response.recommendedPlaces,
                                retrievalCity = response.retrievalCity,
                                offerPlan = response.offerPlan && !shouldOfferPlanSetup,
                                originalQuestion = cleanInput,
                            ),
                            quickReplies = response.quickReplies.ifEmpty { defaultQuickReplies },
                            isSending = false,
                            isStreaming = false,
                            streamingText = "",
                            errorMessage = null,
                            actionSet = if (staleWarning == null) actionSet else null,
                            actionMessage = staleWarning,
                            actionWarnings = response.actionWarnings,
                            cards = responseCards,
                            planSetupRequest = if (shouldOfferPlanSetup) setupRequest else state.planSetupRequest,
                        )
                    }
                },
                onError = { error ->
                    Log.e("AiAssistant", "Stream error, falling back: $error")
                    viewModelScope.launch {
                        fallbackToNonStreaming(request, cleanInput)
                    }
                },
            )
        }
    }

    private suspend fun fallbackToNonStreaming(request: AiChatRequest, cleanInput: String) {
        Log.e("AiAssistant", "Falling back to non-streaming")
        val result = aiRepository.chat(request)
        result.onSuccess { response ->
            Log.e("AiAssistant", "Non-stream success: cards=${response.cards.size}, actions=${response.suggestedActions.size}")
            conversationId = response.conversationId
            lastFailedInput = null
            val latestPlan = activePlanId?.let(travelPlanRepository::getPlan)
            val actionSet = buildActionSet(
                plan = latestPlan,
                actionSetId = response.actionSetId,
                planRevision = response.planRevision,
                actions = response.suggestedActions,
                warnings = response.actionWarnings,
            )
            val staleWarning = if (
                actionSet != null &&
                latestPlan != null &&
                response.planRevision != null &&
                response.planRevision != latestPlan.revision
            ) {
                "AI 建议基于旧版本计划生成，请重新发送需求生成新建议。"
            } else {
                null
            }

            val responseCards = if (staleWarning == null) response.cards else emptyList()
            val shouldOfferPlanSetup = activePlanId == null && isExplicitPlanCreationRequest(cleanInput)
            val setupRequest = buildPlanningHandoff(cleanInput, response.retrievalCity, response.recommendedPlaces)
            upsertRecommendedPlaces(response.recommendedPlaces)

            _uiState.update { state ->
                state.copy(
                    currentPlan = latestPlan,
                    messages = state.messages + ChatMessage(
                        text = response.message,
                        fromUser = false,
                        recommendedPlaces = response.recommendedPlaces,
                        retrievalCity = response.retrievalCity,
                        offerPlan = response.offerPlan && !shouldOfferPlanSetup,
                        originalQuestion = cleanInput,
                    ),
                    quickReplies = response.quickReplies.ifEmpty { defaultQuickReplies },
                    isSending = false,
                    isStreaming = false,
                    streamingText = "",
                    errorMessage = null,
                    actionSet = if (staleWarning == null) actionSet else null,
                    actionMessage = staleWarning,
                    actionWarnings = response.actionWarnings,
                    cards = responseCards,
                    planSetupRequest = if (shouldOfferPlanSetup) setupRequest else state.planSetupRequest,
                )
            }
        }.onFailure { throwable ->
            lastFailedInput = cleanInput
            _uiState.update { state ->
                state.copy(
                    isSending = false,
                    isStreaming = false,
                    streamingText = "",
                    errorMessage = throwable.message ?: "AI 暂时没有回复，请稍后重试。",
                )
            }
        }
    }

    fun retryLastMessage() {
        val retryInput = lastFailedInput ?: return
        _uiState.update { state -> state.copy(errorMessage = null) }
        sendMessage(retryInput)
    }

    fun toggleAction(actionId: String) {
        _uiState.update { state ->
            val actionSet = state.actionSet ?: return@update state
            state.copy(
                actionSet = actionSet.copy(
                    cards = actionSet.cards.map { card ->
                        if (card.action.id == actionId) {
                            card.copy(selected = !card.selected)
                        } else {
                            card
                        }
                    },
                ),
            )
        }
    }

    fun clearSuggestedActions() {
        _uiState.update {
            it.copy(
                actionSet = null,
                cards = it.cards.filter { c -> c.type != "ITINERARY_OPTIMIZATION" },
                actionMessage = "已取消本轮 AI 建议。",
            )
        }
    }

    fun applySuggestedActions() {
        val state = _uiState.value
        val plan = state.currentPlan ?: return
        val actionSet = state.actionSet
        if (actionSet == null) {
            val warnings = state.actionWarnings
            val msg = if (warnings.isNotEmpty()) {
                "AI 建议无法执行：${warnings.joinToString("；")}"
            } else {
                "AI 未生成可执行的调整动作，请重新描述需求。"
            }
            _uiState.update { it.copy(actionMessage = msg) }
            return
        }
        val selectedActions = actionSet.cards.filter { it.selected }.map { it.action }
        if (selectedActions.isEmpty()) {
            _uiState.update { it.copy(actionMessage = "请至少选择一条建议后再应用。") }
            return
        }
        if (actionSet.planRevision != null && actionSet.planRevision != plan.revision) {
            _uiState.update {
                it.copy(
                    actionSet = null,
                    actionMessage = "计划已经发生变化，请重新生成 AI 建议。",
                )
            }
            return
        }

        _uiState.update { it.copy(isApplyingActions = true, actionMessage = null) }
        viewModelScope.launch {
            val result = travelPlanRepository.applyAiSuggestedActions(
                planId = plan.id,
                expectedRevision = actionSet.planRevision,
                actions = selectedActions,
            )
            val latestPlan = travelPlanRepository.getPlan(plan.id)
            _uiState.update { current ->
                current.copy(
                    currentPlan = latestPlan,
                    isApplyingActions = false,
                    actionSet = if (result.success) null else current.actionSet,
                    cards = if (result.success) current.cards.filter { it.type != "ITINERARY_OPTIMIZATION" } else current.cards,
                    undoToken = result.undoToken,
                    actionMessage = result.message,
                )
            }
        }
    }

    fun undoLastAiAction() {
        val plan = _uiState.value.currentPlan ?: return
        val token = _uiState.value.undoToken ?: return
        val result = travelPlanRepository.undoLastAiAction(plan.id, token)
        _uiState.update {
            it.copy(
                currentPlan = travelPlanRepository.getPlan(plan.id),
                undoToken = if (result.success) null else it.undoToken,
                actionMessage = result.message,
            )
        }
    }

    fun onLinkCardClicked() {
        onNavigateToCreatePlan()
    }

    fun onItineraryPlaceClicked(placeId: String) {
        onNavigateToPlaceDetail(placeId)
    }

    fun confirmItineraryCard() {
        applySuggestedActions()
    }

    fun dismissItineraryCard() {
        _uiState.update { state ->
            state.copy(
                cards = state.cards.filter { it.type != "ITINERARY_OPTIMIZATION" },
                actionSet = null,
            )
        }
    }

    fun generateTripPlan(
        destination: String,
        dateRange: String,
        dayCount: Int,
        pace: String,
        requestText: String,
    ) {
        if (destination.isBlank() || dateRange.isBlank() || dayCount !in 1..10 || _uiState.value.isGeneratingPlan) return
        _uiState.update {
            it.copy(
                isGeneratingPlan = true,
                generationProgress = 0,
                generationStage = "正在理解你的旅行偏好",
                planningError = null,
                generatedPlan = null,
                savedGeneratedPlanId = null,
                planSetupRequest = null,
            )
        }
        viewModelScope.launch {
            val request = AiPlanGenerationRequest(
                destination = destination.trim(),
                dateRange = dateRange,
                dayCount = dayCount,
                preferences = listOf(
                    when (pace) {
                        "RELAXED" -> "轻松悠闲，不赶路"
                        "INTENSIVE" -> "紧凑充实，多打卡"
                        else -> "节奏适中，景点与美食兼顾"
                    },
                ),
                freeText = requestText.trim().takeIf { it.isNotBlank() },
                pace = pace,
                clientRequestId = UUID.randomUUID().toString(),
            )
            var completed: AiPlanGenerationResponse? = null
            try {
                aiRepository.streamPlan(request).collect { snapshot ->
                    when (snapshot.status) {
                        "COMPLETED" -> completed = snapshot.result
                        "FAILED" -> throw IllegalStateException(snapshot.error ?: "智能规划失败，请稍后重试。")
                        "CANCELLED" -> throw IllegalStateException("智能规划已取消。")
                        else -> {
                            upsertGeneratedPlaces(snapshot.partialDays)
                            _uiState.update {
                                it.copy(
                                    generationProgress = snapshot.progress,
                                    generationStage = snapshot.stage,
                                )
                            }
                        }
                    }
                }
                val result = completed ?: throw IllegalStateException("规划已结束，但没有返回可用行程。")
                if (result.days.isEmpty()) throw IllegalStateException("没有生成可用行程，请调整条件后重试。")
                upsertGeneratedPlaces(result.days)
                _uiState.update {
                    it.copy(
                        generatedPlan = result,
                        generatedPlanExpanded = false,
                        isGeneratingPlan = false,
                        generationProgress = 100,
                        generationStage = null,
                        planningError = null,
                        messages = it.messages + ChatMessage(
                            text = "智能规划已经按你确认的日期和旅行节奏生成了「${result.title}」。蓝色地点可以直接查看详情；确认后可一键保存到计划页并继续编辑。",
                            fromUser = false,
                        ),
                    )
                }
            } catch (error: Exception) {
                _uiState.update {
                    it.copy(
                        isGeneratingPlan = false,
                        generationStage = null,
                        planningError = error.message ?: "智能规划暂时不可用，请稍后重试。",
                    )
                }
            }
        }
    }

    fun toggleGeneratedPlanExpanded() {
        _uiState.update { it.copy(generatedPlanExpanded = !it.generatedPlanExpanded) }
    }

    fun saveGeneratedPlan() {
        val generated = _uiState.value.generatedPlan ?: return
        val existingId = _uiState.value.savedGeneratedPlanId
        if (existingId != null) {
            onNavigateToPlanDetail(existingId)
            return
        }
        val plan = travelPlanRepository.importGeneratedPlan(generated)
        activePlanId = plan.id
        _uiState.update {
            it.copy(
                currentPlan = plan,
                savedGeneratedPlanId = plan.id,
                actionMessage = "已加入计划页，你可以继续调整日期、地点和顺序。",
            )
        }
        onNavigateToPlanDetail(plan.id)
    }

    fun openGeneratedPlace(placeId: String) {
        onNavigateToPlaceDetail(placeId)
    }

    fun openRecommendedPlace(placeId: String) {
        onNavigateToPlaceDetail(placeId)
    }

    fun requestPlanFromRecommendation(messageId: String) {
        val message = _uiState.value.messages.firstOrNull { it.id == messageId } ?: return
        val originalQuestion = message.originalQuestion ?: return
        val request = buildPlanningHandoff(originalQuestion, message.retrievalCity, message.recommendedPlaces)
        _uiState.update { state ->
            state.copy(
                planSetupRequest = request,
                messages = state.messages.map {
                    if (it.id == messageId) it.copy(offerPlan = false) else it
                },
            )
        }
    }

    fun dismissPlanOffer(messageId: String) {
        _uiState.update { state ->
            state.copy(
                messages = state.messages.map {
                    if (it.id == messageId) it.copy(offerPlan = false) else it
                },
            )
        }
    }

    private fun upsertGeneratedPlaces(days: List<AiGeneratedDay>) {
        days.flatMap { it.places }.forEach { exploreRepository.upsertPlace(it.toPlaceSummary()) }
    }

    private fun upsertRecommendedPlaces(places: List<AiRecommendedPlace>) {
        places.forEach { exploreRepository.upsertPlace(it.toPlaceSummary()) }
    }

    private fun buildPlanningHandoff(
        originalQuestion: String,
        retrievalCity: String?,
        places: List<AiRecommendedPlace>,
    ): String {
        if (retrievalCity.isNullOrBlank()) return originalQuestion
        val placeNames = places.take(6).joinToString("、") { it.name }
        val placeHint = if (placeNames.isBlank()) "" else "。优先考虑这些高德真实地点：$placeNames"
        return "去${retrievalCity}旅行。用户原始需求：$originalQuestion$placeHint"
    }

    private fun AiRecommendedPlace.toPlaceSummary(): PlaceSummary {
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
            distanceMeters = distanceMeters,
            phone = phone,
            rating = rating,
            costAverage = costAverage,
            coverImageUrl = coverImageUrl,
            imageUrls = imageUrls,
            businessArea = businessArea,
            openingHoursToday = openingHoursToday,
            openingHoursWeek = openingHoursWeek,
        )
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

    private fun restoreConversationHistory() {
        val histories = conversationHistoryStore.loadAll()
        val restored = if (initialQuestion.isNullOrBlank()) {
            histories.firstOrNull { it.planId == planId }
        } else {
            null
        }
        if (restored != null) {
            activeHistoryId = restored.id
            conversationId = restored.remoteConversationId
            activePlanId = restored.planId
            val messages = restored.messages.map { it.toChatMessage() }
            messages.flatMap { it.recommendedPlaces }.forEach { exploreRepository.upsertPlace(it.toPlaceSummary()) }
            _uiState.update {
                it.copy(
                    currentPlan = activePlanId?.let(travelPlanRepository::getPlan),
                    messages = messages.ifEmpty { listOf(buildGreeting(null)) },
                    conversationHistories = histories,
                    activeConversationId = activeHistoryId,
                )
            }
        } else {
            _uiState.update {
                it.copy(
                    conversationHistories = histories,
                    activeConversationId = activeHistoryId,
                )
            }
        }
        historyReady = true
    }

    private fun observeConversationPersistence() {
        viewModelScope.launch {
            _uiState
                .map { it.messages }
                .distinctUntilChanged()
                .collect { messages ->
                    if (!historyReady || messages.none { it.fromUser }) return@collect
                    val title = messages.firstOrNull { it.fromUser }
                        ?.text
                        ?.replace("\n", " ")
                        ?.trim()
                        ?.take(26)
                        ?.ifBlank { "新的旅行对话" }
                        ?: "新的旅行对话"
                    conversationHistoryStore.upsert(
                        AiConversationRecord(
                            id = activeHistoryId,
                            title = title,
                            messages = messages.map { it.toHistoryRecord() },
                            remoteConversationId = conversationId,
                            planId = activePlanId,
                            updatedAt = System.currentTimeMillis(),
                        ),
                    )
                    _uiState.update {
                        it.copy(
                            conversationHistories = conversationHistoryStore.loadAll(),
                            activeConversationId = activeHistoryId,
                        )
                    }
                }
        }
    }

    private fun ChatMessage.toHistoryRecord(): AiConversationMessageRecord {
        return AiConversationMessageRecord(
            id = id,
            text = text,
            fromUser = fromUser,
            recommendedPlaces = recommendedPlaces,
            retrievalCity = retrievalCity,
            offerPlan = offerPlan,
            originalQuestion = originalQuestion,
        )
    }

    private fun AiConversationMessageRecord.toChatMessage(): ChatMessage {
        return ChatMessage(
            id = id,
            text = text,
            fromUser = fromUser,
            recommendedPlaces = recommendedPlaces,
            retrievalCity = retrievalCity,
            offerPlan = offerPlan,
            originalQuestion = originalQuestion,
        )
    }

    private fun observePlanChanges() {
        viewModelScope.launch {
            travelPlanRepository.plans.collect { plans ->
                val latestPlan = activePlanId?.let { id -> plans.firstOrNull { it.id == id } }
                _uiState.update { state ->
                    if (state.currentPlan?.revision == latestPlan?.revision) {
                        state
                    } else {
                        state.copy(currentPlan = latestPlan)
                    }
                }
            }
        }
    }

    private fun buildGreeting(plan: TravelPlan?): ChatMessage {
        val text = if (plan != null) {
            "你好，我已经读取「${plan.title}」这个计划。你可以让我分析行程节奏、安排待规划地点，或给出需要你确认的调整建议。"
        } else {
            "你好，我是你的 AI 旅行助手。目的地、美食、景点、交通、住宿、预算和旅行准备都可以直接问我；如果你要生成完整计划，我会帮你把需求交给智能规划。"
        }
        return ChatMessage(text = text, fromUser = false)
    }

    private fun isExplicitPlanCreationRequest(input: String): Boolean {
        val normalized = input.replace(" ", "")
        if (Regex("(?:一|二|两|三|四|五|六|七|八|九|十|\\d+)日游").containsMatchIn(normalized)) return true
        if ("旅游规划" in normalized || "旅行规划" in normalized || "行程计划" in normalized) return true
        return Regex("(?:制定|生成|规划|安排|设计|做).{0,8}(?:旅行计划|旅游计划|计划|行程)")
            .containsMatchIn(normalized)
    }

    private fun buildHistory(messages: List<ChatMessage>): List<AiHistoryMessage> {
        return messages
            .takeLast(8)
            .map {
                AiHistoryMessage(
                    role = if (it.fromUser) "user" else "assistant",
                    content = it.text.take(500),
                )
            }
    }

    private fun buildPlanContext(plan: TravelPlan?): AiPlanContext? {
        if (plan == null) return null
        return AiPlanContext(
            id = plan.id,
            title = plan.title,
            destination = plan.destination,
            dateRange = plan.dateRange,
            revision = plan.revision,
            updatedAt = plan.updatedAt,
            days = plan.days.map { day ->
                AiDayContext(
                    dayIndex = day.dayIndex,
                    title = day.title,
                    places = day.items.sortedBy { it.visitOrder }.map { it.toAiPlaceContext() },
                )
            },
            unplannedPlaces = plan.unplannedItems.sortedBy { it.visitOrder }.map {
                it.toAiPlaceContext()
            },
        )
    }

    private fun PlanItem.toAiPlaceContext(): AiPlaceContext {
        return AiPlaceContext(
            itemId = id,
            sourcePoiId = sourcePoiId,
            name = name,
            category = category,
            typeName = typeName,
            address = address,
            cityName = cityName,
            districtName = districtName,
            imageUrl = thumbnailUrl ?: imageUrls.firstOrNull(),
            dayIndex = dayIndex,
            visitOrder = visitOrder,
            suggestedStart = suggestedStart,
            suggestedEnd = suggestedEnd,
        )
    }

    private fun buildActionSet(
        plan: TravelPlan?,
        actionSetId: String?,
        planRevision: Long?,
        actions: List<AiSuggestedAction>,
        warnings: List<String>,
    ): AiActionSetUi? {
        if (plan == null || actionSetId == null || actions.isEmpty()) return null
        val allItems = plan.days.flatMap { it.items } + plan.unplannedItems
        val itemById = allItems.associateBy { it.id }
        val cards = actions.mapNotNull { action ->
            val item = itemById[action.placeItemId] ?: return@mapNotNull null
            AiActionCardUi(
                action = action,
                placeName = item.name,
                summary = action.toSummary(item),
                reason = action.reason,
            )
        }
        if (cards.isEmpty()) return null
        return AiActionSetUi(
            actionSetId = actionSetId,
            planRevision = planRevision,
            cards = cards,
            warnings = warnings,
        )
    }

    private fun AiSuggestedAction.toSummary(item: PlanItem): String {
        return when (type) {
            "MOVE_PLACE_TO_DAY" -> "把「${item.name}」移动到 DAY ${toDayIndex ?: "?"} 的第 ${toPosition ?: "末"} 位"
            "ASSIGN_UNPLANNED_PLACE" -> "把待规划地点「${item.name}」安排到 DAY ${toDayIndex ?: "?"}"
            "REORDER_PLACE" -> "把「${item.name}」调整到 DAY ${toDayIndex ?: item.dayIndex} 的第 ${toPosition ?: "?"} 位"
            "MOVE_TO_UNPLANNED" -> "把「${item.name}」移回待规划"
            else -> "调整「${item.name}」"
        }
    }

    class Factory(
        private val initialQuestion: String?,
        private val planId: String?,
        private val travelPlanRepository: TravelPlanRepository,
        private val aiRepository: AiRepository,
        private val exploreRepository: ExploreRepository,
        private val conversationHistoryStore: AiConversationHistoryStore,
        private val onNavigateToCreatePlan: () -> Unit = {},
        private val onNavigateToPlaceDetail: (String) -> Unit = {},
        private val onNavigateToPlanDetail: (String) -> Unit = {},
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(AiAssistantViewModel::class.java)) {
                return AiAssistantViewModel(
                    initialQuestion = initialQuestion,
                    planId = planId,
                    travelPlanRepository = travelPlanRepository,
                    aiRepository = aiRepository,
                    exploreRepository = exploreRepository,
                    conversationHistoryStore = conversationHistoryStore,
                    onNavigateToCreatePlan = onNavigateToCreatePlan,
                    onNavigateToPlaceDetail = onNavigateToPlaceDetail,
                    onNavigateToPlanDetail = onNavigateToPlanDetail,
                ) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
