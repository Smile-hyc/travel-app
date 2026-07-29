package com.heoclub.aitravel.ui.plan

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.ui.components.PlaceCoverImage

/** 计划内地点的一条命中结果，附带它属于哪个计划、第几天。 */
data class PlanPlaceMatch(
    val item: PlanItem,
    val planId: String,
    val planTitle: String,
)

data class PlanSearchResults(
    val plans: List<TravelPlan> = emptyList(),
    val places: List<PlanPlaceMatch> = emptyList(),
) {
    val isEmpty: Boolean
        get() = plans.isEmpty() && places.isEmpty()
}

/**
 * 纯本地搜索：计划按标题/目的地/日期/偏好匹配，
 * 计划内地点按名称/分类/地址/备注匹配。
 */
fun searchPlansAndPlaces(plans: List<TravelPlan>, keyword: String): PlanSearchResults {
    val query = keyword.trim()
    if (query.isBlank()) return PlanSearchResults()

    val matchedPlans = plans.filter { plan ->
        plan.matchesQuery(query)
    }
    val matchedPlaces = plans.flatMap { plan ->
        val itemsInDays = plan.days.orEmpty().flatMap { it.items.orEmpty() }
        (itemsInDays + plan.unplannedItems.orEmpty())
            .filter { it.matchesQuery(query) }
            .map { item -> PlanPlaceMatch(item = item, planId = plan.id, planTitle = plan.title) }
    }
    return PlanSearchResults(plans = matchedPlans, places = matchedPlaces)
}

private fun TravelPlan.matchesQuery(query: String): Boolean {
    val fields = listOf(title, destination, dateRange) + preferences
    return fields.any { it.contains(query, ignoreCase = true) }
}

private fun PlanItem.matchesQuery(query: String): Boolean {
    val fields = listOfNotNull(name, typeName, address, districtName, cityName, note)
    return fields.any { it.contains(query, ignoreCase = true) }
}

@Composable
fun PlanSearchScreen(
    plans: List<TravelPlan>,
    onOpenPlan: (String) -> Unit,
    onOpenPlanItem: (PlanItem) -> Unit,
    onDismiss: () -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val trimmed = query.trim()
    val results = remember(plans, trimmed) { searchPlansAndPlaces(plans, trimmed) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(Color(0xFFEAF5FF), Color(0xFFF9FCFF)),
                    ),
                ),
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .imePadding()
                    .padding(horizontal = 22.dp, vertical = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                PlanSearchHeader(
                    query = query,
                    onQueryChange = { query = it },
                    onDismiss = onDismiss,
                )

                Text(
                    text = if (trimmed.isBlank()) {
                        "在我的 ${plans.size} 个计划和其中的地点里搜索"
                    } else {
                        "找到 ${results.plans.size} 个计划、${results.places.size} 个地点"
                    },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )

                when {
                    plans.isEmpty() -> StateCard(text = "还没有任何计划，先创建一个再来搜索")

                    trimmed.isBlank() -> {
                        // 默认态直接列出全部计划，比一片空白更有用。
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            item(key = "all-plans-heading") {
                                SectionHeading(text = "我的计划")
                            }
                            items(plans, key = { "plan-${it.id}" }) { plan ->
                                PlanResultCard(plan = plan, onClick = { onOpenPlan(plan.id) })
                            }
                        }
                    }

                    results.isEmpty -> StateCard(text = "没有匹配「$trimmed」的计划或地点")

                    else -> {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            if (results.plans.isNotEmpty()) {
                                item(key = "plans-heading") {
                                    SectionHeading(text = "计划 ${results.plans.size}")
                                }
                                items(results.plans, key = { "plan-${it.id}" }) { plan ->
                                    PlanResultCard(plan = plan, onClick = { onOpenPlan(plan.id) })
                                }
                            }
                            if (results.places.isNotEmpty()) {
                                item(key = "places-heading") {
                                    SectionHeading(text = "计划内地点 ${results.places.size}")
                                }
                                items(results.places, key = { "item-${it.planId}-${it.item.id}" }) { match ->
                                    PlanPlaceResultCard(
                                        match = match,
                                        onClick = { onOpenPlanItem(match.item) },
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
private fun PlanSearchHeader(
    query: String,
    onQueryChange: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var textFieldValue by remember {
        mutableStateOf(TextFieldValue(text = query, selection = TextRange(query.length)))
    }
    val focusRequester = remember { FocusRequester() }
    val keyboardController = LocalSoftwareKeyboardController.current

    LaunchedEffect(query) {
        if (query != textFieldValue.text) {
            textFieldValue = TextFieldValue(text = query, selection = TextRange(query.length))
        }
    }
    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
        keyboardController?.show()
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(32.dp),
        color = Color.White.copy(alpha = 0.97f),
        shadowElevation = 6.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onDismiss) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
            }
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .height(58.dp),
                shape = RoundedCornerShape(28.dp),
                color = Color.White,
                border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.primary),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Search, contentDescription = null)
                    Spacer(modifier = Modifier.size(10.dp))
                    BasicTextField(
                        value = textFieldValue,
                        onValueChange = { value ->
                            textFieldValue = value
                            onQueryChange(value.text)
                        },
                        modifier = Modifier
                            .weight(1f)
                            .focusRequester(focusRequester),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodyLarge.copy(
                            color = MaterialTheme.colorScheme.onSurface,
                        ),
                        cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                        // 计划搜索是本地实时过滤，回车只需要收起键盘。
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        keyboardActions = KeyboardActions(onSearch = { keyboardController?.hide() }),
                        decorationBox = { innerTextField ->
                            Box(contentAlignment = Alignment.CenterStart) {
                                if (textFieldValue.text.isEmpty()) {
                                    Text(
                                        text = "搜索计划名、目的地或计划里的地点",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                innerTextField()
                            }
                        },
                    )
                    if (textFieldValue.text.isNotEmpty()) {
                        IconButton(onClick = { onQueryChange("") }) {
                            Icon(Icons.Outlined.Close, contentDescription = "清空")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeading(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(top = 4.dp),
    )
}

@Composable
private fun PlanResultCard(
    plan: TravelPlan,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = Color.White,
        shape = RoundedCornerShape(22.dp),
        shadowElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(46.dp)
                    .clip(CircleShape)
                    .background(Color(0xFFEAF5FF)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.CalendarMonth,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(modifier = Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = plan.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = listOf(plan.destination, plan.dateRange, "${plan.dayCount}天 · ${plan.placeCount}个地点")
                        .filter { it.isNotBlank() }
                        .joinToString(" · "),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun PlanPlaceResultCard(
    match: PlanPlaceMatch,
    onClick: () -> Unit,
) {
    val item = match.item
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = Color.White,
        shape = RoundedCornerShape(22.dp),
        shadowElevation = 2.dp,
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PlaceCoverImage(
                imageUrl = item.thumbnailUrl,
                fallbackImageUrls = item.imageUrls,
                placeName = item.name,
                category = item.category,
                modifier = Modifier.size(60.dp),
                shape = RoundedCornerShape(16.dp),
            )
            Spacer(modifier = Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = "${match.planTitle} · DAY ${item.dayIndex}",
                    color = Color(0xFF1F7AE0),
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = listOfNotNull(item.typeName, item.address).joinToString(" · ")
                        .ifBlank { "计划内地点" },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Icon(
                imageVector = Icons.Outlined.LocationOn,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun StateCard(text: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color.White.copy(alpha = 0.9f),
        shape = RoundedCornerShape(24.dp),
        shadowElevation = 2.dp,
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(20.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
