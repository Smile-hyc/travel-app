package com.heoclub.aitravel.ui.journey

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.IosShare
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
import java.time.format.DateTimeFormatter
import kotlin.math.max
import android.graphics.Color as AndroidColor

@Composable
internal fun JourneyJournalShareScreen(
    entry: JournalEntry,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var backgroundBitmap by remember { mutableStateOf<Bitmap?>(entry.photos.firstOrNull()?.bitmap) }
    var blur by remember { mutableFloatStateOf(0f) }
    var brightness by remember { mutableFloatStateOf(1f) }
    var generatedBitmap by remember(entry, backgroundBitmap, blur, brightness) {
        mutableStateOf(createJournalShareBitmap(entry, backgroundBitmap, blur, brightness))
    }
    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) {
            val bitmap = decodeBitmapFromUri(context, uri)
            if (bitmap != null) {
                backgroundBitmap = bitmap
                generatedBitmap = createJournalShareBitmap(entry, bitmap, blur, brightness)
            } else {
                Toast.makeText(context, "背景图读取失败", Toast.LENGTH_SHORT).show()
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF6F8FB))
            .verticalScroll(rememberScrollState()),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(
                onClick = onBack,
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(Color.White),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Outlined.ArrowBack,
                    contentDescription = "返回",
                    tint = Color(0xFF10243D),
                )
            }
            Spacer(modifier = Modifier.width(10.dp))
            Text(
                text = "分享发布",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.ExtraBold,
                color = Color(0xFF081F3A),
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { imagePicker.launch("image/*") }) {
                Icon(
                    imageVector = Icons.Outlined.Image,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Text("背景")
            }
        }

        Column(
            modifier = Modifier.padding(PaddingValues(start = 18.dp, end = 18.dp, bottom = 28.dp)),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(30.dp),
                color = Color.White,
                shadowElevation = 5.dp,
            ) {
                Image(
                    bitmap = generatedBitmap.asImageBitmap(),
                    contentDescription = "分享图片预览",
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp)
                        .clip(RoundedCornerShape(24.dp)),
                    contentScale = ContentScale.FillWidth,
                )
            }

            ShareSliderCard(
                title = "背景模糊",
                value = blur,
                range = 0f..18f,
                display = "${blur.toInt()}",
                onValueChange = {
                    blur = it
                    generatedBitmap = createJournalShareBitmap(entry, backgroundBitmap, it, brightness)
                },
            )
            ShareSliderCard(
                title = "背景亮度",
                value = brightness,
                range = 0.62f..1.35f,
                display = "${(brightness * 100).toInt()}%",
                onValueChange = {
                    brightness = it
                    generatedBitmap = createJournalShareBitmap(entry, backgroundBitmap, blur, it)
                },
            )

            Button(
                onClick = {
                    shareBitmap(context, generatedBitmap)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(54.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                Icon(
                    imageVector = Icons.Outlined.IosShare,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text("生成图片并分享")
            }
        }
    }
}

@Composable
private fun ShareSliderCard(
    title: String,
    value: Float,
    range: ClosedFloatingPointRange<Float>,
    display: String,
    onValueChange: (Float) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = Color.White,
        shadowElevation = 2.dp,
    ) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF10243D),
                    modifier = Modifier.weight(1f),
                )
                Text(
                    text = display,
                    style = MaterialTheme.typography.labelLarge,
                    color = Color(0xFF657384),
                )
            }
            Slider(
                value = value,
                onValueChange = onValueChange,
                valueRange = range,
            )
        }
    }
}

private fun decodeBitmapFromUri(context: Context, uri: Uri): Bitmap? {
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            android.graphics.ImageDecoder.decodeBitmap(
                android.graphics.ImageDecoder.createSource(context.contentResolver, uri),
            ) { decoder, _, _ ->
                decoder.allocator = android.graphics.ImageDecoder.ALLOCATOR_SOFTWARE
            }
        } else {
            @Suppress("DEPRECATION")
            MediaStore.Images.Media.getBitmap(context.contentResolver, uri)
        }
    }.getOrNull()
}

private fun createJournalShareBitmap(
    entry: JournalEntry,
    background: Bitmap?,
    blur: Float,
    brightness: Float,
): Bitmap {
    val width = 1080
    val cardLeft = 88f
    val cardTop = 140f
    val cardRight = width - 88f
    val contentLeft = cardLeft + 58f
    val contentRight = cardRight - 58f

    val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = entry.titleStyle.textColor.toArgb()
        textSize = 72f
        typeface = android.graphics.Typeface.create(
            android.graphics.Typeface.DEFAULT,
            if (entry.titleStyle.bold) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL,
        )
        isUnderlineText = entry.titleStyle.underline
    }
    val metaPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(96, 112, 132)
        textSize = 34f
    }
    val bodyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = entry.bodyStyle.textColor.toArgb()
        textSize = 42f
        typeface = android.graphics.Typeface.create(
            android.graphics.Typeface.DEFAULT,
            if (entry.bodyStyle.bold) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL,
        )
        isUnderlineText = entry.bodyStyle.underline
    }
    val brandPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(31, 122, 224)
        textSize = 32f
        typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
    }
    val body = entry.body.ifBlank { "把这段旅程装进一张图片，分享给想一起出发的人。" }
    val titleLines = wrapText(entry.title, contentRight - contentLeft, titlePaint).take(2)
    val bodyLines = wrapText(body, contentRight - contentLeft, bodyPaint)
    val photos = entry.photos.take(4)
    val photoRows = if (photos.isEmpty()) 0 else (photos.size + 1) / 2
    val photoGap = 18f
    val photoSize = ((cardRight - cardLeft - 116f - photoGap) / 2f)
    val photoHeight = if (photoRows == 0) 0f else photoRows * photoSize + (photoRows - 1) * photoGap + 64f
    val cardBottom = max(
        1300f,
        cardTop + 112f + titleLines.size * 84f + 74f + bodyLines.size * 64f + 46f + photoHeight + 108f,
    )
    val height = (cardBottom + 140f).toInt().coerceAtLeast(1440)
    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)

    if (background != null) {
        val bg = cropCenter(background, width, height)
        val renderedBackground = if (blur >= 1f) blurBitmap(bg, blur.toInt()) else bg
        val brightnessPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            alpha = (255f * brightness).toInt().coerceIn(0, 255)
        }
        canvas.drawBitmap(renderedBackground, 0f, 0f, brightnessPaint)
        canvas.drawColor(AndroidColor.argb(72, 5, 16, 32))
    } else {
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            shader = LinearGradient(
                0f,
                0f,
                width.toFloat(),
                height.toFloat(),
                intArrayOf(AndroidColor.rgb(15, 51, 91), AndroidColor.rgb(135, 199, 192), AndroidColor.rgb(255, 232, 172)),
                null,
                Shader.TileMode.CLAMP,
            )
        }.also { canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), it) }
    }

    val cardPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.argb(232, 255, 255, 255)
        setShadowLayer(20f, 0f, 12f, AndroidColor.argb(80, 18, 38, 66))
    }
    canvas.drawRoundRect(RectF(cardLeft, cardTop, cardRight, cardBottom), 56f, 56f, cardPaint)

    var y = cardTop + 112f
    y = drawWrappedText(
        canvas = canvas,
        lines = titleLines,
        left = contentLeft,
        baseline = y,
        paint = titlePaint,
        lineHeight = 84f,
        highlightColor = entry.titleStyle.highlightColor.takeIf { entry.titleStyle.highlighted }?.toArgb(),
    )
    y += 10f
    canvas.drawText(
        "${entry.location} · ${entry.date.format(DateTimeFormatter.ofPattern("yyyy.M.d"))}",
        contentLeft,
        y,
        metaPaint,
    )
    y += 74f

    y = drawWrappedText(
        canvas = canvas,
        lines = bodyLines,
        left = contentLeft,
        baseline = y,
        paint = bodyPaint,
        lineHeight = 64f,
        highlightColor = entry.bodyStyle.highlightColor.takeIf { entry.bodyStyle.highlighted }?.toArgb(),
    )
    y += 46f

    if (photos.isNotEmpty()) {
        photos.forEachIndexed { index, photo ->
            val row = index / 2
            val column = index % 2
            val left = contentLeft + column * (photoSize + photoGap)
            val top = y + row * (photoSize + photoGap)
            drawSharePhoto(canvas, photo, RectF(left, top, left + photoSize, top + photoSize))
        }
    }

    canvas.drawText("AITravel 途灵 · 生成游记分享图", contentLeft, cardBottom - 58f, brandPaint)
    return bitmap
}

private fun drawSharePhoto(canvas: Canvas, photo: JournalPhoto, rect: RectF) {
    val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    canvas.save()
    canvas.clipRect(rect)
    val bitmap = photo.bitmap
    if (bitmap != null) {
        canvas.drawBitmap(cropCenter(bitmap, rect.width().toInt(), rect.height().toInt()), rect.left, rect.top, paint)
    } else {
        paint.color = photo.color.toArgb()
        canvas.drawRoundRect(rect, 34f, 34f, paint)
        paint.shader = LinearGradient(
            rect.left,
            rect.top,
            rect.right,
            rect.bottom,
            photo.color.toArgb(),
            AndroidColor.argb(170, 255, 255, 255),
            Shader.TileMode.CLAMP,
        )
        canvas.drawRoundRect(rect, 34f, 34f, paint)
        paint.shader = null
        paint.color = AndroidColor.rgb(16, 36, 61)
        paint.textSize = 30f
        paint.typeface = android.graphics.Typeface.create(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
        paint.textAlign = Paint.Align.CENTER
        canvas.drawText(photo.label, rect.centerX(), rect.centerY() + 10f, paint)
    }
    canvas.restore()
}

private fun wrapText(
    text: String,
    maxWidth: Float,
    paint: Paint,
): List<String> {
    val lines = mutableListOf<String>()
    var current = ""
    text.forEach { char ->
        if (char == '\n') {
            if (current.isNotBlank()) lines += current
            current = ""
            return@forEach
        }
        val next = current + char
        if (paint.measureText(next) > maxWidth && current.isNotBlank()) {
            lines += current
            current = char.toString()
        } else {
            current = next
        }
    }
    if (current.isNotBlank()) lines += current
    return lines.ifEmpty { listOf("") }
}

private fun drawWrappedText(
    canvas: Canvas,
    lines: List<String>,
    left: Float,
    baseline: Float,
    paint: Paint,
    lineHeight: Float,
    highlightColor: Int? = null,
): Float {
    val highlightPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = highlightColor ?: AndroidColor.TRANSPARENT
    }
    lines.forEachIndexed { index, line ->
        val y = baseline + index * lineHeight
        if (highlightColor != null && line.isNotBlank()) {
            canvas.drawRoundRect(
                RectF(left - 8f, y - paint.textSize - 8f, left + paint.measureText(line) + 8f, y + 14f),
                12f,
                12f,
                highlightPaint,
            )
        }
        canvas.drawText(line, left, y, paint)
    }
    return baseline + lines.size * lineHeight
}

private fun cropCenter(source: Bitmap, targetWidth: Int, targetHeight: Int): Bitmap {
    val scale = max(targetWidth.toFloat() / source.width, targetHeight.toFloat() / source.height)
    val scaledWidth = (source.width * scale).toInt()
    val scaledHeight = (source.height * scale).toInt()
    val scaled = Bitmap.createScaledBitmap(source, scaledWidth, scaledHeight, true)
    val x = ((scaledWidth - targetWidth) / 2).coerceAtLeast(0)
    val y = ((scaledHeight - targetHeight) / 2).coerceAtLeast(0)
    return Bitmap.createBitmap(scaled, x, y, targetWidth.coerceAtMost(scaled.width), targetHeight.coerceAtMost(scaled.height))
}

private fun blurBitmap(source: Bitmap, radius: Int): Bitmap {
    val scaledWidth = 160
    val scaledHeight = 214
    val small = Bitmap.createScaledBitmap(source, scaledWidth, scaledHeight, true)
    val pixels = IntArray(scaledWidth * scaledHeight)
    val result = IntArray(pixels.size)
    small.getPixels(pixels, 0, scaledWidth, 0, 0, scaledWidth, scaledHeight)
    val safeRadius = radius.coerceIn(1, 18)
    for (y in 0 until scaledHeight) {
        for (x in 0 until scaledWidth) {
            var red = 0
            var green = 0
            var blue = 0
            var count = 0
            for (dy in -safeRadius..safeRadius) {
                val py = (y + dy).coerceIn(0, scaledHeight - 1)
                for (dx in -safeRadius..safeRadius) {
                    val px = (x + dx).coerceIn(0, scaledWidth - 1)
                    val color = pixels[py * scaledWidth + px]
                    red += AndroidColor.red(color)
                    green += AndroidColor.green(color)
                    blue += AndroidColor.blue(color)
                    count += 1
                }
            }
            result[y * scaledWidth + x] = AndroidColor.rgb(red / count, green / count, blue / count)
        }
    }
    val blurredSmall = Bitmap.createBitmap(scaledWidth, scaledHeight, Bitmap.Config.ARGB_8888)
    blurredSmall.setPixels(result, 0, scaledWidth, 0, 0, scaledWidth, scaledHeight)
    return Bitmap.createScaledBitmap(blurredSmall, source.width, source.height, true)
}

private fun shareBitmap(context: Context, bitmap: Bitmap) {
    val cacheDir = File(context.cacheDir, "journal_shares").apply { mkdirs() }
    val file = File(cacheDir, "journal-share-${System.currentTimeMillis()}.png")
    FileOutputStream(file).use { output ->
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)
    }
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "image/png"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "分享游记图片"))
}
