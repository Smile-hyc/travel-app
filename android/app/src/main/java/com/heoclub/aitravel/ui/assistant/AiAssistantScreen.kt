package com.heoclub.aitravel.ui.assistant

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.ClickableText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.ExpandLess
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Menu
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Route
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DateRangePicker
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDateRangePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.heoclub.aitravel.data.model.AiGeneratedDay
import com.heoclub.aitravel.data.model.AiGeneratedPlace
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.AiRecommendedPlace
import com.heoclub.aitravel.data.repository.AiConversationRecord
import com.heoclub.aitravel.ui.components.MarkdownText
import com.heoclub.aitravel.ui.components.PlaceCoverImage
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

private val AssistantBackground = Color(0xFFF7F7F5)
private val AssistantInk = Color(0xFF202124)
private val AssistantMuted = Color(0xFF74777C)
private val AssistantBlue = Color(0xFF247AA4)
private val UserBubble = Color(0xFFC5F4F7)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiAssistantScreen(
    viewModel: AiAssistantViewModel,
    onClose: () -> Unit,
) {
    val state by viewModel.uiState.collectAsState()
    val listState = rememberLazyListState()
    var input by remember { mutableStateOf("") }
    var destination by remember { mutableStateOf(state.currentPlan?.destination.orEmpty()) }
    var startDate by remember { mutableStateOf(LocalDate.now().plusDays(1)) }
    var endDate by remember { mutableStateOf(LocalDate.now().plusDays(2)) }
    var pace by remember { mutableStateOf("BALANCED") }
    var showDatePicker by remember { mutableStateOf(false) }
    var showConversationHistory by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(state.planSetupRequest) {
        state.planSetupRequest?.let { request ->
            if (destination.isBlank()) destination = inferDestination(request)
        }
    }

    LaunchedEffect(state.messages.size, state.streamingText, state.generatedPlan) {
        val lastIndex = listState.layoutInfo.totalItemsCount - 1
        if (lastIndex >= 0) listState.animateScrollToItem(lastIndex)
    }

    Surface(modifier = Modifier.fillMaxSize(), color = AssistantBackground) {
        Column(modifier = Modifier.fillMaxSize().imePadding()) {
            AssistantHeader(
                onClose = onClose,
                onOpenHistory = { showConversationHistory = true },
            )
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 20.dp,
                    end = 20.dp,
                    top = 18.dp,
                    bottom = 18.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                items(state.messages, key = { it.id }) { message ->
                    MessageBlock(
                        message = message,
                        onPlaceClick = viewModel::openRecommendedPlace,
                        onGeneratePlan = { viewModel.requestPlanFromRecommendation(message.id) },
                        onDismissPlan = { viewModel.dismissPlanOffer(message.id) },
                    )
                }
                if (state.isStreaming) {
                    item { AssistantText(state.streamingText.ifBlank { "正在思考…" }, viewModel::openRecommendedPlace) }
                }
                if (state.isGeneratingPlan) {
                    item {
                        GenerationProgress(
                            progress = state.generationProgress,
                            stage = state.generationStage ?: "正在生成行程",
                        )
                    }
                }
                state.planSetupRequest?.let { planRequest ->
                    item {
                        PlanningSetupCard(
                            destination = destination,
                            onDestinationChange = { destination = it },
                            dateLabel = formatDateRange(startDate, endDate),
                            pace = pace,
                            onPaceChange = { pace = it },
                            onOpenCalendar = { showDatePicker = true },
                            enabled = !state.isGeneratingPlan,
                            onGenerate = {
                                viewModel.generateTripPlan(
                                    destination = destination,
                                    dateRange = formatDateRange(startDate, endDate),
                                    dayCount = ChronoUnit.DAYS.between(startDate, endDate).toInt() + 1,
                                    pace = pace,
                                    requestText = planRequest,
                                )
                            },
                        )
                    }
                }
                state.planningError?.let { error ->
                    item { NoticeCard(error, error = true) }
                }
                state.generatedPlan?.let { plan ->
                    item {
                        GeneratedPlanCard(
                            plan = plan,
                            expanded = state.generatedPlanExpanded,
                            saved = state.savedGeneratedPlanId != null,
                            onToggle = viewModel::toggleGeneratedPlanExpanded,
                            onPlaceClick = viewModel::openGeneratedPlace,
                            onSave = viewModel::saveGeneratedPlan,
                        )
                    }
                }
                state.actionSet?.let { actionSet ->
                    item {
                        ExistingPlanActions(
                            actionSet = actionSet,
                            applying = state.isApplyingActions,
                            onApply = viewModel::applySuggestedActions,
                            onCancel = viewModel::clearSuggestedActions,
                        )
                    }
                }
                state.actionMessage?.let { item { NoticeCard(it, error = false) } }
                state.errorMessage?.let { error ->
                    item {
                        NoticeCard(error, error = true, actionLabel = "重试", onAction = viewModel::retryLastMessage)
                    }
                }
            }
            AssistantComposer(
                input = input,
                onInputChange = { input = it },
                enabled = !state.isSending && !state.isGeneratingPlan,
                onSend = {
                    if (input.isNotBlank()) {
                        viewModel.sendMessage(input)
                        input = ""
                    }
                },
            )
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDateRangePickerState(
            initialSelectedStartDateMillis = startDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli(),
            initialSelectedEndDateMillis = endDate.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli(),
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    val startMillis = pickerState.selectedStartDateMillis
                    val endMillis = pickerState.selectedEndDateMillis
                    if (startMillis != null && endMillis != null) {
                        val pickedStart = Instant.ofEpochMilli(startMillis).atZone(ZoneOffset.UTC).toLocalDate()
                        val pickedEnd = Instant.ofEpochMilli(endMillis).atZone(ZoneOffset.UTC).toLocalDate()
                        if (ChronoUnit.DAYS.between(pickedStart, pickedEnd) in 0..9) {
                            startDate = pickedStart
                            endDate = pickedEnd
                            showDatePicker = false
                        }
                    }
                }) { Text("确定") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("取消") } },
        ) { DateRangePicker(state = pickerState) }
    }

    if (showConversationHistory) {
        ConversationHistorySheet(
            histories = state.conversationHistories,
            activeConversationId = state.activeConversationId,
            onDismiss = { showConversationHistory = false },
            onNewConversation = {
                viewModel.startNewConversation()
                showConversationHistory = false
            },
            onOpenConversation = { conversationId ->
                viewModel.openConversation(conversationId)
                showConversationHistory = false
            },
            onDeleteConversation = viewModel::deleteConversation,
        )
    }
}

@Composable
private fun AssistantHeader(onClose: () -> Unit, onOpenHistory: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        RoundHeaderButton(Icons.Outlined.Close, "关闭", onClose)
        Surface(
            modifier = Modifier.weight(1f),
            color = Color.White,
            shape = RoundedCornerShape(50),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE3E3E1)),
        ) {
            Text(
                text = "AI 旅行助手",
                modifier = Modifier.padding(vertical = 15.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
                color = AssistantInk,
            )
        }
        RoundHeaderButton(Icons.Outlined.Menu, "对话历史", onOpenHistory)
    }
}

@Composable
private fun RoundHeaderButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.size(52.dp),
        color = Color.White,
        shape = CircleShape,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE3E3E1)),
        onClick = onClick,
    ) { Box(contentAlignment = Alignment.Center) { Icon(icon, label, tint = AssistantInk) } }
}

@Composable
private fun PlanningSetupCard(
    destination: String,
    onDestinationChange: (String) -> Unit,
    dateLabel: String,
    pace: String,
    onPaceChange: (String) -> Unit,
    onOpenCalendar: () -> Unit,
    enabled: Boolean,
    onGenerate: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("交给智能规划前，确认基本安排", fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = AssistantInk)
        OutlinedTextField(
            value = destination,
            onValueChange = onDestinationChange,
            modifier = Modifier.fillMaxWidth(),
            label = { Text("目的地") },
            placeholder = { Text("例如：天津") },
            shape = RoundedCornerShape(18.dp),
            singleLine = true,
        )
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color.White,
            shape = RoundedCornerShape(18.dp),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFDDDDDA)),
            onClick = onOpenCalendar,
        ) {
            Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.CalendarMonth, null, tint = AssistantBlue)
                Text("旅行日期", modifier = Modifier.padding(start = 12.dp).weight(1f), color = AssistantMuted)
                Text(dateLabel, fontWeight = FontWeight.SemiBold, color = AssistantInk)
            }
        }
        Text("旅行节奏", fontWeight = FontWeight.SemiBold, color = AssistantInk)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PaceOption("RELAXED", "轻松悠闲", pace, onPaceChange, Modifier.weight(1f))
            PaceOption("BALANCED", "适中兼顾", pace, onPaceChange, Modifier.weight(1f))
            PaceOption("INTENSIVE", "紧凑打卡", pace, onPaceChange, Modifier.weight(1f))
        }
        Button(
            onClick = onGenerate,
            enabled = enabled && destination.isNotBlank(),
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = RoundedCornerShape(28.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color.Black, contentColor = Color.White),
        ) {
            Icon(Icons.Outlined.Route, null)
            Text("交给智能规划生成", modifier = Modifier.padding(start = 8.dp), fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun PaceOption(value: String, label: String, selected: String, onSelect: (String) -> Unit, modifier: Modifier) {
    val active = value == selected
    Surface(
        modifier = modifier,
        color = if (active) AssistantInk else Color(0xFFEDEDEC),
        contentColor = if (active) Color.White else AssistantInk,
        shape = RoundedCornerShape(50),
        onClick = { onSelect(value) },
    ) { Text(label, modifier = Modifier.padding(vertical = 11.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center, fontSize = 13.sp) }
}

@Composable
private fun MessageBlock(
    message: ChatMessage,
    onPlaceClick: (String) -> Unit,
    onGeneratePlan: () -> Unit,
    onDismissPlan: () -> Unit,
) {
    if (message.fromUser) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Surface(color = UserBubble, shape = RoundedCornerShape(24.dp)) {
                Text(message.text, modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp), color = AssistantInk, fontSize = 17.sp)
            }
        }
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            AssistantText(message.text, onPlaceClick)
            if (message.recommendedPlaces.isNotEmpty()) {
                PlaceRecommendationSection(
                    city = message.retrievalCity,
                    places = message.recommendedPlaces,
                    onPlaceClick = onPlaceClick,
                )
            }
            if (message.offerPlan) {
                PlanOfferCard(onGeneratePlan = onGeneratePlan, onDismiss = onDismissPlan)
            }
        }
    }
}

@Composable
private fun AssistantText(text: String, onPlaceClick: (String) -> Unit = {}) {
    MarkdownText(
        text = text,
        style = androidx.compose.material3.MaterialTheme.typography.bodyLarge,
        color = AssistantInk,
        onInternalPlaceClick = onPlaceClick,
    )
}

@Composable
private fun PlaceRecommendationSection(
    city: String?,
    places: List<AiRecommendedPlace>,
    onPlaceClick: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = city?.let { "在${it}，为你找到这些真实地点" } ?: "为你找到这些真实地点",
                    fontWeight = FontWeight.Bold,
                    fontSize = 18.sp,
                    color = AssistantInk,
                )
                Text("来自高德地图 · 点击卡片查看详情", color = AssistantMuted, fontSize = 12.sp)
            }
            Surface(color = Color(0xFFEAF5FA), shape = RoundedCornerShape(50)) {
                Text("${places.size} 个", modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = AssistantBlue, fontSize = 12.sp)
            }
        }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            items(places, key = { it.id }) { place ->
                RecommendedPlaceCard(place = place, onClick = { onPlaceClick(place.id) })
            }
        }
    }
}

@Composable
private fun RecommendedPlaceCard(place: AiRecommendedPlace, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.width(272.dp),
        color = Color.White,
        shape = RoundedCornerShape(22.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E4E5)),
        shadowElevation = 1.dp,
        onClick = onClick,
    ) {
        Column {
            PlaceCoverImage(
                imageUrl = place.coverImageUrl ?: place.imageUrls.firstOrNull(),
                placeName = place.name,
                category = place.category,
                modifier = Modifier.fillMaxWidth().height(132.dp),
                shape = RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp),
            )
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Text(
                    text = place.name,
                    color = AssistantBlue,
                    fontWeight = FontWeight.Bold,
                    fontSize = 17.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    place.rating?.let {
                        Icon(Icons.Outlined.Star, null, tint = Color(0xFFE29A24), modifier = Modifier.size(16.dp))
                        Text(it, modifier = Modifier.padding(start = 3.dp), color = AssistantInk, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    }
                    place.costAverage?.let {
                        Text(" · 人均 ¥$it", color = AssistantMuted, fontSize = 13.sp)
                    }
                    if (place.rating == null && place.costAverage == null) {
                        Text(place.typeName ?: "高德真实地点", color = AssistantMuted, fontSize = 13.sp)
                    }
                }
                Text(
                    text = place.description,
                    color = Color(0xFF555A5D),
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.LocationOn, null, tint = AssistantMuted, modifier = Modifier.size(15.dp))
                    Text(
                        text = listOfNotNull(place.districtName, place.address).joinToString(" · ").ifBlank { "地点详情中查看地址" },
                        modifier = Modifier.padding(start = 4.dp).weight(1f),
                        color = AssistantMuted,
                        fontSize = 12.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
                    Text("查看地点", color = AssistantBlue, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Icon(Icons.AutoMirrored.Outlined.ArrowForward, null, tint = AssistantBlue, modifier = Modifier.padding(start = 4.dp).size(16.dp))
                }
            }
        }
    }
}

@Composable
private fun PlanOfferCard(onGeneratePlan: () -> Unit, onDismiss: () -> Unit) {
    Surface(
        color = Color.White,
        shape = RoundedCornerShape(22.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E4E5)),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("要把这些地点安排成旅行计划吗？", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = AssistantInk)
            Text("智能规划会继续询问日期和旅行节奏，再结合真实地点自动生成可编辑行程。", color = AssistantMuted, fontSize = 13.sp, lineHeight = 19.sp)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onGeneratePlan,
                    colors = ButtonDefaults.buttonColors(containerColor = Color.Black, contentColor = Color.White),
                    shape = RoundedCornerShape(50),
                ) { Text("生成计划", fontWeight = FontWeight.Bold) }
                TextButton(onClick = onDismiss) { Text("继续聊聊", color = AssistantMuted) }
            }
        }
    }
}

@Composable
private fun GenerationProgress(progress: Int, stage: String) {
    Surface(color = Color.White, shape = RoundedCornerShape(24.dp), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE2E2DF))) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = AssistantBlue)
                Text(stage, modifier = Modifier.padding(start = 10.dp), fontWeight = FontWeight.SemiBold)
            }
            LinearProgressIndicator(progress = { progress.coerceIn(0, 100) / 100f }, modifier = Modifier.fillMaxWidth(), color = AssistantBlue)
            Text("$progress% · 智能规划正在查询真实地点并安排每日路线", color = AssistantMuted, fontSize = 13.sp)
        }
    }
}

@Composable
private fun GeneratedPlanCard(
    plan: AiPlanGenerationResponse,
    expanded: Boolean,
    saved: Boolean,
    onToggle: () -> Unit,
    onPlaceClick: (String) -> Unit,
    onSave: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Surface(color = Color.White, shape = RoundedCornerShape(28.dp), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E0DD))) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(plan.title, fontSize = 24.sp, color = AssistantInk)
                if (!expanded) {
                    plan.days.sortedBy { it.dayIndex }.forEachIndexed { index, day ->
                        if (index > 0) HorizontalDivider(color = Color(0xFFE5E5E2))
                        Text("DAY ${day.dayIndex}  ${day.title}", fontSize = 17.sp, fontWeight = FontWeight.Medium, color = AssistantInk)
                        LinkedPlaceLine(day.places, onPlaceClick)
                    }
                } else {
                    plan.days.sortedBy { it.dayIndex }.forEachIndexed { index, day ->
                        if (index > 0) HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp), color = Color(0xFFE5E5E2))
                        ExpandedDay(day, onPlaceClick)
                    }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Surface(shape = RoundedCornerShape(50), color = Color.White, border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E0DD)), onClick = onSave) {
                Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (saved) Icons.Outlined.Check else Icons.Outlined.Add, null)
                    Text(if (saved) "查看计划" else "加入计划", modifier = Modifier.padding(start = 7.dp), fontWeight = FontWeight.Bold)
                }
            }
            Surface(shape = RoundedCornerShape(50), color = Color.White, border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E0DD)), onClick = onToggle) {
                Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (expanded) Icons.Outlined.ExpandLess else Icons.Outlined.ExpandMore, null)
                    Text(if (expanded) "收起计划" else "展开计划", modifier = Modifier.padding(start = 7.dp), fontWeight = FontWeight.Bold)
                }
            }
        }
        Text("蓝色地点名称可直接打开探索详情", color = AssistantBlue, fontSize = 13.sp)
    }
}

@Composable
private fun LinkedPlaceLine(places: List<AiGeneratedPlace>, onPlaceClick: (String) -> Unit) {
    val text = remember(places) {
        buildAnnotatedString {
            places.forEachIndexed { index, place ->
                if (index > 0) append(" → ")
                pushStringAnnotation(tag = "place", annotation = place.id)
                pushStyle(SpanStyle(color = AssistantBlue, fontWeight = FontWeight.Medium))
                append(place.name)
                pop()
                pop()
            }
        }
    }
    ClickableText(
        text = text,
        style = androidx.compose.ui.text.TextStyle(fontSize = 15.sp, lineHeight = 22.sp),
        onClick = { offset ->
            text.getStringAnnotations(tag = "place", start = offset, end = offset)
                .firstOrNull()
                ?.let { onPlaceClick(it.item) }
        },
    )
}

@Composable
private fun ExpandedDay(day: AiGeneratedDay, onPlaceClick: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("DAY ${day.dayIndex}  ${day.title}", fontSize = 19.sp, fontWeight = FontWeight.Medium, color = AssistantInk)
        day.places.forEachIndexed { index, place -> ExpandedPlace(index + 1, place, onPlaceClick) }
    }
}

@Composable
private fun ExpandedPlace(number: Int, place: AiGeneratedPlace, onPlaceClick: (String) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().clickable { onPlaceClick(place.id) }, verticalAlignment = Alignment.Top) {
        PlaceCoverImage(
            imageUrl = place.thumbnailUrl ?: place.imageUrls.firstOrNull(),
            placeName = place.name,
            category = place.category,
            modifier = Modifier.size(76.dp),
            shape = RoundedCornerShape(18.dp),
        )
        Column(modifier = Modifier.padding(start = 14.dp).weight(1f)) {
            Text("$number. ${place.name}", color = AssistantBlue, fontWeight = FontWeight.Bold, fontSize = 17.sp)
            Text(place.typeName ?: place.category, color = AssistantMuted, fontSize = 13.sp)
            Text(place.note.ifBlank { place.address.orEmpty() }, color = Color(0xFF55575B), maxLines = 2, overflow = TextOverflow.Ellipsis, lineHeight = 20.sp)
        }
    }
}

@Composable
private fun ExistingPlanActions(actionSet: AiActionSetUi, applying: Boolean, onApply: () -> Unit, onCancel: () -> Unit) {
    Surface(color = Color.White, shape = RoundedCornerShape(24.dp), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E0DD))) {
        Column(modifier = Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("路线优化建议", fontWeight = FontWeight.Bold, fontSize = 18.sp)
            actionSet.cards.forEach { Text("• ${it.summary}", color = AssistantInk) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onApply, enabled = !applying, colors = ButtonDefaults.buttonColors(containerColor = Color.Black)) { Text("确认应用") }
                TextButton(onClick = onCancel) { Text("取消") }
            }
        }
    }
}

@Composable
private fun NoticeCard(text: String, error: Boolean, actionLabel: String? = null, onAction: () -> Unit = {}) {
    Surface(color = if (error) Color(0xFFFFEEEE) else Color(0xFFECF8F1), shape = RoundedCornerShape(18.dp)) {
        Row(modifier = Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(text, modifier = Modifier.weight(1f), color = if (error) Color(0xFF8C3030) else Color(0xFF276A48))
            actionLabel?.let { TextButton(onClick = onAction) { Text(it) } }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationHistorySheet(
    histories: List<AiConversationRecord>,
    activeConversationId: String?,
    onDismiss: () -> Unit,
    onNewConversation: () -> Unit,
    onOpenConversation: (String) -> Unit,
    onDeleteConversation: (String) -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = AssistantBackground,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(start = 20.dp, end = 20.dp, bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("对话历史", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = AssistantInk)
                Button(
                    onClick = onNewConversation,
                    colors = ButtonDefaults.buttonColors(containerColor = AssistantInk),
                ) {
                    Icon(Icons.Outlined.Add, null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("新对话")
                }
            }

            if (histories.isEmpty()) {
                Text(
                    "还没有保存的对话。发送第一条消息后，对话会自动保存在这里。",
                    modifier = Modifier.padding(vertical = 28.dp),
                    color = AssistantMuted,
                    lineHeight = 24.sp,
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 520.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(histories, key = { it.id }) { conversation ->
                        val isActive = conversation.id == activeConversationId
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            color = if (isActive) Color(0xFFE4F6F5) else Color.White,
                            shape = RoundedCornerShape(18.dp),
                            border = androidx.compose.foundation.BorderStroke(
                                1.dp,
                                if (isActive) Color(0xFF8CCFCA) else Color(0xFFE3E3E1),
                            ),
                            onClick = { onOpenConversation(conversation.id) },
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth().padding(start = 16.dp, top = 14.dp, bottom = 14.dp, end = 6.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                    Text(
                                        conversation.title,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        fontWeight = if (isActive) FontWeight.Bold else FontWeight.SemiBold,
                                        color = AssistantInk,
                                    )
                                    Text(
                                        historyPreview(conversation.messages.lastOrNull()?.text.orEmpty()),
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        color = AssistantMuted,
                                        fontSize = 13.sp,
                                    )
                                }
                                IconButton(onClick = { onDeleteConversation(conversation.id) }) {
                                    Icon(Icons.Outlined.DeleteOutline, "删除对话", tint = AssistantMuted)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AssistantComposer(
    input: String,
    onInputChange: (String) -> Unit,
    enabled: Boolean,
    onSend: () -> Unit,
) {
    val canSend = enabled && input.isNotBlank()
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .navigationBarsPadding()
            .padding(horizontal = 20.dp, vertical = 10.dp),
    ) {
        Surface(color = Color.White, shape = RoundedCornerShape(30.dp), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFE0E0DD))) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 58.dp)
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BasicTextField(
                    value = input,
                    onValueChange = onInputChange,
                    modifier = Modifier.weight(1f).padding(horizontal = 14.dp, vertical = 13.dp),
                    enabled = enabled,
                    singleLine = false,
                    maxLines = 3,
                    textStyle = androidx.compose.ui.text.TextStyle(color = AssistantInk, fontSize = 16.sp),
                    decorationBox = { innerTextField ->
                        Box(contentAlignment = Alignment.CenterStart) {
                            if (input.isBlank()) Text("发消息", color = Color(0xFF9B9DA1), fontSize = 16.sp)
                            innerTextField()
                        }
                    },
                )
                Surface(
                    modifier = Modifier.size(44.dp),
                    color = if (canSend) AssistantInk else Color(0xFFE7E8E8),
                    shape = CircleShape,
                    onClick = { if (canSend) onSend() },
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.AutoMirrored.Outlined.Send,
                            "发送",
                            tint = if (canSend) Color.White else Color(0xFF9B9DA1),
                        )
                    }
                }
            }
        }
    }
}

private fun historyPreview(text: String): String = text
    .replace(Regex("""\[([^]]+)]\([^)]+\)"""), "$1")
    .replace("**", "")
    .replace("\n", " ")
    .trim()

private fun formatDateRange(start: LocalDate, end: LocalDate): String {
    val formatter = DateTimeFormatter.ofPattern("MM.dd")
    return "${start.format(formatter)} - ${end.format(formatter)}"
}

private fun inferDestination(request: String): String {
    val normalized = request.replace(" ", "")
    val afterGo = Regex("(?:去|到)([\\u4e00-\\u9fa5]{2,8}?)(?:旅游|旅行|玩|一日游|二日游|两日游|三日游|四日游|五日游)")
        .find(normalized)
        ?.groupValues
        ?.getOrNull(1)
    if (!afterGo.isNullOrBlank()) return afterGo.removeSuffix("市")
    return Regex("([\\u4e00-\\u9fa5]{2,6}?)(?:一日游|二日游|两日游|三日游|四日游|五日游|旅游规划|旅行规划)")
        .find(normalized)
        ?.groupValues
        ?.getOrNull(1)
        ?.removeSuffix("市")
        .orEmpty()
}
