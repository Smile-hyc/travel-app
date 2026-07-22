package com.heoclub.aitravel.data.repository

import com.google.gson.Gson
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.ExploreCategory
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.ExploreWeather
import com.heoclub.aitravel.data.model.PaginatedPlaces
import com.heoclub.aitravel.data.model.PlaceCollection
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.model.PlaceEnrichmentBatchRequest
import com.heoclub.aitravel.data.model.PlaceEnrichmentBatchResponse
import com.heoclub.aitravel.data.model.PlaceEnrichmentEvent
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.model.ReviewHighlight
import com.heoclub.aitravel.data.model.ReverseGeocodePoint
import com.heoclub.aitravel.data.remote.ApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.update

interface ExploreRepository {
    val categories: List<ExploreCategory>
    val collections: List<PlaceCollection>
    val places: StateFlow<List<PlaceSummary>>

    suspend fun searchPlaces(
        adcode: String,
        category: String,
        keyword: String? = null,
        page: Int = 1,
        pageSize: Int = 20,
        cityLimit: Boolean = true,
        append: Boolean = false,
    ): PaginatedPlaces

    suspend fun getInputTips(
        keyword: String,
        adcode: String? = null,
        category: String? = null,
        cityLimit: Boolean = true,
    ): List<PlaceSuggestion>

    suspend fun reverseGeocode(
        latitude: Double,
        longitude: Double,
        radius: Int = 50,
    ): ReverseGeocodePoint

    suspend fun searchCities(keyword: String): List<ExploreCity>

    suspend fun getCityWeather(adcode: String): ExploreWeather

    fun upsertPlace(place: PlaceSummary)
    fun getPlace(placeId: String): PlaceSummary?
    fun getPlaceDetail(placeId: String): PlaceDetail?
    suspend fun refreshPlaceDetail(placeId: String): PlaceDetail?
    suspend fun preparePlaceEnrichment(places: List<PlaceSummary>): PlaceEnrichmentBatchResponse
    fun streamPlaceEnrichment(batchId: String): Flow<PlaceEnrichmentEvent>
    fun toggleFavorite(placeId: String)
}

class RemoteExploreRepository(
    private val apiService: ApiService,
) : ExploreRepository {
    private val gson = Gson()
    override val categories: List<ExploreCategory> = ExploreCategories.all
    override val collections: List<PlaceCollection> = emptyList()

    private val _places = MutableStateFlow<List<PlaceSummary>>(emptyList())
    override val places: StateFlow<List<PlaceSummary>> = _places.asStateFlow()
    private val details = mutableMapOf<String, PlaceDetail>()

    override suspend fun searchPlaces(
        adcode: String,
        category: String,
        keyword: String?,
        page: Int,
        pageSize: Int,
        cityLimit: Boolean,
        append: Boolean,
    ): PaginatedPlaces {
        val result = apiService.searchPois(
            adcode = adcode,
            category = category,
            keyword = keyword?.takeIf { it.isNotBlank() },
            page = page,
            pageSize = pageSize,
            cityLimit = cityLimit,
        )
        val mappableItems = result.items.filter { it.hasLocation }
        _places.value = if (append) {
            (_places.value + mappableItems).distinctBy { it.id }
        } else {
            mappableItems
        }
        return result
    }

    override suspend fun getInputTips(
        keyword: String,
        adcode: String?,
        category: String?,
        cityLimit: Boolean,
    ): List<PlaceSuggestion> {
        if (keyword.trim().length < 2) return emptyList()
        return apiService.getInputTips(
            keyword = keyword.trim(),
            adcode = adcode,
            cityLimit = cityLimit,
            category = category,
        )
    }

    override suspend fun reverseGeocode(
        latitude: Double,
        longitude: Double,
        radius: Int,
    ): ReverseGeocodePoint = apiService.reverseGeocode(
        latitude = latitude,
        longitude = longitude,
        radius = radius,
    )

    override suspend fun searchCities(keyword: String): List<ExploreCity> {
        val query = keyword.trim()
        if (query.length < 2) return emptyList()
        return apiService.searchCities(keyword = query).map { result ->
            ExploreCity(
                id = result.id,
                name = result.name,
                displayName = result.name,
                provinceName = result.provinceName ?: result.name,
                adCode = result.adCode,
                latitude = result.latitude,
                longitude = result.longitude,
                defaultZoom = result.defaultZoom,
                isPopular = false,
            )
        }
    }

    override suspend fun getCityWeather(adcode: String): ExploreWeather {
        return apiService.getExploreWeather(adcode = adcode)
    }

    override fun upsertPlace(place: PlaceSummary) {
        _places.update { current ->
            listOf(place) + current.filterNot { it.id == place.id }
        }
    }

    override fun getPlace(placeId: String): PlaceSummary? {
        return places.value.firstOrNull { it.id == placeId }
    }

    override fun getPlaceDetail(placeId: String): PlaceDetail? {
        val summary = getPlace(placeId) ?: return null
        return details[placeId]?.copy(summary = summary) ?: placeholderDetail(summary)
    }

    override suspend fun refreshPlaceDetail(placeId: String): PlaceDetail? {
        val summary = getPlace(placeId) ?: return null
        val detail = apiService.getPlaceDetail(summary).let { remote ->
            remote.copy(summary = remote.summary.copy(isFavorite = summary.isFavorite))
        }
        details[placeId] = detail
        return detail
    }

    override suspend fun preparePlaceEnrichment(places: List<PlaceSummary>): PlaceEnrichmentBatchResponse {
        val uniquePlaces = places.distinctBy { it.sourcePoiId }.take(30)
        return apiService.preparePlaceEnrichmentBatch(
            PlaceEnrichmentBatchRequest(places = uniquePlaces),
        ).also { batch ->
            batch.items.mapNotNull { it.detail }.forEach(::cacheDetail)
        }
    }

    override fun streamPlaceEnrichment(batchId: String): Flow<PlaceEnrichmentEvent> = flow {
        apiService.streamPlaceEnrichmentBatch(batchId).use { responseBody ->
            responseBody.charStream().buffered().use { reader ->
                val data = StringBuilder()
                while (true) {
                    val line = reader.readLine() ?: break
                    when {
                        line.startsWith("data:") -> data.append(line.removePrefix("data:").trim())
                        line.isBlank() && data.isNotEmpty() -> {
                            val event = gson.fromJson(data.toString(), PlaceEnrichmentEvent::class.java)
                            event.detail?.let(::cacheDetail)
                            emit(event)
                            data.clear()
                        }
                    }
                }
                if (data.isNotEmpty()) {
                    val event = gson.fromJson(data.toString(), PlaceEnrichmentEvent::class.java)
                    event.detail?.let(::cacheDetail)
                    emit(event)
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    private fun cacheDetail(detail: PlaceDetail) {
        val current = getPlace(detail.summary.id)
        details[detail.summary.id] = if (current == null) {
            detail
        } else {
            detail.copy(summary = detail.summary.copy(isFavorite = current.isFavorite))
        }
    }

    override fun toggleFavorite(placeId: String) {
        _places.update { current ->
            current.map { place ->
                if (place.id == placeId) place.copy(isFavorite = !place.isFavorite) else place
            }
        }
        val updatedSummary = getPlace(placeId)
        if (updatedSummary != null) {
            details[placeId]?.let { detail ->
                details[placeId] = detail.copy(summary = updatedSummary)
            }
        }
    }
}

class MockExploreRepository : ExploreRepository {
    override val categories: List<ExploreCategory> = ExploreCategories.all

    override val collections: List<PlaceCollection> = listOf(
        PlaceCollection("imperial", "穿越紫禁城", "历史与神秘的对话", listOf("forbidden-city", "jingshan")),
        PlaceCollection("slow-cafe", "京城治愈咖啡馆", "好天气就该慢下来", listOf("sanlitun")),
        PlaceCollection("free-walk", "北京免费好去处", "不花钱也能玩得尽兴", listOf("shichahai", "tiantan")),
    )

    private val initialPlaces = listOf(
        mockPlace("forbidden-city", "故宫博物院", ExploreCategories.SCENIC, 39.916345, 116.397155, "北京市东城区景山前街4号", "博物馆"),
        mockPlace("jingshan", "景山公园", ExploreCategories.SCENIC, 39.925052, 116.396295, "北京市西城区景山西街44号", "公园广场"),
        mockPlace("shichahai", "什刹海", ExploreCategories.SCENIC, 39.939214, 116.386315, "北京市西城区地安门西大街", "风景名胜"),
        mockPlace("tiantan", "天坛公园", ExploreCategories.SCENIC, 39.882156, 116.406609, "北京市东城区天坛东里甲1号", "公园广场"),
        mockPlace("beijing-station", "北京站", ExploreCategories.TRANSPORT, 39.903543, 116.427062, "北京市东城区毛家湾胡同甲13号", "火车站"),
        mockPlace("sanlitun", "三里屯太古里", ExploreCategories.SHOPPING, 39.933589, 116.454209, "北京市朝阳区三里屯路19号", "购物中心"),
    )

    private val _places = MutableStateFlow(initialPlaces)
    override val places: StateFlow<List<PlaceSummary>> = _places.asStateFlow()

    override suspend fun searchPlaces(
        adcode: String,
        category: String,
        keyword: String?,
        page: Int,
        pageSize: Int,
        cityLimit: Boolean,
        append: Boolean,
    ): PaginatedPlaces {
        val filtered = initialPlaces.filter { it.category == category }
        _places.value = filtered
        return PaginatedPlaces(
            items = filtered,
            page = 1,
            pageSize = filtered.size,
            total = filtered.size,
            hasMore = false,
        )
    }

    override suspend fun getInputTips(
        keyword: String,
        adcode: String?,
        category: String?,
        cityLimit: Boolean,
    ): List<PlaceSuggestion> = emptyList()

    override suspend fun reverseGeocode(
        latitude: Double,
        longitude: Double,
        radius: Int,
    ): ReverseGeocodePoint = ReverseGeocodePoint(
        name = "地图选定位置",
        formattedAddress = "北京市地图选定位置",
        provinceName = "北京市",
        cityName = "北京市",
        districtName = "北京市",
        adCode = "110100",
        latitude = latitude,
        longitude = longitude,
    )

    override suspend fun searchCities(keyword: String): List<ExploreCity> = emptyList()

    override suspend fun getCityWeather(adcode: String): ExploreWeather {
        return ExploreWeather(
            city = "预览城市",
            adCode = adcode,
            weather = "多云",
            dayTemp = "33",
            nightTemp = "24",
            text = "多云 24°-33°",
            reportTime = null,
        )
    }

    override fun upsertPlace(place: PlaceSummary) {
        _places.update { current -> listOf(place) + current.filterNot { it.id == place.id } }
    }

    override fun getPlace(placeId: String): PlaceSummary? {
        return places.value.firstOrNull { it.id == placeId }
    }

    override fun getPlaceDetail(placeId: String): PlaceDetail? {
        val summary = getPlace(placeId) ?: return null
        return placeholderDetail(summary)
    }

    override suspend fun refreshPlaceDetail(placeId: String): PlaceDetail? = getPlaceDetail(placeId)

    override suspend fun preparePlaceEnrichment(places: List<PlaceSummary>): PlaceEnrichmentBatchResponse {
        return PlaceEnrichmentBatchResponse(
            batchId = "mock",
            items = places.take(30).map { place ->
                com.heoclub.aitravel.data.model.PlaceEnrichmentBatchItem(
                    sourcePoiId = place.sourcePoiId,
                    status = "UNAVAILABLE",
                    detail = getPlaceDetail(place.id),
                )
            },
        )
    }

    override fun streamPlaceEnrichment(batchId: String): Flow<PlaceEnrichmentEvent> = emptyFlow()

    override fun toggleFavorite(placeId: String) {
        _places.update { current ->
            current.map { place ->
                if (place.id == placeId) place.copy(isFavorite = !place.isFavorite) else place
            }
        }
    }
}

private fun mockPlace(
    id: String,
    name: String,
    category: String,
    latitude: Double,
    longitude: Double,
    address: String,
    typeName: String,
): PlaceSummary {
    return PlaceSummary(
        id = id,
        sourcePoiId = id,
        name = name,
        category = category,
        categoryCode = category,
        typeName = typeName,
        address = address,
        cityName = "北京市",
        districtName = "北京市",
        adCode = "110100",
        latitude = latitude,
        longitude = longitude,
    )
}

private fun placeholderDetail(summary: PlaceSummary): PlaceDetail {
    val openingHours = summary.openingHoursWeek ?: summary.openingHoursToday
    val positives = buildList {
        summary.rating?.let {
            add(ReviewHighlight("公开评分", "高德地点信息显示评分为 $it 分，可作为选择时的辅助参考。"))
        }
        if (openingHours != null) {
            add(ReviewHighlight("行程更好安排", "已获取营业时间信息，适合在规划路线时预留到访时段。"))
        }
        if (isEmpty()) {
            add(ReviewHighlight("地点信息明确", "已获取地点分类和定位信息，可直接加入计划或导航。"))
        }
    }
    val cautions = if (openingHours == null) {
        listOf(ReviewHighlight("营业时间待确认", "暂未获取可靠营业时间，建议到访前电话或通过官方渠道确认。"))
    } else {
        emptyList()
    }
    return PlaceDetail(
        summary = summary,
        openingHours = openingHours,
        phone = summary.phone,
        description = listOfNotNull(
            summary.typeName,
            summary.districtName,
            summary.address,
            summary.businessArea?.let { "${it}商圈" },
        ).joinToString(" · ").ifBlank { "${summary.name}的公开地点信息。" },
        reviewTitle = "地点亮点",
        reviewSubtitle = "基于地点公开信息整理，出发前建议再次确认",
        positiveHighlights = positives,
        negativeHighlights = cautions,
        sourceLabels = listOf(summary.source),
        relatedPlans = emptyList(),
    )
}
