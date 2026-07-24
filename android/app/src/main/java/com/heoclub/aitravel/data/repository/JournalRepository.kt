package com.heoclub.aitravel.data.repository

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.heoclub.aitravel.data.model.UserJournalCreateRequest
import com.heoclub.aitravel.data.model.UserJournalResponse
import com.heoclub.aitravel.data.model.UserJournalUpdateRequest
import com.heoclub.aitravel.data.remote.ApiService
import com.heoclub.aitravel.ui.journey.JournalEntry
import com.heoclub.aitravel.ui.journey.JournalPhoto
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

/** Minimal photo metadata stored in JSON (no bitmap — those stay local). */
data class JournalPhotoMeta(
    val label: String = "",
    val colorHex: String = "",
)

internal fun UserJournalResponse.toJournalEntry(): JournalEntry = JournalEntry(
    id = id,
    date = date.takeIf { it.isNotBlank() }?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now(),
    title = title,
    location = location,
    body = body,
    photos = runCatching { gson.fromJson<List<JournalPhotoMeta>>(photos, photoListType) }
        .getOrDefault(emptyList())
        .map { JournalPhoto(label = it.label, color = parseColorHex(it.colorHex)) },
)

internal fun JournalEntry.toCreateRequest(): UserJournalCreateRequest = UserJournalCreateRequest(
    title = title,
    location = location,
    date = date.toString(),
    body = body,
    photos = gson.toJson(photos.map { JournalPhotoMeta(label = it.label, colorHex = colorToHex(it.color)) }),
)

internal fun JournalEntry.toUpdateRequest(): UserJournalUpdateRequest = UserJournalUpdateRequest(
    title = title,
    location = location,
    date = date.toString(),
    body = body,
    photos = gson.toJson(photos.map { JournalPhotoMeta(label = it.label, colorHex = colorToHex(it.color)) }),
)

private fun parseColorHex(hex: String): androidx.compose.ui.graphics.Color {
    if (hex.isBlank()) return androidx.compose.ui.graphics.Color.Unspecified
    return runCatching {
        val h = hex.removePrefix("#")
        val argb = h.toLong(16)
        androidx.compose.ui.graphics.Color(argb.toULong())
    }.getOrDefault(androidx.compose.ui.graphics.Color.Unspecified)
}

private fun colorToHex(color: androidx.compose.ui.graphics.Color): String {
    val r = (color.red * 255).toInt().coerceIn(0, 255)
    val g = (color.green * 255).toInt().coerceIn(0, 255)
    val b = (color.blue * 255).toInt().coerceIn(0, 255)
    return "#%02X%02X%02X".format(r, g, b)
}
