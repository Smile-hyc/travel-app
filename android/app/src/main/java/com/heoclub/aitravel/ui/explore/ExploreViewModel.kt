package com.heoclub.aitravel.ui.explore

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.local.ExploreCityData
import com.heoclub.aitravel.data.local.SearchHistoryStore
import com.heoclub.aitravel.data.location.CurrentLocation
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary
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
    private val searchHistoryStore: SearchHistoryStore? = null,
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
    private var searchJob: Job? = null
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
        val resolvedAdCode = location.adCode
            .takeIf { it.isNotBlank() }
            ?.let(::normalizeSearchCityAdCode)
            ?: previousCity.adCode
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
        val state = _uiState.value
        _uiState.update {
            it.copy(
                isPlaceSearchVisible = true,
                placeSearchQuery = "",
                placeSuggestions = emptyList(),
                placeSearchError = null,
                isLoadingSuggestions = false,
                placeSearchResults = emptyList(),
                submittedSearchKeyword = "",
                isSearchingPlaces = false,
                placeSearchNotice = null,
                searchHistory = searchHistoryStore?.load().orEmpty(),
                quickSearchWords = buildQuickSearchWords(state.selectedCity, state.selectedCategoryId),
            )
        }
    }

    fun closePlaceSearch() {
        tipsJob?.cancel()
        searchJob?.cancel()
        _uiState.update {
            it.copy(
                isPlaceSearchVisible = false,
                placeSearchQuery = "",
                placeSuggestions = emptyList(),
                placeSearchError = null,
                isLoadingSuggestions = false,
                placeSearchResults = emptyList(),
                submittedSearchKeyword = "",
                isSearchingPlaces = false,
                placeSearchNotice = null,
            )
        }
    }

    fun updatePlaceSearchQuery(query: String) {
        tipsJob?.cancel()
        searchJob?.cancel()
        val trimmed = query.trim()
        // 用户改了关键字，之前提交的搜索结果就不再对应输入框内容了。
        _uiState.update {
            it.copy(
                placeSearchQuery = query,
                placeSearchError = null,
                placeSearchNotice = null,
                isSearchingPlaces = false,
                placeSearchResults = if (trimmed == it.submittedSearchKeyword) it.placeSearchResults else emptyList(),
                submittedSearchKeyword = if (trimmed == it.submittedSearchKeyword) it.submittedSearchKeyword else "",
                placeSuggestions = if (trimmed.length < 2) emptyList() else it.placeSuggestions,
                isLoadingSuggestions = trimmed.length >= 2,
            )
        }
        if (trimmed.length < 2) {
            _uiState.update { it.copy(isLoadingSuggestions = false) }
            return
        }
        tipsJob = viewModelScope.launch {
            delay(380)
            runCatching {
                exploreRepository.getInputTips(
                    keyword = trimmed,
                    adcode = _uiState.value.selectedCity.adCode,
                    category = _uiState.value.selectedCategoryId,
                )
            }.onSuccess { suggestions ->
                _uiState.update {
                    if (it.placeSearchQuery.trim() != trimmed) return@update it
                    it.copy(
                        placeSuggestions = suggestions,
                        isLoadingSuggestions = false,
                        placeSearchError = null,
                    )
                }
            }.onFailure { throwable ->
                _uiState.update {
                    if (it.placeSearchQuery.trim() != trimmed) return@update it
                    it.copy(
                        isLoadingSuggestions = false,
                        placeSearchError = readableError(throwable),
                    )
                }
            }
        }
    }

    /**
     * 提交一次真正的关键字搜索。按“当前城市 -> 放开城市限制 -> 输入提示兜底”
     * 逐级降级，只有三级都拿不到坐标时才报错。
     */
    fun submitPlaceSearch(keyword: String = _uiState.value.placeSearchQuery) {
        val trimmed = keyword.trim()
        if (trimmed.isBlank()) return
        tipsJob?.cancel()
        searchJob?.cancel()

        val city = _uiState.value.selectedCity
        val history = searchHistoryStore?.add(trimmed)
        _uiState.update {
            it.copy(
                placeSearchQuery = trimmed,
                isSearchingPlaces = true,
                isLoadingSuggestions = false,
                placeSearchError = null,
                placeSearchNotice = null,
                placeSearchResults = emptyList(),
                submittedSearchKeyword = trimmed,
                searchHistory = history ?: it.searchHistory,
            )
        }

        searchJob = viewModelScope.launch {
            runCatching { searchWithFallback(trimmed, city) }
                .onSuccess { outcome ->
                    _uiState.update {
                        if (it.submittedSearchKeyword != trimmed) return@update it
                        it.copy(
                            isSearchingPlaces = false,
                            placeSearchResults = outcome.places,
                            placeSearchNotice = outcome.notice,
                            placeSearchError = if (outcome.places.isEmpty()) {
                                "没找到「$trimmed」，换个说法或先切换城市再试"
                            } else {
                                null
                            },
                        )
                    }
                }
                .onFailure { throwable ->
                    _uiState.update {
                        if (it.submittedSearchKeyword != trimmed) return@update it
                        it.copy(
                            isSearchingPlaces = false,
                            placeSearchError = readableError(throwable),
                        )
                    }
                }
        }
    }

    private data class SearchOutcome(
        val places: List<PlaceSummary>,
        val notice: String?,
    )

    private suspend fun searchWithFallback(keyword: String, city: ExploreCity): SearchOutcome {
        val inCity = queryMappablePlaces(keyword, city.adCode, cityLimit = true)
        if (inCity.isNotEmpty()) return SearchOutcome(inCity, null)

        val nationwide = queryMappablePlaces(keyword, city.adCode, cityLimit = false)
        if (nationwide.isNotEmpty()) {
            return SearchOutcome(
                places = nationwide,
                notice = "${city.displayName}没有匹配结果，已展示更大范围的地点",
            )
        }

        // 最后兜底：输入提示里带坐标的条目也能当成地点用，只是没有图片和评分。
        val fromTips = runCatching {
            exploreRepository.getInputTips(keyword = keyword, adcode = city.adCode, cityLimit = false)
        }.getOrDefault(emptyList())
            .mapNotNull { it.toPlaceSummary() }
            .distinctBy { it.id }
        return if (fromTips.isEmpty()) {
            SearchOutcome(emptyList(), null)
        } else {
            SearchOutcome(fromTips, "仅按名称匹配到以下地点，详细信息可能不完整")
        }
    }

    private suspend fun queryMappablePlaces(
        keyword: String,
        adcode: String,
        cityLimit: Boolean,
    ): List<PlaceSummary> {
        return exploreRepository.queryPlaces(
            adcode = adcode,
            keyword = keyword,
            category = ExploreCategories.ALL,
            page = 1,
            pageSize = 20,
            cityLimit = cityLimit,
        ).items.filter { it.hasLocation }.distinctBy { it.id }
    }

    /** 点击输入提示：带坐标的直接用，不带坐标的退化成一次关键字搜索。 */
    fun selectSuggestion(suggestion: PlaceSuggestion) {
        if (!suggestion.hasLocation) {
            submitPlaceSearch(suggestion.name)
            return
        }
        searchJob?.cancel()
        tipsJob?.cancel()
        searchJob = viewModelScope.launch {
            _uiState.update { it.copy(isSearchingPlaces = true, placeSearchError = null) }
            // 先尝试用 POI 搜索补齐图片、评分等信息，失败也不影响落点。
            val enriched = runCatching {
                queryMappablePlaces(
                    keyword = suggestion.name,
                    adcode = suggestion.adCode ?: _uiState.value.selectedCity.adCode,
                    cityLimit = false,
                )
            }.getOrDefault(emptyList())
            val fallback = suggestion.toPlaceSummary()
            val selected = enriched.firstOrNull { it.sourcePoiId == fallback?.sourcePoiId }
                ?: enriched.firstOrNull { it.name == suggestion.name }
                ?: fallback
                ?: enriched.firstOrNull()
            if (selected == null) {
                _uiState.update {
                    it.copy(isSearchingPlaces = false, placeSearchError = "这个地点暂时拿不到坐标，换一个试试")
                }
                return@launch
            }
            searchHistoryStore?.add(suggestion.name)?.let { history ->
                _uiState.update { it.copy(searchHistory = history) }
            }
            commitSearchSelection(selected, listOf(selected) + enriched)
        }
    }

    /** 用户从结果列表里选中一个地点：结果整批上图，选中的排第一并居中。 */
    fun selectSearchResult(placeId: String) {
        val results = _uiState.value.placeSearchResults
        val selected = results.firstOrNull { it.id == placeId } ?: return
        commitSearchSelection(selected, results)
    }

    private fun commitSearchSelection(selected: PlaceSummary, results: List<PlaceSummary>) {
        val ordered = (listOf(selected) + results).distinctBy { it.id }.filter { it.hasLocation }
        exploreRepository.upsertPlaces(ordered)
        _uiState.update {
            it.copy(
                isPlaceSearchVisible = false,
                isSearchingPlaces = false,
                isLoadingSuggestions = false,
                placeSearchQuery = "",
                placeSuggestions = emptyList(),
                placeSearchResults = emptyList(),
                submittedSearchKeyword = "",
                placeSearchNotice = null,
                placeSearchError = null,
                places = exploreRepository.places.value,
                selectedPlaceId = selected.id,
                placesError = null,
            )
        }
        if (selected.latitude != null && selected.longitude != null) {
            _mapCommands.tryEmit(MapCameraCommand.MoveToPlace(selected.latitude, selected.longitude))
        }
    }

    fun removeSearchHistory(keyword: String) {
        val history = searchHistoryStore?.remove(keyword) ?: return
        _uiState.update { it.copy(searchHistory = history) }
    }

    fun clearSearchHistory() {
        val history = searchHistoryStore?.clear() ?: return
        _uiState.update { it.copy(searchHistory = history) }
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

    /** 输入提示本身也带经纬度，拿不到 POI 详情时可以直接当成一个信息较少的地点。 */
    private fun PlaceSuggestion.toPlaceSummary(): PlaceSummary? {
        if (latitude == null || longitude == null) return null
        // 提示的 id 形如 amap-tip:B000A83M61，底层 POI id 与地点搜索一致，换个前缀即可去重。
        val poiId = id.substringAfter("amap-tip:", id).ifBlank { id }
        val resolvedCategory = inferCategoryFromTypeCode(typeCode)
        return PlaceSummary(
            id = "amap:$poiId",
            sourcePoiId = poiId,
            name = name,
            category = resolvedCategory,
            categoryCode = resolvedCategory,
            typeCode = typeCode,
            address = address,
            cityName = cityName,
            districtName = district,
            adCode = adCode,
            latitude = latitude,
            longitude = longitude,
        )
    }

    /** 与后端 `infer_category` 保持一致，避免同一个地点在两侧显示成不同分类。 */
    private fun inferCategoryFromTypeCode(typeCode: String?): String {
        val primary = typeCode?.split("|")?.firstOrNull()?.trim().orEmpty()
        return when {
            primary.isBlank() -> ExploreCategories.SCENIC
            primary.startsWith("0505") || primary.startsWith("0506") ||
                primary.startsWith("0507") || primary.startsWith("0508") -> ExploreCategories.DRINK
            primary.startsWith("05") -> ExploreCategories.FOOD
            primary.startsWith("06") -> ExploreCategories.SHOPPING
            primary.startsWith("10") -> ExploreCategories.LODGING
            primary.startsWith("15") -> ExploreCategories.TRANSPORT
            else -> ExploreCategories.SCENIC
        }
    }

    /** 热门词跟着当前城市和分类走，而不是写死几个城市。 */
    private fun buildQuickSearchWords(city: ExploreCity, categoryId: String): List<String> {
        val categoryWords = when (categoryId) {
            ExploreCategories.FOOD -> listOf("本地特色菜", "老字号", "小吃街", "火锅")
            ExploreCategories.DRINK -> listOf("咖啡馆", "奶茶", "茶馆", "清吧")
            ExploreCategories.SHOPPING -> listOf("购物中心", "特产", "步行街", "书店")
            ExploreCategories.LODGING -> listOf("酒店", "民宿", "青年旅舍", "温泉酒店")
            ExploreCategories.TRANSPORT -> listOf("火车站", "机场", "地铁站", "汽车站")
            else -> listOf("景点", "博物馆", "公园", "古城")
        }
        val cityName = normalizeCityName(city.displayName)
        val cityWords = if (cityName.isBlank()) {
            emptyList()
        } else {
            listOf("${cityName}必去", "${cityName}地标")
        }
        return (cityWords + categoryWords).distinct().take(8)
    }

    class Factory(
        private val exploreRepository: ExploreRepository,
        private val searchHistoryStore: SearchHistoryStore? = null,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(ExploreViewModel::class.java)) {
                return ExploreViewModel(exploreRepository, searchHistoryStore) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}

internal fun normalizeSearchCityAdCode(adCode: String): String {
    val normalized = adCode.trim()
    if (normalized.length != 6 || normalized.any { !it.isDigit() }) return normalized
    if (normalized.endsWith("00")) {
        return when (normalized) {
            "110100" -> "110000"
            "120100" -> "120000"
            "310100" -> "310000"
            "500100" -> "500000"
            else -> normalized
        }
    }
    return if (normalized.take(2) in setOf("11", "12", "31", "50")) {
        normalized.take(2) + "0000"
    } else {
        normalized.take(4) + "00"
    }
}
