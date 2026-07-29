package com.heoclub.aitravel.ui.components

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MarkdownInternalLinkTest {
    @Test
    fun parsesAmapPlaceIdFromInternalLink() {
        assertEquals("amap:B001", internalPlaceId("aitravel://place/amap:B001"))
    }

    @Test
    fun decodesEscapedPlaceIdAndRejectsWebLinks() {
        assertEquals("amap:天津之眼", internalPlaceId("aitravel://place/amap%3A%E5%A4%A9%E6%B4%A5%E4%B9%8B%E7%9C%BC"))
        assertNull(internalPlaceId("https://example.com/place"))
    }

    @Test
    fun removesBoldWrapperWithoutDuplicatingInternalLink() {
        val source = "**[古丽花儿(西北角店)](aitravel://place/amap:B001)**"

        assertEquals(
            "[古丽花儿(西北角店)](aitravel://place/amap:B001)",
            normalizeInternalPlaceLinks(source),
        )
    }

    @Test
    fun removesWholeLineBoldWrapperAroundNumberedInternalLink() {
        val source = "**1. [庄氏隆兴·非遗蟹点(上海首店)](aitravel://place/amap:B001)**"

        assertEquals(
            "1. [庄氏隆兴·非遗蟹点(上海首店)](aitravel://place/amap:B001)",
            normalizeInternalPlaceLinks(source),
        )
    }

    @Test
    fun removesDuplicateBoldNameRawUrlAndRepeatedLink() {
        val link = "[耳朵眼会馆](aitravel://place/amap:B001)"
        val source = "**耳朵眼会馆** (aitravel://place/amap:B001) $link 耳朵眼会馆 $link"

        assertEquals(link, normalizeInternalPlaceLinks(source))
    }
}
