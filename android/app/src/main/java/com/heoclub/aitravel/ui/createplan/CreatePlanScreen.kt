package com.heoclub.aitravel.ui.createplan

import android.widget.Toast
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.DirectionsCar
import androidx.compose.material.icons.outlined.FlightLand
import androidx.compose.material.icons.outlined.FlightTakeoff
import androidx.compose.material.icons.outlined.Hotel
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DateRangePicker
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberDateRangePickerState
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.model.AiHotelStayInput
import com.heoclub.aitravel.data.model.AiMapPointInput
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.PlaceSuggestion
import java.time.LocalDate
import java.time.Instant
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.time.format.DateTimeFormatter

private data class HotelStayDraft(
    val name: String = "",
    val checkInDay: Int = 1,
    val checkOutDay: Int = 2,
    val mapPoint: AiMapPointInput? = null,
)

private sealed interface MapPickerTarget {
    data object Arrival : MapPickerTarget
    data object Departure : MapPickerTarget
    data object Hotel : MapPickerTarget
    data class HotelStay(val index: Int) : MapPickerTarget
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreatePlanScreen(
    viewModel: CreatePlanViewModel,
    onBack: () -> Unit,
    onDone: () -> Unit,
    onStartAiPlanning: (AiPlanDraftInput) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var destination by remember { mutableStateOf("") }
    var selectedCityAdCode by remember { mutableStateOf<String?>(null) }
    var selectedCityLatitude by remember { mutableStateOf<Double?>(null) }
    var selectedCityLongitude by remember { mutableStateOf<Double?>(null) }
    var dayCount by remember { mutableStateOf(3) }
    var startDate by remember { mutableStateOf(LocalDate.now()) }
    var endDate by remember { mutableStateOf(startDate.plusDays((dayCount - 1).toLong())) }
    var dateRange by remember { mutableStateOf(formatDateRange(startDate, endDate)) }
    var freeText by remember { mutableStateOf("") }
    var arrivalStation by remember { mutableStateOf("") }
    var arrivalPoint by remember { mutableStateOf<AiMapPointInput?>(null) }
    var arrivalDay by remember { mutableStateOf(1) }
    var arrivalTime by remember { mutableStateOf("") }
    var departureStation by remember { mutableStateOf("") }
    var departurePoint by remember { mutableStateOf<AiMapPointInput?>(null) }
    var departureDay by remember { mutableStateOf(dayCount) }
    var departureTime by remember { mutableStateOf("") }
    var hotelName by remember { mutableStateOf("") }
    var hotelPoint by remember { mutableStateOf<AiMapPointInput?>(null) }
    val hotelStays = remember { mutableStateListOf<HotelStayDraft>() }
    var pace by remember { mutableStateOf("BALANCED") }
    var transportPreference by remember { mutableStateOf("MIXED") }
    var dailyStart by remember { mutableStateOf("09:00") }
    var dailyEnd by remember { mutableStateOf("20:00") }
    var showDatePicker by remember { mutableStateOf(false) }
    var showArrivalTimePicker by remember { mutableStateOf(false) }
    var showDepartureTimePicker by remember { mutableStateOf(false) }
    var mapPickerTarget by remember { mutableStateOf<MapPickerTarget?>(null) }
    var resolvingMapCenter by remember { mutableStateOf(false) }
    var optimizationMode by remember { mutableStateOf("REQUIRED") }
    var destinationError by remember { mutableStateOf(false) }
    val citySuggestions by viewModel.citySuggestions.collectAsState()
    val arrivalSuggestions by viewModel.arrivalSuggestions.collectAsState()
    val departureSuggestions by viewModel.departureSuggestions.collectAsState()
    val hotelSuggestions by viewModel.hotelSuggestions.collectAsState()
    val hotelSuggestionTarget by viewModel.hotelSuggestionTarget.collectAsState()
    val selectedPreferences = remember { mutableStateListOf<String>() }
    val preferences = listOf(
        "经典必玩",
        "美食打卡",
        "小众探索",
        "拍照出片",
        "citywalk",
        "自然风光",
        "文艺展览",
        "历史古建",
    )
    val openMapPicker: (MapPickerTarget) -> Unit = { target ->
        when {
            selectedCityLatitude != null && selectedCityLongitude != null -> mapPickerTarget = target
            destination.isBlank() -> {
                destinationError = true
                Toast.makeText(context, "请先输入目的城市", Toast.LENGTH_SHORT).show()
            }
            resolvingMapCenter -> Toast.makeText(context, "正在定位目的城市…", Toast.LENGTH_SHORT).show()
            else -> {
                resolvingMapCenter = true
                viewModel.resolveDestinationCity(destination) { city ->
                    resolvingMapCenter = false
                    if (city == null) {
                        Toast.makeText(context, "暂时无法定位该城市，请从城市联想中选择", Toast.LENGTH_SHORT).show()
                    } else {
                        destination = city.name
                        selectedCityAdCode = city.adCode
                        selectedCityLatitude = city.latitude
                        selectedCityLongitude = city.longitude
                        destinationError = false
                        mapPickerTarget = target
                    }
                }
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(
                color = Color.White,
                shape = CircleShape,
                shadowElevation = 2.dp,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
                }
            }
            Text(
                text = "创建旅行计划",
                modifier = Modifier
                    .weight(1f)
                    .padding(end = 48.dp),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }

        HeroCard()

        StepTitle(number = "1", title = "你想去哪里？")
        OutlinedTextField(
            value = destination,
            onValueChange = {
                destination = it
                selectedCityAdCode = null
                selectedCityLatitude = null
                selectedCityLongitude = null
                arrivalStation = ""
                arrivalPoint = null
                departureStation = ""
                departurePoint = null
                hotelName = ""
                hotelPoint = null
                hotelStays.indices.forEach { index ->
                    hotelStays[index] = hotelStays[index].copy(name = "", mapPoint = null)
                }
                viewModel.clearStationSuggestions(arrival = true)
                viewModel.clearStationSuggestions(arrival = false)
                viewModel.clearHotelSuggestions()
                destinationError = false
                viewModel.searchCities(it)
            },
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = {
                Icon(Icons.Outlined.LocationOn, contentDescription = null)
            },
            label = { Text("目的地") },
            placeholder = { Text("例如 成都") },
            isError = destinationError,
            supportingText = if (destinationError) {
                { Text("请输入并选择具体城市；选择省份后会列出下辖城市") }
            } else {
                null
            },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        if (citySuggestions.isNotEmpty()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                color = Color.White,
                shape = RoundedCornerShape(18.dp),
                shadowElevation = 3.dp,
            ) {
                Column {
                    Text(
                        text = destinationSuggestionTitle(destination, citySuggestions),
                        modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                    )
                    citySuggestions.forEach { city ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    destination = city.name
                                    selectedCityAdCode = city.adCode
                                    selectedCityLatitude = city.latitude
                                    selectedCityLongitude = city.longitude
                                    destinationError = false
                                    viewModel.clearCitySuggestions()
                                }
                                .padding(horizontal = 16.dp, vertical = 13.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(Icons.Outlined.LocationOn, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Column(modifier = Modifier.padding(start = 10.dp)) {
                                Text(city.name, fontWeight = FontWeight.SemiBold)
                                Text(
                                    cityRegionLabel(city),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
        StepTitle(number = "2", title = "你想去多久？")
        OutlinedButton(
            onClick = { showDatePicker = true },
            modifier = Modifier.fillMaxWidth().height(56.dp),
            shape = RoundedCornerShape(18.dp),
        ) {
            Icon(Icons.Outlined.CalendarMonth, contentDescription = null)
            Text(dateRange, modifier = Modifier.padding(start = 10.dp).weight(1f))
            Text("选择日期", color = MaterialTheme.colorScheme.primary)
        }
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color.White,
            shape = RoundedCornerShape(18.dp),
            tonalElevation = 1.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("行程天数", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                IconButton(
                    onClick = {
                        val oldDayCount = dayCount
                        dayCount = (dayCount - 1).coerceAtLeast(1)
                        if (departureDay == oldDayCount) departureDay = dayCount
                        departureDay = departureDay.coerceAtMost(dayCount)
                        arrivalDay = arrivalDay.coerceAtMost(departureDay)
                        endDate = startDate.plusDays((dayCount - 1).toLong())
                        dateRange = formatDateRange(startDate, endDate)
                    },
                    enabled = dayCount > 1,
                ) {
                    Icon(Icons.Outlined.Remove, contentDescription = "减少一天")
                }
                Text("$dayCount 天", modifier = Modifier.padding(horizontal = 8.dp), fontWeight = FontWeight.Bold)
                IconButton(
                    onClick = {
                        val oldDayCount = dayCount
                        dayCount = (dayCount + 1).coerceAtMost(10)
                        if (departureDay == oldDayCount) departureDay = dayCount
                        endDate = startDate.plusDays((dayCount - 1).toLong())
                        dateRange = formatDateRange(startDate, endDate)
                    },
                    enabled = dayCount < 10,
                ) {
                    Icon(Icons.Outlined.Add, contentDescription = "增加一天")
                }
            }
        }

        StepTitle(number = "3", title = "交通与住宿（可选）")
        Text(
            "设置行程起点、终点和每天住宿位置",
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "未设置的项目不会加入行程。自驾或住在非标准地点时，可以直接在地图上选点。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        PlanningAnchorSection(
            title = "到达安排",
            subtitle = "作为行程第一段的起点",
            icon = { Icon(Icons.Outlined.FlightLand, contentDescription = null) },
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = arrivalStation,
                    onValueChange = {
                        arrivalStation = it.take(60)
                        arrivalPoint = null
                        viewModel.searchStations(arrivalStation, selectedCityAdCode, arrival = true)
                    },
                    modifier = Modifier.weight(1f),
                    label = { Text("车站、机场或停车位置") },
                    placeholder = { Text("例如 北京南站") },
                    singleLine = true,
                    shape = RoundedCornerShape(16.dp),
                    enabled = selectedCityAdCode != null,
                    supportingText = if (selectedCityAdCode == null) {
                        { Text("请先选择目的城市") }
                    } else {
                        null
                    },
                )
                MapPickerButton("选择到达位置", enabled = selectedCityAdCode != null) {
                    openMapPicker(MapPickerTarget.Arrival)
                }
            }
            StationSuggestionList(arrivalSuggestions) { suggestion ->
                arrivalStation = suggestion.name
                arrivalPoint = suggestion.toMapPointInput()
                viewModel.clearStationSuggestions(arrival = true)
            }
            arrivalPoint?.let { SelectedAnchorSummary("到达 · 第 $arrivalDay 天", it) }
            DayAndTimeSelector(
                label = "到达",
                day = arrivalDay,
                time = arrivalTime,
                onPreviousDay = { arrivalDay = (arrivalDay - 1).coerceAtLeast(1) },
                onNextDay = { arrivalDay = (arrivalDay + 1).coerceAtMost(departureDay) },
                onSelectTime = { showArrivalTimePicker = true },
            )
        }

        PlanningAnchorSection(
            title = "离开安排",
            subtitle = "作为行程最后一段的终点",
            icon = { Icon(Icons.Outlined.FlightTakeoff, contentDescription = null) },
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = departureStation,
                    onValueChange = {
                        departureStation = it.take(60)
                        departurePoint = null
                        viewModel.searchStations(departureStation, selectedCityAdCode, arrival = false)
                    },
                    modifier = Modifier.weight(1f),
                    label = { Text("车站、机场或停车位置") },
                    placeholder = { Text("例如 北京西站") },
                    singleLine = true,
                    shape = RoundedCornerShape(16.dp),
                    enabled = selectedCityAdCode != null,
                    supportingText = if (selectedCityAdCode == null) {
                        { Text("请先选择目的城市") }
                    } else {
                        null
                    },
                )
                MapPickerButton("选择离开位置", enabled = selectedCityAdCode != null) {
                    openMapPicker(MapPickerTarget.Departure)
                }
            }
            StationSuggestionList(departureSuggestions) { suggestion ->
                departureStation = suggestion.name
                departurePoint = suggestion.toMapPointInput()
                viewModel.clearStationSuggestions(arrival = false)
            }
            departurePoint?.let { SelectedAnchorSummary("离开 · 第 $departureDay 天", it) }
            DayAndTimeSelector(
                label = "离开",
                day = departureDay,
                time = departureTime,
                onPreviousDay = { departureDay = (departureDay - 1).coerceAtLeast(arrivalDay) },
                onNextDay = { departureDay = (departureDay + 1).coerceAtMost(dayCount) },
                onSelectTime = { showDepartureTimePicker = true },
            )
        }

        PlanningAnchorSection(
            title = "住宿安排",
            subtitle = "酒店会作为前一晚终点和次日出发点",
            icon = { Icon(Icons.Outlined.Hotel, contentDescription = null) },
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = hotelName,
                    onValueChange = {
                        hotelName = it.take(80)
                        hotelPoint = null
                        viewModel.searchHotels(hotelName, selectedCityAdCode, "main")
                    },
                    modifier = Modifier.weight(1f),
                    label = { Text("全程同一住宿") },
                    placeholder = { Text("酒店或民宿名称") },
                    singleLine = true,
                    shape = RoundedCornerShape(16.dp),
                )
                MapPickerButton("选择住宿位置") { openMapPicker(MapPickerTarget.Hotel) }
            }
            if (hotelSuggestionTarget == "main") {
                StationSuggestionList(hotelSuggestions) { suggestion ->
                    hotelName = suggestion.name
                    hotelPoint = suggestion.toMapPointInput()
                    viewModel.clearHotelSuggestions()
                }
            }
            hotelPoint?.let { SelectedAnchorSummary("住宿 · 全程", it) }
            hotelStays.forEachIndexed { index, stay ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                ) {
                    Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("第 ${stay.checkInDay} 天至第 ${stay.checkOutDay} 天", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                            IconButton(onClick = { hotelStays.removeAt(index) }) {
                                Icon(Icons.Outlined.Remove, contentDescription = "删除这段住宿")
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(
                                value = stay.name,
                                onValueChange = {
                                    hotelStays[index] = stay.copy(name = it.take(80), mapPoint = null)
                                    viewModel.searchHotels(it, selectedCityAdCode, "stay:$index")
                                },
                                modifier = Modifier.weight(1f),
                                label = { Text("酒店或民宿") },
                                singleLine = true,
                            )
                            MapPickerButton("选择第 ${index + 1} 段住宿位置") {
                                openMapPicker(MapPickerTarget.HotelStay(index))
                            }
                        }
                        if (hotelSuggestionTarget == "stay:$index") {
                            StationSuggestionList(hotelSuggestions) { suggestion ->
                                hotelStays[index] = stay.copy(
                                    name = suggestion.name,
                                    mapPoint = suggestion.toMapPointInput(),
                                )
                                viewModel.clearHotelSuggestions()
                            }
                        }
                        hotelStays[index].mapPoint?.let { point ->
                            SelectedAnchorSummary(
                                "住宿 · 第 ${hotelStays[index].checkInDay} 天入住 · 第 ${hotelStays[index].checkOutDay} 天退房",
                                point,
                            )
                        }
                        StayDateSelector(
                            stay = stay,
                            dayCount = dayCount,
                            onChange = { hotelStays[index] = it },
                        )
                    }
                }
            }
            OutlinedButton(
                onClick = {
                    val checkIn = (hotelStays.lastOrNull()?.checkOutDay ?: 1).coerceAtMost(dayCount)
                    hotelStays.add(HotelStayDraft(checkInDay = checkIn, checkOutDay = (checkIn + 1).coerceAtMost(dayCount + 1)))
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                enabled = hotelStays.size < dayCount,
                shape = RoundedCornerShape(15.dp),
            ) {
                Icon(Icons.Outlined.Add, contentDescription = null)
                Text("添加不同日期的住宿", modifier = Modifier.padding(start = 6.dp))
            }
        }

        StepTitle(number = "4", title = "旅行偏好")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            preferences.chunked(2).forEach { rowItems ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    rowItems.forEach { preference ->
                        PreferenceButton(
                            text = preference,
                            selected = preference in selectedPreferences,
                            modifier = Modifier.weight(1f),
                            onClick = {
                                if (preference in selectedPreferences) {
                                    selectedPreferences.remove(preference)
                                } else {
                                    selectedPreferences.add(preference)
                                }
                            },
                        )
                    }
                    if (rowItems.size == 1) {
                        Spacer(modifier = Modifier.weight(1f))
                    }
                }
            }
        }

        StepTitle(number = "5", title = "节奏与交通")
        Text("旅行节奏", fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf("RELAXED" to "轻松", "BALANCED" to "适中", "INTENSIVE" to "充实").forEach { (value, label) ->
                PreferenceButton(
                    text = label,
                    selected = pace == value,
                    modifier = Modifier.weight(1f),
                    onClick = { pace = value },
                )
            }
        }
        Text("优先交通方式", fontWeight = FontWeight.SemiBold)
        Text(
            "公共交通会依据当地高德实时路线自动识别地铁、公交、轮渡等实际可用方式。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf(
                listOf("MIXED" to "智能混合", "TRANSIT" to "公共交通优先"),
                listOf("WALK" to "步行为主", "DRIVE" to "驾车为主"),
            ).forEach { options ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    options.forEach { (value, label) ->
                        PreferenceButton(
                            text = label,
                            selected = transportPreference == value,
                            modifier = Modifier.weight(1f),
                            onClick = { transportPreference = value },
                        )
                    }
                }
            }
        }
        Text("每日活动时段", fontWeight = FontWeight.SemiBold)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf(
                Triple("08:00", "18:00", "早出早归"),
                Triple("09:00", "20:00", "标准"),
                Triple("10:00", "22:00", "晚起夜游"),
            ).forEach { (start, end, label) ->
                PreferenceButton(
                    text = label,
                    selected = dailyStart == start && dailyEnd == end,
                    modifier = Modifier.weight(1f),
                    onClick = {
                        dailyStart = start
                        dailyEnd = end
                    },
                )
            }
        }

        StepTitle(number = "6", title = "规划方式")
        SelectableOptionCard(
            title = "智能优化",
            description = "先生成可浏览的基础行程，再结合偏好、天气、开放时间与实际通勤进一步优化。",
            selected = optimizationMode == "REQUIRED",
            onClick = { optimizationMode = "REQUIRED" },
        )
        SelectableOptionCard(
            title = "快速规划",
            description = "根据天气、开放时间与实际路线快速生成可编辑的行程方案。",
            selected = optimizationMode == "FAST",
            onClick = { optimizationMode = "FAST" },
        )

        Text("补充想法（可选）", fontWeight = FontWeight.SemiBold)
        OutlinedTextField(
            value = freeText,
            onValueChange = { freeText = it.take(240) },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("例如：想看夜景、不要安排太赶、午餐希望有本地特色") },
            supportingText = { Text("会用于调整地点、节奏、用餐和通勤安排") },
            minLines = 3,
            maxLines = 4,
            shape = RoundedCornerShape(18.dp),
        )

        Spacer(modifier = Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = {
                    viewModel.createPlan(
                        destination = destination,
                        dateRange = dateRange,
                        preferences = selectedPreferences,
                        dayCount = dayCount,
                    )
                    onDone()
                },
                modifier = Modifier.weight(1f).height(52.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                Text("手动规划")
            }
            Button(
                onClick = {
                    when {
                        destination.isBlank() || selectedCityAdCode == null -> {
                            destinationError = true
                            Toast.makeText(context, "请先从联想结果中选择具体目的城市", Toast.LENGTH_SHORT).show()
                        }
                        dateRange.isBlank() -> Toast.makeText(context, "请先填写出行日期", Toast.LENGTH_SHORT).show()
                        else -> onStartAiPlanning(
                            AiPlanDraftInput(
                                destination = destination.trim(),
                                dateRange = dateRange.trim(),
                                dayCount = dayCount,
                                preferences = selectedPreferences.toList(),
                                freeText = freeText.trim().ifBlank { null },
                                arrivalStation = arrivalStation.trim().ifBlank { null },
                                arrivalPoint = arrivalPoint,
                                arrivalDay = arrivalDay,
                                arrivalTime = arrivalTime.trim().ifBlank { null },
                                departureStation = departureStation.trim().ifBlank { null },
                                departurePoint = departurePoint,
                                departureDay = departureDay,
                                departureTime = departureTime.trim().ifBlank { null },
                                hotelName = hotelName.trim().ifBlank { null },
                                hotelPoint = hotelPoint,
                                hotelStays = hotelStays.mapNotNull { stay ->
                                    stay.name.trim().takeIf(String::isNotBlank)?.let { name ->
                                        AiHotelStayInput(name, stay.checkInDay, stay.checkOutDay, stay.mapPoint)
                                    }
                                },
                                optimizationMode = optimizationMode,
                                pace = pace,
                                transportPreference = transportPreference,
                                dailyStart = dailyStart,
                                dailyEnd = dailyEnd,
                            ),
                        )
                    }
                },
                modifier = Modifier.weight(1f).height(52.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                Icon(Icons.Outlined.AutoAwesome, contentDescription = null)
                Text(
                    text = if (optimizationMode == "REQUIRED") "开始智能规划" else "开始快速规划",
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
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
                TextButton(
                    onClick = {
                        val startMillis = pickerState.selectedStartDateMillis
                        val endMillis = pickerState.selectedEndDateMillis
                        if (startMillis != null && endMillis != null) {
                            val start = Instant.ofEpochMilli(startMillis).atZone(ZoneOffset.UTC).toLocalDate()
                            val end = Instant.ofEpochMilli(endMillis).atZone(ZoneOffset.UTC).toLocalDate()
                            val selectedDays = ChronoUnit.DAYS.between(start, end).toInt() + 1
                            if (selectedDays > 10) {
                                Toast.makeText(context, "智能规划最多支持 10 天", Toast.LENGTH_SHORT).show()
                            } else {
                                startDate = start
                                endDate = end
                                val oldDayCount = dayCount
                                dayCount = selectedDays.coerceAtLeast(1)
                                if (departureDay == oldDayCount) departureDay = dayCount
                                departureDay = departureDay.coerceAtMost(dayCount)
                                arrivalDay = arrivalDay.coerceAtMost(departureDay)
                                dateRange = formatDateRange(start, end)
                                showDatePicker = false
                            }
                        }
                    },
                ) { Text("确定") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("取消") }
            },
        ) {
            DateRangePicker(
                state = pickerState,
                title = { Text("选择出行日期", modifier = Modifier.padding(16.dp)) },
                showModeToggle = false,
            )
        }
    }
    if (showArrivalTimePicker) {
        AppTimePickerDialog(
            title = "选择第 $arrivalDay 天到达时间",
            initialTime = arrivalTime.ifBlank { "08:30" },
            onDismiss = { showArrivalTimePicker = false },
            onConfirm = {
                arrivalTime = it
                showArrivalTimePicker = false
            },
        )
    }
    if (showDepartureTimePicker) {
        AppTimePickerDialog(
            title = "选择第 $departureDay 天离开时间",
            initialTime = departureTime.ifBlank { "18:00" },
            onDismiss = { showDepartureTimePicker = false },
            onConfirm = {
                departureTime = it
                showDepartureTimePicker = false
            },
        )
    }
    val mapCenterLatitude = selectedCityLatitude
    val mapCenterLongitude = selectedCityLongitude
    mapPickerTarget?.let { target ->
        if (mapCenterLatitude == null || mapCenterLongitude == null) return@let
        MapPointPickerDialog(
            title = when (target) {
                MapPickerTarget.Arrival -> "选择到达位置"
                MapPickerTarget.Departure -> "选择离开位置"
                MapPickerTarget.Hotel -> "选择住宿位置"
                is MapPickerTarget.HotelStay -> "选择这段住宿位置"
            },
            initialLatitude = mapCenterLatitude,
            initialLongitude = mapCenterLongitude,
            expectedCityName = destination,
            expectedCityAdCode = selectedCityAdCode ?: return@let,
            roleLabel = when (target) {
                MapPickerTarget.Arrival -> "到达点（第 $arrivalDay 天）"
                MapPickerTarget.Departure -> "离开点（第 $departureDay 天）"
                MapPickerTarget.Hotel -> "住宿点（全程）"
                is MapPickerTarget.HotelStay -> hotelStays.getOrNull(target.index)?.let {
                    "住宿点（第 ${it.checkInDay} 天入住，第 ${it.checkOutDay} 天退房）"
                } ?: "住宿点"
            },
            resolvePoint = viewModel::reverseGeocodePoint,
            onDismiss = { mapPickerTarget = null },
            onConfirm = { point ->
                when (target) {
                    MapPickerTarget.Arrival -> {
                        arrivalStation = point.name
                        arrivalPoint = point.toInput()
                    }
                    MapPickerTarget.Departure -> {
                        departureStation = point.name
                        departurePoint = point.toInput()
                    }
                    MapPickerTarget.Hotel -> {
                        hotelName = point.name
                        hotelPoint = point.toInput()
                    }
                    is MapPickerTarget.HotelStay -> {
                        hotelStays.getOrNull(target.index)?.let { stay ->
                            hotelStays[target.index] = stay.copy(name = point.name, mapPoint = point.toInput())
                        }
                    }
                }
                mapPickerTarget = null
            },
        )
    }
}

@Composable
private fun PlanningAnchorSection(
    title: String,
    subtitle: String,
    icon: @Composable () -> Unit,
    content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.38f),
        shape = RoundedCornerShape(22.dp),
        tonalElevation = 1.dp,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Surface(
                    color = MaterialTheme.colorScheme.primaryContainer,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.height(44.dp),
                ) {
                    Box(modifier = Modifier.padding(horizontal = 11.dp), contentAlignment = Alignment.Center) { icon() }
                }
                Column {
                    Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            content()
        }
    }
}

@Composable
private fun MapPickerButton(
    contentDescription: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.height(56.dp),
        shape = RoundedCornerShape(16.dp),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 14.dp),
    ) {
        Icon(Icons.Outlined.Map, contentDescription = contentDescription)
        Text("地图", modifier = Modifier.padding(start = 4.dp))
    }
}

@Composable
private fun DayAndTimeSelector(
    label: String,
    day: Int,
    time: String,
    onPreviousDay: () -> Unit,
    onNextDay: () -> Unit,
    onSelectTime: () -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("第 $day 天$label", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
        IconButton(onClick = onPreviousDay) { Icon(Icons.Outlined.Remove, contentDescription = "提前${label}日") }
        IconButton(onClick = onNextDay) { Icon(Icons.Outlined.Add, contentDescription = "延后${label}日") }
    }
    OutlinedButton(
        onClick = onSelectTime,
        modifier = Modifier.fillMaxWidth().height(52.dp),
        shape = RoundedCornerShape(16.dp),
    ) {
        Icon(Icons.Outlined.AccessTime, contentDescription = null)
        Text(time.ifBlank { "选择第 $day 天${label}时间" }, modifier = Modifier.padding(start = 8.dp).weight(1f))
        if (time.isNotBlank()) Text("修改")
    }
}

@Composable
private fun StayDateSelector(
    stay: HotelStayDraft,
    dayCount: Int,
    onChange: (HotelStayDraft) -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { onChange(stay.copy(checkInDay = (stay.checkInDay - 1).coerceAtLeast(1))) }) {
            Icon(Icons.Outlined.Remove, contentDescription = "提前入住")
        }
        Text("第 ${stay.checkInDay} 天入住", modifier = Modifier.weight(1f))
        IconButton(onClick = { onChange(stay.copy(checkInDay = (stay.checkInDay + 1).coerceAtMost(stay.checkOutDay - 1))) }) {
            Icon(Icons.Outlined.Add, contentDescription = "延后入住")
        }
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { onChange(stay.copy(checkOutDay = (stay.checkOutDay - 1).coerceAtLeast(stay.checkInDay + 1))) }) {
            Icon(Icons.Outlined.Remove, contentDescription = "提前退房")
        }
        Text("第 ${stay.checkOutDay} 天退房", modifier = Modifier.weight(1f))
        IconButton(onClick = { onChange(stay.copy(checkOutDay = (stay.checkOutDay + 1).coerceAtMost(dayCount + 1))) }) {
            Icon(Icons.Outlined.Add, contentDescription = "延后退房")
        }
    }
}

private fun defaultDateRange(dayCount: Int): String {
    val start = LocalDate.now()
    val end = start.plusDays((dayCount - 1).toLong())
    return formatDateRange(start, end)
}

private fun formatDateRange(start: LocalDate, end: LocalDate): String {
    val formatter = DateTimeFormatter.ofPattern("yyyy.MM.dd")
    return "${start.format(formatter)} - ${end.format(formatter)}"
}

private fun PickedMapPoint.toInput(): AiMapPointInput = AiMapPointInput(
    name = name,
    address = address,
    latitude = latitude,
    longitude = longitude,
    adCode = adCode,
    provinceName = provinceName,
    cityName = cityName,
    districtName = districtName,
)

private fun PlaceSuggestion.toMapPointInput(): AiMapPointInput? {
    val lat = latitude ?: return null
    val lng = longitude ?: return null
    return AiMapPointInput(
        name = name,
        address = address,
        latitude = lat,
        longitude = lng,
        adCode = adCode,
        cityName = cityName,
        districtName = district,
    )
}

@Composable
private fun SelectedAnchorSummary(role: String, point: AiMapPointInput) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.45f),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp)) {
            Text(role, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            Text(point.name, fontWeight = FontWeight.SemiBold)
            point.address?.takeIf(String::isNotBlank)?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AppTimePickerDialog(
    title: String,
    initialTime: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit,
) {
    val parts = initialTime.split(':')
    val state = rememberTimePickerState(
        initialHour = parts.getOrNull(0)?.toIntOrNull()?.coerceIn(0, 23) ?: 9,
        initialMinute = parts.getOrNull(1)?.toIntOrNull()?.coerceIn(0, 59) ?: 0,
        is24Hour = true,
    )
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { TimePicker(state = state) },
        confirmButton = {
            TextButton(onClick = { onConfirm("%02d:%02d".format(state.hour, state.minute)) }) {
                Text("确定")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}

@Composable
private fun StationSuggestionList(
    suggestions: List<PlaceSuggestion>,
    onSelect: (PlaceSuggestion) -> Unit,
) {
    if (suggestions.isEmpty()) return
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp,
    ) {
        Column {
            suggestions.forEach { suggestion ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelect(suggestion) }
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.LocationOn, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Column(modifier = Modifier.padding(start = 10.dp)) {
                        Text(suggestion.name, fontWeight = FontWeight.SemiBold)
                        Text(
                            listOfNotNull(
                                transportSuggestionLabel(suggestion),
                                suggestion.district,
                                suggestion.address,
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                        )
                    }
                }
            }
        }
    }
}

private fun transportSuggestionLabel(suggestion: PlaceSuggestion): String = when {
    suggestion.name.contains("机场") || suggestion.name.contains("航站楼") -> "机场"
    suggestion.name.contains("高铁") -> "高铁站"
    suggestion.name.endsWith("站") -> "火车站"
    else -> "交通枢纽"
}

@Composable
private fun SelectableOptionCard(
    title: String,
    description: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        ),
        shape = RoundedCornerShape(18.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = if (selected) 2.dp else 0.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
            Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                if (selected) "已选择" else "点击选择",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun HeroCard() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(112.dp)
            .background(
                brush = Brush.linearGradient(
                    listOf(Color(0xFFEAF5FF), Color.White),
                ),
                shape = RoundedCornerShape(26.dp),
            )
            .padding(18.dp),
    ) {
        Text(
            text = "真实地点、跨天编排、节奏约束与质量检查，一次生成可继续编辑的行程。",
            modifier = Modifier.align(Alignment.CenterStart),
            color = Color(0xFF526173),
            style = MaterialTheme.typography.bodyLarge,
        )
    }
}

@Composable
private fun StepTitle(number: String, title: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            color = MaterialTheme.colorScheme.primary,
            shape = CircleShape,
        ) {
            Text(
                text = number,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                color = Color.White,
                fontWeight = FontWeight.Bold,
            )
        }
        Text(
            text = title,
            modifier = Modifier.padding(start = 10.dp),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

internal fun destinationSuggestionTitle(query: String, suggestions: List<ExploreCity>): String {
    val normalized = query.trim()
    val provinces = suggestions.map { it.provinceName }.distinct()
    val selectedProvince = provinces.singleOrNull()?.takeIf { province ->
        normalized.isNotBlank() && (
            province.contains(normalized, ignoreCase = true) ||
                normalized.contains(province.removeSuffix("省").removeSuffix("市"), ignoreCase = true)
            )
    }
    return selectedProvince?.let { "选择 $it 下的城市" } ?: "选择目的城市"
}

@Composable
private fun PreferenceButton(
    text: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    Card(
        modifier = modifier.clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) Color(0xFFE2EEFF) else Color.White,
        ),
        shape = RoundedCornerShape(18.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 16.dp),
            color = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF162235),
            fontWeight = FontWeight.SemiBold,
        )
    }
}
