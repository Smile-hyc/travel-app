package com.heoclub.aitravel.ui.place

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.repository.ExploreRepository
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PlaceDetailUiState(
    val detail: PlaceDetail? = null,
    val isRefreshing: Boolean = false,
    val isEnrichmentStreaming: Boolean = false,
    val refreshFailed: Boolean = false,
    val isCheckedIn: Boolean = false,
)

class PlaceDetailViewModel(
    private val placeId: String,
    private val exploreRepository: ExploreRepository,
) : ViewModel() {
    private var enrichmentJob: Job? = null
    private val _uiState = MutableStateFlow(
        PlaceDetailUiState(detail = exploreRepository.getPlaceDetail(placeId)),
    )
    val uiState: StateFlow<PlaceDetailUiState> = _uiState.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        if (_uiState.value.isRefreshing) return
        _uiState.update { it.copy(isRefreshing = true, refreshFailed = false) }
        viewModelScope.launch {
            runCatching { exploreRepository.refreshPlaceDetail(placeId) }
                .onSuccess { detail ->
                    _uiState.update {
                        it.copy(
                            detail = detail ?: it.detail,
                            isRefreshing = false,
                            refreshFailed = detail == null,
                        )
                    }
                    detail?.let(::observeEnrichment)
                }
                .onFailure {
                    _uiState.update { state ->
                        state.copy(isRefreshing = false, refreshFailed = true)
                    }
                }
        }
    }

    private fun observeEnrichment(detail: PlaceDetail) {
        val batchId = detail.enrichmentBatchId ?: return
        if (detail.reviewStatus !in setOf("PENDING", "STALE")) return
        enrichmentJob?.cancel()
        enrichmentJob = viewModelScope.launch {
            _uiState.update { it.copy(isEnrichmentStreaming = true) }
            runCatching {
                exploreRepository.streamPlaceEnrichment(batchId).collect { event ->
                    val updated = event.detail
                    if (updated != null && updated.summary.sourcePoiId == detail.summary.sourcePoiId) {
                        _uiState.update { state -> state.copy(detail = updated, refreshFailed = false) }
                    }
                }
            }
            _uiState.update { it.copy(isEnrichmentStreaming = false) }
        }
    }

    fun toggleFavorite() {
        exploreRepository.toggleFavorite(placeId)
        _uiState.update { it.copy(detail = exploreRepository.getPlaceDetail(placeId)) }
    }

    fun toggleCheckIn() {
        _uiState.update { it.copy(isCheckedIn = !it.isCheckedIn) }
    }

    class Factory(
        private val placeId: String,
        private val exploreRepository: ExploreRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(PlaceDetailViewModel::class.java)) {
                return PlaceDetailViewModel(placeId, exploreRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
