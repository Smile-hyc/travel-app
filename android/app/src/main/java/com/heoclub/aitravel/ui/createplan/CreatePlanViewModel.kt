package com.heoclub.aitravel.ui.createplan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.local.ExploreCityData
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.ReverseGeocodePoint
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.Collator
import java.util.Locale

class CreatePlanViewModel(
    private val travelPlanRepository: TravelPlanRepository,
    private val exploreRepository: ExploreRepository,
) : ViewModel() {
    private val _citySuggestions = MutableStateFlow<List<ExploreCity>>(emptyList())
    val citySuggestions: StateFlow<List<ExploreCity>> = _citySuggestions.asStateFlow()
    private var citySearchJob: Job? = null
    private val _arrivalSuggestions = MutableStateFlow<List<PlaceSuggestion>>(emptyList())
    val arrivalSuggestions: StateFlow<List<PlaceSuggestion>> = _arrivalSuggestions.asStateFlow()
    private val _departureSuggestions = MutableStateFlow<List<PlaceSuggestion>>(emptyList())
    val departureSuggestions: StateFlow<List<PlaceSuggestion>> = _departureSuggestions.asStateFlow()
    private var arrivalSearchJob: Job? = null
    private var departureSearchJob: Job? = null
    private val _hotelSuggestions = MutableStateFlow<List<PlaceSuggestion>>(emptyList())
    val hotelSuggestions: StateFlow<List<PlaceSuggestion>> = _hotelSuggestions.asStateFlow()
    private val _hotelSuggestionTarget = MutableStateFlow<String?>(null)
    val hotelSuggestionTarget: StateFlow<String?> = _hotelSuggestionTarget.asStateFlow()
    private var hotelSearchJob: Job? = null

    fun searchCities(query: String) {
        citySearchJob?.cancel()
        if (query.trim().length < 2) {
            _citySuggestions.value = emptyList()
            return
        }
        citySearchJob = viewModelScope.launch {
            delay(280)
            val local = ExploreCityData.searchCities(query)
            val remote = runCatching { exploreRepository.searchCities(query) }.getOrDefault(emptyList())
            _citySuggestions.value = sortDestinationSuggestions(
                query,
                mergeDestinationSuggestions(remote, local),
            ).take(30)
        }
    }

    fun clearCitySuggestions() {
        citySearchJob?.cancel()
        _citySuggestions.value = emptyList()
    }

    fun resolveDestinationCity(query: String, onResult: (ExploreCity?) -> Unit) {
        citySearchJob?.cancel()
        val keyword = query.trim()
        if (keyword.isBlank()) {
            onResult(null)
            return
        }
        val cached = _citySuggestions.value.firstOrNull { city ->
            city.name.equals(keyword, ignoreCase = true) ||
                city.name.removeSuffix("市").equals(keyword.removeSuffix("市"), ignoreCase = true)
        }
        if (cached != null) {
            _citySuggestions.value = emptyList()
            onResult(cached)
            return
        }
        citySearchJob = viewModelScope.launch {
            val cities = sortDestinationSuggestions(
                keyword,
                mergeDestinationSuggestions(
                    runCatching { exploreRepository.searchCities(keyword) }.getOrDefault(emptyList()),
                    ExploreCityData.searchCities(keyword),
                ),
            )
            val resolved = cities.firstOrNull { city ->
                city.name.equals(keyword, ignoreCase = true) ||
                    city.name.removeSuffix("市").equals(keyword.removeSuffix("市"), ignoreCase = true)
            } ?: cities.firstOrNull()
            _citySuggestions.value = emptyList()
            onResult(resolved)
        }
    }

    fun searchStations(query: String, adCode: String?, arrival: Boolean) {
        val target = if (arrival) _arrivalSuggestions else _departureSuggestions
        val previousJob = if (arrival) arrivalSearchJob else departureSearchJob
        previousJob?.cancel()
        val keyword = query.trim()
        if (keyword.isBlank()) {
            target.value = emptyList()
            return
        }
        target.value = emptyList()
        if (keyword.length < 2 || adCode.isNullOrBlank()) return
        val job = viewModelScope.launch {
            delay(380)
            val remote = runCatching {
                exploreRepository.getInputTips(
                    keyword = keyword,
                    adcode = adCode,
                    category = "transport",
                    cityLimit = true,
                )
            }.getOrDefault(emptyList())
            target.value = remote
                .filter { belongsToDestinationCity(it.adCode, adCode) }
                .distinctBy { it.id }
                .sortedWith(transportSuggestionComparator(keyword))
                .take(20)
        }
        if (arrival) arrivalSearchJob = job else departureSearchJob = job
    }

    fun searchHotels(query: String, adCode: String?, targetKey: String) {
        hotelSearchJob?.cancel()
        _hotelSuggestionTarget.value = targetKey
        if (query.trim().length < 2 || adCode.isNullOrBlank()) {
            _hotelSuggestions.value = emptyList()
            return
        }
        hotelSearchJob = viewModelScope.launch {
            delay(240)
            _hotelSuggestions.value = runCatching {
                exploreRepository.getInputTips(
                    keyword = query,
                    adcode = adCode,
                    category = "lodging",
                    cityLimit = true,
                )
            }.getOrDefault(emptyList())
                .filter { belongsToDestinationCity(it.adCode, adCode) }
                .take(6)
        }
    }

    fun clearHotelSuggestions() {
        hotelSearchJob?.cancel()
        _hotelSuggestions.value = emptyList()
        _hotelSuggestionTarget.value = null
    }

    fun clearStationSuggestions(arrival: Boolean) {
        if (arrival) {
            arrivalSearchJob?.cancel()
            _arrivalSuggestions.value = emptyList()
        } else {
            departureSearchJob?.cancel()
            _departureSuggestions.value = emptyList()
        }
    }

    fun reverseGeocodePoint(
        latitude: Double,
        longitude: Double,
        onResult: (Result<ReverseGeocodePoint>) -> Unit,
    ) {
        viewModelScope.launch {
            onResult(
                runCatching {
                    exploreRepository.reverseGeocode(
                        latitude = latitude,
                        longitude = longitude,
                        radius = 50,
                    )
                },
            )
        }
    }

    fun createPlan(
        destination: String,
        dateRange: String,
        preferences: List<String>,
        dayCount: Int,
    ): TravelPlan {
        return travelPlanRepository.createPlan(
            destination = destination,
            dateRange = dateRange,
            preferences = preferences,
            dayCount = dayCount,
        )
    }

    class Factory(
        private val travelPlanRepository: TravelPlanRepository,
        private val exploreRepository: ExploreRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(CreatePlanViewModel::class.java)) {
                return CreatePlanViewModel(travelPlanRepository, exploreRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}

internal fun belongsToDestinationCity(candidateAdCode: String?, destinationAdCode: String?): Boolean {
    if (candidateAdCode.isNullOrBlank() || destinationAdCode.isNullOrBlank()) return false
    val candidate = candidateAdCode.trim()
    val destination = destinationAdCode.trim()
    return when {
        destination.endsWith("0000") -> candidate.take(2) == destination.take(2)
        destination.endsWith("00") -> candidate.take(4) == destination.take(4)
        else -> candidate == destination
    }
}

internal fun transportSuggestionComparator(query: String): Comparator<PlaceSuggestion> =
    compareBy<PlaceSuggestion>(
        { suggestion -> if (query.isNotBlank() && suggestion.name.contains(query.trim())) 0 else 1 },
        { suggestion -> transportHubPriority(suggestion) },
        { suggestion -> suggestion.name },
    )

internal fun transportHubPriority(suggestion: PlaceSuggestion): Int {
    val text = "${suggestion.name} ${suggestion.typeCode.orEmpty()}"
    return when {
        suggestion.name.endsWith("机场") -> 0
        suggestion.name.endsWith("站") && !text.contains("地铁") && !text.contains("公交") -> 0
        suggestion.name.contains("航站楼") -> 1
        else -> 2
    }
}

internal fun PlaceSuggestion.matchesTransportHubQuery(query: String): Boolean {
    val keyword = query.trim().replace(" ", "")
    if (keyword.isBlank()) return true
    val searchable = listOfNotNull(name, district, address, cityName)
        .joinToString("")
        .replace(" ", "")
    return searchable.contains(keyword, ignoreCase = true)
}

private val provincialCapitalAdCodes = setOf(
    "110000", "120000", "130100", "140100", "150100", "210100", "220100", "230100",
    "310000", "320100", "330100", "340100", "350100", "360100", "370100", "410100",
    "420100", "430100", "440100", "450100", "460100", "500000", "510100", "520100",
    "530100", "540100", "610100", "620100", "630100", "640100", "650100",
)

private val municipalityAdCodePrefixes = setOf("11", "12", "31", "50")

internal fun isDirectMunicipality(city: ExploreCity): Boolean =
    city.adCode.take(2) in municipalityAdCodePrefixes

internal fun isProvincialCapital(city: ExploreCity): Boolean =
    city.adCode in provincialCapitalAdCodes

internal fun cityRegionLabel(city: ExploreCity): String = when {
    isDirectMunicipality(city) -> "直辖市"
    isProvincialCapital(city) -> "省会 · ${city.provinceName}"
    city.provinceName.isNotBlank() && city.provinceName != city.name -> city.provinceName
    else -> "地级市"
}

internal fun sortDestinationSuggestions(
    query: String,
    suggestions: List<ExploreCity>,
): List<ExploreCity> {
    val normalized = normalizeRegionName(query)
    val provinces = suggestions.map { it.provinceName }.filter { it.isNotBlank() }.distinct()
    val provinceQuery = provinces.singleOrNull()?.let { province ->
        normalizeRegionName(province) == normalized
    } == true
    val collator = Collator.getInstance(Locale.CHINA)
    return suggestions.sortedWith { left, right ->
        val leftExact = left.name.removeSuffix("市").equals(normalized, ignoreCase = true)
        val rightExact = right.name.removeSuffix("市").equals(normalized, ignoreCase = true)
        val leftRank = when {
            leftExact -> 0
            provinceQuery && isProvincialCapital(left) -> 1
            else -> 2
        }
        val rightRank = when {
            rightExact -> 0
            provinceQuery && isProvincialCapital(right) -> 1
            else -> 2
        }
        if (leftRank != rightRank) leftRank - rightRank else collator.compare(left.name, right.name)
    }
}

private fun normalizeRegionName(value: String): String = value.trim()
    .removeSuffix("特别行政区")
    .removeSuffix("自治区")
    .removeSuffix("省")
    .removeSuffix("市")

internal fun mergeDestinationSuggestions(
    remote: List<ExploreCity>,
    local: List<ExploreCity>,
): List<ExploreCity> = (remote + local)
    .groupBy { destinationAdministrativeKey(it.adCode) }
    .values
    .map { matches ->
        val selected = matches.maxByOrNull { city ->
            when {
                city.id.startsWith("amap-city:") && city.name == canonicalMunicipalityName(city.adCode) -> 3
                isDirectMunicipality(city) -> 2
                city.provinceName.isNotBlank() && city.provinceName != city.name -> 2
                else -> 1
            }
        } ?: matches.first()
        canonicalMunicipalityName(selected.adCode)?.let { canonical ->
            selected.copy(name = canonical, displayName = canonical, provinceName = canonical)
        } ?: selected
    }

private fun canonicalMunicipalityName(adCode: String): String? = when (adCode.take(2)) {
    "11" -> "北京市"
    "12" -> "天津市"
    "31" -> "上海市"
    "50" -> "重庆市"
    else -> null
}

private fun destinationAdministrativeKey(adCode: String): String =
    canonicalMunicipalityName(adCode)?.let { "${adCode.take(2)}0000" } ?: adCode

