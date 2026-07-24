package com.heoclub.aitravel.data.model

import java.time.LocalDate
import java.time.temporal.ChronoUnit

data class PlanDateMatch(
    val plan: TravelPlan,
    val dayIndex: Int,
)

fun findPlanForDate(
    plans: List<TravelPlan>,
    date: LocalDate = LocalDate.now(),
): PlanDateMatch? {
    return plans.firstNotNullOfOrNull { plan ->
        dayIndexForDate(plan.dateRange, date)?.let { dayIndex ->
            PlanDateMatch(plan = plan, dayIndex = dayIndex)
        }
    }
}

fun dayIndexForDate(dateRange: String, date: LocalDate = LocalDate.now()): Int? {
    val range = parsePlanDateRange(dateRange, date) ?: return null
    if (date.isBefore(range.first) || date.isAfter(range.second)) return null
    return ChronoUnit.DAYS.between(range.first, date).toInt() + 1
}

fun parsePlanDateRange(dateRange: String, referenceDate: LocalDate = LocalDate.now()): Pair<LocalDate, LocalDate>? {
    val fullDates = Regex("(\\d{4})[年./-](\\d{1,2})[月./-](\\d{1,2})(?:日)?")
        .findAll(dateRange)
        .mapNotNull { match ->
            localDateOrNull(
                match.groupValues[1].toInt(),
                match.groupValues[2].toInt(),
                match.groupValues[3].toInt(),
            )
        }
        .toList()
    if (fullDates.isNotEmpty()) {
        val start = fullDates.first()
        val end = fullDates.getOrElse(1) { start }
        return if (end >= start) start to end else null
    }

    val monthDays = Regex("(?<!\\d)(\\d{1,2})[月.](\\d{1,2})(?:日)?")
        .findAll(dateRange)
        .mapNotNull { match ->
            val month = match.groupValues[1].toInt()
            val day = match.groupValues[2].toInt()
            if (month in 1..12 && day in 1..31) month to day else null
        }
        .toList()
    if (monthDays.isEmpty()) return null

    val (startMonth, startDay) = monthDays.first()
    val start = localDateOrNull(referenceDate.year, startMonth, startDay) ?: return null
    val (endMonth, endDay) = monthDays.getOrElse(1) { monthDays.first() }
    var end = localDateOrNull(referenceDate.year, endMonth, endDay) ?: return null
    if (end < start) {
        end = localDateOrNull(referenceDate.year + 1, endMonth, endDay) ?: return null
    }
    return start to end
}

private fun localDateOrNull(year: Int, month: Int, day: Int): LocalDate? {
    return runCatching { LocalDate.of(year, month, day) }.getOrNull()
}
