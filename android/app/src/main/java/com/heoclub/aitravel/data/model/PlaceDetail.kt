package com.heoclub.aitravel.data.model

data class PlaceDetail(
    val summary: PlaceSummary,
    val images: List<PlaceImage> = summary.safeImages,
    val openingHours: String,
    val phone: String,
    val description: String,
    val positiveHighlights: List<String>,
    val negativeHighlights: List<String>,
    val sourceLabels: List<String>,
    val relatedPlans: List<String>,
)
