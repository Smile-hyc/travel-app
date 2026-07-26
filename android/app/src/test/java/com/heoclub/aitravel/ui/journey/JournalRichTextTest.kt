package com.heoclub.aitravel.ui.journey

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextRange
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JournalRichTextTest {
    private val base = JournalTextStyle(textColor = Color.Black)

    @Test
    fun `bold applies only to selected text`() {
        val spans = transformJournalSelection(
            textLength = 6,
            spans = emptyList(),
            selection = TextRange(1, 4),
            base = base,
        ) { it.copy(bold = true) }

        assertFalse(styleAt(0, base, spans).bold)
        assertTrue(styleAt(1, base, spans).bold)
        assertTrue(styleAt(3, base, spans).bold)
        assertFalse(styleAt(4, base, spans).bold)
    }

    @Test
    fun `editing before a styled selection shifts its range`() {
        val spans = listOf(JournalTextSpan(2, 4, base.copy(underline = true)))

        val adjusted = adjustJournalSpansForEdit("abcdef", "XXabcdef", spans)

        assertEquals(4, adjusted.single().start)
        assertEquals(6, adjusted.single().end)
    }
}
