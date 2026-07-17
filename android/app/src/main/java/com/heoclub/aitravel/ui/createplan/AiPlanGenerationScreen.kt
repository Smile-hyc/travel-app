package com.heoclub.aitravel.ui.createplan

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.model.AiGeneratedPlace
import com.heoclub.aitravel.data.model.AiPlanProgressEvent
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.ui.components.PlaceCoverImage
import com.heoclub.aitravel.ui.explore.ExploreMap
import com.heoclub.aitravel.ui.explore.MapCameraCommand
import kotlinx.coroutines.flow.MutableSharedFlow
import androidx.compose.foundation.rememberScrollState

@Composable
fun AiPlanGenerationScreen(
    viewModel: AiPlanGenerationViewModel,
    onBack: () -> Unit,
    onOpenPlan: (String) -> Unit,
    onOpenPlace: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsState()
    val loading = uiState as? AiPlanGenerationUiState.Loading
    val ready = uiState as? AiPlanGenerationUiState.Ready
    var selectedDayIndex by remember { mutableIntStateOf(1) }
    var followActiveDay by remember { mutableStateOf(true) }
    LaunchedEffect(loading?.activeDayIndex) {
        if (followActiveDay) {
            loading?.activeDayIndex?.let { selectedDayIndex = it }
        }
    }
    LaunchedEffect(ready?.savedPlanId) {
        if (ready != null) {
            selectedDayIndex = 1
            followActiveDay = false
        }
    }
    val activeLoadingDay = loading?.partialDays
        ?.firstOrNull { it.dayIndex == selectedDayIndex }
        ?: loading?.partialDays?.lastOrNull { it.places.isNotEmpty() }
    val activeReadyDay = ready?.result?.days
        ?.firstOrNull { it.dayIndex == selectedDayIndex }
    val activeMapDay = activeLoadingDay ?: activeReadyDay
    val visiblePlaces = activeMapDay?.places
        .orEmpty()
        .map(AiGeneratedPlace::toPlaceSummary)
    val selectedPlaceId = visiblePlaces.lastOrNull()?.id
    val mapCommands = remember { MutableSharedFlow<MapCameraCommand>(extraBufferCapacity = 1) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF4F8FC)),
    ) {
        Box(modifier = Modifier.fillMaxWidth().height(280.dp)) {
            if (visiblePlaces.isEmpty()) {
                PlanningMapBackdrop(modifier = Modifier.fillMaxSize())
            } else {
                ExploreMap(
                    places = visiblePlaces,
                    selectedPlaceId = selectedPlaceId,
                    mapCommands = mapCommands,
                    onMarkerClick = {},
                    routePlaces = visiblePlaces,
                    modifier = Modifier.fillMaxSize(),
                )
            }
            Surface(
                modifier = Modifier.padding(start = 16.dp, top = 16.dp),
                color = Color.White.copy(alpha = 0.94f),
                shape = CircleShape,
                shadowElevation = 3.dp,
            ) {
                IconButton(
                    onClick = {
                        viewModel.cancel()
                        onBack()
                    },
                    modifier = Modifier.size(48.dp),
                ) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "取消并返回")
                }
            }
            if (visiblePlaces.isNotEmpty()) {
                Surface(
                    modifier = Modifier.align(Alignment.TopEnd).padding(end = 16.dp, top = 16.dp),
                    color = Color.White.copy(alpha = 0.94f),
                    shape = RoundedCornerShape(16.dp),
                    shadowElevation = 3.dp,
                ) {
                    Text(
                        "第 ${activeMapDay?.dayIndex ?: 1} 天 · ${visiblePlaces.size} 个点 · 路线草案",
                        modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }

        Surface(
            modifier = Modifier.fillMaxWidth().weight(1f),
            color = Color.White,
            shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
            shadowElevation = 8.dp,
        ) {
            when (val state = uiState) {
                is AiPlanGenerationUiState.Loading -> LoadingPlanContent(
                    progress = state.progress,
                    stage = state.stage,
                    completedDays = state.completedDays,
                    totalDays = state.totalDays,
                    activeDayIndex = state.activeDayIndex,
                    partialDays = state.partialDays,
                    events = state.events,
                    selectedDayIndex = selectedDayIndex,
                    onSelectDay = { dayIndex ->
                        selectedDayIndex = dayIndex
                        followActiveDay = false
                    },
                    onOpenPlace = onOpenPlace,
                    onCancel = {
                        viewModel.cancel()
                        onBack()
                    },
                )

                is AiPlanGenerationUiState.Ready -> ReadyPlanContent(
                    state = state,
                    onOpenPlan = { onOpenPlan(state.savedPlanId) },
                    selectedDayIndex = selectedDayIndex,
                    onSelectDay = { selectedDayIndex = it },
                    onOpenPlace = onOpenPlace,
                )

                is AiPlanGenerationUiState.Error -> ErrorPlanContent(
                    message = state.message,
                    onRetry = viewModel::retry,
                    onBack = onBack,
                )
            }
        }
    }
}

@Composable
private fun PlanningMapBackdrop(modifier: Modifier = Modifier) {
    Box(modifier = modifier.background(Color(0xFFEFF5F9))) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val road = Color.White.copy(alpha = 0.92f)
            repeat(7) { index ->
                val y = size.height * (0.12f + index * 0.13f)
                drawLine(road, Offset(0f, y), Offset(size.width, y + if (index % 2 == 0) 34f else -24f), 8f, StrokeCap.Round)
            }
            repeat(6) { index ->
                val x = size.width * (0.08f + index * 0.18f)
                drawLine(road, Offset(x, 0f), Offset(x + if (index % 2 == 0) 42f else -34f, size.height), 7f, StrokeCap.Round)
            }
            val path = listOf(
                Offset(size.width * 0.32f, size.height * 0.76f),
                Offset(size.width * 0.47f, size.height * 0.58f),
                Offset(size.width * 0.42f, size.height * 0.38f),
                Offset(size.width * 0.67f, size.height * 0.22f),
            )
            path.zipWithNext().forEach { (start, end) ->
                drawLine(Color(0xFF63B8F0), start, end, 9f, StrokeCap.Round)
            }
            path.forEachIndexed { index, point ->
                drawCircle(Color.White, 22f, point)
                drawCircle(if (index == path.lastIndex) Color(0xFF6C63E8) else Color(0xFF2BA9E8), 15f, point)
            }
        }
        Surface(
            modifier = Modifier.align(Alignment.Center),
            color = Color.White.copy(alpha = 0.94f),
            shape = RoundedCornerShape(18.dp),
            shadowElevation = 5.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Text("AI 正在绘制你的旅行路线", fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun LoadingPlanContent(
    progress: Int,
    stage: String,
    completedDays: Int,
    totalDays: Int,
    activeDayIndex: Int?,
    partialDays: List<com.heoclub.aitravel.data.model.AiGeneratedDay>,
    events: List<AiPlanProgressEvent>,
    selectedDayIndex: Int,
    onSelectDay: (Int) -> Unit,
    onOpenPlace: (String) -> Unit,
    onCancel: () -> Unit,
) {
    val activeDay = partialDays.firstOrNull { it.dayIndex == selectedDayIndex }
        ?: partialDays.lastOrNull { it.places.isNotEmpty() }
    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 18.dp)) {
        Text("实时规划中", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(
            stage,
            modifier = Modifier
                .padding(top = 8.dp)
                .semantics { liveRegion = LiveRegionMode.Polite },
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(14.dp))
        Box(modifier = Modifier.fillMaxWidth().height(5.dp).background(Color(0xFFE5EDF6), CircleShape)) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(progress.coerceIn(0, 100) / 100f)
                    .height(5.dp)
                    .background(MaterialTheme.colorScheme.primary, CircleShape),
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                if (completedDays > 0) "已编排 $completedDays/$totalDays 天" else "服务端实时进度",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text("$progress%", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        }
        LazyColumn(
            modifier = Modifier.padding(top = 18.dp).weight(1f),
            contentPadding = PaddingValues(bottom = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (partialDays.isNotEmpty()) {
                item {
                    DaySelector(
                        days = partialDays,
                        selectedDayIndex = activeDay?.dayIndex ?: selectedDayIndex,
                        activeDayIndex = activeDayIndex,
                        onSelectDay = onSelectDay,
                    )
                }
            }
            if (events.isNotEmpty()) {
                item { PlanningTimeline(events.takeLast(4)) }
            }
            if (activeDay != null) {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(activeDay.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        Text(
                            "已落点 ${activeDay.places.size} 个 · 预估连线 ${activeDay.estimatedDistanceKm} km",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                items(activeDay.places.takeLast(3), key = { it.id }) { place ->
                    GeneratedPlaceCard(place, onOpenPlace = onOpenPlace)
                }
            } else {
                items(3) { index -> PlanSkeletonRow(index) }
            }
        }
        OutlinedButton(
            onClick = onCancel,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(18.dp),
        ) {
            Icon(Icons.Outlined.Close, contentDescription = null)
            Text("取消生成", modifier = Modifier.padding(start = 8.dp))
        }
    }
}

@Composable
private fun DaySelector(
    days: List<com.heoclub.aitravel.data.model.AiGeneratedDay>,
    selectedDayIndex: Int,
    activeDayIndex: Int?,
    onSelectDay: (Int) -> Unit,
) {
    val sortedDays = days.sortedBy { it.dayIndex }
    if (sortedDays.size <= 3) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            sortedDays.forEach { day ->
                DayChip(
                    day = day,
                    selected = day.dayIndex == selectedDayIndex,
                    active = day.dayIndex == activeDayIndex,
                    onClick = { onSelectDay(day.dayIndex) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
    } else {
        Row(
            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            sortedDays.forEach { day ->
                DayChip(
                    day = day,
                    selected = day.dayIndex == selectedDayIndex,
                    active = day.dayIndex == activeDayIndex,
                    onClick = { onSelectDay(day.dayIndex) },
                )
            }
        }
    }
}

@Composable
private fun DayChip(
    day: com.heoclub.aitravel.data.model.AiGeneratedDay,
    selected: Boolean,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.height(48.dp).clickable(onClick = onClick),
        color = if (selected) MaterialTheme.colorScheme.primary else Color(0xFFF1F5F9),
        contentColor = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
        shape = RoundedCornerShape(16.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            Text("Day ${day.dayIndex}", fontWeight = FontWeight.Bold)
            Text(" · ${day.places.size}点", style = MaterialTheme.typography.labelSmall)
            if (active) {
                Text(" •", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun PlanningTimeline(events: List<AiPlanProgressEvent>) {
    Surface(
        color = Color(0xFFEEF6FF),
        shape = RoundedCornerShape(18.dp),
        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("规划动态", fontWeight = FontWeight.Bold, color = Color(0xFF174F86))
            events.forEach { event ->
                Row(
                    verticalAlignment = Alignment.Top,
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                ) {
                    Icon(
                        imageVector = when (event.type) {
                            "PLACE_ADDED" -> Icons.Outlined.LocationOn
                            "DAY_COMPLETED", "PLAN_REFINED" -> Icons.Outlined.CheckCircle
                            else -> Icons.Outlined.AutoAwesome
                        },
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        event.message,
                        style = MaterialTheme.typography.bodySmall,
                        color = Color(0xFF29445E),
                    )
                }
            }
        }
    }
}

@Composable
private fun PlanSkeletonRow(index: Int) {
    Row(
        modifier = Modifier.fillMaxWidth().background(Color(0xFFF7F9FC), RoundedCornerShape(18.dp)).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(modifier = Modifier.size(72.dp).background(Color(0xFFE4EBF3), RoundedCornerShape(14.dp)))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(modifier = Modifier.fillMaxWidth(if (index % 2 == 0) 0.72f else 0.58f).height(14.dp).background(Color(0xFFDDE6EF), CircleShape))
            Box(modifier = Modifier.fillMaxWidth(0.88f).height(11.dp).background(Color(0xFFE7EDF4), CircleShape))
            Box(modifier = Modifier.fillMaxWidth(0.64f).height(11.dp).background(Color(0xFFE7EDF4), CircleShape))
        }
    }
}

@Composable
private fun ReadyPlanContent(
    state: AiPlanGenerationUiState.Ready,
    onOpenPlan: () -> Unit,
    selectedDayIndex: Int,
    onSelectDay: (Int) -> Unit,
    onOpenPlace: (String) -> Unit,
) {
    val complete = state.visibleDayCount >= state.result.days.size
    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                if (complete) Icons.Outlined.CheckCircle else Icons.Outlined.AutoAwesome,
                contentDescription = null,
                tint = if (complete) Color(0xFF159A6A) else MaterialTheme.colorScheme.primary,
            )
            Column(modifier = Modifier.padding(start = 10.dp).weight(1f)) {
                Text(
                    if (complete) "行程已生成并保存" else "正在编辑第 ${state.visibleDayCount} 天",
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    "已完成 ${state.visibleDayCount}/${state.result.days.size} 天",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 16.dp, end = 16.dp, bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                DaySelector(
                    days = state.result.days,
                    selectedDayIndex = selectedDayIndex,
                    activeDayIndex = null,
                    onSelectDay = onSelectDay,
                )
            }
            if (state.result.warnings.isNotEmpty()) {
                item {
                    Surface(color = Color(0xFFFFF4DF), shape = RoundedCornerShape(16.dp)) {
                        Text(
                            state.result.warnings.joinToString("\n"),
                            modifier = Modifier.padding(14.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFF76520C),
                        )
                    }
                }
            }
            item {
                Surface(color = Color(0xFFEAF8F3), shape = RoundedCornerShape(16.dp)) {
                    Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("行程质量检查", fontWeight = FontWeight.Bold, color = Color(0xFF126B50))
                        Text(
                            "${state.result.quality.totalPlaceCount} 个真实 POI · " +
                                "重复 ${state.result.quality.duplicatePlaceCount} 个 · " +
                                state.result.quality.dataSources.joinToString(" + "),
                            style = MaterialTheme.typography.bodySmall,
                            color = Color(0xFF2F6657),
                        )
                    }
                }
            }
            items(
                state.result.days.filter { it.dayIndex == selectedDayIndex },
                key = { it.dayIndex },
            ) { day ->
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(day.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(
                        "${day.intensity} · 约 ${day.estimatedDistanceKm} km · ${day.places.size} 个地点",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(day.summary, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    day.places.forEach { place ->
                        GeneratedPlaceCard(place, onOpenPlace = onOpenPlace)
                    }
                }
            }
        }
        Button(
            onClick = onOpenPlan,
            enabled = complete,
            modifier = Modifier.fillMaxWidth().padding(16.dp).height(54.dp),
            shape = RoundedCornerShape(18.dp),
        ) {
            Text(if (complete) "查看完整行程" else "正在保存行程…")
        }
    }
}

@Composable
private fun GeneratedPlaceCard(
    place: AiGeneratedPlace,
    onOpenPlace: (String) -> Unit,
) {
    Card(
        modifier = Modifier.clickable { onOpenPlace(place.id) },
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF8FAFD)),
        shape = RoundedCornerShape(18.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Row(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
            PlaceCoverImage(
                imageUrl = place.thumbnailUrl,
                placeName = place.name,
                modifier = Modifier.size(78.dp),
                shape = RoundedCornerShape(15.dp),
            )
            Column(modifier = Modifier.padding(start = 12.dp).weight(1f)) {
                Text(place.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(
                    modifier = Modifier.padding(top = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.AccessTime, contentDescription = null, modifier = Modifier.size(15.dp), tint = MaterialTheme.colorScheme.primary)
                    Text(
                        "${place.suggestedStart} - ${place.suggestedEnd}",
                        modifier = Modifier.padding(start = 4.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                Text(
                    place.note,
                    modifier = Modifier.padding(top = 5.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = when {
                        place.scheduleVerified -> "时间已按营业信息校验"
                        !place.openingHoursToday.isNullOrBlank() -> "营业：${place.openingHoursToday}"
                        !place.openingHoursWeek.isNullOrBlank() -> "营业：${place.openingHoursWeek}"
                        else -> "开放时间待确认"
                    },
                    modifier = Modifier.padding(top = 5.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = if (place.scheduleVerified) Color(0xFF167A55) else Color(0xFF9A6700),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    "点击查看地点详情",
                    modifier = Modifier.padding(top = 4.dp),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun ErrorPlanContent(message: String, onRetry: () -> Unit, onBack: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Icon(Icons.Outlined.LocationOn, contentDescription = null, modifier = Modifier.size(42.dp), tint = MaterialTheme.colorScheme.error)
        Text("智能规划没有完成", modifier = Modifier.padding(top = 14.dp), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        Text(
            message,
            modifier = Modifier.padding(top = 10.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(onClick = onRetry, modifier = Modifier.fillMaxWidth().padding(top = 24.dp).height(52.dp), shape = RoundedCornerShape(18.dp)) {
            Icon(Icons.Outlined.Refresh, contentDescription = null)
            Text("重新生成", modifier = Modifier.padding(start = 8.dp))
        }
        OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(52.dp), shape = RoundedCornerShape(18.dp)) {
            Text("返回修改")
        }
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
        coverImageUrl = thumbnailUrl,
        imageUrls = imageUrls,
        phone = phone,
        rating = rating,
        costAverage = costAverage,
        businessArea = businessArea,
        openingHoursToday = openingHoursToday,
        openingHoursWeek = openingHoursWeek,
    )
}
