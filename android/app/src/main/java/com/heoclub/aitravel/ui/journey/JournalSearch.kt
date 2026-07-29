package com.heoclub.aitravel.ui.journey

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import java.util.Locale

internal fun journalSearchTerms(query: String): List<String> = query
    .trim()
    .split(Regex("\\s+"))
    .map { it.trim() }
    .filter { it.isNotEmpty() }
    .distinctBy { it.lowercase(Locale.ROOT) }

internal fun JournalEntry.matchesSearchQuery(query: String): Boolean {
    val terms = journalSearchTerms(query)
    if (terms.isEmpty()) return true
    val dateText = "${date} ${date.year}年${date.monthValue}月${date.dayOfMonth}日"
    val searchableText = buildString {
        append(title)
        append('\n')
        append(body)
        append('\n')
        append(location)
        append('\n')
        append(dateText)
        photos.forEach {
            append('\n')
            append(it.label)
        }
    }
    return terms.all { searchableText.contains(it, ignoreCase = true) }
}

internal fun buildJournalSearchAnnotatedString(
    text: String,
    spans: List<JournalTextSpan>,
    query: String,
): AnnotatedString {
    val builder = AnnotatedString.Builder(buildJournalAnnotatedString(text, spans))
    journalSearchTerms(query).forEach { term ->
        var start = text.indexOf(term, ignoreCase = true)
        while (start >= 0) {
            builder.addStyle(
                SpanStyle(background = Color(0xFFFFE58A)),
                start,
                start + term.length,
            )
            start = text.indexOf(term, startIndex = start + term.length, ignoreCase = true)
        }
    }
    return builder.toAnnotatedString()
}
