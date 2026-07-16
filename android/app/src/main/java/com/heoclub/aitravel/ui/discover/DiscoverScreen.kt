package com.heoclub.aitravel.ui.discover

import androidx.compose.runtime.Composable
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.ui.explore.ExploreScreen
import com.heoclub.aitravel.ui.explore.ExploreViewModel

@Composable
fun DiscoverScreen(
    viewModel: ExploreViewModel,
    onOpenPlace: (String) -> Unit,
    onAddPlace: (PlaceSummary) -> Unit,
) {
    ExploreScreen(
        viewModel = viewModel,
        onOpenPlace = onOpenPlace,
        onAddPlace = onAddPlace,
    )
}
