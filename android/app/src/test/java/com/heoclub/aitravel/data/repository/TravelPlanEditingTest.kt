package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.PlanDay
import com.heoclub.aitravel.data.model.PlanItem
import com.heoclub.aitravel.data.model.RouteModes
import com.heoclub.aitravel.data.model.TravelPlan
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TravelPlanEditingTest {
    @Test
    fun `all user edits persist and keep normalized order`() {
        var persisted: List<TravelPlan> = emptyList()
        val repository = InMemoryTravelPlanRepository(
            initialPlans = listOf(samplePlan()),
            onPlansChanged = { persisted = it },
            seedDefaultPlanWhenEmpty = false,
        )

        repository.updatePlanTitle("plan-1", "我的上海行程")
        repository.updateDayTitle("plan-1", 1, "DAY 1 · 静安漫步")
        repository.updatePlanItemVisitTime("plan-1", 1, "p1", "09:30", "10:45")
        repository.updateTransportModeToNext("plan-1", 1, "p1", RouteModes.TRANSIT)
        repository.applyOptimizedOrder("plan-1", 1, listOf("p2", "p1"))
        repository.movePlanItemToDay("plan-1", "p1", 2)

        val edited = repository.getPlan("plan-1")!!
        assertEquals("我的上海行程", edited.title)
        assertEquals("DAY 1 · 静安漫步", edited.days.first().title)
        assertEquals(listOf("p2"), edited.days[0].items.map { it.id })
        assertEquals(listOf("p1"), edited.days[1].items.map { it.id })
        assertEquals(1, edited.days[1].items.single().visitOrder)
        assertEquals("09:30", edited.days[1].items.single().suggestedStart)
        assertEquals("10:45", edited.days[1].items.single().suggestedEnd)
        assertEquals(RouteModes.TRANSIT, edited.days[1].items.single().transportModeToNext)
        assertTrue(edited.revision > 1L)
        assertEquals(edited, persisted.first())

        repository.removePlanItem("plan-1", "p1")
        assertNull(repository.getPlan("plan-1")!!.days[1].items.firstOrNull())
    }

    @Test
    fun `editing date range resizes days without losing removed day places`() {
        val original = samplePlan().let { plan ->
            plan.copy(
                days = plan.days.map { day ->
                    if (day.dayIndex == 2) {
                        day.copy(items = listOf(sampleItem("p3", "上海博物馆", day.id, 2, 1)))
                    } else {
                        day
                    }
                },
            )
        }
        val repository = InMemoryTravelPlanRepository(
            initialPlans = listOf(original),
            seedDefaultPlanWhenEmpty = false,
        )

        repository.updatePlanDateRange("plan-1", "07.23 - 07.23", 1)

        val shortened = repository.getPlan("plan-1")!!
        assertEquals(1, shortened.dayCount)
        assertEquals(1, shortened.days.size)
        assertEquals("p3", shortened.unplannedItems.single().id)
        assertEquals(0, shortened.unplannedItems.single().dayIndex)

        repository.updatePlanDateRange("plan-1", "07.23 - 07.25", 3)
        val extended = repository.getPlan("plan-1")!!
        assertEquals(3, extended.days.size)
        assertEquals("DAY 3", extended.days.last().title)
        assertEquals("p3", extended.unplannedItems.single().id)
    }

    private fun samplePlan(): TravelPlan {
        val firstDay = PlanDay(
            id = "day-1",
            dayIndex = 1,
            title = "DAY 1 · 静安区",
            items = listOf(sampleItem("p1", "外滩", "day-1", 1, 1), sampleItem("p2", "豫园", "day-1", 1, 2)),
        )
        val secondDay = PlanDay(id = "day-2", dayIndex = 2, title = "DAY 2 · 黄浦区")
        return TravelPlan(
            id = "plan-1",
            title = "上海 2 日智能行程",
            destination = "上海",
            dateRange = "07.23 - 07.24",
            dayCount = 2,
            preferences = listOf("智能规划"),
            createdAt = 1L,
            revision = 1L,
            updatedAt = 1L,
            days = listOf(firstDay, secondDay),
        )
    }

    private fun sampleItem(
        id: String,
        name: String,
        dayId: String,
        dayIndex: Int,
        visitOrder: Int,
    ): PlanItem {
        return PlanItem(
            id = id,
            source = "AMAP",
            sourcePoiId = id,
            name = name,
            category = "scenic",
            categoryCode = "scenic",
            latitude = 31.2,
            longitude = 121.4,
            dayId = dayId,
            dayIndex = dayIndex,
            visitOrder = visitOrder,
        )
    }
}
