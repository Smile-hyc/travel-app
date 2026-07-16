package com.heoclub.aitravel.data.model

data class ExploreCity(
    val id: String,
    val name: String,
    val displayName: String,
    val provinceName: String,
    val adCode: String,
    val latitude: Double,
    val longitude: Double,
    val defaultZoom: Float,
    val isPopular: Boolean = false,
)

data class ExploreProvince(
    val name: String,
    val cities: List<ExploreCity>,
)

data class CitySearchResult(
    val id: String,
    val name: String,
    val provinceName: String? = null,
    val adCode: String,
    val latitude: Double,
    val longitude: Double,
    val defaultZoom: Float = 13.2f,
)
