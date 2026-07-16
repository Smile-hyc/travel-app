package com.heoclub.aitravel.data.model

data class ExploreWeather(
    val city: String,
    val adCode: String,
    val weather: String,
    val dayTemp: String? = null,
    val nightTemp: String? = null,
    val text: String,
    val reportTime: String? = null,
)
