package com.heoclub.aitravel.ui.detail

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
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
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.MoveDirection
import android.graphics.Color as AndroidColor

@Composable
fun PlanDetailScreen(
    viewModel: PlanDetailViewModel,
    onBack: () -> Unit,
    onAskAi: (String) -> Unit,
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
        items = uiState.selectedDay?.items.orEmpty(),
        optimizedPlaceIds = uiState.optimization?.optimizedPlaceIds,
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
                    .height(360.dp),
            )
            PlanDetailSheet(
                plan = plan,
                uiState = uiState,
                onBack = onBack,
                onAskAi = { onAskAi(plan.id) },
                onSelectDay = viewModel::selectDay,
                onSelectMode = viewModel::selectMode,
                onMoveItem = viewModel::moveItem,
                onMoveUnplannedToDay = viewModel::moveUnplannedItemToDay,
                onOptimize = viewModel::optimizeRoute,
                onApplyOptimization = viewModel::applyOptimization,
                onDismissOptimization = viewModel::dismissOptimization,
                onRetry = viewModel::retryRoute,
                modifier = Modifier.weight(1f),
            )
        }

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
    onBack: () -> Unit,
    onAskAi: () -> Unit,
    onSelectDay: (Int) -> Unit,
    onSelectMode: (String) -> Unit,
    onMoveItem: (String, MoveDirection) -> Unit,
    onMoveUnplannedToDay: (String, Int) -> Unit,
    onOptimize: () -> Unit,
    onApplyOptimization: () -> Unit,
    onDismissOptimization: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val displayRoute = uiState.optimization?.route ?: uiState.route
    val displayItems = orderedPreviewItems(
        items = uiState.selectedDay?.items.orEmpty(),
        optimizedPlaceIds = uiState.optimization?.optimizedPlaceIds,
    )

    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
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
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Box(
                    modifier = Modifier
                        .size(width = 48.dp, height = 5.dp)
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
                previewing = uiState.optimization != null,
                onMoveItem = onMoveItem,
            )

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
                    Text("问 AI", modifier = Modifier.padding(start = 6.dp))
                }
                OutlinedButton(
                    onClick = onBack,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Icon(Icons.Outlined.Add, contentDescription = null)
                    Text("继续加地点", modifier = Modifier.padding(start = 6.dp))
                }
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
                        text = "${formatDistance(route.totalDistanceMeters)} · ${formatDuration(route.totalDurationSeconds)} · ${RouteModes.label(route.mode)}",
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
    previewing: Boolean,
    onMoveItem: (String, MoveDirection) -> Unit,
) {
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
        if (items.isEmpty()) {
            EmptyDayCard()
        } else {
            items.forEachIndexed { index, item ->
                PlanItemCard(
                    index = index,
                    item = item,
                    nextSegmentText = route?.segments?.getOrNull(index)?.let {
                        "${formatDistance(it.distanceMeters)} · ${formatDuration(it.durationSeconds)}"
                    },
                    canMoveUp = !previewing && index > 0,
                    canMoveDown = !previewing && index < items.lastIndex,
                    onMoveUp = { if (!previewing) onMoveItem(item.id, MoveDirection.UP) },
                    onMoveDown = { if (!previewing) onMoveItem(item.id, MoveDirection.DOWN) },
                )
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
private fun EmptyDayCard() {
    Surface(color = Color(0xFFF6FAFF), shape = RoundedCornerShape(22.dp)) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("这一天还没有地点", fontWeight = FontWeight.Bold)
            Text("去探索页选择真实高德地点，点击 + 加入计划。", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun PlanItemCard(
    index: Int,
    item: PlanItem,
    nextSegmentText: String?,
    canMoveUp: Boolean,
    canMoveDown: Boolean,
    onMoveUp: () -> Unit,
    onMoveDown: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(color = Color(0xFFE8F7FF), shape = CircleShape) {
                Text(
                    text = "${index + 1}",
                    modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Bold,
                )
            }
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 12.dp),
            ) {
                Text(item.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                Text(
                    text = listOfNotNull(item.typeName, item.districtName, item.address).joinToString(" · "),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            IconButton(onClick = onMoveUp, enabled = canMoveUp) {
                Icon(Icons.Outlined.KeyboardArrowUp, contentDescription = "上移")
            }
            IconButton(onClick = onMoveDown, enabled = canMoveDown) {
                Icon(Icons.Outlined.KeyboardArrowDown, contentDescription = "下移")
            }
        }
        if (nextSegmentText != null) {
            Text(
                text = "下一段：$nextSegmentText",
                modifier = Modifier.padding(start = 42.dp),
                color = Color(0xFF98A2B3),
                style = MaterialTheme.typography.bodySmall,
            )
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
    val mapView = remember {
        MapView(context).apply { onCreate(Bundle()) }
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
                    map.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(39.9105, 116.3972), 12.8f))
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

        items.forEachIndexed { index, item ->
            val lat = item.latitude ?: return@forEachIndexed
            val lng = item.longitude ?: return@forEachIndexed
            val latLng = LatLng(lat, lng)
            amap.addMarker(
                MarkerOptions()
                    .position(latLng)
                    .icon(BitmapDescriptorFactory.fromBitmap(createNumberedMarker(context, index + 1)))
                    .anchor(0.5f, 0.5f)
                    .zIndex(20f),
            )
            boundsBuilder.include(latLng)
            hasBounds = true
        }

        if (hasBounds) {
            amap.animateCamera(CameraUpdateFactory.newLatLngBounds(boundsBuilder.build(), 90))
        }
    }
}

private fun createNumberedMarker(context: Context, number: Int): Bitmap {
    val density = context.resources.displayMetrics.density
    val size = (42 * density).toInt()
    val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val center = size / 2f
    val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(49, 180, 224)
        setShadowLayer(5f * density, 0f, 2f * density, AndroidColor.argb(60, 0, 0, 0))
    }
    canvas.drawCircle(center, center, center - 3 * density, paint)
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
        textSize = 16f * density
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }
    val y = center - (textPaint.descent() + textPaint.ascent()) / 2
    canvas.drawText(number.toString(), center, y, textPaint)
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
