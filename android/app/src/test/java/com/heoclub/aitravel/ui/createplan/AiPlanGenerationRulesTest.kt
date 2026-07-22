package com.heoclub.aitravel.ui.createplan

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import com.heoclub.aitravel.data.model.AiPlanProgressEvent
import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.PlaceSuggestion

class AiPlanGenerationRulesTest {
    @Test
    fun `current plan action stays hidden before thirty seconds`() {
        assertFalse(
            canUseCurrentPlan(
                waitingForAi = true,
                waitingSeconds = CURRENT_PLAN_FALLBACK_DELAY_SECONDS - 1,
                partialDayCount = 3,
                completedDays = 3,
                totalDays = 3,
            ),
        )
    }

    @Test
    fun `current plan action appears at thirty seconds`() {
        assertTrue(
            canUseCurrentPlan(
                waitingForAi = true,
                waitingSeconds = CURRENT_PLAN_FALLBACK_DELAY_SECONDS,
                partialDayCount = 3,
                completedDays = 3,
                totalDays = 3,
            ),
        )
    }

    @Test
    fun `current plan action requires a complete visible plan`() {
        assertFalse(canUseCurrentPlan(true, 60, 0, 3, 3))
        assertFalse(canUseCurrentPlan(true, 60, 2, 2, 3))
        assertFalse(canUseCurrentPlan(false, 60, 3, 3, 3))
    }

    @Test
    fun `province query asks user to choose a child city`() {
        val suggestions = listOf(
            ExploreCity("chengdu", "成都市", "成都市", "四川省", "510100", 30.57, 104.06, 13.2f),
            ExploreCity("leshan", "乐山市", "乐山市", "四川省", "511100", 29.55, 103.76, 13.2f),
        )

        assertEquals("选择 四川省 下的城市", destinationSuggestionTitle("四川省", suggestions))
    }

    @Test
    fun `province cities put capital first then use chinese phonetic order`() {
        val suggestions = listOf(
            ExploreCity("zigong", "自贡市", "自贡市", "四川省", "510300", 29.33, 104.77, 13.2f),
            ExploreCity("aba", "阿坝藏族羌族自治州", "阿坝藏族羌族自治州", "四川省", "513200", 31.90, 102.22, 13.2f),
            ExploreCity("chengdu", "成都市", "成都市", "四川省", "510100", 30.57, 104.06, 13.2f),
        )

        assertEquals(
            listOf("成都市", "阿坝藏族羌族自治州", "自贡市"),
            sortDestinationSuggestions("四川省", suggestions).map { it.name },
        )
    }

    @Test
    fun `ordinary capital is not labeled as municipality`() {
        val chengdu = ExploreCity("chengdu", "成都市", "成都市", "四川省", "510100", 30.57, 104.06, 13.2f)
        val nanjing = ExploreCity("nanjing", "南京市", "南京市", "江苏省", "320100", 32.06, 118.79, 13.2f)
        val beijing = ExploreCity("beijing", "北京市", "北京市", "北京市", "110000", 39.90, 116.40, 13.2f)

        assertEquals("省会 · 四川省", cityRegionLabel(chengdu))
        assertEquals("省会 · 江苏省", cityRegionLabel(nanjing))
        assertEquals("直辖市", cityRegionLabel(beijing))
    }

    @Test
    fun `analysis event displays its real message instead of generic duplicate`() {
        val event = AiPlanProgressEvent(
            sequence = 1,
            type = "ANALYSIS",
            message = "正在比较午餐与下午景点的通勤成本",
            decision = "保留顺路餐馆",
            createdAt = "2026-07-22T00:00:00Z",
        )

        assertEquals("正在比较午餐与下午景点的通勤成本", planningFeatureText(event, null))
    }

    @Test
    fun `identical planning events are shown once`() {
        val event = AiPlanProgressEvent(
            sequence = 1,
            type = "ANALYSIS",
            message = "正在完善行程安排",
            createdAt = "2026-07-22T00:00:00Z",
        )

        assertEquals(
            1,
            deduplicatedPlanningEvents(
                listOf(
                    event,
                    event.copy(sequence = 2, type = "MODEL_REASON"),
                ),
            ).size,
        )
    }

    @Test
    fun `station and hotel suggestions stay inside destination city`() {
        assertTrue(belongsToDestinationCity("510107", "510100"))
        assertTrue(belongsToDestinationCity("110105", "110000"))
        assertFalse(belongsToDestinationCity("320114", "510100"))
        assertFalse(belongsToDestinationCity(null, "510100"))
    }

    @Test
    fun `map poi matching uses strict fifty meter distance`() {
        val near = mapDistanceMeters(30.5728, 104.0668, 30.5730, 104.0669)
        val far = mapDistanceMeters(30.5728, 104.0668, 30.5740, 104.0668)

        assertTrue(near < 50.0)
        assertTrue(far > 50.0)
    }

    @Test
    fun `reverse geocode without adcode can use matching city address`() {
        assertTrue(
            mapLocationBelongsToDestination(
                adCode = null,
                cityName = null,
                formattedAddress = "四川省成都市武侯区天府大道北段",
                expectedCityAdCode = "510100",
                expectedCityName = "成都市",
            ),
        )
        assertFalse(
            mapLocationBelongsToDestination(
                adCode = null,
                cityName = "德阳市",
                formattedAddress = "四川省德阳市旌阳区",
                expectedCityAdCode = "510100",
                expectedCityName = "成都市",
            ),
        )
    }

    @Test
    fun `railway stations and airports are ranked before other transport`() {
        val ordinary = PlaceSuggestion(id = "3", name = "某交通服务点", adCode = "510107")
        val airport = PlaceSuggestion(id = "2", name = "成都双流国际机场", adCode = "510116")
        val railway = PlaceSuggestion(id = "1", name = "成都东站", adCode = "510107")

        assertEquals(
            listOf("成都东站", "成都双流国际机场", "某交通服务点"),
            listOf(ordinary, airport, railway).sortedWith(transportSuggestionComparator("成都")).map { it.name },
        )
    }

    @Test
    fun `transport hub input filters the cached destination hubs`() {
        val south = PlaceSuggestion(
            id = "nanjing-south",
            name = "南京南站",
            cityName = "南京市",
            adCode = "320114",
        )
        val airport = PlaceSuggestion(
            id = "nanjing-airport",
            name = "南京禄口国际机场",
            cityName = "南京市",
            adCode = "320115",
        )

        assertTrue(south.matchesTransportHubQuery("南京"))
        assertTrue(south.matchesTransportHubQuery("南站"))
        assertFalse(airport.matchesTransportHubQuery("南站"))
    }
}
