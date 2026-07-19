package com.heoclub.aitravel.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.DayRoutePlan
import com.heoclub.aitravel.data.model.OptimizeDayRouteResponse
import com.heoclub.aitravel.data.model.PlanDay
import com.heoclub.aitravel.data.model.RouteModes
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.data.repository.RouteRepository
import com.heoclub.aitravel.data.repository.TravelPlanRepository
import com.heoclub.aitravel.data.repository.toRoutePlace
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.io.IOException

data class PlanDetailUiState(
    val plan: TravelPlan? = null,
    val selectedDayIndex: Int = 1,
    val routeMode: String = RouteModes.MIXED,
    val route: DayRoutePlan? = null,
    val isLoadingRoute: Boolean = false,
    val routeError: String? = null,
    val isOptimizing: Boolean = false,
    val optimization: OptimizeDayRouteResponse? = null,
) {
    val selectedDay: PlanDay?
        get() = plan?.days?.firstOrNull { it.dayIndex == selectedDayIndex }
            ?: plan?.days?.firstOrNull()
}

class PlanDetailViewModel(
    private val planId: String,
    private val travelPlanRepository: TravelPlanRepository,
    private val routeRepository: RouteRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(PlanDetailUiState())
    val uiState: StateFlow<PlanDetailUiState> = _uiState.asStateFlow()

    private var routeJob: Job? = null

    init {
        viewModelScope.launch {
            travelPlanRepository.plans.collect { plans ->
                val plan = plans.firstOrNull { it.id == planId }
                _uiState.update { state ->
                    state.copy(
                        plan = plan,
                        selectedDayIndex = state.selectedDayIndex.coerceAtMost(
                            plan?.days?.size?.coerceAtLeast(1) ?: 1,
                        ),
                    )
                }
                loadRoute()
            }
        }
    }

    fun selectDay(dayIndex: Int) {
        if (dayIndex == _uiState.value.selectedDayIndex) return
        _uiState.update {
            it.copy(
                selectedDayIndex = dayIndex,
                route = null,
                routeError = null,
                optimization = null,
            )
        }
        loadRoute()
    }

    fun selectMode(mode: String) {
        if (mode == _uiState.value.routeMode) return
        _uiState.update {
            it.copy(
                routeMode = mode,
                route = null,
                routeError = null,
                optimization = null,
            )
        }
        loadRoute()
    }

    fun retryRoute() {
        loadRoute()
    }

    fun reorderItems(orderedItemIds: List<String>) {
        val state = _uiState.value
        if (orderedItemIds == state.selectedDay?.items.orEmpty().map { it.id }) return
        routeJob?.cancel()
        _uiState.update {
            it.copy(
                optimization = null,
                route = null,
                isLoadingRoute = true,
                routeError = null,
            )
        }
        travelPlanRepository.applyOptimizedOrder(
            planId = planId,
            dayIndex = state.selectedDayIndex,
            orderedPlaceIds = orderedItemIds,
        )
    }

    fun moveUnplannedItemToDay(itemId: String, dayIndex: Int) {
        val result = travelPlanRepository.moveUnplannedItemToDay(planId, itemId, dayIndex)
        if (result == AddPlaceResult.MISSING_LOCATION) {
            _uiState.update { it.copy(routeError = "这个待规划地点缺少坐标，不能加入路线 DAY。") }
        }
    }

    fun deletePlan(): Boolean {
        routeJob?.cancel()
        return travelPlanRepository.deletePlan(planId)
    }

    fun optimizeRoute() {
        val state = _uiState.value
        val places = state.selectedDay?.items
            ?.sortedBy { it.visitOrder }
            ?.mapNotNull { it.toRoutePlace() }
            .orEmpty()
        if (places.size < 3) {
            _uiState.update { it.copy(routeError = "至少需要 3 个带坐标的地点，才需要优化顺序。") }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(isOptimizing = true, routeError = null, optimization = null) }
            runCatching {
                routeRepository.optimizeDayRoute(
                    places,
                    state.routeMode.takeUnless { it == RouteModes.MIXED } ?: RouteModes.WALKING,
                )
            }.onSuccess { optimization ->
                _uiState.update {
                    it.copy(
                        isOptimizing = false,
                        optimization = optimization,
                        routeError = null,
                    )
                }
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isOptimizing = false,
                        routeError = readableError(throwable),
                    )
                }
            }
        }
    }

    fun applyOptimization() {
        val state = _uiState.value
        val optimization = state.optimization ?: return
        travelPlanRepository.applyOptimizedOrder(
            planId = planId,
            dayIndex = state.selectedDayIndex,
            orderedPlaceIds = optimization.optimizedPlaceIds,
        )
        _uiState.update { it.copy(optimization = null) }
    }

    fun dismissOptimization() {
        _uiState.update { it.copy(optimization = null) }
        loadRoute()
    }

    private fun loadRoute() {
        routeJob?.cancel()
        val state = _uiState.value
        val places = state.selectedDay?.items
            ?.sortedBy { it.visitOrder }
            ?.mapNotNull { it.toRoutePlace() }
            .orEmpty()

        if (places.size < 2) {
            _uiState.update {
                it.copy(
                    route = DayRoutePlan(places = places, mode = state.routeMode),
                    isLoadingRoute = false,
                    routeError = null,
                )
            }
            return
        }

        routeJob = viewModelScope.launch {
            _uiState.update { it.copy(isLoadingRoute = true, routeError = null) }
            runCatching {
                if (_uiState.value.routeMode == RouteModes.MIXED) {
                    routeRepository.calculateMixedDayRoute(state.selectedDay?.items.orEmpty())
                } else {
                    routeRepository.calculateDayRoute(places, _uiState.value.routeMode)
                }
            }.onSuccess { route ->
                _uiState.update {
                    it.copy(
                        route = route,
                        isLoadingRoute = false,
                        routeError = null,
                    )
                }
            }.onFailure { throwable ->
                _uiState.update {
                    it.copy(
                        isLoadingRoute = false,
                        routeError = readableError(throwable),
                    )
                }
            }
        }
    }

    private fun readableError(throwable: Throwable): String {
        return when (throwable) {
            is HttpException -> throwable.response()?.errorBody()?.string()?.takeIf { it.isNotBlank() }
                ?: "路线服务暂时不可用，请稍后重试。"
            is IOException -> "请确认后端服务已经启动，且模拟器可以访问 10.0.2.2:8000。"
            else -> throwable.message?.takeIf { it.isNotBlank() } ?: "路线服务暂时不可用，请稍后重试。"
        }
    }

    class Factory(
        private val planId: String,
        private val travelPlanRepository: TravelPlanRepository,
        private val routeRepository: RouteRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(PlanDetailViewModel::class.java)) {
                return PlanDetailViewModel(
                    planId = planId,
                    travelPlanRepository = travelPlanRepository,
                    routeRepository = routeRepository,
                ) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
