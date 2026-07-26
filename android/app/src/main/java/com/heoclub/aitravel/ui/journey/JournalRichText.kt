package com.heoclub.aitravel.ui.journey

import androidx.compose.ui.text.TextRange

internal fun styleAt(
    offset: Int,
    base: JournalTextStyle,
    spans: List<JournalTextSpan>,
): JournalTextStyle = spans.lastOrNull { offset >= it.start && offset < it.end }?.style ?: base

internal fun transformJournalSelection(
    textLength: Int,
    spans: List<JournalTextSpan>,
    selection: TextRange,
    base: JournalTextStyle,
    transform: (JournalTextStyle) -> JournalTextStyle,
): List<JournalTextSpan> {
    val selectedStart = selection.min.coerceIn(0, textLength)
    val selectedEnd = selection.max.coerceIn(selectedStart, textLength)
    if (selectedStart == selectedEnd) return spans

    val boundaries = buildSet {
        add(0)
        add(textLength)
        add(selectedStart)
        add(selectedEnd)
        spans.forEach {
            add(it.start.coerceIn(0, textLength))
            add(it.end.coerceIn(0, textLength))
        }
    }.sorted()

    val result = mutableListOf<JournalTextSpan>()
    boundaries.zipWithNext().forEach { (start, end) ->
        if (start == end) return@forEach
        val current = styleAt(start, base, spans)
        val next = if (start >= selectedStart && end <= selectedEnd) transform(current) else current
        if (next != base) {
            val previous = result.lastOrNull()
            if (previous != null && previous.end == start && previous.style == next) {
                result[result.lastIndex] = previous.copy(end = end)
            } else {
                result += JournalTextSpan(start, end, next)
            }
        }
    }
    return result
}

internal fun adjustJournalSpansForEdit(
    oldText: String,
    newText: String,
    spans: List<JournalTextSpan>,
): List<JournalTextSpan> {
    if (oldText == newText || spans.isEmpty()) return spans
    val prefix = oldText.indices.firstOrNull { it >= newText.length || oldText[it] != newText[it] }
        ?: minOf(oldText.length, newText.length)
    var suffix = 0
    while (
        suffix < oldText.length - prefix &&
        suffix < newText.length - prefix &&
        oldText[oldText.lastIndex - suffix] == newText[newText.lastIndex - suffix]
    ) suffix++
    val oldEnd = oldText.length - suffix
    val newEnd = newText.length - suffix
    val delta = newEnd - oldEnd

    return spans.mapNotNull { span ->
        when {
            span.end <= prefix -> span
            span.start >= oldEnd -> span.copy(start = span.start + delta, end = span.end + delta)
            else -> {
                val start = minOf(span.start, prefix)
                val end = maxOf(prefix, span.end + delta).coerceAtMost(newText.length)
                if (start < end) span.copy(start = start, end = end) else null
            }
        }
    }
}
