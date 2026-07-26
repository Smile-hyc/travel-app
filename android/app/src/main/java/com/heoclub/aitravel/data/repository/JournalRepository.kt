package com.heoclub.aitravel.data.repository

import com.google.gson.Gson
import com.google.gson.JsonParser
import com.google.gson.reflect.TypeToken
import com.heoclub.aitravel.data.model.UserJournalCreateRequest
import com.heoclub.aitravel.data.model.UserJournalResponse
import com.heoclub.aitravel.data.model.UserJournalUpdateRequest
import com.heoclub.aitravel.data.remote.ApiService
import com.heoclub.aitravel.ui.journey.JournalEntry
import com.heoclub.aitravel.ui.journey.JournalPhoto
import com.heoclub.aitravel.ui.journey.JournalTextSpan
import com.heoclub.aitravel.ui.journey.JournalTextStyle
import java.time.LocalDate

class JournalRepository(
    private val apiService: ApiService,
) {
    suspend fun getJournals(): Result<List<UserJournalResponse>> = runCatching {
        apiService.getUserJournals()
    }

    suspend fun createJournal(request: UserJournalCreateRequest): Result<UserJournalResponse> = runCatching {
        apiService.createUserJournal(request)
    }

    suspend fun updateJournal(id: String, request: UserJournalUpdateRequest): Result<UserJournalResponse> = runCatching {
        apiService.updateUserJournal(id, request)
    }

    suspend fun deleteJournal(id: String): Result<Unit> = runCatching {
        apiService.deleteUserJournal(id)
    }
}

// ── Conversion helpers between API models and UI JournalEntry ──

private val gson = Gson()
private val photoListType = object : TypeToken<List<JournalPhotoMeta>>() {}.type
private val defaultJournalPhotoColor = androidx.compose.ui.graphics.Color(0xFFD9E8F7)

/** Minimal photo metadata stored in JSON (no bitmap — those stay local). */
data class JournalPhotoMeta(
    val label: String = "",
    val colorHex: String = "",
    val storedFileName: String? = null,
)

data class JournalTextSpanMeta(
    val start: Int = 0,
    val end: Int = 0,
    val bold: Boolean = false,
    val underline: Boolean = false,
    val highlighted: Boolean = false,
    val textColorHex: String = "",
    val highlightColorHex: String = "",
)

data class JournalDocumentMeta(
    val photos: List<JournalPhotoMeta> = emptyList(),
    val titleSpans: List<JournalTextSpanMeta> = emptyList(),
    val bodySpans: List<JournalTextSpanMeta> = emptyList(),
)

private fun parseDocumentMeta(raw: String): JournalDocumentMeta = runCatching {
    val root = JsonParser.parseString(raw)
    if (root.isJsonArray) {
        JournalDocumentMeta(photos = gson.fromJson(root, photoListType))
    } else {
        gson.fromJson(root, JournalDocumentMeta::class.java) ?: JournalDocumentMeta()
    }
}.getOrDefault(JournalDocumentMeta())

internal fun UserJournalResponse.toJournalEntry(photoStore: JournalPhotoStore? = null): JournalEntry {
    val document = parseDocumentMeta(photos)
    return JournalEntry(
    id = id,
    date = date.takeIf { it.isNotBlank() }?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now(),
    title = title,
    location = location,
    body = body,
    photos = document.photos
        .map {
            JournalPhoto(
                bitmap = photoStore?.load(it.storedFileName),
                label = it.label,
                color = parseColorHex(it.colorHex),
                storedFileName = it.storedFileName,
            )
        },
    titleSpans = document.titleSpans.mapNotNull(::toTextSpan),
    bodySpans = document.bodySpans.mapNotNull(::toTextSpan),
    )
}

internal fun JournalEntry.toCreateRequest(): UserJournalCreateRequest = UserJournalCreateRequest(
    title = title,
    location = location,
    date = date.toString(),
    body = body,
    photos = gson.toJson(toDocumentMeta()),
)

internal fun JournalEntry.toUpdateRequest(): UserJournalUpdateRequest = UserJournalUpdateRequest(
    title = title,
    location = location,
    date = date.toString(),
    body = body,
    photos = gson.toJson(toDocumentMeta()),
)

private fun JournalEntry.toDocumentMeta() = JournalDocumentMeta(
    photos = photos.map {
        JournalPhotoMeta(
            label = it.label,
            colorHex = colorToHex(it.color),
            storedFileName = it.storedFileName,
        )
    },
    titleSpans = titleSpans.map(::toTextSpanMeta),
    bodySpans = bodySpans.map(::toTextSpanMeta),
)

private fun toTextSpanMeta(span: JournalTextSpan) = JournalTextSpanMeta(
    start = span.start,
    end = span.end,
    bold = span.style.bold,
    underline = span.style.underline,
    highlighted = span.style.highlighted,
    textColorHex = colorToHex(span.style.textColor),
    highlightColorHex = colorToHex(span.style.highlightColor),
)

private fun toTextSpan(meta: JournalTextSpanMeta): JournalTextSpan? {
    if (meta.start < 0 || meta.end <= meta.start) return null
    return JournalTextSpan(
        start = meta.start,
        end = meta.end,
        style = JournalTextStyle(
            bold = meta.bold,
            underline = meta.underline,
            highlighted = meta.highlighted,
            textColor = parseColorHex(meta.textColorHex),
            highlightColor = parseColorHex(meta.highlightColorHex.ifBlank { "#FFF0A8" }),
        ),
    )
}

private fun parseColorHex(hex: String): androidx.compose.ui.graphics.Color {
    if (hex.isBlank()) return defaultJournalPhotoColor
    return runCatching {
        val h = hex.removePrefix("#")
        val argb = when (h.length) {
            6 -> 0xFF000000L or h.toLong(16)
            8 -> h.toLong(16)
            else -> error("Unsupported journal photo color: $hex")
        }
        // Color(ULong) expects Compose's packed wide-gamut representation.
        // Journal metadata stores ordinary #RRGGBB/#AARRGGBB values instead.
        androidx.compose.ui.graphics.Color(argb.toInt())
    }.getOrDefault(defaultJournalPhotoColor)
}

private fun colorToHex(color: androidx.compose.ui.graphics.Color): String {
    val r = (color.red * 255).toInt().coerceIn(0, 255)
    val g = (color.green * 255).toInt().coerceIn(0, 255)
    val b = (color.blue * 255).toInt().coerceIn(0, 255)
    return "#%02X%02X%02X".format(r, g, b)
}
