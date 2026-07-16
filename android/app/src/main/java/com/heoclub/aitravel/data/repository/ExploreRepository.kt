package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.ExploreCategory
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.ExploreWeather
import com.heoclub.aitravel.data.model.PaginatedPlaces
import com.heoclub.aitravel.data.model.PlaceCollection
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.remote.ApiService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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

    suspend fun searchCities(keyword: String): List<ExploreCity>

    suspend fun getCityWeather(adcode: String): ExploreWeather

    fun upsertPlace(place: PlaceSummary)
    fun getPlace(placeId: String): PlaceSummary?
    fun getPlaceDetail(placeId: String): PlaceDetail?
    fun toggleFavorite(placeId: String)
}

class RemoteExploreRepository(
    private val apiService: ApiService,
) : ExploreRepository {
    override val categories: List<ExploreCategory> = ExploreCategories.all
    override val collections: List<PlaceCollection> = emptyList()

    private val _places = MutableStateFlow<List<PlaceSummary>>(emptyList())
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
        return placeholderDetail(summary)
    }

    override fun toggleFavorite(placeId: String) {
        _places.update { current ->
            current.map { place ->
                if (place.id == placeId) place.copy(isFavorite = !place.isFavorite) else place
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
    return PlaceDetail(
        summary = summary,
        openingHours = "详情真实化将在下一阶段接入",
        phone = summary.phone ?: "暂无公开电话",
        description = "${summary.name} 来自高德 POI 或本地预览数据。本阶段先完成地图、列表和搜索联动，详情页后续再真实化。",
        positiveHighlights = listOf("真实地点坐标", "可在地图中定位", "可作为行程锚点"),
        negativeHighlights = listOf("详情内容待补全", "营业时间待接入", "评价内容待接入"),
        sourceLabels = listOf(summary.source, "POI 基础信息"),
        relatedPlans = emptyList(),
    )
}
