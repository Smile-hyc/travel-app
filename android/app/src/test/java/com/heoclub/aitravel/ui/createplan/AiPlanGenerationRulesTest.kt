package com.heoclub.aitravel.ui.createplan

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

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
}
