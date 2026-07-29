package com.heoclub.aitravel.data.model

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PlanDateMatcherTest {
    @Test
    fun `finds day in compact app date range`() {
        assertEquals(1, dayIndexForDate("07.23 - 07.25", LocalDate.of(2026, 7, 23)))
        assertEquals(3, dayIndexForDate("07.23 - 07.25", LocalDate.of(2026, 7, 25)))
    }

    @Test
    fun `supports chinese and full year date ranges`() {
        assertEquals(2, dayIndexForDate("7月23日 - 7月25日", LocalDate.of(2026, 7, 24)))
        assertEquals(2, dayIndexForDate("2026-07-23 - 2026-07-25", LocalDate.of(2026, 7, 24)))
    }

    @Test
    fun `returns null outside plan range`() {
        assertNull(dayIndexForDate("07.24 - 07.25", LocalDate.of(2026, 7, 23)))
    }
}
