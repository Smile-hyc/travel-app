package com.heoclub.aitravel.ui.explore

import com.heoclub.aitravel.data.local.ExploreCityData
import com.heoclub.aitravel.data.model.ExploreCategory
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.ExploreProvince
import com.heoclub.aitravel.data.model.PlaceCollection
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary

data class ExploreUiState(
    val selectedCity: ExploreCity = ExploreCityData.defaultCity,
    val weatherText: String = "天气加载中",
    val isCitySelectorVisible: Boolean = false,
    val citySearchQuery: String = "",
    val expandedProvinceName: String? = null,
    val popularCities: List<ExploreCity> = emptyList(),
    val provinces: List<ExploreProvince> = emptyList(),
    val citySearchResults: List<ExploreCity> = emptyList(),
    val isSearchingCities: Boolean = false,
    val citySearchError: String? = null,
    val categories: List<ExploreCategory> = emptyList(),
    val selectedCategoryId: String = "",
    val collections: List<PlaceCollection> = emptyList(),
    val places: List<PlaceSummary> = emptyList(),
    val selectedPlaceId: String? = null,
    val isLoadingPlaces: Boolean = false,
    val isLoadingMore: Boolean = false,
    val placesError: String? = null,
    val currentPage: Int = 1,
    val hasMore: Boolean = false,
    val isPlaceSearchVisible: Boolean = false,
    val placeSearchQuery: String = "",
    val placeSuggestions: List<PlaceSuggestion> = emptyList(),
    val isLoadingSuggestions: Boolean = false,
    val placeSearchError: String? = null,
)
