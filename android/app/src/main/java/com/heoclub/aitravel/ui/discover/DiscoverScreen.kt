package com.heoclub.aitravel.ui.discover

import androidx.compose.runtime.Composable
import com.heoclub.aitravel.data.location.CurrentLocationUiState
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.ui.explore.ExploreMapViewHolder
import com.heoclub.aitravel.ui.explore.ExploreScreen
import com.heoclub.aitravel.ui.explore.ExploreViewModel

@Composable
fun DiscoverScreen(
    viewModel: ExploreViewModel,
    mapViewHolder: ExploreMapViewHolder,
    locationState: CurrentLocationUiState,
    requestedDestination: String? = null,
    destinationRequestKey: Long? = null,
    onLocate: () -> Unit,
    onOpenPlace: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
) {
    ExploreScreen(
        viewModel = viewModel,
        mapViewHolder = mapViewHolder,
        locationState = locationState,
        requestedDestination = requestedDestination,
        destinationRequestKey = destinationRequestKey,
        onLocate = onLocate,
        onOpenPlace = onOpenPlace,
        onAddPlace = onAddPlace,
    )
}
