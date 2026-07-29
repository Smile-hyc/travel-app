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
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.MyLocation
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
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
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.location.CurrentLocationUiState
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.PlaceSuggestion
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.repository.ExploreRepository
import com.heoclub.aitravel.data.repository.JournalPhotoStore
import com.heoclub.aitravel.ui.explore.PlaceSearchScreen
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate

private enum class EditorTextTarget {
    Title,
    Body,
}

@Composable
internal fun JourneyJournalEditorScreen(
    initialEntry: JournalEntry? = null,
    locationState: CurrentLocationUiState = CurrentLocationUiState(),
    onLocate: () -> Unit = {},
    exploreRepository: ExploreRepository? = null,
    photoStore: JournalPhotoStore? = null,
    onBack: () -> Unit,
    onSave: (JournalEntry) -> Unit,
    onShareDraft: (JournalEntry) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var title by remember(initialEntry?.id) { mutableStateOf(TextFieldValue(initialEntry?.title.orEmpty())) }
    var titleColor by remember(initialEntry?.id) { mutableStateOf(initialEntry?.titleColor ?: Color(0xFF081F3A)) }
    var titleStyle by remember(initialEntry?.id) {
        mutableStateOf(initialEntry?.titleStyle ?: JournalTextStyle(bold = true, textColor = Color(0xFF081F3A)))
    }
    var location by remember(initialEntry?.id) { mutableStateOf(initialEntry?.location.orEmpty()) }
    var titleSpans by remember(initialEntry?.id) { mutableStateOf(initialEntry?.titleSpans.orEmpty()) }
    var body by remember(initialEntry?.id) { mutableStateOf(TextFieldValue(initialEntry?.body.orEmpty())) }
    var bodyStyle by remember(initialEntry?.id) { mutableStateOf(initialEntry?.bodyStyle ?: JournalTextStyle()) }
    var bodySpans by remember(initialEntry?.id) { mutableStateOf(initialEntry?.bodySpans.orEmpty()) }
    var activeTarget by remember { mutableStateOf(EditorTextTarget.Body) }
    val draftId = remember(initialEntry?.id) { initialEntry?.id ?: "entry-${System.nanoTime()}" }
    val photos = remember(initialEntry?.id) {
        mutableStateListOf<JournalPhoto>().apply { addAll(initialEntry?.photos.orEmpty()) }
    }
    var waitingForLocation by remember { mutableStateOf(false) }
    var isLocationPickerVisible by remember { mutableStateOf(false) }
    var locationQuery by remember { mutableStateOf("") }
    var locationSuggestions by remember { mutableStateOf<List<PlaceSuggestion>>(emptyList()) }
    var locationResults by remember { mutableStateOf<List<PlaceSummary>>(emptyList()) }
    var isLoadingLocationSuggestions by remember { mutableStateOf(false) }
    var isSearchingLocations by remember { mutableStateOf(false) }
    var locationSearchError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(locationState.location?.updateSequence, locationState.errorMessage, waitingForLocation) {
        if (!waitingForLocation) return@LaunchedEffect
        val current = locationState.location
        when {
            current != null && !locationState.isLocating -> {
                location = current.address.ifBlank {
                    listOf(current.cityName, current.districtName)
                        .filter(String::isNotBlank)
                        .distinct()
                        .joinToString(" ")
                }
                waitingForLocation = false
            }
            locationState.errorMessage != null && !locationState.isLocating -> {
                Toast.makeText(context, locationState.errorMessage, Toast.LENGTH_SHORT).show()
                waitingForLocation = false
            }
        }
    }

    LaunchedEffect(isLocationPickerVisible, locationQuery) {
        val repository = exploreRepository ?: return@LaunchedEffect
        val keyword = locationQuery.trim()
        if (!isLocationPickerVisible || keyword.length < 2) {
            locationSuggestions = emptyList()
            isLoadingLocationSuggestions = false
            return@LaunchedEffect
        }
        isLoadingLocationSuggestions = true
        delay(350)
        val currentAdCode = locationState.location?.adCode
        runCatching {
            repository.getInputTips(
                keyword = keyword,
                adcode = currentAdCode,
                cityLimit = !currentAdCode.isNullOrBlank(),
            )
        }.onSuccess { locationSuggestions = it }
            .onFailure { locationSearchError = it.message }
        isLoadingLocationSuggestions = false
    }

    fun selectLocation(place: PlaceSummary) {
        location = place.name.ifBlank { place.address.orEmpty() }
        isLocationPickerVisible = false
    }

    fun searchLocations(keyword: String) {
        val repository = exploreRepository ?: return
        val trimmed = keyword.trim()
        if (trimmed.isBlank()) return
        locationQuery = trimmed
        scope.launch {
            isSearchingLocations = true
            locationSearchError = null
            val currentAdCode = locationState.location?.adCode
            runCatching {
                repository.queryPlaces(
                    adcode = currentAdCode ?: "100000",
                    keyword = trimmed,
                    category = ExploreCategories.ALL,
                    page = 1,
                    pageSize = 20,
                    cityLimit = !currentAdCode.isNullOrBlank(),
                ).items.filter { it.hasLocation }
            }.onSuccess { locationResults = it }
                .onFailure { locationSearchError = it.message ?: "地点搜索失败" }
            isSearchingLocations = false
        }
    }

    val imagePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.GetMultipleContents(),
    ) { uris ->
        uris.forEachIndexed { index, uri ->
            decodeJournalBitmap(context, uri)?.let { bitmap ->
                val storedFileName = photoStore?.save(bitmap)
                photos.add(
                    JournalPhoto(
                        bitmap = bitmap,
                        label = "相册 ${photos.size + index + 1}",
                        color = Color(0xFFD9E8F7),
                        storedFileName = storedFileName,
                    ),
                )
                if (photoStore != null && storedFileName == null) {
                    Toast.makeText(context, "照片本地保存失败，请重试", Toast.LENGTH_SHORT).show()
                }
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
            val storedFileName = photoStore?.save(bitmap)
            photos.add(
                JournalPhoto(
                    bitmap = bitmap,
                    label = "拍照",
                    color = Color(0xFFD9E8F7),
                    storedFileName = storedFileName,
                ),
            )
            if (photoStore != null && storedFileName == null) {
                Toast.makeText(context, "照片本地保存失败，请重试", Toast.LENGTH_SHORT).show()
            }
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
                            id = draftId,
                            date = initialEntry?.date ?: LocalDate.now(),
                            title = title.text,
                            titleColor = titleColor,
                            titleStyle = titleStyle.copy(textColor = titleColor),
                            titleSpans = titleSpans,
                            location = location,
                            body = body.text,
                            bodyStyle = bodyStyle,
                            bodySpans = bodySpans,
                            photos = photos.toList(),
                        ),
                    )
                },
                onSave = {
                    onSave(
                        buildJournalEntry(
                            id = draftId,
                            date = initialEntry?.date ?: LocalDate.now(),
                            title = title.text,
                            titleColor = titleColor,
                            titleStyle = titleStyle.copy(textColor = titleColor),
                            titleSpans = titleSpans,
                            location = location,
                            body = body.text,
                            bodyStyle = bodyStyle,
                            bodySpans = bodySpans,
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
                        titleSpans = adjustJournalSpansForEdit(title.text, it.text, titleSpans)
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
                    visualTransformation = JournalSpanTransformation(titleSpans),
                    singleLine = true,
                    shape = RoundedCornerShape(18.dp),
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    EditorAddButton(
                        label = if (locationState.isLocating && waitingForLocation) "定位中" else "当前位置",
                        icon = Icons.Outlined.MyLocation,
                        onClick = {
                            waitingForLocation = true
                            onLocate()
                        },
                        modifier = Modifier.weight(1f),
                    )
                    EditorAddButton(
                        label = "地图选点",
                        icon = Icons.Outlined.Map,
                        onClick = { isLocationPickerVisible = true },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
            item {
                RichTextToolbar(
                    activeTarget = activeTarget,
                    titleStyle = styleAt(title.selection.min.coerceAtMost((title.text.length - 1).coerceAtLeast(0)), titleStyle, titleSpans),
                    bodyStyle = styleAt(body.selection.min.coerceAtMost((body.text.length - 1).coerceAtLeast(0)), bodyStyle, bodySpans),
                    onTargetChange = { activeTarget = it },
                    onTitleStyleChange = {
                        if (title.selection.collapsed) {
                            titleStyle = it
                            titleColor = it.textColor
                        } else {
                            val selected = title.selection
                            titleSpans = transformJournalSelection(title.text.length, titleSpans, selected, titleStyle) { current ->
                                current.copy(
                                    bold = it.bold,
                                    underline = it.underline,
                                    highlighted = it.highlighted,
                                    textColor = it.textColor,
                                    highlightColor = it.highlightColor,
                                )
                            }
                        }
                    },
                    onBodyStyleChange = {
                        if (body.selection.collapsed) {
                            bodyStyle = it
                        } else {
                            val selected = body.selection
                            bodySpans = transformJournalSelection(body.text.length, bodySpans, selected, bodyStyle) { current ->
                                current.copy(
                                    bold = it.bold,
                                    underline = it.underline,
                                    highlighted = it.highlighted,
                                    textColor = it.textColor,
                                    highlightColor = it.highlightColor,
                                )
                            }
                        }
                    },
                )
            }
            item {
                OutlinedTextField(
                    value = body,
                    onValueChange = {
                        activeTarget = EditorTextTarget.Body
                        bodySpans = adjustJournalSpansForEdit(body.text, it.text, bodySpans)
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
                    visualTransformation = JournalSpanTransformation(bodySpans),
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
                    onLocation = { isLocationPickerVisible = true },
                )
            }
        }
    }

    if (isLocationPickerVisible && exploreRepository != null) {
        PlaceSearchScreen(
            cityName = locationState.location?.cityName ?: "全国",
            query = locationQuery,
            suggestions = locationSuggestions,
            results = locationResults,
            hasSubmittedSearch = locationResults.isNotEmpty(),
            isLoadingSuggestions = isLoadingLocationSuggestions,
            isSearching = isSearchingLocations,
            notice = "搜索并选择高德地图中的真实地点",
            error = locationSearchError,
            history = emptyList(),
            quickWords = emptyList(),
            currentLatitude = locationState.location?.latitude,
            currentLongitude = locationState.location?.longitude,
            onQueryChange = {
                locationQuery = it
                locationSearchError = null
                locationResults = emptyList()
            },
            onSubmitSearch = ::searchLocations,
            onSuggestionClick = { suggestion ->
                if (suggestion.hasLocation) {
                    location = suggestion.name
                    isLocationPickerVisible = false
                } else {
                    searchLocations(suggestion.name)
                }
            },
            onResultClick = { placeId ->
                locationResults.firstOrNull { it.id == placeId }?.let(::selectLocation)
            },
            onAddPlace = ::selectLocation,
            onRemoveHistory = {},
            onClearHistory = {},
            onDismiss = { isLocationPickerVisible = false },
        )
    }
}

private fun buildJournalEntry(
    id: String,
    date: LocalDate,
    title: String,
    titleColor: Color,
    titleStyle: JournalTextStyle,
    titleSpans: List<JournalTextSpan>,
    location: String,
    body: String,
    bodyStyle: JournalTextStyle,
    bodySpans: List<JournalTextSpan>,
    photos: List<JournalPhoto>,
): JournalEntry {
    return JournalEntry(
        id = id,
        date = date,
        title = title.ifBlank { "未命名旅记" },
        titleColor = titleColor,
        titleStyle = titleStyle,
        titleSpans = titleSpans,
        location = location.ifBlank { "未选择地点" },
        body = body,
        bodyStyle = bodyStyle,
        bodySpans = bodySpans,
        photos = photos,
    )
}

private class JournalSpanTransformation(
    private val spans: List<JournalTextSpan>,
) : VisualTransformation {
    override fun filter(text: androidx.compose.ui.text.AnnotatedString): TransformedText = TransformedText(
        buildJournalAnnotatedString(text.text, spans),
        OffsetMapping.Identity,
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
