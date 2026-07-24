package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.outlined.FormatBold
import androidx.compose.material.icons.outlined.FormatColorFill
import androidx.compose.material.icons.outlined.FormatColorText
import androidx.compose.material.icons.outlined.FormatUnderlined
import androidx.compose.material3.FilterChip
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.AddPhotoAlternate
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import java.time.LocalDate

private enum class EditorTextTarget {
    Title,
    Body,
}

@Composable
internal fun JourneyJournalEditorScreen(
    onBack: () -> Unit,
    onSave: (JournalEntry) -> Unit,
    onShareDraft: (JournalEntry) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var title by remember { mutableStateOf("") }
    var titleColor by remember { mutableStateOf(Color(0xFF081F3A)) }
    var titleStyle by remember { mutableStateOf(JournalTextStyle(bold = true, textColor = Color(0xFF081F3A))) }
    var location by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    var bodyStyle by remember { mutableStateOf(JournalTextStyle()) }
    var activeTarget by remember { mutableStateOf(EditorTextTarget.Body) }
    val photos = remember { mutableStateListOf<JournalPhoto>() }
    val imagePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetMultipleContents(),
    ) { uris ->
        uris.forEachIndexed { index, uri ->
            decodeJournalBitmap(context, uri)?.let { bitmap ->
                photos.add(
                    JournalPhoto(
                        bitmap = bitmap,
                        label = "相册 ${photos.size + index + 1}",
                        color = Color(0xFFD9E8F7),
                    ),
                )
            }
        }
        if (uris.isNotEmpty() && photos.isEmpty()) {
            Toast.makeText(context, "照片读取失败", Toast.LENGTH_SHORT).show()
        }
    }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicturePreview(),
    ) { bitmap: Bitmap? ->
        if (bitmap == null) {
            Toast.makeText(context, "未获取照片", Toast.LENGTH_SHORT).show()
        } else {
            photos.add(
                JournalPhoto(
                    bitmap = bitmap,
                    label = "拍照",
                    color = Color(0xFFD9E8F7),
                ),
            )
        }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = Color(0xFFF6F8FB),
        topBar = {
            EditorTopBar(
                onBack = onBack,
                onShare = {
                    onShareDraft(
                        buildJournalEntry(
                            title = title,
                            titleColor = titleColor,
                            titleStyle = titleStyle.copy(textColor = titleColor),
                            location = location,
                            body = body,
                            bodyStyle = bodyStyle,
                            photos = photos.toList(),
                        ),
                    )
                },
                onSave = {
                    onSave(
                        buildJournalEntry(
                            title = title,
                            titleColor = titleColor,
                            titleStyle = titleStyle.copy(textColor = titleColor),
                            location = location,
                            body = body,
                            bodyStyle = bodyStyle,
                            photos = photos.toList(),
                        ),
                    )
                },
            )
        },
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .imePadding(),
            contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                OutlinedTextField(
                    value = title,
                    onValueChange = {
                        activeTarget = EditorTextTarget.Title
                        title = it
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { activeTarget = EditorTextTarget.Title },
                    placeholder = { Text("添加标题") },
                    textStyle = MaterialTheme.typography.headlineSmall.copy(
                        color = titleColor,
                        fontWeight = if (titleStyle.bold) FontWeight.ExtraBold else FontWeight.SemiBold,
                        textDecoration = if (titleStyle.underline) TextDecoration.Underline else TextDecoration.None,
                        background = if (titleStyle.highlighted) titleStyle.highlightColor else Color.Transparent,
                    ),
                    singleLine = true,
                    shape = RoundedCornerShape(18.dp),
                )
            }
            item {
                RichTextToolbar(
                    activeTarget = activeTarget,
                    titleStyle = titleStyle,
                    bodyStyle = bodyStyle,
                    onTargetChange = { activeTarget = it },
                    onTitleStyleChange = {
                        titleStyle = it
                        titleColor = it.textColor
                    },
                    onBodyStyleChange = { bodyStyle = it },
                )
            }
            item {
                OutlinedTextField(
                    value = body,
                    onValueChange = {
                        activeTarget = EditorTextTarget.Body
                        body = it
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(260.dp),
                    placeholder = { Text("记录这段旅程的见闻、攻略和心情...") },
                    textStyle = MaterialTheme.typography.bodyLarge.copy(
                        color = bodyStyle.textColor,
                        fontWeight = if (bodyStyle.bold) FontWeight.Bold else FontWeight.Normal,
                        textDecoration = if (bodyStyle.underline) TextDecoration.Underline else TextDecoration.None,
                        background = if (bodyStyle.highlighted) bodyStyle.highlightColor else Color.Transparent,
                    ),
                    minLines = 10,
                    shape = RoundedCornerShape(22.dp),
                )
            }
            if (photos.isNotEmpty()) {
                items(photos.chunked(2)) { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        row.forEach { photo ->
                            EditorPhotoThumb(
                                photo = photo,
                                modifier = Modifier
                                    .weight(1f)
                                    .aspectRatio(1.2f),
                            )
                        }
                        if (row.size == 1) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
            item {
                OutlinedTextField(
                    value = location,
                    onValueChange = { location = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("定位") },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Outlined.LocationOn,
                            contentDescription = null,
                        )
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(18.dp),
                )
            }
            item {
                EditorAddBar(
                    onAddImage = {
                        imagePicker.launch("image/*")
                    },
                    onCamera = { cameraLauncher.launch(null) },
                    onLocation = {
                        if (location.isBlank()) location = "杭州市"
                    },
                )
            }
        }
    }
}

private fun buildJournalEntry(
    title: String,
    titleColor: Color,
    titleStyle: JournalTextStyle,
    location: String,
    body: String,
    bodyStyle: JournalTextStyle,
    photos: List<JournalPhoto>,
): JournalEntry {
    return JournalEntry(
        id = "entry-${System.nanoTime()}",
        date = LocalDate.now(),
        title = title.ifBlank { "未命名旅记" },
        titleColor = titleColor,
        titleStyle = titleStyle,
        location = location.ifBlank { "未选择地点" },
        body = body,
        bodyStyle = bodyStyle,
        photos = photos,
    )
}

@Composable
private fun EditorTopBar(
    onBack: () -> Unit,
    onShare: () -> Unit,
    onSave: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color(0xFFF6F8FB))
            .padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            Icon(
                imageVector = Icons.AutoMirrored.Outlined.ArrowBack,
                contentDescription = "返回",
            )
        }
        Text(
            text = "写旅记",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.ExtraBold,
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = onShare) {
            Icon(
                imageVector = Icons.Outlined.Share,
                contentDescription = null,
                modifier = Modifier.size(18.dp),
            )
            Text("分享")
        }
        Button(onClick = onSave) {
            Text("保存")
        }
    }
}

@Composable
private fun RichTextToolbar(
    activeTarget: EditorTextTarget,
    titleStyle: JournalTextStyle,
    bodyStyle: JournalTextStyle,
    onTargetChange: (EditorTextTarget) -> Unit,
    onTitleStyleChange: (JournalTextStyle) -> Unit,
    onBodyStyleChange: (JournalTextStyle) -> Unit,
) {
    val colors = listOf(
        Color(0xFF081F3A),
        Color(0xFF1F7AE0),
        Color(0xFF21A67A),
        Color(0xFFE49A1A),
        Color(0xFFE15A68),
        Color(0xFF7B61FF),
    )
    val style = if (activeTarget == EditorTextTarget.Title) titleStyle else bodyStyle
    fun update(next: JournalTextStyle) {
        if (activeTarget == EditorTextTarget.Title) {
            onTitleStyleChange(next)
        } else {
            onBodyStyleChange(next)
        }
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = Color.White,
        shadowElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = activeTarget == EditorTextTarget.Title,
                    onClick = { onTargetChange(EditorTextTarget.Title) },
                    label = { Text("标题") },
                )
                FilterChip(
                    selected = activeTarget == EditorTextTarget.Body,
                    onClick = { onTargetChange(EditorTextTarget.Body) },
                    label = { Text("正文") },
                )
                EditorToolButton(
                    active = style.bold,
                    icon = Icons.Outlined.FormatBold,
                    label = "粗体",
                    onClick = { update(style.copy(bold = !style.bold)) },
                )
                EditorToolButton(
                    active = style.underline,
                    icon = Icons.Outlined.FormatUnderlined,
                    label = "下划线",
                    onClick = { update(style.copy(underline = !style.underline)) },
                )
                EditorToolButton(
                    active = style.highlighted,
                    icon = Icons.Outlined.FormatColorFill,
                    label = "高亮",
                    onClick = { update(style.copy(highlighted = !style.highlighted)) },
                )
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Outlined.FormatColorText,
                    contentDescription = null,
                    tint = Color(0xFF657384),
                )
                colors.forEach { color ->
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(color)
                            .border(
                                width = if (color == style.textColor) 3.dp else 1.dp,
                                color = if (color == style.textColor) Color.White else Color(0xFFE0E6EF),
                                shape = CircleShape,
                            )
                            .clickable { update(style.copy(textColor = color)) },
                    )
                }
            }
        }
    }
}

@Composable
private fun EditorToolButton(
    active: Boolean,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    onClick: () -> Unit,
) {
    Box(
        modifier = Modifier
            .size(38.dp)
            .clip(CircleShape)
            .background(if (active) Color(0xFFE1EEFF) else Color(0xFFF3F7FB))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = label,
            tint = if (active) Color(0xFF1F7AE0) else Color(0xFF657384),
            modifier = Modifier.size(20.dp),
        )
    }
}

private fun decodeJournalBitmap(
    context: android.content.Context,
    uri: android.net.Uri,
): Bitmap? {
    return runCatching {
        context.contentResolver.openInputStream(uri)?.use(BitmapFactory::decodeStream)
    }.getOrNull()
}

@Composable
private fun EditorAddBar(
    onAddImage: () -> Unit,
    onCamera: () -> Unit,
    onLocation: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = Color.White,
        shadowElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            EditorAddButton("图片", Icons.Outlined.AddPhotoAlternate, onAddImage, Modifier.weight(1f))
            EditorAddButton("拍照", Icons.Outlined.CameraAlt, onCamera, Modifier.weight(1f))
            EditorAddButton("定位", Icons.Outlined.LocationOn, onLocation, Modifier.weight(1f))
        }
    }
}

@Composable
private fun EditorAddButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(Color(0xFFEAF2FF))
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = Color(0xFF1F7AE0),
        )
        Text(
            text = label,
            color = Color(0xFF10243D),
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(start = 6.dp),
        )
    }
}

@Composable
private fun EditorPhotoThumb(
    photo: JournalPhoto,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(18.dp))
            .background(photo.color),
        contentAlignment = Alignment.Center,
    ) {
        val bitmap = photo.bitmap
        if (bitmap != null) {
            Image(
                bitmap = bitmap.asImageBitmap(),
                contentDescription = photo.label,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )
        } else {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.linearGradient(
                            listOf(photo.color.copy(alpha = 0.88f), Color.White.copy(alpha = 0.34f)),
                        ),
                    ),
            )
            Text(
                text = photo.label,
                color = Color(0xFF10243D),
                fontWeight = FontWeight.Bold,
            )
        }
    }
}
