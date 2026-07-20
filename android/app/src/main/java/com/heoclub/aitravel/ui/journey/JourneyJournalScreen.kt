package com.heoclub.aitravel.ui.journey

import android.graphics.Bitmap
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
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Image
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Publish
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.format.TextStyle
import java.util.Locale

private enum class JournalGroupMode {
    Time,
    Place,
}

@Composable
internal fun JourneyJournalRoute(
    entries: List<JournalEntry>,
    onBack: () -> Unit,
    onWriteJourney: () -> Unit,
    onAddEntry: (JournalEntry) -> Unit,
    onOpenEntry: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val selectedIds = remember { mutableStateListOf<String>() }
    var query by remember { mutableStateOf("") }
    var groupMode by remember { mutableStateOf(JournalGroupMode.Time) }
    var selecting by remember { mutableStateOf(false) }
    var pendingPhoto by remember { mutableStateOf<android.graphics.Bitmap?>(null) }
    var showPhotoEditor by remember { mutableStateOf(false) }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicturePreview(),
    ) { bitmap ->
        if (bitmap == null) {
            Toast.makeText(context, "未获取照片", Toast.LENGTH_SHORT).show()
        } else {
            pendingPhoto = bitmap
            showPhotoEditor = true
        }
    }

    val filteredEntries = remember(entries.toList(), query, groupMode) {
        entries
            .filter { entry ->
                query.isBlank() ||
                    entry.title.contains(query, ignoreCase = true) ||
                    entry.location.contains(query, ignoreCase = true) ||
                    entry.body.contains(query, ignoreCase = true)
            }
            .let { list ->
                when (groupMode) {
                    JournalGroupMode.Time -> list.sortedWith(compareByDescending<JournalEntry> { it.date }.thenBy { it.title })
                    JournalGroupMode.Place -> list.sortedWith(compareBy<JournalEntry> { placeInitial(it.location) }.thenBy { it.location })
                }
            }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        containerColor = Color(0xFFF4F8FA),
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
        ) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(
                    start = 16.dp,
                    end = if (groupMode == JournalGroupMode.Place) 34.dp else 16.dp,
                    top = 14.dp,
                    bottom = 26.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    JournalTopBar(
                        query = query,
                        onQueryChange = { query = it },
                        onBack = onBack,
                    )
                }

                item {
                    JournalActionBar(
                        onWrite = onWriteJourney,
                        onSnap = { cameraLauncher.launch(null) },
                        onPublish = {
                            Toast.makeText(context, "分享发布入口待定", Toast.LENGTH_SHORT).show()
                        },
                    )
                }

                item {
                    JournalModeBar(
                        groupMode = groupMode,
                        selecting = selecting,
                        allSelected = selectedIds.size == filteredEntries.size && filteredEntries.isNotEmpty(),
                        onModeChange = { groupMode = it },
                        onToggleManage = {
                            selecting = !selecting
                            selectedIds.clear()
                        },
                        onToggleSelectAll = {
                            if (selectedIds.size == filteredEntries.size) {
                                selectedIds.clear()
                            } else {
                                selectedIds.clear()
                                selectedIds.addAll(filteredEntries.map { it.id })
                            }
                        },
                    )
                }

                items(filteredEntries, key = { it.id }) { entry ->
                    JournalEntryCard(
                        entry = entry,
                        selecting = selecting,
                        selected = entry.id in selectedIds,
                        onSelectedChange = { checked ->
                            if (checked) selectedIds.add(entry.id) else selectedIds.remove(entry.id)
                        },
                        onOpen = { onOpenEntry(entry.id) },
                    )
                }
            }

            if (groupMode == JournalGroupMode.Place) {
                AlphabetRail(
                    modifier = Modifier
                        .align(Alignment.CenterEnd)
                        .padding(end = 5.dp),
                )
            }
        }
    }

    if (showPhotoEditor) {
        PhotoJournalDialog(
            bitmap = pendingPhoto,
            onDismiss = {
                showPhotoEditor = false
                pendingPhoto = null
            },
            onSave = { title, location, date ->
                onAddEntry(
                    JournalEntry(
                        id = "snap-${System.nanoTime()}",
                        date = date,
                        title = title.ifBlank { "随手拍" },
                        location = location.ifBlank { "未选择地点" },
                        body = "",
                        photos = listOf(
                            JournalPhoto(
                                bitmap = pendingPhoto,
                                label = "随手拍",
                                color = Color(0xFFD9E8F7),
                            ),
                        ),
                    ),
                )
                showPhotoEditor = false
                pendingPhoto = null
            },
        )
    }
}

@Composable
private fun JournalTopBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onBack: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
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
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            modifier = Modifier.weight(1f),
            placeholder = { Text("搜索笔记标题关键词") },
            leadingIcon = {
                Icon(
                    imageVector = Icons.Outlined.Search,
                    contentDescription = null,
                )
            },
            singleLine = true,
            shape = RoundedCornerShape(28.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedContainerColor = Color.White,
                unfocusedContainerColor = Color.White,
                focusedBorderColor = Color.Transparent,
                unfocusedBorderColor = Color.Transparent,
            ),
        )
    }
}

@Composable
private fun JournalModeBar(
    groupMode: JournalGroupMode,
    selecting: Boolean,
    allSelected: Boolean,
    onModeChange: (JournalGroupMode) -> Unit,
    onToggleManage: () -> Unit,
    onToggleSelectAll: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = groupMode == JournalGroupMode.Place,
                onClick = { onModeChange(JournalGroupMode.Place) },
                label = { Text("按地点") },
            )
            FilterChip(
                selected = groupMode == JournalGroupMode.Time,
                onClick = { onModeChange(JournalGroupMode.Time) },
                label = { Text("按时间") },
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (selecting) {
                TextButton(onClick = onToggleSelectAll) {
                    Text(if (allSelected) "取消全选" else "全选")
                }
            }
            TextButton(onClick = onToggleManage) {
                Text(if (selecting) "完成" else "管理")
            }
        }
    }
}

@Composable
private fun JournalActionBar(
    onWrite: () -> Unit,
    onSnap: () -> Unit,
    onPublish: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        JournalActionTile(
            title = "写旅记",
            icon = Icons.Outlined.Add,
            color = Color(0xFFE8F4FF),
            accent = Color(0xFF1F7AE0),
            onClick = onWrite,
            modifier = Modifier.weight(1f),
        )
        JournalActionTile(
            title = "随手拍",
            icon = Icons.Outlined.CameraAlt,
            color = Color(0xFFFFF4D8),
            accent = Color(0xFFE49A1A),
            onClick = onSnap,
            modifier = Modifier.weight(1f),
        )
        JournalActionTile(
            title = "分享发布",
            icon = Icons.Outlined.Publish,
            color = Color(0xFFF0F3F7),
            accent = Color(0xFF778597),
            onClick = onPublish,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun JournalActionTile(
    title: String,
    icon: ImageVector,
    color: Color,
    accent: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier
            .height(104.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(24.dp),
        color = color,
        shadowElevation = 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(Color.White.copy(alpha = 0.82f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = accent,
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF10243D),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun JournalEntryCard(
    entry: JournalEntry,
    selecting: Boolean,
    selected: Boolean,
    onSelectedChange: (Boolean) -> Unit,
    onOpen: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable {
                if (selecting) {
                    onSelectedChange(!selected)
                } else {
                    onOpen()
                }
            },
        shape = RoundedCornerShape(22.dp),
        color = Color.White,
        shadowElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.Top,
        ) {
            if (selecting) {
                Checkbox(
                    checked = selected,
                    onCheckedChange = onSelectedChange,
                    modifier = Modifier.padding(top = 18.dp),
                )
                Spacer(modifier = Modifier.width(4.dp))
            }
            DateBlock(date = entry.date)
            Spacer(modifier = Modifier.width(14.dp))
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = entry.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.ExtraBold,
                        color = Color(0xFF10243D),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Icon(
                        imageVector = Icons.Outlined.LocationOn,
                        contentDescription = null,
                        tint = Color(0xFF1F7AE0),
                        modifier = Modifier.size(18.dp),
                    )
                    Text(
                        text = entry.location.removeSuffix("市"),
                        style = MaterialTheme.typography.labelMedium,
                        color = Color(0xFF657384),
                    )
                }
                if (entry.body.isNotBlank()) {
                    Text(
                        text = entry.body,
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color(0xFF5E6C7C),
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                JournalPhotoPreview(photos = entry.photos, textOnly = entry.body.isNotBlank())
            }
        }
    }
}

@Composable
private fun DateBlock(date: LocalDate) {
    Column(
        modifier = Modifier.width(66.dp),
        horizontalAlignment = Alignment.Start,
    ) {
        Text(
            text = date.year.toString(),
            style = MaterialTheme.typography.labelMedium,
            color = Color(0xFF778597),
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = date.month.getDisplayName(TextStyle.SHORT, Locale.ENGLISH),
            style = MaterialTheme.typography.titleSmall,
            color = Color(0xFF10243D),
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = date.dayOfMonth.toString(),
            style = MaterialTheme.typography.headlineSmall,
            color = Color(0xFF10243D),
            fontWeight = FontWeight.ExtraBold,
        )
    }
}

@Composable
private fun JournalPhotoPreview(
    photos: List<JournalPhoto>,
    textOnly: Boolean,
) {
    when {
        photos.isEmpty() -> Unit
        photos.size == 1 && !textOnly -> {
            PhotoBox(
                photo = photos.first(),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(150.dp),
            )
        }
        else -> {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                photos.take(4).forEach { photo ->
                    PhotoBox(
                        photo = photo,
                        modifier = Modifier
                            .weight(1f)
                            .aspectRatio(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun PhotoBox(
    photo: JournalPhoto,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
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
                    .matchParentSize()
                    .background(
                        Brush.linearGradient(
                            listOf(photo.color.copy(alpha = 0.85f), Color.White.copy(alpha = 0.35f)),
                        ),
                    ),
            )
            Text(
                text = photo.label,
                style = MaterialTheme.typography.labelLarge,
                color = Color(0xFF10243D),
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun AlphabetRail(modifier: Modifier = Modifier) {
    val letters = listOf("A", "B", "C", "G", "H", "K", "S", "X")
    Surface(
        modifier = modifier
            .width(22.dp)
            .fillMaxHeight(0.62f),
        shape = RoundedCornerShape(99.dp),
        color = Color.White.copy(alpha = 0.92f),
        shadowElevation = 2.dp,
    ) {
        Column(
            modifier = Modifier.padding(vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceEvenly,
        ) {
            letters.forEach { letter ->
                Text(
                    text = letter,
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFF1F7AE0),
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
private fun PhotoJournalDialog(
    bitmap: Bitmap?,
    onDismiss: () -> Unit,
    onSave: (String, String, LocalDate) -> Unit,
) {
    var title by remember { mutableStateOf("随手拍") }
    var location by remember { mutableStateOf("") }
    var dateText by remember { mutableStateOf(LocalDate.now().toString()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            Button(
                onClick = {
                    onSave(
                        title,
                        location,
                        runCatching { LocalDate.parse(dateText) }.getOrDefault(LocalDate.now()),
                    )
                },
            ) {
                Text("留下记录")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("取消")
            }
        },
        title = { Text("随手拍记录") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                PhotoBox(
                    photo = JournalPhoto(bitmap = bitmap, label = "随手拍", color = Color(0xFFD9E8F7)),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(160.dp),
                )
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("标题") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = location,
                    onValueChange = { location = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("地点") },
                    singleLine = true,
                )
                OutlinedTextField(
                    value = dateText,
                    onValueChange = { dateText = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("时间") },
                    singleLine = true,
                )
            }
        },
        shape = RoundedCornerShape(24.dp),
        containerColor = Color.White,
    )
}

private fun placeInitial(location: String): String {
    return when {
        location.startsWith("北京市") -> "B"
        location.startsWith("成都市") -> "C"
        location.startsWith("广州市") -> "G"
        location.startsWith("杭州市") -> "H"
        location.startsWith("哈尔滨") -> "H"
        location.startsWith("昆明") -> "K"
        location.startsWith("上海") -> "S"
        location.startsWith("西安") -> "X"
        else -> location.firstOrNull()?.uppercaseChar()?.toString() ?: "#"
    }
}
