package com.heoclub.aitravel.ui.journey

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
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
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.maps.model.PolygonOptions
import com.amap.api.services.district.DistrictItem
import com.amap.api.services.district.DistrictResult
import com.amap.api.services.district.DistrictSearch
import com.amap.api.services.district.DistrictSearchQuery
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

private const val LEVEL_PROVINCE = "province"
private const val LEVEL_CITY = "city"
private const val REGION_STORE = "journey_lit_regions"
private const val REGION_STORE_KEY = "regions"
private val municipalityNames = setOf("北京市", "天津市", "上海市", "重庆市")

private val MapNight = Color(0xFF041A20)
private val MapPanel = Color(0xF20A2329)
private val MapPanelSoft = Color(0xE619353B)
private val MapText = Color(0xFFF1FAF8)
private val MapTextMuted = Color(0xFFA6BDBA)
private val MapAccent = Color(0xFF24D5CF)
private val MapAccentDeep = Color(0xFF0B8D91)

private data class ProvinceMapLabel(
    val name: String,
    val center: LatLng,
)

private val provinceMapLabels = listOf(
    ProvinceMapLabel("北京市", LatLng(39.90, 116.40)),
    ProvinceMapLabel("天津市", LatLng(39.12, 117.20)),
    ProvinceMapLabel("河北省", LatLng(38.04, 114.51)),
    ProvinceMapLabel("山西省", LatLng(37.87, 112.55)),
    ProvinceMapLabel("内蒙古自治区", LatLng(43.95, 111.67)),
    ProvinceMapLabel("辽宁省", LatLng(41.80, 123.43)),
    ProvinceMapLabel("吉林省", LatLng(43.90, 125.32)),
    ProvinceMapLabel("黑龙江省", LatLng(47.35, 127.60)),
    ProvinceMapLabel("上海市", LatLng(31.23, 121.47)),
    ProvinceMapLabel("江苏省", LatLng(32.06, 118.80)),
    ProvinceMapLabel("浙江省", LatLng(30.27, 120.15)),
    ProvinceMapLabel("安徽省", LatLng(31.86, 117.28)),
    ProvinceMapLabel("福建省", LatLng(26.08, 119.30)),
    ProvinceMapLabel("江西省", LatLng(28.68, 115.86)),
    ProvinceMapLabel("山东省", LatLng(36.67, 117.02)),
    ProvinceMapLabel("河南省", LatLng(34.75, 113.63)),
    ProvinceMapLabel("湖北省", LatLng(30.59, 114.30)),
    ProvinceMapLabel("湖南省", LatLng(28.23, 112.94)),
    ProvinceMapLabel("广东省", LatLng(23.13, 113.27)),
    ProvinceMapLabel("广西壮族自治区", LatLng(23.82, 108.32)),
    ProvinceMapLabel("海南省", LatLng(20.02, 110.35)),
    ProvinceMapLabel("重庆市", LatLng(29.56, 106.55)),
    ProvinceMapLabel("四川省", LatLng(30.65, 104.07)),
    ProvinceMapLabel("贵州省", LatLng(26.65, 106.63)),
    ProvinceMapLabel("云南省", LatLng(25.04, 102.71)),
    ProvinceMapLabel("西藏自治区", LatLng(30.10, 88.80)),
    ProvinceMapLabel("陕西省", LatLng(34.27, 108.95)),
    ProvinceMapLabel("甘肃省", LatLng(36.06, 103.83)),
    ProvinceMapLabel("青海省", LatLng(36.62, 101.78)),
    ProvinceMapLabel("宁夏回族自治区", LatLng(38.47, 106.26)),
    ProvinceMapLabel("新疆维吾尔自治区", LatLng(42.80, 85.60)),
    ProvinceMapLabel("香港特别行政区", LatLng(22.32, 114.17)),
    ProvinceMapLabel("澳门特别行政区", LatLng(22.20, 113.54)),
    ProvinceMapLabel("台湾省", LatLng(23.75, 120.96)),
)

private data class LitRegion(
    val id: String,
    val name: String,
    val level: String,
    val center: LatLng,
    val rings: List<List<LatLng>>,
) {
    val levelLabel: String
        get() = if (level == LEVEL_PROVINCE) "省级行政区" else "地级市"
}

private data class StoredLitRegion(
    val id: String,
    val name: String,
    val level: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
) {
    fun toPlaceholder(): LitRegion? {
        val lat = latitude ?: return null
        val lon = longitude ?: return null
        return LitRegion(
            id = id,
            name = name,
            level = level,
            center = LatLng(lat, lon),
            rings = emptyList(),
        )
    }

    companion object {
        fun from(region: LitRegion): StoredLitRegion = StoredLitRegion(
            id = region.id,
            name = region.name,
            level = region.level,
            latitude = region.center.latitude,
            longitude = region.center.longitude,
        )
    }
}

private class LitJourneyMapController(
    private val context: Context,
) {
    private var mapView: MapView? = null
    private var resumed = false
    private var lastFocusedRegionId: String? = null
    private val activeSearches = mutableSetOf<DistrictSearch>()

    fun obtain(): MapView {
        return mapView ?: MapView(context).apply {
            onCreate(Bundle())
            map.mapType = AMap.MAP_TYPE_NIGHT
            map.showBuildings(false)
            map.showIndoorMap(false)
            map.showMapText(false)
            map.setTrafficEnabled(false)
            map.setRoadArrowEnable(false)
            map.setConstructingRoadEnable(false)
            map.setMinZoomLevel(3.2f)
            map.setMaxZoomLevel(8.0f)
            map.uiSettings.isZoomControlsEnabled = false
            map.uiSettings.isMyLocationButtonEnabled = false
            map.uiSettings.isCompassEnabled = false
            map.uiSettings.isScaleControlsEnabled = false
            map.moveCamera(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(35.8617, 104.1954),
                    3.7f,
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
        activeSearches.clear()
        mapView?.onDestroy()
        mapView = null
    }

    fun search(
        keyword: String,
        onResult: (List<LitRegion>) -> Unit,
    ) {
        request(keyword, LEVEL_CITY) { regions ->
            onResult(regions.sortedBy { it.name.length })
        }
    }

    fun restore(
        stored: StoredLitRegion,
        onResult: (LitRegion?) -> Unit,
    ) {
        request(stored.name, stored.level) { candidates ->
            onResult(
                candidates.firstOrNull { it.id == stored.id }
                    ?: candidates.firstOrNull { it.name == stored.name },
            )
        }
    }

    private fun request(
        keyword: String,
        level: String,
        onResult: (List<LitRegion>) -> Unit,
    ) {
        runCatching {
            val search = DistrictSearch(context)
            activeSearches += search
            search.setQuery(
                DistrictSearchQuery().apply {
                    keywords = keyword.trim()
                    keywordsLevel = level
                    isShowBoundary = true
                    subDistrict = 0
                    pageSize = 20
                },
            )
            search.setOnDistrictSearchListener { result ->
                activeSearches -= search
                onResult(result.toLitRegions(level))
            }
            search.searchDistrictAsyn()
        }.onFailure {
            onResult(emptyList())
        }
    }

    fun render(
        litRegions: Collection<LitRegion>,
        selectedRegion: LitRegion?,
        onSelectRegion: (LitRegion) -> Unit,
    ) {
        val amap = obtain().map
        amap.clear()
        amap.setOnMarkerClickListener { marker ->
            val regionId = marker.`object` as? String
            litRegions
                .firstOrNull { it.id == regionId }
                ?.let(onSelectRegion)
            true
        }

        provinceMapLabels.forEach { province ->
            amap.addMarker(
                MarkerOptions()
                    .position(province.center)
                    .icon(
                        BitmapDescriptorFactory.fromBitmap(
                            createProvinceMapLabel(context, province.name),
                        ),
                    )
                    .anchor(0.5f, 0.5f)
                    .zIndex(4f),
            )
        }

        val regionsToDraw = litRegions
            .filter { it.level == LEVEL_CITY }
            .associateBy(LitRegion::id)
            .values
        regionsToDraw.forEach { region ->
            val isSelected = selectedRegion?.id == region.id
            region.rings.forEach { ring ->
                if (ring.size >= 3) {
                    amap.addPolygon(
                        PolygonOptions()
                            .addAll(ring)
                            .fillColor(AndroidColor.argb(248, 0, 218, 230))
                            .strokeColor(AndroidColor.rgb(132, 255, 249))
                            .strokeWidth(if (isSelected) 6f else 4f)
                            .zIndex(if (isSelected) 9f else 7f),
                    )
                }
            }
            val marker = amap.addMarker(
                MarkerOptions()
                    .position(region.center)
                    .icon(
                        BitmapDescriptorFactory.fromBitmap(
                            createLitCityLabel(context, region.name, isSelected),
                        ),
                    )
                    .anchor(0.5f, 0.5f)
                    .zIndex(20f),
            )
            marker?.`object` = region.id
        }

        if (selectedRegion != null && lastFocusedRegionId != selectedRegion.id) {
            lastFocusedRegionId = selectedRegion.id
            val zoom = if (selectedRegion.level == LEVEL_CITY) 7.4f else 5.2f
            obtain().post {
                amap.animateCamera(CameraUpdateFactory.newLatLngZoom(selectedRegion.center, zoom))
            }
        }
    }
}

private suspend fun LitJourneyMapController.restoreAwait(stored: StoredLitRegion): LitRegion? {
    return suspendCancellableCoroutine { continuation ->
        restore(stored) { region ->
            if (continuation.isActive) continuation.resume(region)
        }
    }
}

@Composable
internal fun JourneyScreen(
    journalEntries: List<JournalEntry>,
    onOpenJournal: () -> Unit,
    onOpenJournalEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val controller = remember(context) { LitJourneyMapController(context) }
    var query by remember { mutableStateOf("") }
    var searchResults by remember { mutableStateOf(emptyList<LitRegion>()) }
    var searching by remember { mutableStateOf(false) }
    var searchMessage by remember { mutableStateOf<String?>(null) }
    var searchRequestToken by remember { mutableStateOf(0) }
    var selectedRegion by remember { mutableStateOf<LitRegion?>(null) }
    val initialStoredRegions = remember(context) {
        readStoredRegions(context).associateBy(StoredLitRegion::id)
    }
    var storedRegions by remember(context) { mutableStateOf(initialStoredRegions) }
    var litRegions by remember(context) {
        mutableStateOf(
            initialStoredRegions.values
                .mapNotNull(StoredLitRegion::toPlaceholder)
                .associateBy(LitRegion::id),
        )
    }

    fun submitSearch() {
        val keyword = query.trim()
        if (keyword.isBlank()) {
            searchResults = emptyList()
            searchMessage = "请输入地级市名称"
            return
        }
        searchRequestToken += 1
        val requestToken = searchRequestToken
        searching = true
        searchMessage = null
        controller.search(keyword) { results ->
            if (requestToken != searchRequestToken) return@search
            searching = false
            searchResults = results
            searchMessage = if (results.isEmpty()) "没有找到对应的地级市" else null
        }
    }

    fun toggle(region: LitRegion) {
        selectedRegion = region
        searchResults = emptyList()
        query = region.name
        val nextStored = if (region.id in storedRegions) {
            storedRegions - region.id
        } else {
            storedRegions + (region.id to StoredLitRegion.from(region))
        }
        if (!writeStoredRegions(context, nextStored.values)) {
            searchMessage = "点亮记录保存失败，请重试"
            return
        }
        storedRegions = nextStored
        litRegions = if (region.id in nextStored) {
            litRegions + (region.id to region)
        } else {
            litRegions - region.id
        }
    }

    LaunchedEffect(controller) {
        initialStoredRegions.values.forEach { stored ->
            var restored: LitRegion? = null
            repeat(2) { attempt ->
                if (restored == null) {
                    restored = withTimeoutOrNull(6_000) { controller.restoreAwait(stored) }
                    if (restored == null && attempt == 0) delay(300)
                }
            }
            restored?.let { region ->
                if (stored.id in storedRegions) {
                    litRegions = litRegions + (region.id to region)
                    val upgradedStored = storedRegions + (region.id to StoredLitRegion.from(region))
                    if (writeStoredRegions(context, upgradedStored.values)) {
                        storedRegions = upgradedStored
                    }
                }
            }
            delay(120)
        }
    }

    DisposableEffect(controller) {
        onDispose(controller::destroy)
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MapNight),
    ) {
        LitSatelliteMap(
            controller = controller,
            litRegions = litRegions.values,
            selectedRegion = selectedRegion,
            onSelectRegion = {
                selectedRegion = it
                query = it.name
                searchResults = emptyList()
            },
            modifier = Modifier.fillMaxSize(),
        )

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        0f to Color(0xB3001015),
                        0.22f to Color(0x26001015),
                        0.48f to Color.Transparent,
                        0.74f to Color.Transparent,
                        1f to Color(0xC7001015),
                    ),
                ),
        )

        Column(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            LitJourneyHeader(cityCount = storedRegions.size)
            LitRegionSearch(
                query = query,
                searching = searching,
                message = searchMessage,
                results = searchResults,
                litRegionIds = storedRegions.keys,
                onQueryChange = {
                    query = it
                    searchMessage = null
                    if (it.isBlank()) searchResults = emptyList()
                },
                onSearch = {
                    focusManager.clearFocus()
                    submitSearch()
                },
                onPreview = {
                    selectedRegion = it
                    query = it.name
                    searchResults = emptyList()
                },
                onToggle = ::toggle,
            )
        }

        selectedRegion?.let { region ->
            LitRegionPanel(
                region = region,
                isLit = region.id in storedRegions,
                journalEntries = journalEntries,
                onToggle = { toggle(region) },
                onOpenJournal = onOpenJournal,
                onOpenEntry = onOpenJournalEntry,
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }

        if (selectedRegion == null) {
            JourneyJournalButton(
                onClick = onOpenJournal,
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .padding(start = 18.dp, bottom = 16.dp),
            )
        }
    }
}

@Composable
private fun LitJourneyHeader(cityCount: Int) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            text = "旅程地图",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Black,
            color = MapText,
        )
        Text(
            text = "点亮你走过的城市，让足迹在地图上留下形状",
            style = MaterialTheme.typography.bodyMedium,
            color = MapTextMuted,
        )
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = MapPanelSoft,
        ) {
            Text(
                text = "已点亮 $cityCount 个地级市",
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                style = MaterialTheme.typography.labelLarge,
                color = MapAccent,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun LitRegionSearch(
    query: String,
    searching: Boolean,
    message: String?,
    results: List<LitRegion>,
    litRegionIds: Set<String>,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
    onPreview: (LitRegion) -> Unit,
    onToggle: (LitRegion) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = {
                Icon(Icons.Outlined.Search, contentDescription = null, tint = MapTextMuted)
            },
            trailingIcon = {
                IconButton(onClick = onSearch) {
                    Icon(Icons.Outlined.LocationOn, contentDescription = "搜索行政区", tint = MapAccent)
                }
            },
            placeholder = { Text("搜索地级市", color = MapTextMuted) },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { onSearch() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = MapText,
                unfocusedTextColor = MapText,
                cursorColor = MapAccent,
                focusedContainerColor = MapPanel,
                unfocusedContainerColor = MapPanel,
                focusedBorderColor = MapAccent,
                unfocusedBorderColor = Color(0x667B9B98),
            ),
        )

        if (searching) {
            LinearProgressIndicator(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(99.dp)),
                color = MapAccent,
                trackColor = MapPanelSoft,
            )
        }

        if (message != null) {
            Surface(shape = RoundedCornerShape(14.dp), color = MapPanel) {
                Text(
                    text = message,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    color = MapTextMuted,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }

        if (results.isNotEmpty()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = MapPanel,
                shadowElevation = 10.dp,
            ) {
                Column(modifier = Modifier.padding(vertical = 5.dp)) {
                    results.take(6).forEach { region ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onPreview(region) }
                                .padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(MapAccent.copy(alpha = 0.14f)),
                                contentAlignment = Alignment.Center,
                            ) {
                                Icon(
                                    Icons.Outlined.LocationOn,
                                    contentDescription = null,
                                    tint = MapAccent,
                                    modifier = Modifier.size(20.dp),
                                )
                            }
                            Spacer(Modifier.width(10.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = region.name,
                                    color = MapText,
                                    fontWeight = FontWeight.Bold,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    text = region.levelLabel,
                                    color = MapTextMuted,
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            }
                            TextButton(onClick = { onToggle(region) }) {
                                Text(
                                    text = if (region.id in litRegionIds) "取消" else "点亮",
                                    color = if (region.id in litRegionIds) MapTextMuted else MapAccent,
                                    fontWeight = FontWeight.Bold,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LitRegionPanel(
    region: LitRegion,
    isLit: Boolean,
    journalEntries: List<JournalEntry>,
    onToggle: () -> Unit,
    onOpenJournal: () -> Unit,
    onOpenEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val shortName = region.name
        .removeSuffix("市")
        .removeSuffix("省")
        .removeSuffix("自治区")
    val matchingEntries = journalEntries.filter {
        it.location.contains(region.name, ignoreCase = true) ||
            it.location.contains(shortName, ignoreCase = true)
    }
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(topStart = 26.dp, topEnd = 26.dp),
        color = Color.White.copy(alpha = 0.97f),
        shadowElevation = 14.dp,
    ) {
        Column(
            modifier = Modifier.padding(start = 18.dp, end = 18.dp, top = 10.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier
                    .align(Alignment.CenterHorizontally)
                    .size(width = 42.dp, height = 4.dp)
                    .clip(RoundedCornerShape(99.dp))
                    .background(Color(0xFFD4DCE7)),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = region.name,
                        color = Color(0xFF081F3A),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        text = "${region.levelLabel} · ${matchingEntries.size} 篇旅行记录",
                        color = Color(0xFF627083),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                Button(
                    onClick = onToggle,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (isLit) Color(0xFFE5EEF1) else Color(0xFFD8F5F0),
                        contentColor = if (isLit) Color(0xFF244449) else Color(0xFF006E70),
                    ),
                    shape = RoundedCornerShape(14.dp),
                ) {
                    Icon(
                        Icons.Outlined.Star,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(if (isLit) "取消点亮" else "点亮")
                }
            }

            matchingEntries.firstOrNull()?.let { entry ->
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenEntry(entry.id) },
                    shape = RoundedCornerShape(16.dp),
                    color = Color(0xFFF3F7FB),
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Text(
                            text = entry.title,
                            color = Color(0xFF10243D),
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            text = entry.body,
                            color = Color(0xFF5E6C7C),
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            JourneyJournalButton(onClick = onOpenJournal)
        }
    }
}

@Composable
private fun JourneyJournalButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = Color(0xFFE6F0FF),
        shadowElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            JourneySaturnIcon(modifier = Modifier.size(26.dp))
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = "游记",
                color = Color(0xFF0A2C52),
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun JourneySaturnIcon(modifier: Modifier = Modifier) {
    androidx.compose.foundation.Canvas(modifier = modifier) {
        val center = androidx.compose.ui.geometry.Offset(size.width * 0.50f, size.height * 0.50f)
        drawOval(
            color = Color(0xFFFFD36A),
            topLeft = androidx.compose.ui.geometry.Offset(size.width * 0.08f, size.height * 0.35f),
            size = androidx.compose.ui.geometry.Size(size.width * 0.84f, size.height * 0.28f),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = size.width * 0.10f),
        )
        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color(0xFFFFE5A6), Color(0xFFFFB84D)),
                center = center,
                radius = size.width * 0.34f,
            ),
            radius = size.width * 0.28f,
            center = center,
        )
    }
}

@Composable
private fun LitSatelliteMap(
    controller: LitJourneyMapController,
    litRegions: Collection<LitRegion>,
    selectedRegion: LitRegion?,
    onSelectRegion: (LitRegion) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    if (!isLitJourneyMapSupported(context)) {
        Box(modifier = modifier.background(MapNight), contentAlignment = Alignment.Center) {
            Text("请使用 Android 真机查看卫星地图", color = MapTextMuted)
        }
        return
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    val mapView = remember(controller) { controller.obtain() }
    DisposableEffect(lifecycleOwner, mapView, controller) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> controller.resume()
                Lifecycle.Event.ON_PAUSE -> controller.pause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            controller.resume()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            controller.pause()
        }
    }
    LaunchedEffect(litRegions, selectedRegion) {
        controller.render(litRegions, selectedRegion, onSelectRegion)
    }
    AndroidView(factory = { mapView }, modifier = modifier)
}

private fun DistrictResult?.toLitRegions(requestedLevel: String): List<LitRegion> {
    return this?.district.orEmpty().mapNotNull { item -> item.toLitRegion(requestedLevel) }
}

private fun DistrictItem.toLitRegion(requestedLevel: String): LitRegion? {
    val itemName = name?.takeIf(String::isNotBlank) ?: return null
    val itemCenter = center ?: return null
    val rings = districtBoundary()
        .orEmpty()
        .asIterable()
        .flatMap { boundary -> boundary.split('|') }
        .mapNotNull(::parseLitBoundaryRing)
    if (rings.isEmpty()) return null
    val normalizedLevel = when {
        itemName in municipalityNames -> LEVEL_CITY
        requestedLevel == LEVEL_CITY -> LEVEL_CITY
        level == LEVEL_PROVINCE -> LEVEL_PROVINCE
        else -> requestedLevel
    }
    if (normalizedLevel != LEVEL_PROVINCE && normalizedLevel != LEVEL_CITY) return null
    return LitRegion(
        id = adcode?.takeIf(String::isNotBlank) ?: "$normalizedLevel:$itemName",
        name = itemName,
        level = normalizedLevel,
        center = LatLng(itemCenter.latitude, itemCenter.longitude),
        rings = rings,
    )
}

private fun parseLitBoundaryRing(boundary: String): List<LatLng>? {
    val points = boundary.split(';').mapNotNull { raw ->
        val pair = raw.split(',')
        val longitude = pair.getOrNull(0)?.toDoubleOrNull()
        val latitude = pair.getOrNull(1)?.toDoubleOrNull()
        if (longitude == null || latitude == null) null else LatLng(latitude, longitude)
    }
    return points.takeIf { it.size >= 3 }
}

private fun createLitCityLabel(
    context: Context,
    cityName: String,
    selected: Boolean,
): Bitmap {
    val density = context.resources.displayMetrics.density
    fun dp(value: Float) = value * density
    val label = cityName.removeSuffix("市")
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
        textSize = dp(if (selected) 12f else 10.5f)
        typeface = Typeface.create("sans-serif-black", Typeface.NORMAL)
    }
    val bounds = Rect()
    textPaint.getTextBounds(label, 0, label.length, bounds)
    val padding = dp(5f)
    val width = textPaint.measureText(label) + padding * 2
    val height = bounds.height() + padding * 2
    val bitmap = Bitmap.createBitmap(width.toInt(), height.toInt(), Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val baseline = padding - bounds.top
    val outlinePaint = Paint(textPaint).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(if (selected) 2.2f else 1.8f)
        color = AndroidColor.argb(225, 0, 25, 32)
        strokeJoin = Paint.Join.ROUND
    }
    canvas.drawText(label, padding, baseline, outlinePaint)
    canvas.drawText(label, padding, baseline, textPaint)
    return bitmap
}

private fun createProvinceMapLabel(context: Context, provinceName: String): Bitmap {
    val density = context.resources.displayMetrics.density
    fun dp(value: Float) = value * density
    val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.argb(150, 153, 174, 177)
        textSize = dp(9.5f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.NORMAL)
    }
    val bounds = Rect()
    textPaint.getTextBounds(provinceName, 0, provinceName.length, bounds)
    val padding = dp(4f)
    val width = textPaint.measureText(provinceName) + padding * 2
    val height = bounds.height() + padding * 2
    val bitmap = Bitmap.createBitmap(width.toInt(), height.toInt(), Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val baseline = padding - bounds.top
    val outlinePaint = Paint(textPaint).apply {
        style = Paint.Style.STROKE
        strokeWidth = dp(1.4f)
        color = AndroidColor.argb(175, 0, 23, 30)
        strokeJoin = Paint.Join.ROUND
    }
    canvas.drawText(provinceName, padding, baseline, outlinePaint)
    canvas.drawText(provinceName, padding, baseline, textPaint)
    return bitmap
}

private fun writeStoredRegions(context: Context, regions: Collection<StoredLitRegion>): Boolean {
    val encoded = regions
        .filter { it.level == LEVEL_CITY }
        .map { region ->
            listOf(
                region.level,
                region.id,
                region.name,
                region.latitude?.toString().orEmpty(),
                region.longitude?.toString().orEmpty(),
            ).joinToString("|")
        }
        .toSet()
    return context.getSharedPreferences(REGION_STORE, Context.MODE_PRIVATE)
        .edit()
        .putStringSet(REGION_STORE_KEY, encoded)
        .commit()
}

private fun readStoredRegions(context: Context): List<StoredLitRegion> {
    return context.getSharedPreferences(REGION_STORE, Context.MODE_PRIVATE)
        .getStringSet(REGION_STORE_KEY, emptySet())
        .orEmpty()
        .mapNotNull { encoded ->
            val parts = encoded.split('|', limit = 5)
            if (parts.size < 3) null else StoredLitRegion(
                level = if (parts[2] in municipalityNames) LEVEL_CITY else parts[0],
                id = parts[1],
                name = parts[2],
                latitude = parts.getOrNull(3)?.toDoubleOrNull(),
                longitude = parts.getOrNull(4)?.toDoubleOrNull(),
            )
        }
        .filter { it.level == LEVEL_CITY }
}

private fun isLitJourneyMapSupported(context: Context): Boolean {
    if (isLitJourneyEmulator()) return false
    val nativeLibraryDir = context.applicationInfo.nativeLibraryDir.orEmpty()
    if (nativeLibraryDir.contains("arm64") || nativeLibraryDir.contains("armeabi")) return true
    return Build.SUPPORTED_ABIS.any { it == "arm64-v8a" || it == "armeabi-v7a" }
}

private fun isLitJourneyEmulator(): Boolean {
    return Build.FINGERPRINT.startsWith("generic") ||
        Build.FINGERPRINT.contains("emulator", ignoreCase = true) ||
        Build.MODEL.contains("sdk", ignoreCase = true) ||
        Build.MODEL.contains("emulator", ignoreCase = true) ||
        Build.HARDWARE.contains("ranchu", ignoreCase = true) ||
        Build.HARDWARE.contains("goldfish", ignoreCase = true)
}
