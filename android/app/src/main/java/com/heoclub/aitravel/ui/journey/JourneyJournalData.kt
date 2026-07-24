package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import androidx.compose.ui.graphics.Color
import java.time.LocalDate

internal data class JournalPhoto(
    val bitmap: Bitmap? = null,
    val label: String,
    val color: Color,
)

internal data class JournalEntry(
    val id: String,
    val date: LocalDate,
    val title: String,
    val location: String,
    val body: String,
    val photos: List<JournalPhoto>,
)
