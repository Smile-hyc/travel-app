package com.heoclub.aitravel.ui.place

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.repository.ExploreRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class PlaceDetailViewModel(
    private val placeId: String,
    private val exploreRepository: ExploreRepository,
) : ViewModel() {
    private val _placeDetail = MutableStateFlow(exploreRepository.getPlaceDetail(placeId))
    val placeDetail: StateFlow<PlaceDetail?> = _placeDetail.asStateFlow()

    fun toggleFavorite() {
        exploreRepository.toggleFavorite(placeId)
        _placeDetail.value = exploreRepository.getPlaceDetail(placeId)
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

