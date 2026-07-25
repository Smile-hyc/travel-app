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
    val enrichmentBatchId: String? = null,
    val reviewStatus: String = "UNAVAILABLE",
    val factLayer: PlaceFactLayer = PlaceFactLayer(),
    val officialLayer: OfficialPlaceLayer = OfficialPlaceLayer(),
    val experienceLayer: PlaceExperienceLayer = PlaceExperienceLayer(),
)

data class PlaceFactLayer(
    val source: String = "AMAP",
    val verifiedAt: String? = null,
    val expiresAt: String? = null,
)

data class OfficialPlaceLayer(
    val status: String = "UNAVAILABLE",
    val notices: List<OfficialNotice> = emptyList(),
    val updatedAt: String? = null,
    val sourceId: String? = null,
    val officialName: String? = null,
    val scenicGrade: String? = null,
    val maxDailyCapacity: Int? = null,
    val websiteUrl: String? = null,
    val wechatName: String? = null,
    val miniProgramName: String? = null,
    val ticketingUrl: String? = null,
    val discoveryStatus: String? = null,
    val verifiedAt: String? = null,
    val sourceType: String? = null,
)

data class OfficialNotice(
    val type: String,
    val title: String,
    val detail: String,
    val sourceUrl: String? = null,
    val effectiveAt: String? = null,
    val expiresAt: String? = null,
)

data class PlaceExperienceLayer(
    val status: String = "UNAVAILABLE",
    val insights: List<ExperienceInsight> = emptyList(),
    val evidenceCount: Int = 0,
    val minimumEvidenceCount: Int = 1,
    val summaryVersion: String? = null,
    val updatedAt: String? = null,
)

data class ExperienceInsight(
    val tag: String,
    val title: String,
    val summary: String,
    val mentionCount: Int,
    val confidence: Double = 0.0,
    val evidenceIds: List<String> = emptyList(),
    val points: List<ExperienceInsightPoint> = emptyList(),
    val updatedAt: String? = null,
    val expiresAt: String? = null,
)

data class ExperienceInsightPoint(
    val text: String,
    val evidenceIds: List<String> = emptyList(),
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
    val evidenceId: String? = null,
    val relevanceScore: Double? = null,
    val anonymousAuthorId: String? = null,
    val tags: List<String> = emptyList(),
    val deleted: Boolean = false,
)

data class PlaceEnrichmentBatchRequest(
    val places: List<PlaceSummary>,
    val forceRefresh: Boolean = false,
)

data class PlaceEnrichmentBatchItem(
    val sourcePoiId: String,
    val status: String,
    val detail: PlaceDetail? = null,
)

data class PlaceEnrichmentBatchResponse(
    val batchId: String,
    val items: List<PlaceEnrichmentBatchItem> = emptyList(),
    val pendingCount: Int = 0,
)

data class PlaceEnrichmentEvent(
    val batchId: String,
    val type: String,
    val sourcePoiId: String? = null,
    val status: String? = null,
    val detail: PlaceDetail? = null,
    val message: String? = null,
    val completed: Int = 0,
    val total: Int = 0,
)
