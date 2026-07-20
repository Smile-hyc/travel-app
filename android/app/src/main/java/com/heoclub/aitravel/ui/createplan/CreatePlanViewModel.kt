package com.heoclub.aitravel.ui.createplan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

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

    fun searchCities(query: String) {
        citySearchJob?.cancel()
        if (query.trim().length < 2) {
            _citySuggestions.value = emptyList()
            return
        }
        citySearchJob = viewModelScope.launch {
            delay(280)
            _citySuggestions.value = runCatching { exploreRepository.searchCities(query) }
                .getOrDefault(emptyList())
                .take(5)
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
            val cities = runCatching { exploreRepository.searchCities(keyword) }.getOrDefault(emptyList())
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
        if (query.trim().length < 2) {
            target.value = emptyList()
            return
        }
        val job = viewModelScope.launch {
            delay(240)
            target.value = runCatching {
                exploreRepository.getInputTips(
                    keyword = query,
                    adcode = adCode,
                    category = "transport",
                    cityLimit = adCode != null,
                )
            }.getOrDefault(emptyList()).take(6)
        }
        if (arrival) arrivalSearchJob = job else departureSearchJob = job
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

