package com.heoclub.aitravel.ui.assistant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiDayContext
import com.heoclub.aitravel.data.model.AiHistoryMessage
import com.heoclub.aitravel.data.model.AiPlaceContext
import com.heoclub.aitravel.data.model.AiPlanContext
import com.heoclub.aitravel.data.model.AiSuggestedAction
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AiRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class ChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val text: String,
    val fromUser: Boolean,
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
    val isApplyingActions: Boolean = false,
    val errorMessage: String? = null,
    val actionSet: AiActionSetUi? = null,
    val actionMessage: String? = null,
    val undoToken: String? = null,
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
) : ViewModel() {
    private var conversationId: String? = null
    private var lastFailedInput: String? = null

    private val _uiState = MutableStateFlow(
        AiAssistantUiState(
            currentPlan = planId?.let(travelPlanRepository::getPlan),
            messages = listOf(buildGreeting(planId?.let(travelPlanRepository::getPlan))),
        ),
    )
    val uiState: StateFlow<AiAssistantUiState> = _uiState.asStateFlow()

    init {
        observePlanChanges()
        if (!initialQuestion.isNullOrBlank()) {
            sendMessage(initialQuestion)
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
            )
        }

        viewModelScope.launch {
            val currentPlan = planId?.let(travelPlanRepository::getPlan)
            val request = AiChatRequest(
                conversationId = conversationId,
                planId = planId,
                message = cleanInput,
                history = history,
                context = buildPlanContext(currentPlan),
            )

            val result = aiRepository.chat(request)
            result.onSuccess { response ->
                conversationId = response.conversationId
                lastFailedInput = null
                val latestPlan = planId?.let(travelPlanRepository::getPlan)
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

                _uiState.update { state ->
                    state.copy(
                        currentPlan = latestPlan,
                        messages = state.messages + ChatMessage(
                            text = response.message,
                            fromUser = false,
                        ),
                        quickReplies = response.quickReplies.ifEmpty { defaultQuickReplies },
                        isSending = false,
                        errorMessage = null,
                        actionSet = if (staleWarning == null) actionSet else null,
                        actionMessage = staleWarning,
                    )
                }
            }.onFailure { throwable ->
                lastFailedInput = cleanInput
                _uiState.update { state ->
                    state.copy(
                        isSending = false,
                        errorMessage = throwable.message ?: "AI 暂时没有回复，请稍后重试。",
                    )
                }
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
                actionMessage = "已取消本轮 AI 建议。",
            )
        }
    }

    fun applySuggestedActions() {
        val state = _uiState.value
        val plan = state.currentPlan ?: return
        val actionSet = state.actionSet ?: return
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

    private fun observePlanChanges() {
        viewModelScope.launch {
            travelPlanRepository.plans.collect { plans ->
                val latestPlan = planId?.let { id -> plans.firstOrNull { it.id == id } }
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
            "你好，我是你的 AI 旅行助手。你可以问我目的地建议、旅行准备清单，或从某个计划详情页带着上下文来问。"
        }
        return ChatMessage(text = text, fromUser = false)
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
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(AiAssistantViewModel::class.java)) {
                return AiAssistantViewModel(
                    initialQuestion = initialQuestion,
                    planId = planId,
                    travelPlanRepository = travelPlanRepository,
                    aiRepository = aiRepository,
                ) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
