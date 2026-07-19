package com.heoclub.aitravel.data.model

data class PlaceDetail(
    val summary: PlaceSummary,
    val images: List<PlaceImage> = summary.safeImages,
    val openingHours: String? = null,
    val phone: String? = null,
    val description: String,
    val reviewTitle: String = "地点亮点",
    val reviewSubtitle: String? = null,
    val positiveHighlights: List<ReviewHighlight> = emptyList(),
    val negativeHighlights: List<ReviewHighlight> = emptyList(),
    val reviewSources: List<ReviewSource> = emptyList(),
    val sourceLabels: List<String> = emptyList(),
    val relatedPlans: List<String> = emptyList(),
    val hasRealReviews: Boolean = false,
    val reviewUpdatedAt: String? = null,
)

data class ReviewHighlight(
    val title: String,
    val description: String,
)

data class ReviewSource(
    val id: String,
    val platform: String,
    val title: String,
    val url: String,
    val author: String? = null,
    val excerpt: String? = null,
    val publishedAt: String? = null,
    val coverImageUrl: String? = null,
    val likeCount: String? = null,
    val provider: String? = null,
)
