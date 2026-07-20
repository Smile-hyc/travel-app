package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
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
import androidx.compose.ui.unit.dp
import java.time.LocalDate

@Composable
internal fun JourneyJournalEditorScreen(
    onBack: () -> Unit,
    onSave: (JournalEntry) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    var title by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var body by remember { mutableStateOf("") }
    val photos = remember { mutableStateListOf<JournalPhoto>() }
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
                    Toast.makeText(context, "分享发布入口待定", Toast.LENGTH_SHORT).show()
                },
                onSave = {
                    onSave(
                        JournalEntry(
                            id = "entry-${System.nanoTime()}",
                            date = LocalDate.now(),
                            title = title.ifBlank { "未命名旅记" },
                            location = location.ifBlank { "未选择地点" },
                            body = body,
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
                    onValueChange = { title = it },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("添加标题") },
                    textStyle = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.ExtraBold),
                    singleLine = true,
                    shape = RoundedCornerShape(18.dp),
                )
            }
            item {
                OutlinedTextField(
                    value = body,
                    onValueChange = { body = it },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(260.dp),
                    placeholder = { Text("记录这段旅程的见闻、攻略和心情...") },
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
                        val colors = listOf(Color(0xFFAEDDE8), Color(0xFFD6E6B8), Color(0xFFFFD999), Color(0xFFBFD0F2))
                        photos.add(
                            JournalPhoto(
                                label = "Pic ${photos.size + 1}",
                                color = colors[photos.size % colors.size],
                            ),
                        )
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
