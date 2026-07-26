package com.heoclub.aitravel.ui.explore

import org.junit.Assert.assertEquals
import org.junit.Test

class ExploreCityAdCodeTest {
    @Test
    fun `municipality district location searches the whole municipality`() {
        assertEquals("120000", normalizeSearchCityAdCode("120112"))
    }

    @Test
    fun `ordinary city district location searches the whole prefecture city`() {
        assertEquals("510100", normalizeSearchCityAdCode("510107"))
    }

    @Test
    fun `city adcode remains unchanged`() {
        assertEquals("330100", normalizeSearchCityAdCode("330100"))
    }
}
