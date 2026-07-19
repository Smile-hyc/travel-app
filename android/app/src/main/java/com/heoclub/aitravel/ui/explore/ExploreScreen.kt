package com.heoclub.aitravel.ui.explore

import android.widget.Toast
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.location.CurrentLocationUiState
import com.heoclub.aitravel.data.model.ExploreCategory
import com.heoclub.aitravel.data.model.PlaceCollection
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.ui.components.PlaceCoverImage

@Composable
fun ExploreScreen(
    viewModel: ExploreViewModel,
    mapViewHolder: ExploreMapViewHolder,
    locationState: CurrentLocationUiState,
    requestedDestination: String? = null,
    destinationRequestKey: Long? = null,
    onLocate: () -> Unit,
    onOpenPlace: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    var panelExpanded by remember { mutableFloatStateOf(0f) }
    val expanded = panelExpanded > 0.5f

    LaunchedEffect(destinationRequestKey) {
        requestedDestination
            ?.takeIf(String::isNotBlank)
            ?.let(viewModel::openDestinationCity)
    }
    LaunchedEffect(locationState.location?.updateSequence, destinationRequestKey) {
        if (requestedDestination.isNullOrBlank()) {
            locationState.location?.let(viewModel::useCurrentLocation)
        }
    }
    LaunchedEffect(locationState.errorMessage) {
        locationState.errorMessage?.let { message ->
            Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        ExploreMap(
            places = uiState.places,
            selectedPlaceId = uiState.selectedPlaceId,
            mapCommands = viewModel.mapCommands,
            onMarkerClick = viewModel::selectPlace,
            mapViewHolder = mapViewHolder,
            currentLocation = locationState.location,
            modifier = Modifier.fillMaxSize(),
        )

        Column(
            modifier = Modifier
                .align(Alignment.TopStart)
                .fillMaxWidth()
                .background(
                    Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = 0.97f),
                            Color.White.copy(alpha = 0.62f),
                            Color.Transparent,
                        ),
                    ),
                )
                .padding(horizontal = 18.dp, vertical = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            ExploreTopBar(
                cityName = uiState.selectedCity.displayName,
                weatherText = uiState.weatherText,
                onCityClick = viewModel::openCitySelector,
                onSearchClick = viewModel::openPlaceSearch,
            )
            CategoryBar(
                categories = uiState.categories,
                selectedCategoryId = uiState.selectedCategoryId,
                onSelectCategory = viewModel::selectCategory,
            )
        }

        Surface(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .offset(y = 72.dp)
                .padding(end = 18.dp),
            shape = CircleShape,
            color = Color.White,
            shadowElevation = 4.dp,
        ) {
            IconButton(
                onClick = onLocate,
                enabled = !locationState.isLocating,
            ) {
                if (locationState.isLocating) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(21.dp),
                        strokeWidth = 2.5.dp,
                    )
                } else {
                    Icon(Icons.Outlined.MyLocation, contentDescription = "回到当前位置")
                }
            }
        }

        RecommendationPanel(
            uiState = uiState,
            expanded = expanded,
            onExpandedChange = { panelExpanded = if (it) 1f else 0f },
            onSelectPlace = viewModel::focusPlace,
            onOpenPlace = onOpenPlace,
            onAddPlace = onAddPlace,
            onRetry = viewModel::retryLoadPlaces,
            onLoadMore = viewModel::loadMorePlaces,
            modifier = Modifier.align(Alignment.BottomCenter),
        )

        if (uiState.isCitySelectorVisible) {
            CitySelectorScreen(
                selectedCity = uiState.selectedCity,
                searchQuery = uiState.citySearchQuery,
                popularCities = uiState.popularCities,
                provinces = uiState.provinces,
                searchResults = uiState.citySearchResults,
                isSearching = uiState.isSearchingCities,
                searchError = uiState.citySearchError,
                expandedProvinceName = uiState.expandedProvinceName,
                onSearchQueryChange = viewModel::updateCitySearchQuery,
                onCitySelected = viewModel::selectCity,
                onProvinceToggle = viewModel::toggleProvince,
                onDismiss = viewModel::closeCitySelector,
            )
        }

        if (uiState.isPlaceSearchVisible) {
            PlaceSearchScreen(
                cityName = uiState.selectedCity.displayName,
                query = uiState.placeSearchQuery,
                suggestions = uiState.placeSuggestions,
                loading = uiState.isLoadingSuggestions,
                error = uiState.placeSearchError,
                onQueryChange = viewModel::updatePlaceSearchQuery,
                onSuggestionClick = viewModel::selectSuggestion,
                onDismiss = viewModel::closePlaceSearch,
            )
        }
    }
}

@Composable
private fun ExploreTopBar(
    cityName: String,
    weatherText: String,
    onCityClick: () -> Unit,
    onSearchClick: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Surface(
            modifier = Modifier.fillMaxWidth().height(58.dp),
            color = Color.White.copy(alpha = 0.96f),
            shape = RoundedCornerShape(30.dp),
            shadowElevation = 5.dp,
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(
                    modifier = Modifier
                        .clip(RoundedCornerShape(24.dp))
                        .clickable(onClick = onCityClick)
                        .padding(horizontal = 4.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = cityName,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF071A3D),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Icon(Icons.Outlined.KeyboardArrowDown, contentDescription = "切换城市", tint = Color(0xFF071A3D))
                }
                Row(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(24.dp))
                        .clickable(onClick = onSearchClick)
                        .padding(start = 12.dp, end = 6.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "搜索地点/目的地",
                        modifier = Modifier.weight(1f),
                        color = Color(0xFF9AA6B2),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Icon(Icons.Outlined.Search, contentDescription = "搜索地点", tint = Color(0xFF071A3D))
                }
            }
        }
        Text(
            text = weatherText,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(start = 6.dp),
        )
    }
}

@Composable
private fun CategoryBar(
    categories: List<ExploreCategory>,
    selectedCategoryId: String,
    onSelectCategory: (String) -> Unit,
) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        items(categories, key = { it.id }) { category ->
            val selected = category.id == selectedCategoryId
            Surface(
                onClick = { onSelectCategory(category.id) },
                color = if (selected) Color.White else Color.White.copy(alpha = 0.88f),
                shape = RoundedCornerShape(50),
                shadowElevation = if (selected) 5.dp else 1.dp,
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(category.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Text(
                        text = category.title,
                        modifier = Modifier.padding(start = 8.dp),
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

@Composable
private fun RecommendationPanel(
    uiState: ExploreUiState,
    expanded: Boolean,
    onExpandedChange: (Boolean) -> Unit,
    onSelectPlace: (String) -> Unit,
    onOpenPlace: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
    onRetry: () -> Unit,
    onLoadMore: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var dragTotal by remember { mutableFloatStateOf(0f) }
    val panelHeight by animateDpAsState(
        targetValue = if (expanded) 560.dp else 232.dp,
        label = "recommendation-panel-height",
    )
    val selectedPlace = uiState.places.firstOrNull { it.id == uiState.selectedPlaceId } ?: uiState.places.firstOrNull()

    Card(
        modifier = modifier
            .fillMaxWidth()
            .height(panelHeight)
            .pointerInput(expanded) {
                detectVerticalDragGestures(
                    onDragStart = { dragTotal = 0f },
                    onVerticalDrag = { _, dragAmount -> dragTotal += dragAmount },
                    onDragEnd = {
                        when {
                            dragTotal < -36f -> onExpandedChange(true)
                            dragTotal > 36f -> onExpandedChange(false)
                        }
                    },
                )
            },
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp).animateContentSize(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PanelHandle(expanded = expanded, onToggle = { onExpandedChange(!expanded) })
            Row(
                modifier = Modifier.fillMaxWidth().clickable { onExpandedChange(!expanded) },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "为你发现真实地点 ✨",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF071A3D),
                )
                Icon(
                    imageVector = if (expanded) Icons.Outlined.KeyboardArrowDown else Icons.Outlined.KeyboardArrowUp,
                    contentDescription = if (expanded) "收起" else "展开",
                    tint = MaterialTheme.colorScheme.primary,
                )
            }

            when {
                uiState.isLoadingPlaces && uiState.places.isEmpty() -> LoadingCard()
                uiState.placesError != null && uiState.places.isEmpty() -> ErrorCard(uiState.placesError, onRetry)
                uiState.places.isEmpty() -> EmptyCard(onRetry)
                expanded -> PlacesList(
                    collections = uiState.collections,
                    places = uiState.places,
                    selectedPlaceId = uiState.selectedPlaceId,
                    hasMore = uiState.hasMore,
                    isLoadingMore = uiState.isLoadingMore,
                    onSelectPlace = onSelectPlace,
                    onOpenPlace = onOpenPlace,
                    onAddPlace = onAddPlace,
                    onLoadMore = onLoadMore,
                )
                selectedPlace != null -> CollapsedPlacePreview(
                    place = selectedPlace,
                    onClick = {
                        onSelectPlace(selectedPlace.id)
                        onOpenPlace(selectedPlace.id)
                    },
                    onAdd = { onAddPlace(selectedPlace) },
                )
            }
        }
    }
}

@Composable
private fun PlacesList(
    collections: List<PlaceCollection>,
    places: List<PlaceSummary>,
    selectedPlaceId: String?,
    hasMore: Boolean,
    isLoadingMore: Boolean,
    onSelectPlace: (String) -> Unit,
    onOpenPlace: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
    onLoadMore: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (collections.isNotEmpty()) {
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(collections, key = { it.id }) { collection ->
                        CollectionCard(collection = collection)
                    }
                }
            }
        }
        item {
            Text("热门地点", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }
        items(places, key = { it.id }) { place ->
            PlaceListItem(
                place = place,
                selected = place.id == selectedPlaceId,
                onClick = {
                    onSelectPlace(place.id)
                    onOpenPlace(place.id)
                },
                onAdd = { onAddPlace(place) },
            )
        }
        if (hasMore) {
            item {
                OutlinedButton(
                    onClick = onLoadMore,
                    enabled = !isLoadingMore,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (isLoadingMore) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(modifier = Modifier.size(8.dp))
                    }
                    Text(if (isLoadingMore) "加载中" else "加载更多")
                }
            }
        }
    }
}

@Composable
private fun PanelHandle(expanded: Boolean, onToggle: () -> Unit) {
    Box(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onToggle),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(width = 48.dp, height = 5.dp)
                .clip(RoundedCornerShape(50))
                .background(if (expanded) Color(0xFFC6CEDB) else Color(0xFFD8DEE8)),
        )
    }
}

@Composable
private fun LoadingCard() {
    Box(modifier = Modifier.fillMaxWidth().height(96.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun EmptyCard(onRetry: () -> Unit) {
    StateCard(text = "未找到相关地点", buttonText = "重新加载", onClick = onRetry)
}

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    StateCard(text = error, buttonText = "重试", onClick = onRetry)
}

@Composable
private fun StateCard(text: String, buttonText: String, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFFF8FBFF),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(onClick = onClick) {
                Icon(Icons.Outlined.Refresh, contentDescription = null)
                Spacer(modifier = Modifier.size(8.dp))
                Text(buttonText)
            }
        }
    }
}

@Composable
private fun CollectionCard(collection: PlaceCollection) {
    Box(
        modifier = Modifier
            .size(width = 168.dp, height = 96.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(Brush.linearGradient(listOf(Color(0xFF7DBDFF), Color(0xFF1F7AE0))))
            .padding(14.dp),
    ) {
        Column(modifier = Modifier.align(Alignment.BottomStart)) {
            Text(collection.title, color = Color.White, fontWeight = FontWeight.Bold)
            Text(collection.subtitle, color = Color.White.copy(alpha = 0.86f), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun CollapsedPlacePreview(
    place: PlaceSummary,
    onClick: () -> Unit,
    onAdd: () -> Unit,
) {
    PlaceCard(place = place, selected = true, compact = true, onClick = onClick, onAdd = onAdd)
}

@Composable
private fun PlaceListItem(
    place: PlaceSummary,
    selected: Boolean,
    onClick: () -> Unit,
    onAdd: () -> Unit,
) {
    PlaceCard(place = place, selected = selected, compact = false, onClick = onClick, onAdd = onAdd)
}

@Composable
private fun PlaceCard(
    place: PlaceSummary,
    selected: Boolean,
    compact: Boolean,
    onClick: () -> Unit,
    onAdd: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = if (selected) Color(0xFFEAF5FF) else Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = if (selected) 3.dp else 0.dp),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            PlaceCoverImage(
                imageUrl = place.displayCoverImageUrl,
                placeName = place.name,
                modifier = Modifier.size(if (compact) 58.dp else 74.dp),
                shape = RoundedCornerShape(16.dp),
            )
            Column(
                modifier = Modifier.weight(1f).padding(horizontal = 12.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Text(place.name, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                Text(place.metaText, color = Color(0xFF1F7AE0), style = MaterialTheme.typography.bodySmall, maxLines = 1)
                Text(
                    place.displayAddress,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = if (compact) 1 else 2,
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
