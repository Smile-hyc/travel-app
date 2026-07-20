package com.heoclub.aitravel.ui.detail

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.DragHandle
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.amap.api.maps.AMap
import com.amap.api.maps.CameraUpdateFactory
import com.amap.api.maps.MapView
import com.amap.api.maps.model.BitmapDescriptorFactory
import com.amap.api.maps.model.LatLng
import com.amap.api.maps.model.LatLngBounds
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.maps.model.PolylineOptions
import com.heoclub.aitravel.data.model.DayRoutePlan
import com.heoclub.aitravel.data.model.PlanDay
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.RouteModes
import com.heoclub.aitravel.data.model.RouteStep
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.R
import com.heoclub.aitravel.ui.components.DeletePlanConfirmationDialog
import com.heoclub.aitravel.ui.components.PlaceCoverImage
import com.heoclub.aitravel.ui.components.loadMapMarkerImage
import android.graphics.Color as AndroidColor

@Composable
fun PlanDetailScreen(
    viewModel: PlanDetailViewModel,
    onBack: () -> Unit,
    onAskAi: (String) -> Unit,
    onContinueAdding: (String, String) -> Unit,
    onOpenPlace: (PlanItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsState()
    val plan = uiState.plan

    if (plan == null) {
        MissingPlan(onBack = onBack, modifier = modifier)
        return
    }
    val displayRoute = uiState.optimization?.route ?: uiState.route
    val displayItems = orderedPreviewItems(
        items = if (uiState.selectedDayIndex == 0) {
            plan.days.sortedBy { it.dayIndex }.flatMap { it.items.sortedBy { item -> item.visitOrder } }
        } else {
            uiState.selectedDay?.items.orEmpty()
        },
        optimizedPlaceIds = uiState.optimization?.optimizedPlaceIds,
    )
    var sheetExpanded by remember { mutableStateOf(false) }
    var showDeleteConfirmation by remember(plan.id) { mutableStateOf(false) }
    val mapHeight by animateDpAsState(
        targetValue = if (sheetExpanded) 0.dp else 360.dp,
        label = "计划详情地图高度",
    )

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            PlanRouteMap(
                items = displayItems,
                route = displayRoute,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(mapHeight),
            )
            PlanDetailSheet(
                plan = plan,
                uiState = uiState,
                expanded = sheetExpanded,
                onExpandedChange = { sheetExpanded = it },
                onBack = onBack,
                onAskAi = { onAskAi(plan.id) },
                onContinueAdding = { onContinueAdding(plan.id, plan.destination) },
                onDelete = { showDeleteConfirmation = true },
                onSelectDay = viewModel::selectDay,
                onSelectMode = viewModel::selectMode,
                onReorderItems = viewModel::reorderItems,
                onSelectSegmentMode = viewModel::updateSegmentTransportMode,
                onMoveUnplannedToDay = viewModel::moveUnplannedItemToDay,
                onOptimize = viewModel::optimizeRoute,
                onApplyOptimization = viewModel::applyOptimization,
                onDismissOptimization = viewModel::dismissOptimization,
                onRetry = viewModel::retryRoute,
                onOpenPlace = onOpenPlace,
                modifier = Modifier.weight(1f),
            )
        }

        if (!sheetExpanded) {
            Surface(
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(18.dp),
                color = Color.White,
                shape = CircleShape,
                shadowElevation = 4.dp,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
                }
            }
        }
    }

    if (showDeleteConfirmation) {
        DeletePlanConfirmationDialog(
            planTitle = plan.title,
            onConfirm = {
                showDeleteConfirmation = false
                if (viewModel.deletePlan()) onBack()
            },
            onDismiss = { showDeleteConfirmation = false },
        )
    }
}

@Composable
private fun MissingPlan(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(20.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("没有找到这个旅行计划")
        Button(onClick = onBack, modifier = Modifier.padding(top = 16.dp)) {
            Text("返回")
        }
    }
}

@Composable
private fun PlanDetailSheet(
    plan: TravelPlan,
    uiState: PlanDetailUiState,
    expanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onBack: () -> Unit,
    onAskAi: () -> Unit,
    onContinueAdding: () -> Unit,
    onDelete: () -> Unit,
    onSelectDay: (Int) -> Unit,
    onSelectMode: (String) -> Unit,
    onReorderItems: (List<String>) -> Unit,
    onSelectSegmentMode: (String, String) -> Unit,
    onMoveUnplannedToDay: (String, Int) -> Unit,
    onOptimize: () -> Unit,
    onApplyOptimization: () -> Unit,
    onDismissOptimization: () -> Unit,
    onRetry: () -> Unit,
    onOpenPlace: (PlanItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    val displayRoute = uiState.optimization?.route ?: uiState.route
    val displayItems = orderedPreviewItems(
        items = if (uiState.selectedDayIndex == 0) {
            plan.days.sortedBy { it.dayIndex }.flatMap { it.items.sortedBy { item -> item.visitOrder } }
        } else {
            uiState.selectedDay?.items.orEmpty()
        },
        optimizedPlaceIds = uiState.optimization?.optimizedPlaceIds,
    )
    val dragThresholdPx = with(LocalDensity.current) { 48.dp.toPx() }

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = if (expanded) {
            RoundedCornerShape(0.dp)
        } else {
            RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
        },
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(if (expanded) 44.dp else 22.dp)
                    .pointerInput(expanded, dragThresholdPx) {
                        var accumulatedDrag = 0f
                        detectVerticalDragGestures(
                            onDragStart = { accumulatedDrag = 0f },
                            onVerticalDrag = { change, dragAmount ->
                                change.consume()
                                accumulatedDrag += dragAmount
                            },
                            onDragEnd = {
                                when {
                                    accumulatedDrag <= -dragThresholdPx -> onExpandedChange(true)
                                    accumulatedDrag >= dragThresholdPx -> onExpandedChange(false)
                                }
                                accumulatedDrag = 0f
                            },
                            onDragCancel = { accumulatedDrag = 0f },
                        )
                    },
                contentAlignment = Alignment.Center,
            ) {
                if (expanded) {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.align(Alignment.CenterStart),
                    ) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
                    }
                }
                Box(
                    modifier = Modifier
                        .size(width = 48.dp, height = 5.dp)
                        .clickable { onExpandedChange(!expanded) }
                        .background(Color(0xFFD8DEE8), RoundedCornerShape(50)),
                )
            }

            Text(
                text = plan.title,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF071A3D),
            )
            Text(
                text = "${plan.dayCount.coerceAtLeast(1)} 天 · ${plan.placeCount} 个地点 · ${plan.dateRange}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            DayTabs(
                days = plan.days,
                selectedDayIndex = uiState.selectedDayIndex,
                onSelectDay = onSelectDay,
            )

            if (uiState.selectedDayIndex == 0) {
                Surface(color = Color(0xFFF6FAFF), shape = RoundedCornerShape(18.dp)) {
                    Text(
                        "全程总览按天分组展示；各天路线独立计算，不会把前一天终点错误连接到第二天起点。",
                        modifier = Modifier.padding(14.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                PlanOverviewItinerary(plan.days, onOpenPlace)
            } else {
                RouteModeTabs(
                    selectedMode = uiState.routeMode,
                    onSelectMode = onSelectMode,
                )

                RouteSummary(
                    route = displayRoute,
                    loading = uiState.isLoadingRoute,
                    error = uiState.routeError,
                    onRetry = onRetry,
                )

                OptimizationBanner(
                    uiState = uiState,
                    onOptimize = onOptimize,
                    onApplyOptimization = onApplyOptimization,
                    onDismissOptimization = onDismissOptimization,
                )

                DayItinerary(
                    day = uiState.selectedDay,
                    items = displayItems,
                    route = displayRoute,
                    routeLoading = uiState.isLoadingRoute,
                    previewing = uiState.optimization != null,
                    onReorderItems = onReorderItems,
                    onSelectSegmentMode = onSelectSegmentMode,
                    onOpenPlace = onOpenPlace,
                )
            }

            UnplannedSection(
                items = plan.unplannedItems,
                days = plan.days,
                onMoveToDay = onMoveUnplannedToDay,
            )

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onAskAi,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Icon(Icons.Outlined.AutoAwesome, contentDescription = null)
                    Text("行程助手", modifier = Modifier.padding(start = 6.dp))
                }
                OutlinedButton(
                    onClick = onContinueAdding,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Icon(Icons.Outlined.Add, contentDescription = null)
                    Text("继续加地点", modifier = Modifier.padding(start = 6.dp))
                }
            }

            OutlinedButton(
                onClick = onDelete,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = MaterialTheme.colorScheme.error,
                ),
                border = BorderStroke(
                    width = 1.dp,
                    color = MaterialTheme.colorScheme.error.copy(alpha = 0.55f),
                ),
            ) {
                Icon(Icons.Outlined.DeleteOutline, contentDescription = null)
                Text("删除计划", modifier = Modifier.padding(start = 6.dp))
            }

            Spacer(modifier = Modifier.height(20.dp))
        }
    }
}

@Composable
private fun DayTabs(
    days: List<PlanDay>,
    selectedDayIndex: Int,
    onSelectDay: (Int) -> Unit,
) {
    Row(
        modifier = Modifier.horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        val overviewSelected = selectedDayIndex == 0
        Surface(
            modifier = Modifier.clickable { onSelectDay(0) },
            color = if (overviewSelected) Color(0xFFE8F7FF) else Color(0xFFF4F7FB),
            shape = RoundedCornerShape(50),
        ) {
            Text(
                text = "全程总览",
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 9.dp),
                color = if (overviewSelected) MaterialTheme.colorScheme.primary else Color(0xFF667085),
                fontWeight = FontWeight.Bold,
            )
        }
        days.forEach { day ->
            val selected = day.dayIndex == selectedDayIndex
            Surface(
                modifier = Modifier.clickable { onSelectDay(day.dayIndex) },
                color = if (selected) Color(0xFFE8F7FF) else Color(0xFFF4F7FB),
                shape = RoundedCornerShape(50),
            ) {
                Text(
                    text = day.title,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 9.dp),
                    color = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF667085),
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun RouteModeTabs(
    selectedMode: String,
    onSelectMode: (String) -> Unit,
) {
    Row(
        modifier = Modifier.horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        RouteModes.all.forEach { mode ->
            val selected = mode == selectedMode
            Surface(
                modifier = Modifier.clickable { onSelectMode(mode) },
                color = if (selected) MaterialTheme.colorScheme.primary else Color(0xFFF4F7FB),
                shape = RoundedCornerShape(50),
            ) {
                Text(
                    text = RouteModes.label(mode),
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                    color = if (selected) Color.White else Color(0xFF667085),
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}

@Composable
private fun RouteSummary(
    route: DayRoutePlan?,
    loading: Boolean,
    error: String?,
    onRetry: () -> Unit,
) {
    Surface(
        color = Color(0xFFF6FAFF),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when {
                loading -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        Text("正在计算真实路线...", modifier = Modifier.padding(start = 10.dp))
                    }
                }
                error != null -> {
                    Text(error, color = Color(0xFFB42318))
                    OutlinedButton(onClick = onRetry) {
                        Text("重试")
                    }
                }
                route == null || route.places.size < 2 -> {
                    Text("至少加入 2 个带坐标的真实地点后，就可以生成路线。")
                }
                else -> {
                    Text("路线总览", fontWeight = FontWeight.Bold)
                    Text(
                        text = "${formatDistance(route.totalDistanceMeters)} · ${formatDuration(route.totalDurationSeconds)} · ${routeTransportLabel(route)}",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

@Composable
private fun OptimizationBanner(
    uiState: PlanDetailUiState,
    onOptimize: () -> Unit,
    onApplyOptimization: () -> Unit,
    onDismissOptimization: () -> Unit,
) {
    val itemCount = uiState.selectedDay?.items?.size ?: 0
    if (uiState.optimization != null) {
        val optimizedRoute = uiState.optimization.route
        val originalRoute = uiState.route
        val savedDistance = ((originalRoute?.totalDistanceMeters ?: 0) - optimizedRoute.totalDistanceMeters)
            .coerceAtLeast(0)
        val savedDuration = ((originalRoute?.totalDurationSeconds ?: 0) - optimizedRoute.totalDurationSeconds)
            .coerceAtLeast(0)
        Surface(color = Color(0xFFEAF8EF), shape = RoundedCornerShape(20.dp)) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Text("已生成优化顺序预览", fontWeight = FontWeight.Bold, color = Color(0xFF166534))
                Text(
                    text = "优化后：${formatDistance(optimizedRoute.totalDistanceMeters)} · ${formatDuration(optimizedRoute.totalDurationSeconds)}",
                    color = Color(0xFF166534),
                    fontWeight = FontWeight.SemiBold,
                )
                if (savedDistance > 0 || savedDuration > 0) {
                    Text("预计节省：${formatDistance(savedDistance)} · ${formatDuration(savedDuration)}")
                }
                Text(uiState.optimization.warning ?: "你可以先看看地图和列表变化，确认后再应用到计划。")
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(onClick = onApplyOptimization, shape = RoundedCornerShape(16.dp)) {
                        Text("确认应用")
                    }
                    OutlinedButton(onClick = onDismissOptimization, shape = RoundedCornerShape(16.dp)) {
                        Text("取消预览")
                    }
                }
            }
        }
    } else {
        OutlinedButton(
            onClick = onOptimize,
            enabled = itemCount >= 3 && !uiState.isOptimizing,
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
        ) {
            if (uiState.isOptimizing) {
                CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                Spacer(modifier = Modifier.size(8.dp))
            }
            Text(if (uiState.isOptimizing) "正在优化..." else "路线优化")
        }
    }
}

@Composable
private fun DayItinerary(
    day: PlanDay?,
    items: List<PlanItem>,
    route: DayRoutePlan?,
    routeLoading: Boolean,
    previewing: Boolean,
    onReorderItems: (List<String>) -> Unit,
    onSelectSegmentMode: (String, String) -> Unit,
    onOpenPlace: (PlanItem) -> Unit,
) {
    var visualItems by remember(day?.id) { mutableStateOf(items) }
    var activeItemId by remember(day?.id) { mutableStateOf<String?>(null) }
    var pointerDragging by remember(day?.id) { mutableStateOf(false) }
    var dragOffsetY by remember(day?.id) { mutableFloatStateOf(0f) }
    var dragStartIndex by remember(day?.id) { mutableIntStateOf(-1) }
    var targetIndex by remember(day?.id) { mutableIntStateOf(-1) }
    var pendingTargetIndex by remember(day?.id) { mutableIntStateOf(-1) }
    var settleFromY by remember(day?.id) { mutableFloatStateOf(0f) }
    var settleToY by remember(day?.id) { mutableFloatStateOf(0f) }
    var settleRequestId by remember(day?.id) { mutableIntStateOf(0) }
    var settleReady by remember(day?.id) { mutableStateOf(false) }
    var reorderVersion by remember(day?.id) { mutableIntStateOf(0) }
    val settleOffsetY = remember(day?.id) { Animatable(0f) }
    val itemHeights = remember(day?.id) { mutableStateMapOf<String, Int>() }
    val itemSpacingPx = with(LocalDensity.current) { 12.dp.toPx() }
    val fallbackItemHeightPx = with(LocalDensity.current) { 92.dp.toPx() }
    val hapticFeedback = LocalHapticFeedback.current

    LaunchedEffect(items) {
        if (activeItemId == null) visualItems = items
    }

    fun measuredHeight(index: Int): Float {
        val item = visualItems.getOrNull(index) ?: return fallbackItemHeightPx
        return itemHeights[item.id]?.toFloat() ?: fallbackItemHeightPx
    }

    fun itemTop(index: Int): Float {
        var top = 0f
        repeat(index.coerceAtLeast(0)) { itemIndex ->
            top += measuredHeight(itemIndex) + itemSpacingPx
        }
        return top
    }

    fun resolveTargetIndex(startIndex: Int, rawOffsetY: Float): Int {
        if (startIndex !in visualItems.indices) return startIndex
        val draggedCenter = itemTop(startIndex) + measuredHeight(startIndex) / 2f + rawOffsetY
        var resolved = startIndex
        if (rawOffsetY > 0f) {
            for (index in (startIndex + 1)..visualItems.lastIndex) {
                val itemCenter = itemTop(index) + measuredHeight(index) / 2f
                if (draggedCenter >= itemCenter) resolved = index else break
            }
        } else if (rawOffsetY < 0f) {
            for (index in (startIndex - 1) downTo 0) {
                val itemCenter = itemTop(index) + measuredHeight(index) / 2f
                if (draggedCenter <= itemCenter) resolved = index else break
            }
        }
        return resolved
    }

    fun targetDisplacement(startIndex: Int, endIndex: Int): Float {
        if (startIndex !in visualItems.indices || endIndex !in visualItems.indices) return 0f
        var displacement = 0f
        if (endIndex > startIndex) {
            for (index in (startIndex + 1)..endIndex) {
                displacement += measuredHeight(index) + itemSpacingPx
            }
        } else if (endIndex < startIndex) {
            for (index in endIndex until startIndex) {
                displacement -= measuredHeight(index) + itemSpacingPx
            }
        }
        return displacement
    }

    fun requestSettle(endIndex: Int) {
        pendingTargetIndex = endIndex.coerceIn(0, visualItems.lastIndex.coerceAtLeast(0))
        settleFromY = dragOffsetY
        settleToY = targetDisplacement(dragStartIndex, pendingTargetIndex)
        pointerDragging = false
        settleReady = false
        settleRequestId += 1
    }

    LaunchedEffect(settleRequestId) {
        if (settleRequestId == 0) return@LaunchedEffect
        val itemId = activeItemId ?: return@LaunchedEffect
        settleOffsetY.snapTo(settleFromY)
        settleReady = true
        settleOffsetY.animateTo(
            targetValue = settleToY,
            animationSpec = spring(
                dampingRatio = 0.86f,
                stiffness = Spring.StiffnessMediumLow,
            ),
        )

        val sourceIndex = visualItems.indexOfFirst { it.id == itemId }
        val destinationIndex = pendingTargetIndex.coerceIn(0, visualItems.lastIndex)
        val reordered = visualItems.toMutableList()
        if (sourceIndex in reordered.indices && sourceIndex != destinationIndex) {
            val movedItem = reordered.removeAt(sourceIndex)
            reordered.add(destinationIndex, movedItem)
        }
        val orderChanged = reordered.map { it.id } != visualItems.map { it.id }
        visualItems = reordered
        reorderVersion += 1
        activeItemId = null
        pointerDragging = false
        dragOffsetY = 0f
        dragStartIndex = -1
        targetIndex = -1
        pendingTargetIndex = -1
        settleReady = false
        settleOffsetY.snapTo(0f)
        if (orderChanged) onReorderItems(reordered.map { it.id })
    }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                day?.title ?: "DAY 1",
                modifier = Modifier.weight(1f),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            if (previewing) {
                Surface(color = Color(0xFFEAF8EF), shape = RoundedCornerShape(50)) {
                    Text(
                        text = "优化预览",
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                        color = Color(0xFF166534),
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        if (!previewing && visualItems.size > 1) {
            Text(
                text = "长按地点并上下拖动，可调整当天的游览顺序",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
        }
        if (visualItems.isEmpty()) {
            EmptyDayCard()
        } else {
            visualItems.forEachIndexed { index, item ->
                androidx.compose.runtime.key(item.id) {
                    val active = activeItemId == item.id
                    val dragEnabled = !previewing && visualItems.size > 1
                    val draggedSlotHeight = if (dragStartIndex in visualItems.indices) {
                        measuredHeight(dragStartIndex) + itemSpacingPx
                    } else {
                        0f
                    }
                    val siblingTargetOffset = when {
                        activeItemId == null || index == dragStartIndex -> 0f
                        targetIndex > dragStartIndex && index in (dragStartIndex + 1)..targetIndex ->
                            -draggedSlotHeight
                        targetIndex < dragStartIndex && index in targetIndex until dragStartIndex ->
                            draggedSlotHeight
                        else -> 0f
                    }
                    val animatedSiblingOffset by androidx.compose.runtime.key(reorderVersion) {
                        animateFloatAsState(
                            targetValue = siblingTargetOffset,
                            animationSpec = spring(
                                dampingRatio = 0.86f,
                                stiffness = Spring.StiffnessMediumLow,
                            ),
                            label = "相邻地点让位",
                        )
                    }
                    val activeOffset = when {
                        !active -> 0f
                        pointerDragging -> dragOffsetY
                        settleReady -> settleOffsetY.value
                        else -> dragOffsetY
                    }
                    PlanItemCard(
                        item = item,
                        nextPlaceName = visualItems.getOrNull(index + 1)?.name,
                        nextSegmentText = when {
                            routeLoading && index < visualItems.lastIndex -> "正在重新计算..."
                            else -> route?.segments?.getOrNull(index)?.let {
                                "${formatDistance(it.distanceMeters)} · ${formatDuration(it.durationSeconds)}"
                            }
                        },
                        segmentMode = route?.segments?.getOrNull(index)?.mode
                            ?: item.transportModeToNext,
                        segmentSteps = route?.segments?.getOrNull(index)?.steps.orEmpty(),
                        segmentEditable = !previewing,
                        onSegmentModeChange = { mode -> onSelectSegmentMode(item.id, mode) },
                        dragEnabled = dragEnabled,
                        isDragging = active,
                        onOpenPlace = { onOpenPlace(item) },
                        modifier = Modifier
                            .zIndex(if (active) 1f else 0f)
                            .onSizeChanged { size -> itemHeights[item.id] = size.height }
                            .graphicsLayer {
                                translationY = if (active) activeOffset else animatedSiblingOffset
                            }
                            .pointerInput(item.id, dragEnabled, reorderVersion) {
                                if (!dragEnabled) return@pointerInput
                                detectDragGesturesAfterLongPress(
                                    onDragStart = {
                                        if (activeItemId != null) return@detectDragGesturesAfterLongPress
                                        activeItemId = item.id
                                        dragStartIndex = index
                                        targetIndex = index
                                        pendingTargetIndex = index
                                        pointerDragging = true
                                        dragOffsetY = 0f
                                        hapticFeedback.performHapticFeedback(HapticFeedbackType.LongPress)
                                    },
                                    onDrag = { change, dragAmount ->
                                        change.consume()
                                        if (activeItemId != item.id || !pointerDragging) {
                                            return@detectDragGesturesAfterLongPress
                                        }
                                        dragOffsetY += dragAmount.y
                                        targetIndex = resolveTargetIndex(dragStartIndex, dragOffsetY)
                                    },
                                    onDragEnd = {
                                        if (activeItemId == item.id) requestSettle(targetIndex)
                                    },
                                    onDragCancel = {
                                        if (activeItemId == item.id) requestSettle(dragStartIndex)
                                    },
                                )
                            },
                    )
                }
            }
        }
    }
}

@Composable
private fun UnplannedSection(
    items: List<PlanItem>,
    days: List<PlanDay>,
    onMoveToDay: (String, Int) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("待规划", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        if (items.isEmpty()) {
            Surface(color = Color(0xFFF8FAFC), shape = RoundedCornerShape(20.dp)) {
                Text(
                    text = "暂时没有待规划地点。你可以从探索页先把地点放到这里，再安排到某一天。",
                    modifier = Modifier.padding(16.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            items.sortedBy { it.visitOrder }.forEach { item ->
                Surface(color = Color(0xFFFFFBF0), shape = RoundedCornerShape(20.dp)) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(item.name, fontWeight = FontWeight.Bold)
                        Text(
                            text = listOfNotNull(item.typeName, item.districtName, item.address).joinToString(" · "),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            days.forEach { day ->
                                OutlinedButton(
                                    onClick = { onMoveToDay(item.id, day.dayIndex) },
                                    enabled = item.latitude != null && item.longitude != null,
                                    shape = RoundedCornerShape(50),
                                ) {
                                    Text("移到 ${day.title}")
                                }
                            }
                        }
                        if (item.latitude == null || item.longitude == null) {
                            Text(
                                text = "这个地点缺少坐标，只能先作为普通待规划地点保存。",
                                color = Color(0xFFB42318),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PlanOverviewItinerary(
    days: List<PlanDay>,
    onOpenPlace: (PlanItem) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        days.sortedBy { it.dayIndex }.forEach { day ->
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(
                        text = day.title,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF071A3D),
                    )
                    Text(
                        text = "${day.items.size} 个地点",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                val items = day.items.sortedBy { it.visitOrder }
                if (items.isEmpty()) {
                    EmptyDayCard()
                } else {
                    items.forEach { item ->
                        PlanItemCard(
                            item = item,
                            nextSegmentText = null,
                            dragEnabled = false,
                            isDragging = false,
                            onOpenPlace = { onOpenPlace(item) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyDayCard() {
    Surface(color = Color(0xFFF6FAFF), shape = RoundedCornerShape(22.dp)) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("这一天还没有地点", fontWeight = FontWeight.Bold)
            Text("去探索页选择地点，点击 + 加入计划。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun PlanItemCard(
    item: PlanItem,
    nextPlaceName: String? = null,
    nextSegmentText: String?,
    segmentMode: String? = null,
    segmentSteps: List<RouteStep> = emptyList(),
    segmentEditable: Boolean = false,
    onSegmentModeChange: (String) -> Unit = {},
    dragEnabled: Boolean,
    isDragging: Boolean,
    onOpenPlace: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var modeMenuExpanded by remember(item.id) { mutableStateOf(false) }
    val containerColor by animateColorAsState(
        targetValue = if (isDragging) Color(0xFFF4F8FF) else Color.Transparent,
        animationSpec = spring(
            dampingRatio = 0.88f,
            stiffness = Spring.StiffnessMedium,
        ),
        label = "拖拽地点背景",
    )
    val elevation by animateDpAsState(
        targetValue = if (isDragging) 8.dp else 0.dp,
        animationSpec = spring(
            dampingRatio = 0.82f,
            stiffness = Spring.StiffnessMedium,
        ),
        label = "拖拽地点阴影",
    )

    Surface(
        modifier = modifier
            .fillMaxWidth()
            .clickable(enabled = !isDragging, onClick = onOpenPlace),
        color = containerColor,
        shape = RoundedCornerShape(16.dp),
        shadowElevation = elevation,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PlaceCoverImage(
                    imageUrl = item.thumbnailUrl?.takeIf(String::isNotBlank)
                        ?: item.imageUrls.firstOrNull { it.isNotBlank() },
                    placeName = item.name,
                    category = item.category,
                    modifier = Modifier.size(64.dp),
                    shape = RoundedCornerShape(16.dp),
                )
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .padding(start = 12.dp),
                ) {
                    Text(item.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Row(
                        modifier = Modifier.padding(top = 3.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            Icons.Outlined.AccessTime,
                            contentDescription = null,
                            modifier = Modifier.size(15.dp),
                            tint = MaterialTheme.colorScheme.primary,
                        )
                        Text(
                            text = visitTimeLabel(item),
                            modifier = Modifier.padding(start = 5.dp),
                            color = MaterialTheme.colorScheme.primary,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Text(
                        text = listOfNotNull(item.typeName, item.districtName, item.address).joinToString(" · "),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = "点击查看地点详情",
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Icon(
                    imageVector = Icons.Outlined.DragHandle,
                    contentDescription = if (dragEnabled) "长按拖动调整顺序" else "当前不能调整顺序",
                    modifier = Modifier.size(28.dp),
                    tint = if (dragEnabled) Color(0xFF667085) else Color(0xFFC4CAD4),
                )
            }
            if (nextPlaceName != null) {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(start = 76.dp),
                    color = Color(0xFFF6FAFF),
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Text(
                            text = "到 $nextPlaceName：${nextSegmentText ?: "等待路线数据"}",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Box {
                            OutlinedButton(
                                onClick = { modeMenuExpanded = true },
                                enabled = segmentEditable,
                                modifier = Modifier.height(48.dp),
                                shape = RoundedCornerShape(14.dp),
                            ) {
                                Text("交通方式：${RouteModes.label(segmentMode ?: item.transportModeToNext, segmentSteps)}")
                            }
                            DropdownMenu(
                                expanded = modeMenuExpanded,
                                onDismissRequest = { modeMenuExpanded = false },
                            ) {
                                listOf(
                                    RouteModes.WALKING,
                                    RouteModes.TRANSIT,
                                    RouteModes.DRIVING,
                                    RouteModes.CYCLING,
                                ).forEach { mode ->
                                    DropdownMenuItem(
                                        text = { Text(RouteModes.label(mode)) },
                                        onClick = {
                                            modeMenuExpanded = false
                                            onSegmentModeChange(mode)
                                        },
                                    )
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
private fun PlanRouteMap(
    items: List<PlanItem>,
    route: DayRoutePlan?,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    if (!isAmapNativeRuntimeSupported(context)) {
        Box(
            modifier = modifier.background(Brush.verticalGradient(listOf(Color(0xFFEAF5FF), Color(0xFFF8FBFF)))),
            contentAlignment = Alignment.Center,
        ) {
            Text("当前模拟器无法加载真实高德地图")
        }
        return
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    val initialMapCenter = items.firstOrNull { it.latitude != null && it.longitude != null }?.let {
        LatLng(it.latitude!!, it.longitude!!)
    }
    val mapView = remember {
        MapView(context).apply {
            onCreate(Bundle())
            initialMapCenter?.let { center ->
                map.moveCamera(CameraUpdateFactory.newLatLngZoom(center, 13.2f))
            }
        }
    }

    DisposableEffect(lifecycleOwner, mapView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_DESTROY -> mapView.onDestroy()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            mapView.onDestroy()
        }
    }

    Box(modifier = modifier) {
        AndroidView(
            factory = {
                mapView.apply {
                    map.mapType = AMap.MAP_TYPE_NORMAL
                    map.showBuildings(false)
                    map.showIndoorMap(false)
                    map.showMapText(true)
                    map.uiSettings.isZoomControlsEnabled = false
                    map.uiSettings.isMyLocationButtonEnabled = false
                    map.uiSettings.isCompassEnabled = false
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .background(Color.White.copy(alpha = 0.36f)),
        )
    }

    LaunchedEffect(items, route) {
        val amap = mapView.map
        amap.clear()
        val boundsBuilder = LatLngBounds.builder()
        var hasBounds = false

        val polylinePoints = route?.segments.orEmpty()
            .flatMap { it.polyline }
            .map { LatLng(it.latitude, it.longitude) }
        if (polylinePoints.size >= 2) {
            amap.addPolyline(
                PolylineOptions()
                    .addAll(polylinePoints)
                    .width(12f)
                    .color(AndroidColor.rgb(42, 169, 230))
                    .zIndex(8f),
            )
            polylinePoints.forEach {
                boundsBuilder.include(it)
                hasBounds = true
            }
        }

        val photoMarkers = mutableListOf<Pair<com.amap.api.maps.model.Marker, PlanItem>>()
        items.forEach { item ->
            val lat = item.latitude ?: return@forEach
            val lng = item.longitude ?: return@forEach
            val latLng = LatLng(lat, lng)
            val marker = amap.addMarker(
                MarkerOptions()
                    .position(latLng)
                    .icon(BitmapDescriptorFactory.fromBitmap(createPlanPlaceMarker(context, item, null)))
                    .anchor(0.5f, 0.5f)
                    .zIndex(20f),
            )
            if (marker != null && (item.thumbnailUrl != null || item.imageUrls.isNotEmpty())) {
                photoMarkers += marker to item
            }
            boundsBuilder.include(latLng)
            hasBounds = true
        }

        val markerPhotoSize = (64f * context.resources.displayMetrics.density).toInt()
        photoMarkers.forEach { (marker, item) ->
            val imageUrl = item.thumbnailUrl?.takeIf { it.isNotBlank() }
                ?: item.imageUrls.firstOrNull { it.isNotBlank() }
            val photo = loadMapMarkerImage(context, imageUrl, markerPhotoSize)
            if (photo != null) {
                marker.setIcon(BitmapDescriptorFactory.fromBitmap(createPlanPlaceMarker(context, item, photo)))
            }
        }

        if (hasBounds) {
            amap.animateCamera(CameraUpdateFactory.newLatLngBounds(boundsBuilder.build(), 90))
        }
    }
}

private fun createPlanPlaceMarker(context: Context, item: PlanItem, photo: Bitmap?): Bitmap {
    val density = context.resources.displayMetrics.density
    val size = (48 * density).toInt()
    val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val center = size / 2f
    val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
        setShadowLayer(5f * density, 0f, 2f * density, AndroidColor.argb(60, 0, 0, 0))
    }
    canvas.drawCircle(center, center, center - 3 * density, backgroundPaint)
    val radius = center - 6 * density
    if (photo != null) {
        val clip = Path().apply { addCircle(center, center, radius, Path.Direction.CW) }
        canvas.save()
        canvas.clipPath(clip)
        canvas.drawBitmap(
            photo,
            null,
            RectF(center - radius, center - radius, center + radius, center + radius),
            Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG),
        )
        canvas.restore()
    } else {
        val iconRes = when (item.category) {
            "food" -> R.drawable.ic_marker_food
            "drink" -> R.drawable.ic_marker_drink
            "shopping" -> R.drawable.ic_marker_shopping
            "lodging" -> R.drawable.ic_marker_lodging
            "transport" -> R.drawable.ic_marker_transport
            else -> R.drawable.ic_marker_scenic
        }
        val icon = context.getDrawable(iconRes)?.mutate()
        val half = (13f * density).toInt()
        icon?.setTint(AndroidColor.rgb(31, 122, 224))
        icon?.setBounds((center - half).toInt(), (center - half).toInt(), (center + half).toInt(), (center + half).toInt())
        icon?.draw(canvas)
    }
    val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f * density
        color = AndroidColor.rgb(49, 180, 224)
    }
    canvas.drawCircle(center, center, radius, ring)
    return bitmap
}

private fun isAmapNativeRuntimeSupported(context: Context): Boolean {
    val nativeLibraryDir = context.applicationInfo.nativeLibraryDir.orEmpty()
    if (nativeLibraryDir.contains("arm64") || nativeLibraryDir.contains("armeabi")) return true
    val primaryAbi = Build.SUPPORTED_ABIS.firstOrNull().orEmpty()
    return primaryAbi == "arm64-v8a" || primaryAbi == "armeabi-v7a"
}

private fun orderedPreviewItems(
    items: List<PlanItem>,
    optimizedPlaceIds: List<String>?,
): List<PlanItem> {
    val sortedItems = items.sortedBy { it.visitOrder }
    if (optimizedPlaceIds.isNullOrEmpty()) return sortedItems
    val byId = sortedItems.associateBy { it.id }
    val optimized = optimizedPlaceIds.mapNotNull(byId::get)
    val remaining = sortedItems.filterNot { it.id in optimizedPlaceIds }
    return optimized + remaining
}

private fun visitTimeLabel(item: PlanItem): String {
    return when {
        !item.suggestedStart.isNullOrBlank() && !item.suggestedEnd.isNullOrBlank() ->
            "${item.suggestedStart} - ${item.suggestedEnd}"
        !item.suggestedStart.isNullOrBlank() -> "${item.suggestedStart} 起"
        !item.suggestedEnd.isNullOrBlank() -> "${item.suggestedEnd} 前结束"
        else -> "时间待安排"
    }
}

private fun routeTransportLabel(route: DayRoutePlan): String {
    val actualModes = route.segments
        .map { RouteModes.label(it.mode, it.steps) }
        .distinct()
    return when {
        actualModes.isEmpty() -> RouteModes.label(route.mode)
        actualModes.size == 1 -> actualModes.first()
        else -> actualModes.joinToString(" + ")
    }
}

private fun formatDistance(meters: Int): String {
    return if (meters >= 1000) {
        "%.1f 公里".format(meters / 1000f)
    } else {
        "$meters 米"
    }
}

private fun formatDuration(seconds: Int): String {
    val minutes = (seconds / 60).coerceAtLeast(1)
    return if (minutes >= 60) {
        "${minutes / 60} 小时 ${minutes % 60} 分钟"
    } else {
        "$minutes 分钟"
    }
}
