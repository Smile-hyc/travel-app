package com.heoclub.aitravel.ui.plan

import com.heoclub.aitravel.data.model.PlanDay
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.TravelPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PlanSearchTest {
    private val tianjinPlan = travelPlan(
        id = "plan-tj",
        title = "天津周末漫游",
        destination = "天津市",
        dateRange = "07.23 - 07.25",
        preferences = listOf("citywalk", "美食"),
        items = listOf(
            planItem(id = "item-eye", name = "天津之眼", typeName = "风景名胜", address = "河北区海河沿岸"),
            planItem(id = "item-hotpot", name = "海底捞火锅", typeName = "火锅店", note = "晚饭备选"),
        ),
    )
    private val beijingPlan = travelPlan(
        id = "plan-bj",
        title = "北京三日",
        destination = "北京市",
        dateRange = "08.01 - 08.03",
        preferences = listOf("历史"),
        items = listOf(
            planItem(id = "item-palace", name = "故宫博物院", typeName = "博物馆", address = "东城区景山前街4号"),
        ),
    )
    private val plans = listOf(tianjinPlan, beijingPlan)

    @Test
    fun `blank keyword matches nothing`() {
        val results = searchPlansAndPlaces(plans, "   ")

        assertTrue(results.isEmpty)
    }

    @Test
    fun `matches plan by title destination and preference`() {
        assertEquals(listOf("plan-tj"), searchPlansAndPlaces(plans, "漫游").plans.map { it.id })
        assertEquals(listOf("plan-bj"), searchPlansAndPlaces(plans, "北京市").plans.map { it.id })
        assertEquals(listOf("plan-tj"), searchPlansAndPlaces(plans, "citywalk").plans.map { it.id })
        assertEquals(listOf("plan-tj"), searchPlansAndPlaces(plans, "07.23").plans.map { it.id })
    }

    @Test
    fun `matches plan items by name address and note`() {
        val byName = searchPlansAndPlaces(plans, "天津之眼")
        assertEquals(listOf("item-eye"), byName.places.map { it.item.id })
        assertEquals("天津周末漫游", byName.places.single().planTitle)

        assertEquals(listOf("item-palace"), searchPlansAndPlaces(plans, "景山前街").places.map { it.item.id })
        assertEquals(listOf("item-hotpot"), searchPlansAndPlaces(plans, "晚饭").places.map { it.item.id })
    }

    @Test
    fun `keyword can match both a plan and items across plans`() {
        val results = searchPlansAndPlaces(plans, "天津")

        assertEquals(listOf("plan-tj"), results.plans.map { it.id })
        assertEquals(listOf("item-eye"), results.places.map { it.item.id })
    }

    @Test
    fun `search is case insensitive and covers unplanned items`() {
        val plan = travelPlan(
            id = "plan-x",
            title = "待定行程",
            destination = "上海市",
            dateRange = "09.01 - 09.02",
            preferences = emptyList(),
            items = emptyList(),
            unplannedItems = listOf(planItem(id = "item-bund", name = "The Bund", typeName = "风景名胜")),
        )

        val results = searchPlansAndPlaces(listOf(plan), "the bund")

        assertEquals(listOf("item-bund"), results.places.map { it.item.id })
    }
}

private fun travelPlan(
    id: String,
    title: String,
    destination: String,
    dateRange: String,
    preferences: List<String>,
    items: List<PlanItem>,
    unplannedItems: List<PlanItem> = emptyList(),
): TravelPlan {
    return TravelPlan(
        id = id,
        title = title,
        destination = destination,
        dateRange = dateRange,
        dayCount = 1,
        preferences = preferences,
        createdAt = 0L,
        days = listOf(PlanDay(id = "day-1", dayIndex = 1, title = "DAY 1", items = items)),
        unplannedItems = unplannedItems,
    )
}

private fun planItem(
    id: String,
    name: String,
    typeName: String? = null,
    address: String? = null,
    note: String? = null,
): PlanItem {
    return PlanItem(
        id = id,
        source = "AMAP",
        sourcePoiId = id,
        name = name,
        category = "scenic",
        categoryCode = "scenic",
        typeName = typeName,
        address = address,
        dayId = "day-1",
        dayIndex = 1,
        visitOrder = 1,
        note = note,
    )
}
