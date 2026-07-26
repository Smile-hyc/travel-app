package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import java.time.LocalDate

internal data class JournalPhoto(
    val bitmap: Bitmap? = null,
    val label: String,
    val color: Color,
    val storedFileName: String? = null,
)

internal data class JournalTextStyle(
    val bold: Boolean = false,
    val underline: Boolean = false,
    val highlighted: Boolean = false,
    val textColor: Color = Color(0xFF26384D),
    val highlightColor: Color = Color(0xFFFFF0A8),
)

internal data class JournalTextSpan(
    val start: Int,
    val end: Int,
    val style: JournalTextStyle,
)

internal data class JournalEntry(
    val id: String,
    val date: LocalDate,
    val title: String,
    val titleColor: Color = Color(0xFF081F3A),
    val titleStyle: JournalTextStyle = JournalTextStyle(bold = true, textColor = titleColor),
    val titleSpans: List<JournalTextSpan> = emptyList(),
    val location: String,
    val body: String,
    val bodyStyle: JournalTextStyle = JournalTextStyle(),
    val bodySpans: List<JournalTextSpan> = emptyList(),
    val photos: List<JournalPhoto>,
)

internal fun buildJournalAnnotatedString(
    text: String,
    spans: List<JournalTextSpan>,
): AnnotatedString = AnnotatedString.Builder(text).apply {
    spans.forEach { span ->
        val start = span.start.coerceIn(0, text.length)
        val end = span.end.coerceIn(start, text.length)
        if (start < end) {
            addStyle(
                SpanStyle(
                    color = span.style.textColor,
                    fontWeight = if (span.style.bold) FontWeight.Bold else FontWeight.Normal,
                    textDecoration = if (span.style.underline) TextDecoration.Underline else TextDecoration.None,
                    background = if (span.style.highlighted) span.style.highlightColor else Color.Transparent,
                ),
                start,
                end,
            )
        }
    }
}.toAnnotatedString()
