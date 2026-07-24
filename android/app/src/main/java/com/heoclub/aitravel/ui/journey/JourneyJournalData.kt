package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import androidx.compose.ui.graphics.Color
import java.time.LocalDate

internal data class JournalPhoto(
    val bitmap: Bitmap? = null,
    val label: String,
    val color: Color,
)

internal data class JournalTextStyle(
    val bold: Boolean = false,
    val underline: Boolean = false,
    val highlighted: Boolean = false,
    val textColor: Color = Color(0xFF26384D),
    val highlightColor: Color = Color(0xFFFFF0A8),
)

internal data class JournalEntry(
    val id: String,
    val date: LocalDate,
    val title: String,
    val titleColor: Color = Color(0xFF081F3A),
    val titleStyle: JournalTextStyle = JournalTextStyle(bold = true, textColor = titleColor),
    val location: String,
    val body: String,
    val bodyStyle: JournalTextStyle = JournalTextStyle(),
    val photos: List<JournalPhoto>,
)
