package com.heoclub.aitravel.ui.explore

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
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.CircularProgressIndicator
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
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.ui.components.PlaceCoverImage
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

@Composable
fun PlaceSearchScreen(
    cityName: String,
    query: String,
    suggestions: List<PlaceSuggestion>,
    results: List<PlaceSummary>,
    hasSubmittedSearch: Boolean,
    isLoadingSuggestions: Boolean,
    isSearching: Boolean,
    notice: String?,
    error: String?,
    history: List<String>,
    quickWords: List<String>,
    currentLatitude: Double? = null,
    currentLongitude: Double? = null,
    onQueryChange: (String) -> Unit,
    onSubmitSearch: (String) -> Unit,
    onSuggestionClick: (PlaceSuggestion) -> Unit,
    onResultClick: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
    onRemoveHistory: (String) -> Unit,
    onClearHistory: () -> Unit,
    onDismiss: () -> Unit,
) {
    val trimmedQuery = query.trim()
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
                SearchHeader(
                    query = query,
                    onQueryChange = onQueryChange,
                    onSubmit = { onSubmitSearch(it) },
                    onDismiss = onDismiss,
                )

                Text(
                    text = "当前搜索城市：$cityName",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )

                if (notice != null) {
                    NoticeCard(text = notice)
                }

                when {
                    isSearching -> LoadingBlock()

                    hasSubmittedSearch && results.isNotEmpty() -> {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            items(results, key = { it.id }) { place ->
                                PlaceResultCard(
                                    place = place,
                                    distanceText = distanceText(place, currentLatitude, currentLongitude),
                                    onClick = { onResultClick(place.id) },
                                    onAdd = { onAddPlace(place) },
                                )
                            }
                        }
                    }

                    error != null -> SearchStateCard(text = error)

                    trimmedQuery.length < 2 -> {
                        DefaultSearchContent(
                            history = history,
                            quickWords = quickWords,
                            onWordClick = { word ->
                                onQueryChange(word)
                                onSubmitSearch(word)
                            },
                            onRemoveHistory = onRemoveHistory,
                            onClearHistory = onClearHistory,
                        )
                    }

                    isLoadingSuggestions -> LoadingBlock()

                    else -> {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            item(key = "search-action") {
                                SearchActionRow(
                                    keyword = trimmedQuery,
                                    onClick = { onSubmitSearch(trimmedQuery) },
                                )
                            }
                            items(suggestions, key = { it.id }) { suggestion ->
                                SuggestionItem(
                                    suggestion = suggestion,
                                    onClick = { onSuggestionClick(suggestion) },
                                )
                            }
                            if (suggestions.isEmpty()) {
                                item(key = "empty-tips") {
                                    SearchStateCard(text = "没有匹配的联想词，可以直接搜索完整名称")
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
private fun SearchHeader(
    query: String,
    onQueryChange: (String) -> Unit,
    onSubmit: (String) -> Unit,
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
    // 打开搜索页就直接可以打字，不用再点一次输入框。
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
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                        keyboardActions = KeyboardActions(
                            onSearch = {
                                keyboardController?.hide()
                                onSubmit(textFieldValue.text.trim())
                            },
                        ),
                        decorationBox = { innerTextField ->
                            Box(contentAlignment = Alignment.CenterStart) {
                                if (textFieldValue.text.isEmpty()) {
                                    Text(
                                        text = "搜索地点，例如 天津之眼",
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
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
private fun DefaultSearchContent(
    history: List<String>,
    quickWords: List<String>,
    onWordClick: (String) -> Unit,
    onRemoveHistory: (String) -> Unit,
    onClearHistory: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (history.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "搜索历史",
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "清空",
                        modifier = Modifier
                            .clip(RoundedCornerShape(12.dp))
                            .clickable(onClick = onClearHistory)
                            .padding(horizontal = 10.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(history, key = { it }) { keyword ->
                        HistoryChip(
                            keyword = keyword,
                            onClick = { onWordClick(keyword) },
                            onRemove = { onRemoveHistory(keyword) },
                        )
                    }
                }
            }
        }

        if (quickWords.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    text = "大家都在搜",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                quickWords.chunked(2).forEach { rowWords ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        rowWords.forEach { word ->
                            Surface(
                                modifier = Modifier
                                    .weight(1f)
                                    .height(44.dp)
                                    .clip(RoundedCornerShape(18.dp))
                                    .clickable { onWordClick(word) },
                                color = Color.White,
                                shape = RoundedCornerShape(18.dp),
                                shadowElevation = 1.dp,
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Text(
                                        text = word,
                                        fontWeight = FontWeight.SemiBold,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                        }
                        repeat(2 - rowWords.size) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        }

        if (history.isEmpty() && quickWords.isEmpty()) {
            SearchStateCard(text = "输入至少两个字，搜索当前城市里的真实地点")
        }
    }
}

@Composable
private fun HistoryChip(
    keyword: String,
    onClick: () -> Unit,
    onRemove: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(50),
        color = Color.White,
        shadowElevation = 1.dp,
    ) {
        Row(
            modifier = Modifier.padding(start = 12.dp, end = 6.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.History,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = keyword,
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .clickable(onClick = onClick)
                    .padding(horizontal = 6.dp, vertical = 6.dp),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Icon(
                imageVector = Icons.Outlined.Close,
                contentDescription = "删除「$keyword」",
                modifier = Modifier
                    .clip(CircleShape)
                    .clickable(onClick = onRemove)
                    .padding(4.dp)
                    .size(14.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun SearchActionRow(
    keyword: String,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
        shape = RoundedCornerShape(20.dp),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Search,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
            Spacer(modifier = Modifier.size(10.dp))
            Text(
                text = "搜索「$keyword」",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun PlaceResultCard(
    place: PlaceSummary,
    distanceText: String?,
    onClick: () -> Unit,
    onAdd: () -> Unit,
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
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PlaceCoverImage(
                imageUrl = place.displayCoverImageUrl,
                fallbackImageUrls = place.displayImageUrls,
                placeName = place.name,
                category = place.category,
                modifier = Modifier.size(66.dp),
                shape = RoundedCornerShape(16.dp),
            )
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(
                    text = place.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = listOfNotNull(place.metaText.takeIf { it.isNotBlank() }, distanceText)
                        .joinToString(" · "),
                    color = Color(0xFF1F7AE0),
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = place.displayAddress,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Surface(color = Color.White, shape = CircleShape, shadowElevation = 2.dp) {
                IconButton(onClick = onAdd) {
                    Icon(Icons.Outlined.Add, contentDescription = "加入计划")
                }
            }
        }
    }
}

@Composable
private fun LoadingBlock() {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 48.dp),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator()
    }
}

@Composable
private fun NoticeCard(text: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFFFFF4E0),
        shape = RoundedCornerShape(18.dp),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            color = Color(0xFF8A5A00),
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun SearchStateCard(text: String) {
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

@Composable
private fun SuggestionItem(
    suggestion: PlaceSuggestion,
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
                    imageVector = Icons.Outlined.LocationOn,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(modifier = Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = suggestion.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = listOfNotNull(suggestion.district, suggestion.address).joinToString(" · ")
                        .ifBlank { if (suggestion.hasLocation) "高德地点" else "点击后按名称继续搜索" },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** 文本搜索的结果没有距离字段，这里用当前定位自己算一个粗略直线距离。 */
private fun distanceText(place: PlaceSummary, latitude: Double?, longitude: Double?): String? {
    val meters = place.distanceMeters
        ?: run {
            if (latitude == null || longitude == null) return null
            val placeLat = place.latitude ?: return null
            val placeLng = place.longitude ?: return null
            haversineMeters(latitude, longitude, placeLat, placeLng)
        }
    return when {
        meters < 1000 -> "距我 ${meters}m"
        else -> "距我 ${"%.1f".format(meters / 1000.0)}km"
    }
}

private fun haversineMeters(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Int {
    val earthRadius = 6371000.0
    val dLat = Math.toRadians(lat2 - lat1)
    val dLng = Math.toRadians(lng2 - lng1)
    val a = sin(dLat / 2) * sin(dLat / 2) +
        cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLng / 2) * sin(dLng / 2)
    return (earthRadius * 2 * atan2(sqrt(a), sqrt(1 - a))).roundToInt()
}
