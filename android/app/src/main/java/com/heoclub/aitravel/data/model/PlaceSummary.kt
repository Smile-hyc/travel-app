package com.heoclub.aitravel.data.model

data class PlaceImage(
    val id: String,
    val url: String? = null,
    val thumbnailUrl: String? = null,
    val title: String? = null,
    val source: String = "AMAP",
    val sourcePageUrl: String? = null,
    val author: String? = null,
    val license: String? = null,
    val isPrimary: Boolean = false,
    val width: Int? = null,
    val height: Int? = null,
)

data class PlaceSummary(
    val id: String,
    val source: String = "AMAP",
    val sourcePoiId: String,
    val name: String,
    val category: String,
    val categoryCode: String,
    val typeName: String? = null,
    val typeCode: String? = null,
    val address: String? = null,
    val provinceName: String? = null,
    val cityName: String? = null,
    val districtName: String? = null,
    val adCode: String? = null,
    val cityCode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val distanceMeters: Int? = null,
    val phone: String? = null,
    val rating: String? = null,
    val costAverage: String? = null,
    val images: List<PlaceImage>? = emptyList(),
    val coverImageUrl: String? = null,
    val imageUrls: List<String>? = emptyList(),
    val businessArea: String? = null,
    val openingHoursToday: String? = null,
    val openingHoursWeek: String? = null,
    val isFavorite: Boolean = false,
) {
    val categoryId: String
        get() = category

    val hasLocation: Boolean
        get() = latitude != null && longitude != null

    val displayAddress: String
        get() = listOfNotNull(districtName, address).joinToString(" · ").ifBlank {
            "暂无详细地址"
        }

    val metaText: String
        get() = listOfNotNull(typeName, rating?.let { "评分 $it" }, costAverage?.let { "人均 ¥$it" })
            .joinToString(" · ")
            .ifBlank { businessArea ?: "高德真实地点" }

    val rankingText: String
        get() = metaText

    val popularity: String
        get() = listOfNotNull(cityName, districtName).joinToString(" · ").ifBlank { source }

    val shortDescription: String
        get() = displayAddress

    val displayCoverImageUrl: String?
        get() = coverImageUrl?.takeIf { it.isValidRemoteImageUrl() }
            ?: safeImages.firstOrNull { it.isPrimary }?.url?.takeIf { it.isValidRemoteImageUrl() }
            ?: safeImages.firstOrNull()?.url?.takeIf { it.isValidRemoteImageUrl() }
            ?: safeImageUrls.firstOrNull { it.isValidRemoteImageUrl() }

    val displayImageUrls: List<String>
        get() = (safeImages.mapNotNull { it.url } + safeImageUrls)
            .map { it.trim() }
            .filter { it.isValidRemoteImageUrl() }
            .distinct()

    val safeImages: List<PlaceImage>
        get() = images.orEmpty()

    private val safeImageUrls: List<String>
        get() = imageUrls.orEmpty()
}

private fun String.isValidRemoteImageUrl(): Boolean {
    val value = trim()
    return value.startsWith("http://", ignoreCase = true) ||
        value.startsWith("https://", ignoreCase = true)
}

data class PlaceSuggestion(
    val id: String,
    val name: String,
    val district: String? = null,
    val address: String? = null,
    val cityName: String? = null,
    val adCode: String? = null,
    val typeCode: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val hasLocation: Boolean = false,
)

data class PaginatedPlaces(
    val items: List<PlaceSummary>,
    val page: Int,
    val pageSize: Int,
    val total: Int,
    val hasMore: Boolean,
)
