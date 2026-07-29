package com.heoclub.aitravel.ui.journey

import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class JournalSearchTest {
    private val entry = JournalEntry(
        id = "journal-1",
        date = LocalDate.of(2026, 7, 26),
        title = "天津城市漫步",
        location = "和平区五大道",
        body = "傍晚去了民园广场，建筑很好看",
        photos = listOf(JournalPhoto(label = "夜景照片", color = Color.White)),
    )

    @Test
    fun `search covers title body location date and photo label`() {
        assertTrue(entry.matchesSearchQuery("城市漫步"))
        assertTrue(entry.matchesSearchQuery("民园广场"))
        assertTrue(entry.matchesSearchQuery("五大道"))
        assertTrue(entry.matchesSearchQuery("2026-07-26"))
        assertTrue(entry.matchesSearchQuery("夜景"))
    }

    @Test
    fun `multiple terms can match different journal fields`() {
        assertTrue(entry.matchesSearchQuery("天津  五大道  民园"))
        assertFalse(entry.matchesSearchQuery("天津 成都"))
    }

    @Test
    fun `blank search keeps every entry`() {
        assertTrue(entry.matchesSearchQuery("   "))
    }
}
