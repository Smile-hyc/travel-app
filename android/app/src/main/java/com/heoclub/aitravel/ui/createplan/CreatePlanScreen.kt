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
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Remove
import androidx.compose.material3.Button
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
import androidx.compose.material3.rememberDateRangePickerState
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
import java.time.LocalDate
import java.time.Instant
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.time.format.DateTimeFormatter

private data class HotelStayDraft(
    val name: String = "",
    val checkInDay: Int = 1,
    val checkOutDay: Int = 2,
)

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
    var dayCount by remember { mutableStateOf(3) }
    var startDate by remember { mutableStateOf(LocalDate.now()) }
    var endDate by remember { mutableStateOf(startDate.plusDays((dayCount - 1).toLong())) }
    var dateRange by remember { mutableStateOf(formatDateRange(startDate, endDate)) }
    var freeText by remember { mutableStateOf("") }
    var arrivalStation by remember { mutableStateOf("") }
    var arrivalDay by remember { mutableStateOf(1) }
    var arrivalTime by remember { mutableStateOf("") }
    var departureStation by remember { mutableStateOf("") }
    var departureDay by remember { mutableStateOf(dayCount) }
    var departureTime by remember { mutableStateOf("") }
    var hotelName by remember { mutableStateOf("") }
    val hotelStays = remember { mutableStateListOf<HotelStayDraft>() }
    var pace by remember { mutableStateOf("BALANCED") }
    var transportPreference by remember { mutableStateOf("MIXED") }
    var dailyStart by remember { mutableStateOf("09:00") }
    var dailyEnd by remember { mutableStateOf("20:00") }
    var showDatePicker by remember { mutableStateOf(false) }
    var destinationError by remember { mutableStateOf(false) }
    val citySuggestions by viewModel.citySuggestions.collectAsState()
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
                { Text("请输入并选择一个城市后再开始规划") }
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
                    citySuggestions.forEach { city ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    destination = city.name
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
                                    city.provinceName,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
        Text(
            "出发与住宿锚点（可选）",
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "只采用你明确填写的项目；留空不会自动加入车站、机场或酒店。时间请用 HH:mm。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = arrivalStation,
            onValueChange = { arrivalStation = it.take(60) },
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = { Icon(Icons.Outlined.LocationOn, contentDescription = null) },
            label = { Text("到达车站 / 机场") },
            placeholder = { Text("例如 北京南站或首都机场") },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        OutlinedTextField(
            value = arrivalTime,
            onValueChange = { arrivalTime = it.filter { char -> char.isDigit() || char == ':' }.take(5) },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("到达时间（可选）") },
            placeholder = { Text("例如 08:35") },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("第 $arrivalDay 天到达", modifier = Modifier.weight(1f))
            IconButton(onClick = { arrivalDay = (arrivalDay - 1).coerceAtLeast(1) }) {
                Icon(Icons.Outlined.Remove, contentDescription = "提前到达日")
            }
            IconButton(onClick = { arrivalDay = (arrivalDay + 1).coerceAtMost(departureDay) }) {
                Icon(Icons.Outlined.Add, contentDescription = "延后到达日")
            }
        }
        OutlinedTextField(
            value = departureStation,
            onValueChange = { departureStation = it.take(60) },
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = { Icon(Icons.Outlined.LocationOn, contentDescription = null) },
            label = { Text("离开车站 / 机场") },
            placeholder = { Text("例如 北京西站") },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        OutlinedTextField(
            value = departureTime,
            onValueChange = { departureTime = it.filter { char -> char.isDigit() || char == ':' }.take(5) },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("离开时间（可选，默认最后一天）") },
            placeholder = { Text("例如 18:20") },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("第 $departureDay 天离开", modifier = Modifier.weight(1f))
            IconButton(onClick = { departureDay = (departureDay - 1).coerceAtLeast(arrivalDay) }) {
                Icon(Icons.Outlined.Remove, contentDescription = "提前离开日")
            }
            IconButton(onClick = { departureDay = (departureDay + 1).coerceAtMost(dayCount) }) {
                Icon(Icons.Outlined.Add, contentDescription = "延后离开日")
            }
        }
        OutlinedTextField(
            value = hotelName,
            onValueChange = { hotelName = it.take(80) },
            modifier = Modifier.fillMaxWidth(),
            leadingIcon = { Icon(Icons.Outlined.LocationOn, contentDescription = null) },
            label = { Text("全程同一酒店（可选）") },
            placeholder = { Text("例如 北京王府井希尔顿酒店") },
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
        )
        hotelStays.forEachIndexed { index, stay ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f)),
            ) {
                Column(
                    modifier = Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("分段酒店 ${index + 1}", fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                        IconButton(onClick = { hotelStays.removeAt(index) }) {
                            Icon(Icons.Outlined.Remove, contentDescription = "删除这段酒店")
                        }
                    }
                    OutlinedTextField(
                        value = stay.name,
                        onValueChange = { hotelStays[index] = stay.copy(name = it.take(80)) },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("酒店准确名称") },
                        singleLine = true,
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = {
                            hotelStays[index] = stay.copy(checkInDay = (stay.checkInDay - 1).coerceAtLeast(1))
                        }) { Icon(Icons.Outlined.Remove, contentDescription = "提前入住") }
                        Text("第 ${stay.checkInDay} 天入住", modifier = Modifier.weight(1f))
                        IconButton(onClick = {
                            hotelStays[index] = stay.copy(
                                checkInDay = (stay.checkInDay + 1).coerceAtMost(stay.checkOutDay - 1),
                            )
                        }) { Icon(Icons.Outlined.Add, contentDescription = "延后入住") }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = {
                            hotelStays[index] = stay.copy(
                                checkOutDay = (stay.checkOutDay - 1).coerceAtLeast(stay.checkInDay + 1),
                            )
                        }) { Icon(Icons.Outlined.Remove, contentDescription = "提前退房") }
                        Text("第 ${stay.checkOutDay} 天退房", modifier = Modifier.weight(1f))
                        IconButton(onClick = {
                            hotelStays[index] = stay.copy(checkOutDay = (stay.checkOutDay + 1).coerceAtMost(dayCount + 1))
                        }) { Icon(Icons.Outlined.Add, contentDescription = "延后退房") }
                    }
                }
            }
        }
        OutlinedButton(
            onClick = {
                val checkIn = (hotelStays.lastOrNull()?.checkOutDay ?: 1).coerceAtMost(dayCount)
                hotelStays.add(HotelStayDraft(checkInDay = checkIn, checkOutDay = (checkIn + 1).coerceAtMost(dayCount + 1)))
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = hotelStays.size < dayCount,
        ) {
            Icon(Icons.Outlined.Add, contentDescription = null)
            Text("按入住日期添加不同酒店")
        }
        OutlinedTextField(
            value = freeText,
            onValueChange = { freeText = it.take(240) },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("补充想法（可选）") },
            placeholder = { Text("例如：住在市中心、不要太赶") },
            minLines = 2,
            maxLines = 3,
            shape = RoundedCornerShape(18.dp),
        )

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

        StepTitle(number = "3", title = "旅行偏好")
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

        StepTitle(number = "4", title = "节奏与交通")
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
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            listOf(
                listOf("MIXED" to "智能混合", "TRANSIT" to "公交地铁"),
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
                        destination.isBlank() -> destinationError = true
                        dateRange.isBlank() -> Toast.makeText(context, "请先填写出行日期", Toast.LENGTH_SHORT).show()
                        arrivalTime.isNotBlank() && !isValidClockTime(arrivalTime) ->
                            Toast.makeText(context, "到达时间请使用 HH:mm，例如 08:35", Toast.LENGTH_SHORT).show()
                        departureTime.isNotBlank() && !isValidClockTime(departureTime) ->
                            Toast.makeText(context, "离开时间请使用 HH:mm，例如 18:20", Toast.LENGTH_SHORT).show()
                        else -> onStartAiPlanning(
                            AiPlanDraftInput(
                                destination = destination.trim(),
                                dateRange = dateRange.trim(),
                                dayCount = dayCount,
                                preferences = selectedPreferences.toList(),
                                freeText = freeText.trim().ifBlank { null },
                                arrivalStation = arrivalStation.trim().ifBlank { null },
                                arrivalDay = arrivalDay,
                                arrivalTime = arrivalTime.trim().ifBlank { null },
                                departureStation = departureStation.trim().ifBlank { null },
                                departureDay = departureDay,
                                departureTime = departureTime.trim().ifBlank { null },
                                hotelName = hotelName.trim().ifBlank { null },
                                hotelStays = hotelStays.mapNotNull { stay ->
                                    stay.name.trim().takeIf(String::isNotBlank)?.let { name ->
                                        AiHotelStayInput(name, stay.checkInDay, stay.checkOutDay)
                                    }
                                },
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
                    text = "智能规划",
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
}

private fun defaultDateRange(dayCount: Int): String {
    val start = LocalDate.now()
    val end = start.plusDays((dayCount - 1).toLong())
    return formatDateRange(start, end)
}

private fun formatDateRange(start: LocalDate, end: LocalDate): String {
    val formatter = DateTimeFormatter.ofPattern("MM.dd")
    return "${start.format(formatter)} - ${end.format(formatter)}"
}

private fun isValidClockTime(value: String): Boolean {
    return Regex("(?:[01]\\d|2[0-3]):[0-5]\\d").matches(value)
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
