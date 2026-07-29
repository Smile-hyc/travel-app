package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.UserJournalResponse
import org.junit.Assert.assertEquals
import org.junit.Test

class JournalRepositoryTest {
    @Test
    fun `cloud RGB photo color remains valid when alpha is copied`() {
        val photo = journalWithColor("#D9E8F7").toJournalEntry().photos.single()

        val translucent = photo.color.copy(alpha = 0.85f)

        assertEquals(217f / 255f, translucent.red, 0.001f)
        assertEquals(232f / 255f, translucent.green, 0.001f)
        assertEquals(247f / 255f, translucent.blue, 0.001f)
        assertEquals(0.85f, translucent.alpha, 0.001f)
    }

    @Test
    fun `invalid cloud photo color falls back to a safe color`() {
        val photo = journalWithColor("not-a-color").toJournalEntry().photos.single()

        val translucent = photo.color.copy(alpha = 0.85f)

        assertEquals(0.85f, translucent.alpha, 0.001f)
    }

    @Test
    fun `cloud photo metadata keeps its private storage file name`() {
        val photo = UserJournalResponse(
            id = "journal-photo",
            userId = "user-1",
            title = "天津游记",
            location = "天津市",
            date = "2026-07-26",
            body = "",
            photos = """[{"label":"相册 1","colorHex":"#D9E8F7","storedFileName":"journal-photo.jpg"}]""",
            createdAt = "2026-07-26T00:00:00",
            updatedAt = "2026-07-26T00:00:00",
        ).toJournalEntry().photos.single()

        assertEquals("journal-photo.jpg", photo.storedFileName)
    }

    @Test
    fun `rich text spans survive cloud metadata round trip`() {
        val entry = UserJournalResponse(
            id = "journal-rich",
            userId = "user-1",
            title = "天津之旅",
            location = "天津市",
            date = "2026-07-26",
            body = "五大道很好看",
            photos = """{"photos":[],"titleSpans":[{"start":0,"end":2,"bold":true,"textColorHex":"#E15A68","highlightColorHex":"#FFF0A8"}],"bodySpans":[]}""",
            createdAt = "2026-07-26T00:00:00",
            updatedAt = "2026-07-26T00:00:00",
        ).toJournalEntry()

        assertEquals(1, entry.titleSpans.size)
        assertEquals(0, entry.titleSpans.single().start)
        assertEquals(2, entry.titleSpans.single().end)
        assertEquals(true, entry.titleSpans.single().style.bold)
        assertEquals(225f / 255f, entry.titleSpans.single().style.textColor.red, 0.001f)
    }

    private fun journalWithColor(colorHex: String) = UserJournalResponse(
        id = "journal-1",
        userId = "user-1",
        title = "天津游记",
        location = "天津市",
        date = "2026-07-26",
        body = "",
        photos = """[{"label":"随手拍","colorHex":"$colorHex"}]""",
        createdAt = "2026-07-26T00:00:00",
        updatedAt = "2026-07-26T00:00:00",
    )
}
