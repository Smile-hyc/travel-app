package com.heoclub.aitravel.ui.components

import android.content.Context
import android.graphics.Bitmap
import androidx.core.graphics.drawable.toBitmap
import coil.imageLoader
import coil.request.ImageRequest
import coil.request.SuccessResult

internal suspend fun loadMapMarkerImage(
    context: Context,
    imageUrl: String?,
    sizePx: Int,
): Bitmap? {
    val url = imageUrl?.trim()?.takeIf { it.startsWith("http://") || it.startsWith("https://") }
        ?: return null
    val request = ImageRequest.Builder(context)
        .data(url)
        .size(sizePx, sizePx)
        .allowHardware(false)
        .build()
    val result = runCatching { context.imageLoader.execute(request) }.getOrNull() as? SuccessResult
        ?: return null
    return result.drawable.toBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
}
