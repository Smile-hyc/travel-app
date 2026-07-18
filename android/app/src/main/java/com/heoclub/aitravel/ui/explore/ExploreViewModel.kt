package com.heoclub.aitravel.ui.explore

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.local.ExploreCityData
import com.heoclub.aitravel.data.location.CurrentLocation
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.repository.ExploreRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

class ExploreViewModel(
    private val exploreRepository: ExploreRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(
        ExploreUiState(
            selectedCity = ExploreCityData.defaultCity,
            popularCities = ExploreCityData.popularCities,
            provinces = ExploreCityData.provinces,
            categories = exploreRepository.categories,
            selectedCategoryId = ExploreCategories.SCENIC,
            collections = exploreRepository.collections,
        ),
    )
    val uiState: StateFlow<ExploreUiState> = _uiState.asStateFlow()

    private val _mapCommands = MutableSharedFlow<MapCameraCommand>(extraBufferCapacity = 1)
    val mapCommands: SharedFlow<MapCameraCommand> = _mapCommands.asSharedFlow()

    private var loadPlacesJob: Job? = null
    private var tipsJob: Job? = null
    private var citySearchJob: Job? = null
    private var destinationJob: Job? = null
    private var weatherJob: Job? = null
    private var loadPlacesRequestId: Long = 0L
    private var weatherRequestId: Long = 0L

    init {
        loadWeather()
        loadPlaces(resetPage = true)
    }

    fun selectCategory(categoryId: String) {
        if (categoryId == _uiState.value.selectedCategoryId) return
        _uiState.update {
            it.copy(
                selectedCategoryId = categoryId,
                selectedPlaceId = null,
                currentPage = 1,
                hasMore = false,
                placesError = null,
                weatherText = "天气加载中",
            )
        }
        loadPlaces(resetPage = true)
    }

    fun selectPlace(placeId: String) {
        _uiState.update { it.copy(selectedPlaceId = placeId) }
    }

    fun focusPlace(placeId: String) {
        val place = _uiState.value.places.firstOrNull { it.id == placeId }
        _uiState.update { it.copy(selectedPlaceId = placeId) }
        if (place?.latitude != null && place.longitude != null) {
            _mapCommands.tryEmit(MapCameraCommand.MoveToPlace(place.latitude, place.longitude))
        }
    }

    fun retryLoadPlaces() {
        loadPlaces(resetPage = _uiState.value.places.isEmpty())
    }

    fun loadMorePlaces() {
        val state = _uiState.value
        if (!state.hasMore || state.isLoadingMore || state.isLoadingPlaces) return
        loadPlaces(resetPage = false)
    }

    fun toggleFavorite(placeId: String) {
        exploreRepository.toggleFavorite(placeId)
        _uiState.update { it.copy(places = exploreRepository.places.value) }
    }

    fun openCitySelector() {
        _uiState.update { it.copy(isCitySelectorVisible = true) }
    }

    fun closeCitySelector() {
        citySearchJob?.cancel()
        _uiState.update {
            it.copy(
                isCitySelectorVisible = false,
                citySearchQuery = "",
                expandedProvinceName = null,
                isSearchingCities = false,
                citySearchError = null,
            )
        }
    }

    fun updateCitySearchQuery(query: String) {
        citySearchJob?.cancel()
        val localResults = ExploreCityData.searchCities(query)
        _uiState.update {
            it.copy(
                citySearchQuery = query,
                citySearchResults = localResults,
                isSearchingCities = query.trim().length >= 2,
                citySearchError = null,
            )
        }
        if (query.trim().length < 2) {
            _uiState.update { it.copy(isSearchingCities = false) }
            return
        }
        citySearchJob = viewModelScope.launch {
            delay(320)
            runCatching {
                exploreRepository.searchCities(query)
            }.onSuccess { remoteResults ->
                val mergedResults = (localResults + remoteResults)
                    .distinctBy { "${it.adCode}:${it.displayName}" }
                _uiState.update {
                    if (it.citySearchQuery == query) {
                        it.copy(
                            citySearchResults = mergedResults,
                            isSearchingCities = false,
                            citySearchError = null,
                        )
                    } else {
                        it
                    }
                }
            }.onFailure { throwable ->
                _uiState.update {
                    if (it.citySearchQuery == query) {
                        it.copy(
                            isSearchingCities = false,
                            citySearchError = readableError(throwable),
                        )
                    } else {
                        it
                    }
                }
            }
        }
    }

    fun toggleProvince(provinceName: String) {
        _uiState.update {
            it.copy(
                expandedProvinceName = if (it.expandedProvinceName == provinceName) null else provinceName,
            )
        }
    }

    fun useCurrentLocation(location: CurrentLocation) {
        val previousCity = _uiState.value.selectedCity
        val resolvedAdCode = location.adCode.ifBlank { previousCity.adCode }
        val locatedCity = ExploreCity(
            id = "located-${resolvedAdCode.ifBlank { location.cityName }}",
            name = location.cityName,
            displayName = location.cityName,
            provinceName = location.provinceName,
            adCode = resolvedAdCode,
            latitude = location.latitude,
            longitude = location.longitude,
            defaultZoom = 14.2f,
        )
        val cityChanged = previousCity.adCode != locatedCity.adCode ||
            previousCity.displayName != locatedCity.displayName
        _uiState.update {
            it.copy(
                selectedCity = locatedCity,
                selectedPlaceId = if (cityChanged) null else it.selectedPlaceId,
                currentPage = if (cityChanged) 1 else it.currentPage,
                hasMore = if (cityChanged) false else it.hasMore,
                placesError = if (cityChanged) null else it.placesError,
            )
        }
        if (cityChanged) {
            loadWeather()
            loadPlaces(resetPage = true)
        }
    }

    fun selectCity(city: ExploreCity) {
        citySearchJob?.cancel()
        _uiState.update {
            it.copy(
                selectedCity = city,
                isCitySelectorVisible = false,
                citySearchQuery = "",
                citySearchResults = emptyList(),
                isSearchingCities = false,
                citySearchError = null,
                expandedProvinceName = null,
                selectedPlaceId = null,
                currentPage = 1,
                hasMore = false,
                placesError = null,
            )
        }
        _mapCommands.tryEmit(
            MapCameraCommand.MoveToCity(
                latitude = city.latitude,
                longitude = city.longitude,
                zoom = city.defaultZoom,
            ),
        )
        loadWeather()
        loadPlaces(resetPage = true)
    }

    fun openDestinationCity(destination: String) {
        val query = destination.trim()
        if (query.isBlank()) return

        destinationJob?.cancel()
        val localCity = bestMatchingCity(query, ExploreCityData.allCities)
        if (localCity != null) {
            selectCity(localCity)
            return
        }

        destinationJob = viewModelScope.launch {
            runCatching { exploreRepository.searchCities(query) }
                .getOrNull()
                ?.let { cities -> bestMatchingCity(query, cities) }
                ?.let(::selectCity)
        }
    }

    fun openPlaceSearch() {
        _uiState.update {
            it.copy(
                isPlaceSearchVisible = true,
                placeSearchQuery = "",
                placeSuggestions = emptyList(),
                placeSearchError = null,
                isLoadingSuggestions = false,
            )
        }
    }

    fun closePlaceSearch() {
        tipsJob?.cancel()
        _uiState.update {
            it.copy(
                isPlaceSearchVisible = false,
                placeSearchQuery = "",
                placeSuggestions = emptyList(),
                placeSearchError = null,
                isLoadingSuggestions = false,
            )
        }
    }

    fun updatePlaceSearchQuery(query: String) {
        tipsJob?.cancel()
        _uiState.update {
            it.copy(
                placeSearchQuery = query,
                placeSearchError = null,
                placeSuggestions = if (query.trim().length < 2) emptyList() else it.placeSuggestions,
                isLoadingSuggestions = query.trim().length >= 2,
            )
        }
        if (query.trim().length < 2) {
            _uiState.update { it.copy(isLoadingSuggestions = false) }
            return
        }
        tipsJob = viewModelScope.launch {
            delay(380)
            runCatching {
                exploreRepository.getInputTips(
                    keyword = query,
                    adcode = _uiState.value.selectedCity.adCode,
                    category = _uiState.value.selectedCategoryId,
                )
            }.onSuccess { suggestions ->
                _uiState.update {
                    it.copy(
                        placeSuggestions = suggestions,
                        isLoadingSuggestions = false,
                        placeSearchError = null,
                    )
                }
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isLoadingSuggestions = false,
                        placeSearchError = readableError(throwable),
                    )
                }
            }
        }
    }

    fun selectSuggestion(suggestion: PlaceSuggestion) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoadingSuggestions = true, placeSearchError = null) }
            val result = runCatching {
                exploreRepository.searchPlaces(
                    adcode = suggestion.adCode ?: _uiState.value.selectedCity.adCode,
                    category = _uiState.value.selectedCategoryId,
                    keyword = suggestion.name,
                    page = 1,
                    pageSize = 10,
                    cityLimit = true,
                    append = false,
                )
            }
            result.onSuccess { page ->
                val selected = page.items.firstOrNull { it.hasLocation }
                if (selected == null) {
                    _uiState.update {
                        it.copy(
                            isLoadingSuggestions = false,
                            placeSearchError = "未找到带坐标的地点结果",
                        )
                    }
                    return@launch
                }
                exploreRepository.upsertPlace(selected)
                _uiState.update {
                    it.copy(
                        isPlaceSearchVisible = false,
                        isLoadingSuggestions = false,
                        placeSearchQuery = "",
                        placeSuggestions = emptyList(),
                        places = exploreRepository.places.value,
                        selectedPlaceId = selected.id,
                        placesError = null,
                    )
                }
                if (selected.latitude != null && selected.longitude != null) {
                    _mapCommands.tryEmit(MapCameraCommand.MoveToPlace(selected.latitude, selected.longitude))
                }
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isLoadingSuggestions = false,
                        placeSearchError = readableError(throwable),
                    )
                }
            }
        }
    }

    private fun loadPlaces(resetPage: Boolean) {
        loadPlacesJob?.cancel()
        val snapshot = _uiState.value
        val requestId = ++loadPlacesRequestId
        val nextPage = if (resetPage) 1 else snapshot.currentPage + 1
        loadPlacesJob = viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isLoadingPlaces = resetPage,
                    isLoadingMore = !resetPage,
                    placesError = null,
                    selectedPlaceId = if (resetPage) null else it.selectedPlaceId,
                )
            }
            runCatching {
                exploreRepository.searchPlaces(
                    adcode = snapshot.selectedCity.adCode,
                    category = snapshot.selectedCategoryId,
                    page = nextPage,
                    pageSize = 20,
                    append = !resetPage,
                )
            }.onSuccess { page ->
                if (requestId != loadPlacesRequestId) return@onSuccess
                val places = exploreRepository.places.value
                _uiState.update {
                    it.copy(
                        places = places,
                        selectedPlaceId = it.selectedPlaceId ?: places.firstOrNull()?.id,
                        isLoadingPlaces = false,
                        isLoadingMore = false,
                        placesError = null,
                        currentPage = page.page,
                        hasMore = page.hasMore,
                    )
                }
            }.onFailure { throwable ->
                if (requestId != loadPlacesRequestId) return@onFailure
                _uiState.update {
                    it.copy(
                        isLoadingPlaces = false,
                        isLoadingMore = false,
                        placesError = readableError(throwable),
                    )
                }
            }
        }
    }

    private fun loadWeather() {
        weatherJob?.cancel()
        val city = _uiState.value.selectedCity
        val requestId = ++weatherRequestId
        weatherJob = viewModelScope.launch {
            _uiState.update { it.copy(weatherText = "天气加载中") }
            runCatching {
                exploreRepository.getCityWeather(city.adCode)
            }.onSuccess { weather ->
                if (requestId != weatherRequestId) return@onSuccess
                _uiState.update { current ->
                    if (current.selectedCity.adCode == city.adCode) {
                        current.copy(weatherText = weather.text.ifBlank { "${weather.weather} ${weather.nightTemp ?: ""}°-${weather.dayTemp ?: ""}°" })
                    } else {
                        current
                    }
                }
            }.onFailure {
                if (requestId != weatherRequestId) return@onFailure
                _uiState.update { current ->
                    if (current.selectedCity.adCode == city.adCode) {
                        current.copy(weatherText = "天气暂不可用")
                    } else {
                        current
                    }
                }
            }
        }
    }

    private fun readableError(throwable: Throwable): String {
        return when (throwable) {
            is HttpException -> throwable.response()?.errorBody()?.string()?.takeIf { it.isNotBlank() }
                ?: "地点服务暂时不可用，请稍后重试"
            is IOException -> "请检查后端服务是否启动，或网络是否可用"
            else -> throwable.message?.takeIf { it.isNotBlank() } ?: "地点服务暂时不可用"
        }
    }

    private fun bestMatchingCity(query: String, cities: List<ExploreCity>): ExploreCity? {
        val normalizedQuery = normalizeCityName(query)
        return cities.firstOrNull { normalizeCityName(it.displayName) == normalizedQuery }
            ?: cities.firstOrNull { normalizeCityName(it.name) == normalizedQuery }
            ?: cities.firstOrNull {
                normalizeCityName(it.displayName).contains(normalizedQuery) ||
                    normalizedQuery.contains(normalizeCityName(it.displayName))
            }
    }

    private fun normalizeCityName(value: String): String {
        return listOf("特别行政区", "自治州", "地区", "市")
            .fold(value.trim().replace(" ", "")) { name, suffix -> name.removeSuffix(suffix) }
    }

    class Factory(
        private val exploreRepository: ExploreRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(ExploreViewModel::class.java)) {
                return ExploreViewModel(exploreRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
