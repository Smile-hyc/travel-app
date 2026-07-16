package com.heoclub.aitravel.ui.explore

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.heoclub.aitravel.data.local.ExploreCityData
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.ExploreProvince

@Composable
fun CitySelectorScreen(
    selectedCity: ExploreCity,
    searchQuery: String,
    popularCities: List<ExploreCity>,
    provinces: List<ExploreProvince>,
    searchResults: List<ExploreCity>,
    isSearching: Boolean,
    searchError: String?,
    expandedProvinceName: String?,
    onSearchQueryChange: (String) -> Unit,
    onCitySelected: (ExploreCity) -> Unit,
    onProvinceToggle: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        CitySelectorContent(
            selectedCity = selectedCity,
            searchQuery = searchQuery,
            popularCities = popularCities,
            provinces = provinces,
            searchResults = searchResults,
            isSearching = isSearching,
            searchError = searchError,
            expandedProvinceName = expandedProvinceName,
            onSearchQueryChange = onSearchQueryChange,
            onCitySelected = onCitySelected,
            onProvinceToggle = onProvinceToggle,
            onDismiss = onDismiss,
        )
    }
}

@Composable
private fun CitySelectorContent(
    selectedCity: ExploreCity,
    searchQuery: String,
    popularCities: List<ExploreCity>,
    provinces: List<ExploreProvince>,
    searchResults: List<ExploreCity>,
    isSearching: Boolean,
    searchError: String?,
    expandedProvinceName: String?,
    onSearchQueryChange: (String) -> Unit,
    onCitySelected: (ExploreCity) -> Unit,
    onProvinceToggle: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFFF2F6FA)),
    ) {
        CityMapMoodBackground()
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .imePadding()
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            CitySearchBar(
                query = searchQuery,
                onQueryChange = onSearchQueryChange,
                onBack = onDismiss,
            )
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                shape = RoundedCornerShape(30.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.96f)),
                elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
            ) {
                DomesticCityContent(
                    selectedCity = selectedCity,
                    searchQuery = searchQuery,
                    popularCities = popularCities,
                    provinces = provinces,
                    searchResults = searchResults,
                    isSearching = isSearching,
                    searchError = searchError,
                    expandedProvinceName = expandedProvinceName,
                    onCitySelected = onCitySelected,
                    onProvinceToggle = onProvinceToggle,
                )
            }
        }
    }
}

@Composable
private fun CityMapMoodBackground() {
    Canvas(modifier = Modifier.fillMaxSize()) {
        val roadColor = Color.White.copy(alpha = 0.88f)
        val minorRoadColor = Color(0xFFDDE6EF).copy(alpha = 0.75f)
        val waterColor = Color(0xFFBDEFFF).copy(alpha = 0.45f)

        repeat(7) { index ->
            val x = size.width * (index + 1) / 8f
            drawLine(
                color = minorRoadColor,
                start = Offset(x, 0f),
                end = Offset(x + size.width * 0.28f, size.height),
                strokeWidth = 3f,
            )
        }
        repeat(5) { index ->
            val y = size.height * (index + 1) / 6f
            drawLine(
                color = roadColor,
                start = Offset(0f, y),
                end = Offset(size.width, y - size.height * 0.08f),
                strokeWidth = 10f,
            )
        }
        drawCircle(waterColor, radius = size.width * 0.28f, center = Offset(size.width * 0.88f, size.height * 0.04f))
    }
}

@Composable
private fun CitySearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onBack: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(36.dp),
        color = Color.White,
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(66.dp)
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回探索页")
            }
            TextField(
                value = query,
                onValueChange = onQueryChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("搜索城市/目的地") },
                singleLine = true,
                leadingIcon = {
                    Icon(Icons.Outlined.Search, contentDescription = null)
                },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                ),
            )
        }
    }
}

@Composable
private fun DomesticCityContent(
    selectedCity: ExploreCity,
    searchQuery: String,
    popularCities: List<ExploreCity>,
    provinces: List<ExploreProvince>,
    searchResults: List<ExploreCity>,
    isSearching: Boolean,
    searchError: String?,
    expandedProvinceName: String?,
    onCitySelected: (ExploreCity) -> Unit,
    onProvinceToggle: (String) -> Unit,
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        if (searchQuery.isNotBlank()) {
            item {
                SectionTitle("搜索结果")
            }
            if (isSearching) {
                item {
                    SearchStatusText("正在从高德搜索城市...")
                }
            } else if (searchError != null && searchResults.isEmpty()) {
                item {
                    SearchStatusText("城市搜索暂时不可用，可先从热门城市或省份列表选择")
                }
            } else if (searchResults.isEmpty()) {
                item {
                    EmptySearchResult(query = searchQuery)
                }
            } else {
                items(searchResults, key = { it.id }) { city ->
                    CityListRow(
                        city = city,
                        selected = city.id == selectedCity.id,
                        onClick = { onCitySelected(city) },
                    )
                }
            }
        } else {
            item {
                SectionTitle("热门城市")
                CityChipGrid(
                    cities = popularCities,
                    selectedCity = selectedCity,
                    onCitySelected = onCitySelected,
                )
            }
            item {
                SectionTitle("按省份选择")
            }
            items(provinces, key = { it.name }) { province ->
                ProvinceCityGroup(
                    province = province,
                    expanded = province.name == expandedProvinceName,
                    selectedCity = selectedCity,
                    onProvinceToggle = onProvinceToggle,
                    onCitySelected = onCitySelected,
                )
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
        color = Color(0xFF071A3D),
        modifier = Modifier.padding(bottom = 10.dp),
    )
}

@Composable
private fun SearchStatusText(text: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(120.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = text, color = Color(0xFF6B778C))
    }
}

@Composable
private fun CityChipGrid(
    cities: List<ExploreCity>,
    selectedCity: ExploreCity,
    onCitySelected: (ExploreCity) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        cities.chunked(3).forEach { rowCities ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                rowCities.forEach { city ->
                    CityChip(
                        city = city,
                        selected = city.id == selectedCity.id,
                        onClick = { onCitySelected(city) },
                        modifier = Modifier.weight(1f),
                    )
                }
                repeat(3 - rowCities.size) {
                    Box(modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun CityChip(
    city: ExploreCity,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(48.dp)
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = if (selected) Color(0xFFE5F0FF) else Color(0xFFF6F8FB),
        border = if (selected) androidx.compose.foundation.BorderStroke(1.5.dp, Color(0xFF1F7AE0)) else null,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            Text(
                text = city.displayName,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                fontWeight = FontWeight.Bold,
                color = if (selected) Color(0xFF1F7AE0) else Color(0xFF071A3D),
            )
            if (selected) {
                Icon(
                    imageVector = Icons.Outlined.Check,
                    contentDescription = null,
                    tint = Color(0xFF1F7AE0),
                    modifier = Modifier
                        .padding(start = 4.dp)
                        .size(16.dp),
                )
            }
        }
    }
}

@Composable
private fun ProvinceCityGroup(
    province: ExploreProvince,
    expanded: Boolean,
    selectedCity: ExploreCity,
    onProvinceToggle: (String) -> Unit,
    onCitySelected: (ExploreCity) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp)
                .clip(RoundedCornerShape(18.dp))
                .clickable { onProvinceToggle(province.name) },
            shape = RoundedCornerShape(18.dp),
            color = Color(0xFFF6F8FB),
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = province.name,
                    modifier = Modifier.weight(1f),
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF071A3D),
                )
                Icon(
                    imageVector = if (expanded) Icons.Outlined.KeyboardArrowUp else Icons.Outlined.KeyboardArrowDown,
                    contentDescription = if (expanded) "收起${province.name}" else "展开${province.name}",
                )
            }
        }
        if (expanded) {
            Column(
                modifier = Modifier.padding(start = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                province.cities.forEach { city ->
                    CityListRow(
                        city = city,
                        selected = city.id == selectedCity.id,
                        onClick = { onCitySelected(city) },
                    )
                }
            }
        }
    }
}

@Composable
private fun CityListRow(
    city: ExploreCity,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(56.dp)
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = if (selected) Color(0xFFE5F0FF) else Color.White,
        border = if (selected) androidx.compose.foundation.BorderStroke(1.5.dp, Color(0xFF1F7AE0)) else null,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(if (selected) Color(0xFF1F7AE0) else Color(0xFFEAF2FF)),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = city.displayName.take(1),
                    color = if (selected) Color.White else Color(0xFF1F7AE0),
                    fontWeight = FontWeight.Bold,
                )
            }
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 12.dp),
            ) {
                Text(city.displayName, fontWeight = FontWeight.Bold, color = Color(0xFF071A3D))
                Text(city.provinceName, style = MaterialTheme.typography.bodySmall, color = Color(0xFF6B778C))
            }
            if (selected) {
                Icon(Icons.Outlined.Check, contentDescription = "当前城市", tint = Color(0xFF1F7AE0))
            }
        }
    }
}

@Composable
private fun EmptySearchResult(query: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(180.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = "没有找到“$query”相关城市",
            color = Color(0xFF6B778C),
        )
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun CitySelectorScreenPreview() {
    val selectedCity = ExploreCityData.defaultCity
    CitySelectorContent(
        selectedCity = selectedCity,
        searchQuery = "",
        popularCities = ExploreCityData.popularCities,
        provinces = ExploreCityData.provinces,
        searchResults = emptyList(),
        isSearching = false,
        searchError = null,
        expandedProvinceName = "浙江省",
        onSearchQueryChange = {},
        onCitySelected = {},
        onProvinceToggle = {},
        onDismiss = {},
    )
}
