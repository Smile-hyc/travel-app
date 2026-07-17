package com.heoclub.aitravel.ui.createplan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.ExploreCity
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

