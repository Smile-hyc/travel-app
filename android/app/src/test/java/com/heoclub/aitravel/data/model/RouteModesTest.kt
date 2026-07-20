package com.heoclub.aitravel.data.model

import org.junit.Assert.assertEquals
import org.junit.Test

class RouteModesTest {
    @Test
    fun `transit label reflects locally returned route steps`() {
        val steps = listOf(
            RouteStep(instruction = "乘坐地铁 2 号线"),
            RouteStep(instruction = "换乘快速公交 1 线"),
        )

        assertEquals("地铁 + 公交", RouteModes.label(RouteModes.TRANSIT, steps))
    }

    @Test
    fun `transit without route details uses truthful generic label`() {
        assertEquals("公共交通", RouteModes.label(RouteModes.TRANSIT))
    }
}
