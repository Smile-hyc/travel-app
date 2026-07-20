package com.heoclub.aitravel.ui.journey

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.Orientation
import androidx.compose.foundation.gestures.draggable
import androidx.compose.foundation.gestures.rememberDraggableState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.AssistChip
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
import com.amap.api.maps.model.PolygonOptions
import com.amap.api.services.core.AMapException
import com.amap.api.services.district.DistrictResult
import com.amap.api.services.district.DistrictSearch
import com.amap.api.services.district.DistrictSearchQuery
import java.time.format.DateTimeFormatter
import android.graphics.Canvas as AndroidCanvas
import android.graphics.Color as AndroidColor

private data class JourneyCity(
    val name: String,
    val province: String,
    val aliases: List<String>,
    val latitude: Double,
    val longitude: Double,
    val visited: Boolean,
    val noteCount: Int,
    val guideCount: Int,
    val records: List<JourneyRecord>,
)

private data class JourneyRecord(
    val title: String,
    val type: String,
    val summary: String,
)

private data class ProvinceBoundary(
    val province: String,
    val rings: List<List<LatLng>>,
)

private val journeyCities = listOf(
    JourneyCity(
        name = "北京市",
        province = "北京市",
        aliases = listOf("北京", "beijing", "bj"),
        latitude = 39.9042,
        longitude = 116.4074,
        visited = true,
        noteCount = 4,
        guideCount = 2,
        records = listOf(
            JourneyRecord("故宫午后路线", "攻略", "午门进、神武门出，留足半天给展厅和角楼。"),
            JourneyRecord("景山看日落", "笔记", "傍晚登顶能俯瞰中轴线，拍照光线更柔和。"),
        ),
    ),
    JourneyCity(
        name = "上海市",
        province = "上海市",
        aliases = listOf("上海", "shanghai", "sh"),
        latitude = 31.2304,
        longitude = 121.4737,
        visited = true,
        noteCount = 3,
        guideCount = 3,
        records = listOf(
            JourneyRecord("武康路街区散步", "笔记", "上午人少，咖啡店和老建筑适合慢慢逛。"),
            JourneyRecord("外滩夜景机位", "攻略", "南京东路步行到外滩，避开晚高峰人流。"),
        ),
    ),
    JourneyCity(
        name = "成都市",
        province = "四川省",
        aliases = listOf("成都", "chengdu", "cd"),
        latitude = 30.5728,
        longitude = 104.0668,
        visited = true,
        noteCount = 6,
        guideCount = 4,
        records = listOf(
            JourneyRecord("宽窄巷子夜游", "笔记", "从人民公园走过去，茶馆和小吃可以连在一起。"),
            JourneyRecord("熊猫基地半日", "攻略", "早到看幼年熊猫活动，返程可接春熙路。"),
        ),
    ),
    JourneyCity(
        name = "西安市",
        province = "陕西省",
        aliases = listOf("西安", "xian", "xa"),
        latitude = 34.3416,
        longitude = 108.9398,
        visited = false,
        noteCount = 0,
        guideCount = 2,
        records = listOf(
            JourneyRecord("城墙骑行备选", "攻略", "南门上城墙更方便，傍晚温度更舒适。"),
        ),
    ),
    JourneyCity(
        name = "广州市",
        province = "广东省",
        aliases = listOf("广州", "guangzhou", "gz"),
        latitude = 23.1291,
        longitude = 113.2644,
        visited = true,
        noteCount = 5,
        guideCount = 2,
        records = listOf(
            JourneyRecord("老城区早茶", "笔记", "荔湾一带适合把早茶、骑楼和小吃串起来。"),
            JourneyRecord("珠江夜游", "攻略", "靠近蓝调时刻登船，城市灯光层次更好。"),
        ),
    ),
    JourneyCity(
        name = "杭州市",
        province = "浙江省",
        aliases = listOf("杭州", "hangzhou", "hz"),
        latitude = 30.2741,
        longitude = 120.1551,
        visited = false,
        noteCount = 0,
        guideCount = 3,
        records = listOf(
            JourneyRecord("西湖慢行路线", "攻略", "断桥到苏堤适合步行，返程可接灵隐。"),
        ),
    ),
    JourneyCity(
        name = "昆明市",
        province = "云南省",
        aliases = listOf("昆明", "kunming", "km"),
        latitude = 25.0389,
        longitude = 102.7183,
        visited = false,
        noteCount = 0,
        guideCount = 1,
        records = listOf(
            JourneyRecord("滇池海埂公园", "攻略", "冬季看海鸥，建议安排在晴朗上午。"),
        ),
    ),
    JourneyCity(
        name = "哈尔滨市",
        province = "黑龙江省",
        aliases = listOf("哈尔滨", "haerbin", "harbin", "heb"),
        latitude = 45.8038,
        longitude = 126.5349,
        visited = false,
        noteCount = 0,
        guideCount = 2,
        records = listOf(
            JourneyRecord("冰雪大世界", "攻略", "傍晚入园能同时看到白天和夜景。"),
        ),
    ),
)

private val provinceCenters = mapOf(
    "北京市" to LatLng(40.12, 116.40),
    "上海市" to LatLng(31.23, 121.47),
    "四川省" to LatLng(30.65, 104.07),
    "陕西省" to LatLng(34.32, 108.94),
    "广东省" to LatLng(23.13, 113.27),
    "浙江省" to LatLng(30.27, 120.15),
    "云南省" to LatLng(25.04, 102.72),
    "黑龙江省" to LatLng(45.80, 126.53),
)

private class JourneyMapViewHolder(
    private val context: Context,
) {
    private var mapView: MapView? = null
    private var resumed = false
    private val boundaryCache = mutableMapOf<String, ProvinceBoundary>()
    private val pendingBoundaryRequests = mutableSetOf<String>()
    private var lastSelectedCityName: String? = null

    fun obtain(): MapView {
        return mapView ?: MapView(context).apply {
            onCreate(Bundle())
            map.mapType = AMap.MAP_TYPE_NORMAL
            map.showBuildings(false)
            map.showIndoorMap(false)
            map.showMapText(false)
            map.uiSettings.isZoomControlsEnabled = false
            map.uiSettings.isMyLocationButtonEnabled = false
            map.uiSettings.isCompassEnabled = false
            map.uiSettings.isScaleControlsEnabled = false
            map.moveCamera(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(35.8617, 104.1954),
                    3.65f,
                ),
            )
        }.also { mapView = it }
    }

    fun resume() {
        if (resumed) return
        obtain().onResume()
        resumed = true
    }

    fun pause() {
        if (!resumed) return
        mapView?.onPause()
        resumed = false
    }

    fun destroy() {
        pause()
        mapView?.onDestroy()
        mapView = null
    }

    fun ensureProvinceBoundaries(
        provinces: Collection<String>,
        onBoundaryLoaded: () -> Unit,
    ) {
        provinces.forEach { province ->
            if (province in boundaryCache || province in pendingBoundaryRequests) return@forEach
            pendingBoundaryRequests += province
            runCatching {
                DistrictSearch(context).apply {
                    setQuery(
                        DistrictSearchQuery().apply {
                            keywords = province
                            keywordsLevel = DistrictSearchQuery.KEYWORDS_PROVINCE
                            isShowBoundary = true
                            subDistrict = 0
                        },
                    )
                    setOnDistrictSearchListener { result ->
                        pendingBoundaryRequests -= province
                        result.toBoundary(province)?.let { boundary ->
                            boundaryCache[province] = boundary
                            onBoundaryLoaded()
                        }
                    }
                    searchDistrictAsyn()
                }
            }.onFailure {
                pendingBoundaryRequests -= province
            }
        }
    }

    fun render(
        cities: List<JourneyCity>,
        selectedCity: JourneyCity,
        litProvinces: Set<String>,
        onSelectCity: (JourneyCity) -> Unit,
        onToggleProvince: (String) -> Unit,
    ) {
        val amap = obtain().map
        val showCityLabels = amap.cameraPosition.zoom >= 5.8f
        amap.clear()
        amap.setOnMarkerClickListener { marker ->
            when (val tag = marker.`object` as? String) {
                null -> Unit
                else -> when {
                    tag.startsWith("city:") -> {
                        val cityName = tag.removePrefix("city:")
                        cities.firstOrNull { it.name == cityName }?.let(onSelectCity)
                    }
                    tag.startsWith("province:") -> {
                        val province = tag.removePrefix("province:")
                        onToggleProvince(province)
                        cities.firstOrNull { it.province == province }?.let(onSelectCity)
                    }
                }
            }
            true
        }

        val renderProvinces = cities.map { it.province }.distinct()
        renderProvinces.forEach { province ->
            val boundary = boundaryCache[province] ?: return@forEach
            val isVisited = province in litProvinces
            val isSelected = province == selectedCity.province
            val fillColor = when {
                isSelected -> AndroidColor.argb(122, 255, 200, 87)
                isVisited -> AndroidColor.argb(110, 31, 122, 224)
                else -> AndroidColor.argb(34, 255, 255, 255)
            }
            val strokeColor = when {
                isSelected -> AndroidColor.rgb(240, 166, 32)
                isVisited -> AndroidColor.rgb(31, 122, 224)
                else -> AndroidColor.rgb(176, 194, 213)
            }
            boundary.rings.forEach ringLoop@{ ring ->
                if (ring.size < 3) return@ringLoop
                amap.addPolygon(
                    PolygonOptions()
                        .addAll(ring)
                        .fillColor(fillColor)
                        .strokeColor(strokeColor)
                        .strokeWidth(if (isSelected) 5f else 3f)
                        .zIndex(if (isSelected) 6f else if (isVisited) 5f else 2f),
                )
            }
            provinceCenters[province]?.let { center ->
                val marker = amap.addMarker(
                    MarkerOptions()
                        .position(center)
                        .icon(
                            BitmapDescriptorFactory.fromBitmap(
                                createProvinceLabelBitmap(context, province, isVisited, isSelected),
                            ),
                        )
                        .anchor(0.5f, 0.5f)
                        .zIndex(if (isSelected) 25f else 18f),
                )
                marker?.`object` = "province:$province"
            }
        }

        cities.forEach { city ->
            val selected = city == selectedCity
            val showLabel = selected || showCityLabels
            val marker = amap.addMarker(
                MarkerOptions()
                    .position(LatLng(city.latitude, city.longitude))
                    .icon(
                        BitmapDescriptorFactory.fromBitmap(
                            createJourneyCityMarkerBitmap(context, city, selected, showLabel),
                        ),
                    )
                    .anchor(0.5f, if (showLabel) 0.88f else 0.5f)
                    .zIndex(if (selected) 40f else if (city.visited) 30f else 20f),
            )
            marker?.`object` = "city:${city.name}"
        }

        if (lastSelectedCityName != selectedCity.name) {
            lastSelectedCityName = selectedCity.name
            amap.animateCamera(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(selectedCity.latitude, selectedCity.longitude),
                    6.6f,
                ),
            )
        }
    }

    private fun DistrictResult.toBoundary(province: String): ProvinceBoundary? {
        val rings = district
            ?.flatMap { item -> item.districtBoundary().orEmpty().asIterable() }
            ?.mapNotNull(::parseBoundaryRing)
            .orEmpty()
        return if (rings.isEmpty()) null else ProvinceBoundary(province, rings)
    }

    private fun parseBoundaryRing(boundary: String): List<LatLng>? {
        val points = boundary
            .split(';')
            .mapNotNull { raw ->
                val parts = raw.split(',')
                val longitude = parts.getOrNull(0)?.toDoubleOrNull()
                val latitude = parts.getOrNull(1)?.toDoubleOrNull()
                if (latitude == null || longitude == null) null else LatLng(latitude, longitude)
            }
        return points.takeIf { it.size >= 3 }
    }
}

@Composable
private fun rememberJourneyMapViewHolder(): JourneyMapViewHolder {
    val context = LocalContext.current
    val holder = remember(context) { JourneyMapViewHolder(context) }
    DisposableEffect(holder) {
        onDispose(holder::destroy)
    }
    return holder
}

@Composable
internal fun JourneyScreen(
    journalEntries: List<JournalEntry>,
    onOpenJournal: () -> Unit,
    onOpenJournalEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var query by remember { mutableStateOf("") }
    var selectedCity by remember { mutableStateOf(journeyCities.first { it.name == "成都市" }) }
    var litProvinces by remember {
        mutableStateOf(journeyCities.filter(JourneyCity::visited).map { it.province }.toSet())
    }
    var sheetExpanded by remember { mutableStateOf(false) }
    val suggestions = remember(query) {
        if (query.isBlank()) {
            emptyList()
        } else {
            journeyCities.filter { city ->
                city.name.contains(query, ignoreCase = true) ||
                    city.province.contains(query, ignoreCase = true) ||
                    city.aliases.any { it.contains(query, ignoreCase = true) }
            }.take(4)
        }
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF4F8FA)),
    ) {
        ChinaJourneyMap(
            selectedCity = selectedCity,
            litProvinces = litProvinces,
            onSelectCity = {
                selectedCity = it
                query = it.name
            },
            onToggleProvince = { province ->
                litProvinces = if (province in litProvinces) {
                    litProvinces - province
                } else {
                    litProvinces + province
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        Column(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(horizontal = 18.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            JourneyHeader()
            JourneySearch(
                query = query,
                suggestions = suggestions,
                onQueryChange = { query = it },
                onSelectCity = {
                    selectedCity = it
                    query = it.name
                },
            )
        }

        JourneyJournalSheet(
            city = selectedCity,
            entries = journalEntries.filter { it.matchesCity(selectedCity) },
            expanded = sheetExpanded,
            onExpandedChange = { sheetExpanded = it },
            onOpenEntry = onOpenJournalEntry,
            modifier = Modifier.align(Alignment.BottomCenter),
        )

        FloatingActionButton(
            onClick = onOpenJournal,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(start = 22.dp, bottom = 16.dp),
            containerColor = Color(0xFF092B4A),
            contentColor = Color.White,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SaturnIcon(modifier = Modifier.size(30.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "游记",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun JourneyHeader() {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            text = "旅程",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.ExtraBold,
            color = Color(0xFF081F3A),
        )
        Text(
            text = "点亮走过的城市，回看每一段旅行记录",
            style = MaterialTheme.typography.bodyMedium,
            color = Color(0xFF5E6C7C),
        )
    }
}

@Composable
private fun JourneySearch(
    query: String,
    suggestions: List<JourneyCity>,
    onQueryChange: (String) -> Unit,
    onSelectCity: (JourneyCity) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = {
                Icon(
                    imageVector = Icons.Outlined.Search,
                    contentDescription = null,
                )
            },
            placeholder = { Text("搜索城市") },
            singleLine = true,
            shape = RoundedCornerShape(28.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = Color.White,
                unfocusedContainerColor = Color.White,
                focusedBorderColor = Color(0xFF1F7AE0),
                unfocusedBorderColor = Color.Transparent,
            ),
        )

        if (suggestions.isNotEmpty()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = Color.White,
                tonalElevation = 2.dp,
                shadowElevation = 4.dp,
            ) {
                Column(modifier = Modifier.padding(vertical = 6.dp)) {
                    suggestions.forEach { city ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onSelectCity(city) }
                                .padding(horizontal = 16.dp, vertical = 11.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                imageVector = Icons.Outlined.LocationOn,
                                contentDescription = null,
                                tint = Color(0xFF1F7AE0),
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = city.name,
                                style = MaterialTheme.typography.bodyLarge,
                                fontWeight = FontWeight.SemiBold,
                                color = Color(0xFF13263E),
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = city.province,
                                style = MaterialTheme.typography.bodyMedium,
                                color = Color(0xFF778597),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ChinaJourneyMap(
    selectedCity: JourneyCity,
    litProvinces: Set<String>,
    onSelectCity: (JourneyCity) -> Unit,
    onToggleProvince: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val holder = rememberJourneyMapViewHolder()
    val lifecycleOwner = LocalLifecycleOwner.current
    val mapView = remember(holder) { holder.obtain() }
    var boundaryVersion by remember { mutableStateOf(0) }

    if (!isJourneyAmapRuntimeSupported(LocalContext.current)) {
        JourneyMapUnsupportedNotice(modifier = modifier)
        return
    }

    DisposableEffect(lifecycleOwner, mapView, holder) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> holder.resume()
                Lifecycle.Event.ON_PAUSE -> holder.pause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            holder.resume()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            holder.pause()
        }
    }

    LaunchedEffect(boundaryVersion, selectedCity, litProvinces) {
        holder.render(
            cities = journeyCities,
            selectedCity = selectedCity,
            litProvinces = litProvinces,
            onSelectCity = onSelectCity,
            onToggleProvince = onToggleProvince,
        )
    }

    LaunchedEffect(Unit) {
        holder.ensureProvinceBoundaries(
            provinces = journeyCities.map { it.province }.distinct(),
            onBoundaryLoaded = { boundaryVersion += 1 },
        )
    }

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(0.dp),
        color = Color(0xFFEAF5F8),
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            AndroidView(
                factory = { mapView },
                modifier = Modifier.fillMaxSize(),
            )
            Box(
                modifier = Modifier
                    .matchParentSize()
                    .background(Color.White.copy(alpha = 0.18f)),
            )
        }
    }
}

@Composable
private fun JourneyMapUnsupportedNotice(modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(0.dp),
        color = Color.White,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Brush.verticalGradient(listOf(Color(0xFFEAF5FF), Color(0xFFF8FBFF))))
                .padding(24.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(
                    imageVector = Icons.Outlined.LocationOn,
                    contentDescription = null,
                    tint = Color(0xFF1F7AE0),
                )
                Text(
                    text = "当前设备无法加载高德地图",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF071A3D),
                    textAlign = TextAlign.Center,
                )
                Text(
                    text = "当前运行环境是模拟器或不兼容的原生渲染环境。高德地图在部分 Android Emulator 上会因为 OpenGL Context 创建失败而崩溃，请使用 Android 真机调试真实地图。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color(0xFF5E6C7C),
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun JourneyJournalSheet(
    city: JourneyCity,
    entries: List<JournalEntry>,
    expanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onOpenEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val sheetFraction by animateFloatAsState(
        targetValue = if (expanded) 0.66f else 0.33f,
        label = "journeySheetFraction",
    )
    var dragDelta by remember { mutableStateOf(0f) }
    val dragModifier = Modifier.draggable(
        orientation = Orientation.Vertical,
        state = rememberDraggableState { delta ->
            dragDelta += delta
        },
        onDragStarted = {
            dragDelta = 0f
        },
        onDragStopped = {
            when {
                dragDelta < -28f -> onExpandedChange(true)
                dragDelta > 28f -> onExpandedChange(false)
            }
        },
    )

    Surface(
        modifier = modifier
            .fillMaxWidth()
            .fillMaxHeight(sheetFraction),
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
        color = Color.White.copy(alpha = 0.96f),
        shadowElevation = 12.dp,
    ) {
        Column(
            modifier = Modifier.padding(start = 18.dp, end = 18.dp, top = 10.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .fillMaxWidth()
                    .height(24.dp)
                    .then(dragModifier)
                    .clickable { onExpandedChange(!expanded) },
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    modifier = Modifier
                        .size(width = 42.dp, height = 5.dp)
                        .clip(RoundedCornerShape(99.dp))
                        .background(Color(0xFFD4DCE7)),
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .then(dragModifier),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text(
                        text = "${city.name}旅记",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = Color(0xFF081F3A),
                    )
                    Text(
                        text = "${entries.size} 篇笔记 · ${city.guideCount} 份攻略",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color(0xFF627083),
                    )
                }
            }

            if (entries.isEmpty()) {
                EmptyJourneyJournalCard(city = city)
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 72.dp),
                ) {
                    items(entries.take(3), key = { it.id }) { entry ->
                        JourneyJournalPreviewCard(
                            entry = entry,
                            onClick = { onOpenEntry(entry.id) },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyJourneyJournalCard(city: JourneyCity) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = Color(0xFFF3F7FB),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "还没有${city.name.removeSuffix("市")}的旅记",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF10243D),
            )
            Text(
                text = "从右侧游记入口进入“写旅记”，保存后会同步出现在这里。",
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF5E6C7C),
            )
        }
    }
}

@Composable
private fun JourneyJournalPreviewCard(
    entry: JournalEntry,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(22.dp),
        color = Color(0xFFF3F7FB),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Text(
                text = entry.date.format(DateTimeFormatter.ofPattern("M月d日")),
                style = MaterialTheme.typography.labelLarge,
                color = Color(0xFF1F7AE0),
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = entry.title,
                style = MaterialTheme.typography.titleMedium,
                color = Color(0xFF10243D),
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (entry.body.isNotBlank()) {
                Text(
                    text = entry.body,
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color(0xFF5E6C7C),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            JourneySheetPhotoStrip(photos = entry.photos)
        }
    }
}

@Composable
private fun JourneySheetPhotoStrip(photos: List<JournalPhoto>) {
    if (photos.isEmpty()) return
    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        photos.take(3).forEach { photo ->
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(62.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(photo.color),
                contentAlignment = Alignment.Center,
            ) {
                val bitmap = photo.bitmap
                if (bitmap != null) {
                    Image(
                        bitmap = bitmap.asImageBitmap(),
                        contentDescription = photo.label,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop,
                    )
                } else {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(
                                Brush.linearGradient(
                                    listOf(photo.color.copy(alpha = 0.86f), Color.White.copy(alpha = 0.34f)),
                                ),
                            ),
                    )
                    Text(
                        text = photo.label,
                        style = MaterialTheme.typography.labelMedium,
                        color = Color(0xFF10243D),
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

private fun JournalEntry.matchesCity(city: JourneyCity): Boolean {
    val shortName = city.name.removeSuffix("市")
    return location.contains(city.name, ignoreCase = true) ||
        location.contains(shortName, ignoreCase = true) ||
        city.aliases.any { alias -> location.contains(alias, ignoreCase = true) }
}

private fun isJourneyAmapRuntimeSupported(context: Context): Boolean {
    if (isAndroidEmulator()) return false
    val nativeLibraryDir = context.applicationInfo.nativeLibraryDir.orEmpty()
    if (nativeLibraryDir.contains("arm64") || nativeLibraryDir.contains("armeabi")) return true
    return Build.SUPPORTED_ABIS.any { abi -> abi == "arm64-v8a" || abi == "armeabi-v7a" }
}

private fun isAndroidEmulator(): Boolean {
    return Build.FINGERPRINT.startsWith("generic") ||
        Build.FINGERPRINT.contains("emulator", ignoreCase = true) ||
        Build.MODEL.contains("sdk", ignoreCase = true) ||
        Build.MODEL.contains("emulator", ignoreCase = true) ||
        Build.HARDWARE.contains("ranchu", ignoreCase = true) ||
        Build.HARDWARE.contains("goldfish", ignoreCase = true) ||
        Build.PRODUCT.contains("sdk", ignoreCase = true)
}

private fun createJourneyCityMarkerBitmap(
    context: Context,
    city: JourneyCity,
    selected: Boolean,
    showLabel: Boolean,
): Bitmap {
    val density = context.resources.displayMetrics.density
    fun dp(value: Float): Float = value * density

    val label = city.name.removeSuffix("市")
    val circleSize = dp(if (selected) 20f else 12f)
    val labelGap = dp(4f)
    val labelPaddingX = dp(8f)
    val labelPaddingY = dp(4f)
    val shadowPadding = dp(6f)

    val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(10, 31, 58)
        textSize = dp(if (selected) 13f else 11f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }
    val labelBounds = Rect()
    labelPaint.getTextBounds(label, 0, label.length, labelBounds)

    val labelWidth = if (showLabel) labelPaint.measureText(label) + labelPaddingX * 2f else 0f
    val bitmapWidth = maxOf(circleSize, labelWidth) + shadowPadding * 2f
    val labelHeight = if (showLabel) labelGap + labelBounds.height() + labelPaddingY * 2f else 0f
    val bitmapHeight = circleSize + labelHeight + shadowPadding * 2f
    val bitmap = Bitmap.createBitmap(bitmapWidth.toInt(), bitmapHeight.toInt(), Bitmap.Config.ARGB_8888)
    val canvas = AndroidCanvas(bitmap)

    val centerX = bitmapWidth / 2f
    val circleCenterY = shadowPadding + circleSize / 2f
    val fillColor = when {
        selected -> AndroidColor.rgb(255, 200, 87)
        city.visited -> AndroidColor.rgb(31, 122, 224)
        else -> AndroidColor.WHITE
    }

    val shadowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = fillColor
        setShadowLayer(dp(4f), 0f, dp(1.5f), AndroidColor.argb(80, 29, 61, 100))
    }
    canvas.drawCircle(centerX, circleCenterY, circleSize / 2f, shadowPaint)

    val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(if (selected) 3f else 2f)
        color = if (selected) AndroidColor.rgb(255, 255, 255) else AndroidColor.rgb(191, 211, 232)
    }
    canvas.drawCircle(centerX, circleCenterY, circleSize / 2f - dp(1f), ringPaint)

    if (showLabel) {
        val labelTop = shadowPadding + circleSize + labelGap
        val labelLeft = centerX - labelWidth / 2f
        val labelBackgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = AndroidColor.argb(232, 255, 255, 255)
        }
        canvas.drawRoundRect(
            RectF(labelLeft, labelTop, labelLeft + labelWidth, labelTop + labelBounds.height() + labelPaddingY * 2f),
            dp(8f),
            dp(8f),
            labelBackgroundPaint,
        )
        canvas.drawText(
            label,
            centerX - labelPaint.measureText(label) / 2f,
            labelTop + labelPaddingY + labelBounds.height(),
            labelPaint,
        )
    }

    return bitmap
}

private fun createProvinceLabelBitmap(
    context: Context,
    province: String,
    lit: Boolean,
    selected: Boolean,
): Bitmap {
    val density = context.resources.displayMetrics.density
    fun dp(value: Float): Float = value * density

    val label = province.removeSuffix("省").removeSuffix("市")
    val paddingX = dp(11f)
    val paddingY = dp(7f)
    val shadowPadding = dp(6f)
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = when {
            selected -> AndroidColor.rgb(95, 67, 0)
            lit -> AndroidColor.rgb(5, 67, 130)
            else -> AndroidColor.rgb(80, 94, 111)
        }
        textSize = dp(if (selected) 15f else 13f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }
    val textBounds = Rect()
    textPaint.getTextBounds(label, 0, label.length, textBounds)
    val width = textPaint.measureText(label) + paddingX * 2f + shadowPadding * 2f
    val height = textBounds.height() + paddingY * 2f + shadowPadding * 2f
    val bitmap = Bitmap.createBitmap(width.toInt(), height.toInt(), Bitmap.Config.ARGB_8888)
    val canvas = AndroidCanvas(bitmap)
    val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = when {
            selected -> AndroidColor.argb(238, 255, 223, 137)
            lit -> AndroidColor.argb(232, 220, 238, 255)
            else -> AndroidColor.argb(230, 255, 255, 255)
        }
        setShadowLayer(dp(4f), 0f, dp(1.5f), AndroidColor.argb(45, 32, 54, 84))
    }
    canvas.drawRoundRect(
        RectF(shadowPadding, shadowPadding, width - shadowPadding, height - shadowPadding),
        dp(12f),
        dp(12f),
        backgroundPaint,
    )
    canvas.drawText(
        label,
        shadowPadding + paddingX,
        shadowPadding + paddingY + textBounds.height(),
        textPaint,
    )
    return bitmap
}

@Composable
private fun CityRecordPanel(city: JourneyCity) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = Color.White,
        shadowElevation = 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(
                        text = city.name,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.ExtraBold,
                        color = Color(0xFF081F3A),
                    )
                    Text(
                        text = "${city.noteCount} 篇笔记 · ${city.guideCount} 份攻略",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color(0xFF627083),
                    )
                }
                AssistChip(
                    onClick = {},
                    label = { Text(if (city.visited) "已点亮" else "想去") },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Outlined.Star,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                    },
                )
            }

            city.records.forEach { record ->
                RecordRow(
                    icon = Icons.AutoMirrored.Outlined.MenuBook,
                    title = record.title,
                    label = record.type,
                    summary = record.summary,
                )
            }
        }
    }
}

@Composable
private fun RecordRow(
    icon: ImageVector,
    title: String,
    label: String,
    summary: String,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(Color(0xFFF3F7FB))
            .padding(14.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Box(
            modifier = Modifier
                .size(42.dp)
                .clip(CircleShape)
                .background(Color(0xFFE0ECFF)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = Color(0xFF1F7AE0),
            )
        }
        Spacer(modifier = Modifier.width(12.dp))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF10243D),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = label,
                    style = MaterialTheme.typography.labelMedium,
                    color = Color(0xFF1F7AE0),
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Text(
                text = summary,
                style = MaterialTheme.typography.bodyMedium,
                color = Color(0xFF5E6C7C),
            )
        }
    }
}

@Composable
private fun SaturnIcon(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        val center = Offset(size.width * 0.50f, size.height * 0.50f)
        drawOval(
            color = Color(0xFFFFD36A),
            topLeft = Offset(size.width * 0.08f, size.height * 0.35f),
            size = androidx.compose.ui.geometry.Size(size.width * 0.84f, size.height * 0.28f),
            style = Stroke(width = size.width * 0.10f),
        )
        drawCircle(
            brush = Brush.radialGradient(
                listOf(Color(0xFFFFE5A6), Color(0xFFFFB84D)),
                center = center,
                radius = size.width * 0.34f,
            ),
            radius = size.width * 0.28f,
            center = center,
        )
    }
}

@Composable
internal fun JourneyJournalScreen(
    entries: List<JournalEntry>,
    onBack: () -> Unit,
    onWriteJourney: () -> Unit,
    onAddEntry: (JournalEntry) -> Unit,
    onOpenEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    JourneyJournalRoute(
        entries = entries,
        onBack = onBack,
        onWriteJourney = onWriteJourney,
        onAddEntry = onAddEntry,
        onOpenEntry = onOpenEntry,
        modifier = modifier,
    )
}
