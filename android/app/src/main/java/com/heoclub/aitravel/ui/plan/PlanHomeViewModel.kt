package com.heoclub.aitravel.ui.plan

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import kotlinx.coroutines.flow.StateFlow

class PlanHomeViewModel(
    private val travelPlanRepository: TravelPlanRepository,
) : ViewModel() {
    val plans: StateFlow<List<TravelPlan>> = travelPlanRepository.plans

    fun deletePlan(planId: String): Boolean = travelPlanRepository.deletePlan(planId)

    class Factory(
        private val travelPlanRepository: TravelPlanRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(PlanHomeViewModel::class.java)) {
                return PlanHomeViewModel(travelPlanRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
