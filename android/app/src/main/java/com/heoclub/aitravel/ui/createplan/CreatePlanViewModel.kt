package com.heoclub.aitravel.ui.createplan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.TravelPlanRepository

class CreatePlanViewModel(
    private val travelPlanRepository: TravelPlanRepository,
) : ViewModel() {
    fun createPlan(
        destination: String,
        dateRange: String,
        preferences: List<String>,
    ): TravelPlan {
        return travelPlanRepository.createPlan(
            destination = destination,
            dateRange = dateRange,
            preferences = preferences,
        )
    }

    class Factory(
        private val travelPlanRepository: TravelPlanRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(CreatePlanViewModel::class.java)) {
                return CreatePlanViewModel(travelPlanRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}

