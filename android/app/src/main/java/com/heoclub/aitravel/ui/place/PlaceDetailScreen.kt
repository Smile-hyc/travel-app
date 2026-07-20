package com.heoclub.aitravel.ui.place

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.AccessTime
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.KeyboardArrowDown
import androidx.compose.material.icons.outlined.KeyboardArrowUp
import androidx.compose.material.icons.outlined.Navigation
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.model.ReviewHighlight
import com.heoclub.aitravel.data.model.ReviewSource
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.data.repository.AddPlaceTarget
import com.heoclub.aitravel.ui.components.AddPlaceToPlanDialog
import com.heoclub.aitravel.ui.components.PlaceImageCarousel

private val Ink = Color(0xFF171717)
private val MutedInk = Color(0xFF737373)
private val PageBackground = Color.White
private val PositiveBackground = Color(0xFFF1F8E8)
private val CautionBackground = Color(0xFFFFF1EC)
private val XiaohongshuRed = Color(0xFFFF2442)

@Composable
fun PlaceDetailScreen(
    viewModel: PlaceDetailViewModel,
    travelPlans: List<TravelPlan>,
    onBack: () -> Unit,
    onCreatePlan: () -> Unit,
    onAddToPlan: (TravelPlan, AddPlaceTarget) -> AddPlaceResult,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsState()
    val detail = state.detail
    val context = LocalContext.current
    var showPlanDialog by remember { mutableStateOf(false) }

    if (detail == null) {
        MissingPlace(onBack = onBack, modifier = modifier)
        return
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(PageBackground),
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 116.dp),
            verticalArrangement = Arrangement.spacedBy(0.dp),
        ) {
            item { DetailHeader(detail = detail, onBack = onBack) }
            if (state.refreshFailed) {
                item {
                    RefreshNotice(
                        onRetry = viewModel::refresh,
                        modifier = Modifier.padding(horizontal = 20.dp),
                    )
                }
            }
            item {
                OverviewSection(
                    detail,
                    Modifier.padding(start = 24.dp, end = 24.dp, top = 30.dp),
                )
            }
            if (detail.relatedPlans.isNotEmpty()) {
                item { RelatedPlansSection(detail) }
            }
            if (detail.hasRealReviews && detail.reviewSources.isNotEmpty()) {
                item {
                    ReviewSection(
                        detail = detail,
                        onOpen = { openUrl(context, it.url) },
                        modifier = Modifier.padding(top = 34.dp),
                    )
                }
            }
            item {
                InformationSection(
                    detail = detail,
                    onOpenAddress = { openNavigation(context, detail) },
                    onCall = { detail.phone?.let { openDialer(context, it) } },
                    onFeedback = {
                        Toast.makeText(context, "感谢反馈，我们会核对地点信息", Toast.LENGTH_SHORT).show()
                    },
                    modifier = Modifier.padding(start = 24.dp, end = 24.dp, top = 28.dp),
                )
            }
        }

        if (state.isRefreshing) {
            LinearProgressIndicator(
                modifier = Modifier
                    .fillMaxWidth()
                    .align(Alignment.TopCenter),
            )
        }

        BottomActions(
            favorite = detail.summary.isFavorite,
            checkedIn = state.isCheckedIn,
            onAdd = { showPlanDialog = true },
            onFavorite = viewModel::toggleFavorite,
            onCheckIn = viewModel::toggleCheckIn,
            onNavigate = { openNavigation(context, detail) },
            modifier = Modifier.align(Alignment.BottomCenter),
        )
    }

    if (showPlanDialog) {
        AddPlaceToPlanDialog(
            plans = travelPlans,
            placeName = detail.summary.name,
            onDismiss = { showPlanDialog = false },
            onCreatePlan = onCreatePlan,
            onConfirm = onAddToPlan,
            onResult = { message -> Toast.makeText(context, message, Toast.LENGTH_SHORT).show() },
        )
    }
}

@Composable
private fun DetailHeader(detail: PlaceDetail, onBack: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(Color.White)
            .statusBarsPadding()
            .padding(bottom = 4.dp),
    ) {
        IconButton(
            onClick = onBack,
            modifier = Modifier
                .padding(start = 8.dp, top = 4.dp)
                .size(48.dp),
        ) {
            Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回", tint = Ink)
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = detail.summary.name,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                detail.summary.typeName?.takeIf { it.isNotBlank() }?.let {
                    InfoChip(it, Color(0xFFFFF2D7), Color(0xFFB46A00))
                }
                detail.summary.rating?.takeIf { it.isNotBlank() }?.let {
                    InfoChip("评分 $it", Color(0xFFF1F1F1), Color(0xFF555555))
                }
                detail.summary.districtName?.takeIf { it.isNotBlank() }?.let {
                    InfoChip(it, Color(0xFFF1F1F1), Color(0xFF555555))
                }
            }
            PlaceImageCarousel(
                images = detail.images,
                fallbackUrls = detail.summary.displayImageUrls,
                placeName = detail.summary.name,
                category = detail.summary.category,
                modifier = Modifier.fillMaxWidth(),
                itemHeight = 176.dp,
            )
        }
    }
}

@Composable
private fun OverviewSection(detail: PlaceDetail, modifier: Modifier = Modifier) {
    var expanded by remember(detail.summary.id) { mutableStateOf(false) }
    Column(modifier = modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("地点介绍", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Ink)
            Surface(
                color = Color(0xFFF1F1F1),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.padding(start = 8.dp),
            ) {
                Text(
                    "AI生成",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFF9A9A9A),
                    modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp),
                )
            }
        }
        Spacer(Modifier.height(10.dp))
        Text(
            text = detail.description,
            style = MaterialTheme.typography.bodyLarge,
            color = Color(0xFF3C3C3C),
            maxLines = if (expanded) Int.MAX_VALUE else 3,
            overflow = TextOverflow.Ellipsis,
        )
        if (detail.description.length > 62) {
            TextButton(
                onClick = { expanded = !expanded },
                contentPadding = PaddingValues(0.dp),
            ) {
                Text(if (expanded) "收起" else "…展开", color = MutedInk)
            }
        }
    }
}

@Composable
private fun RelatedPlansSection(detail: PlaceDetail) {
    Column(modifier = Modifier.padding(top = 22.dp)) {
        LazyRow(
            contentPadding = PaddingValues(horizontal = 24.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(detail.relatedPlans) { plan ->
                Surface(
                    modifier = Modifier.size(width = 250.dp, height = 76.dp),
                    color = Color.White,
                    shape = RoundedCornerShape(18.dp),
                    border = BorderStroke(1.dp, Color(0xFFEFEFEF)),
                ) {
                    Column(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalArrangement = Arrangement.Center,
                    ) {
                        Text("热门计划", style = MaterialTheme.typography.labelMedium, color = Color(0xFFC8792B))
                        Text(plan, style = MaterialTheme.typography.titleSmall, color = Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

@Composable
private fun ReviewSection(
    detail: PlaceDetail,
    onOpen: (ReviewSource) -> Unit,
    modifier: Modifier = Modifier,
) {
    var sourcesExpanded by remember(detail.summary.id) { mutableStateOf(true) }
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "真实评价",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = Ink,
            modifier = Modifier.padding(horizontal = 24.dp),
        )

        if (detail.positiveHighlights.isNotEmpty()) {
            HighlightCard(
                detail.positiveHighlights,
                PositiveBackground,
                Modifier.padding(horizontal = 24.dp),
            )
        }
        if (detail.negativeHighlights.isNotEmpty()) {
            HighlightCard(
                detail.negativeHighlights,
                CautionBackground,
                Modifier.padding(horizontal = 24.dp),
            )
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { sourcesExpanded = !sourcesExpanded }
                .padding(horizontal = 24.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                if (sourcesExpanded) "收起来源" else "查看来源",
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF9A9A9A),
            )
            Surface(
                color = XiaohongshuRed,
                shape = CircleShape,
                modifier = Modifier.padding(start = 5.dp).size(16.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("源", color = Color.White, style = MaterialTheme.typography.labelSmall)
                }
            }
            Icon(
                if (sourcesExpanded) Icons.Outlined.KeyboardArrowUp else Icons.Outlined.KeyboardArrowDown,
                contentDescription = null,
                tint = Color(0xFFAAAAAA),
                modifier = Modifier.size(18.dp),
            )
        }
        if (sourcesExpanded) {
            LazyRow(
                contentPadding = PaddingValues(horizontal = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(detail.reviewSources, key = { it.id }) { source ->
                    SourceCard(source = source, onClick = { onOpen(source) })
                }
            }
        }
        detail.reviewSubtitle?.takeIf { it.isNotBlank() }?.let {
            Text(
                it,
                style = MaterialTheme.typography.labelSmall,
                color = Color(0xFFAAAAAA),
                modifier = Modifier.padding(horizontal = 24.dp),
            )
        }
    }
}

@Composable
private fun HighlightCard(
    highlights: List<ReviewHighlight>,
    background: Color,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = background),
        shape = RoundedCornerShape(22.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 17.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            highlights.forEach { highlight ->
                Text(
                    text = buildAnnotatedString {
                        withStyle(SpanStyle(fontWeight = FontWeight.Bold, color = Ink)) {
                            append(highlight.title)
                            append("：")
                        }
                        append(highlight.description)
                    },
                    style = MaterialTheme.typography.bodyLarge,
                    color = Color(0xFF555555),
                )
            }
        }
    }
}

@Composable
private fun SourceCard(source: ReviewSource, onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .size(width = 276.dp, height = 92.dp)
            .clip(RoundedCornerShape(16.dp))
            .clickable(onClick = onClick),
        color = Color(0xFFF7F7F7),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Text(
                    source.title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium,
                    color = Ink,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Icon(
                    Icons.AutoMirrored.Outlined.KeyboardArrowRight,
                    contentDescription = "查看原文",
                    tint = Color(0xFFB7B7B7),
                    modifier = Modifier.size(18.dp),
                )
            }
            Spacer(Modifier.weight(1f))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(color = XiaohongshuRed, shape = CircleShape, modifier = Modifier.size(15.dp)) {}
                Text(
                    "来自${source.platform}",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFFAAAAAA),
                    modifier = Modifier.padding(start = 5.dp),
                )
            }
        }
    }
}

@Composable
private fun InformationSection(
    detail: PlaceDetail,
    onOpenAddress: () -> Unit,
    onCall: () -> Unit,
    onFeedback: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val address = listOfNotNull(detail.summary.districtName, detail.summary.address)
        .distinct()
        .joinToString(" · ")
        .takeIf { it.isNotBlank() }
    Column(modifier = modifier.fillMaxWidth().background(Color.White)) {
        detail.openingHours?.takeIf { it.isNotBlank() }?.let {
            InfoRow(Icons.Outlined.AccessTime, "营业时间", it)
            HorizontalDivider(color = Color(0xFFEDF0F4))
        }
        address?.let {
            InfoRow(Icons.Outlined.LocationOn, "地址", it, onClick = onOpenAddress)
            HorizontalDivider(color = Color(0xFFEDF0F4))
        }
        detail.phone?.takeIf { it.isNotBlank() }?.let {
            InfoRow(Icons.Outlined.Phone, "电话", it, onClick = onCall)
            HorizontalDivider(color = Color(0xFFEDF0F4))
        }
        val provider = listOf("高德地点信息") + detail.sourceLabels.filterNot { it.equals("AMAP", true) }
        InfoRow(Icons.Outlined.CheckCircle, "内容来源", provider.distinct().joinToString(" · "))
        HorizontalDivider(color = Color(0xFFEDF0F4))
        InfoRow(Icons.Outlined.Flag, "反馈问题", "信息有误？告诉我们", onClick = onFeedback)
    }
}

@Composable
private fun InfoRow(
    icon: ImageVector,
    label: String,
    value: String,
    onClick: (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = Ink, modifier = Modifier.size(22.dp))
        Column(modifier = Modifier.padding(start = 14.dp).weight(1f)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MutedInk)
            Text(value, style = MaterialTheme.typography.bodyLarge, color = Ink, modifier = Modifier.padding(top = 2.dp))
        }
        if (onClick != null) {
            Icon(
                Icons.AutoMirrored.Outlined.KeyboardArrowRight,
                contentDescription = null,
                tint = Color(0xFFAAB2BF),
            )
        }
    }
}

@Composable
private fun RefreshNotice(onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Surface(modifier = modifier.fillMaxWidth(), color = Color(0xFFFFF7E9), shape = RoundedCornerShape(16.dp)) {
        Row(
            modifier = Modifier.padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("暂时无法更新用户内容，当前展示地点公开信息", style = MaterialTheme.typography.bodySmall, color = MutedInk, modifier = Modifier.weight(1f))
            TextButton(onClick = onRetry) {
                Icon(Icons.Outlined.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
                Text("重试", modifier = Modifier.padding(start = 4.dp))
            }
        }
    }
}

@Composable
private fun BottomActions(
    favorite: Boolean,
    checkedIn: Boolean,
    onAdd: () -> Unit,
    onFavorite: () -> Unit,
    onCheckIn: () -> Unit,
    onNavigate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = Color.White,
        shadowElevation = 12.dp,
    ) {
        Row(
            modifier = Modifier
                .navigationBarsPadding()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ActionButton(Icons.Outlined.Add, "添加至", onAdd, Modifier.weight(1f))
            ActionButton(Icons.Outlined.Favorite, if (favorite) "已收藏" else "收藏", onFavorite, Modifier.weight(1f), favorite)
            ActionButton(Icons.Outlined.CheckCircle, if (checkedIn) "已打卡" else "打卡", onCheckIn, Modifier.weight(1f), checkedIn)
            ActionButton(Icons.Outlined.Navigation, "导航", onNavigate, Modifier.weight(1f))
        }
    }
}

@Composable
private fun ActionButton(
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    selected: Boolean = false,
) {
    val background = when {
        selected -> Color(0xFFE6F1FF)
        else -> Color.White
    }
    val foreground = if (selected) MaterialTheme.colorScheme.primary else Ink
    Surface(
        modifier = modifier
            .height(60.dp)
            .clip(RoundedCornerShape(18.dp))
            .clickable(onClick = onClick),
        color = background,
        shape = RoundedCornerShape(18.dp),
        border = BorderStroke(1.dp, Color(0xFFE3E3E3)),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Icon(icon, contentDescription = null, tint = foreground, modifier = Modifier.size(21.dp))
            Text(label, style = MaterialTheme.typography.labelMedium, color = foreground, modifier = Modifier.padding(top = 3.dp))
        }
    }
}

@Composable
private fun InfoChip(text: String, background: Color, foreground: Color) {
    Surface(color = background, shape = RoundedCornerShape(10.dp)) {
        Text(
            text = text,
            color = foreground,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            maxLines = 1,
        )
    }
}

@Composable
private fun MissingPlace(onBack: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Outlined.Close, contentDescription = null, tint = MutedInk, modifier = Modifier.size(38.dp))
        Text("没有找到这个地点", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 12.dp))
        Button(onClick = onBack, modifier = Modifier.padding(top = 18.dp)) { Text("返回探索") }
    }
}

private fun openUrl(context: Context, url: String) {
    openIntent(context, Intent(Intent.ACTION_VIEW, Uri.parse(url)))
}

private fun openDialer(context: Context, phone: String) {
    openIntent(context, Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Uri.encode(phone)}")))
}

private fun openNavigation(context: Context, detail: PlaceDetail) {
    val summary = detail.summary
    val uri = if (summary.latitude != null && summary.longitude != null) {
        Uri.parse("geo:${summary.latitude},${summary.longitude}?q=${summary.latitude},${summary.longitude}(${Uri.encode(summary.name)})")
    } else {
        Uri.parse("geo:0,0?q=${Uri.encode(listOfNotNull(summary.cityName, summary.address, summary.name).joinToString(" "))}")
    }
    openIntent(context, Intent(Intent.ACTION_VIEW, uri))
}

private fun openIntent(context: Context, intent: Intent) {
    try {
        context.startActivity(intent)
    } catch (_: ActivityNotFoundException) {
        Toast.makeText(context, "未找到可处理此操作的应用", Toast.LENGTH_SHORT).show()
    } catch (_: SecurityException) {
        Toast.makeText(context, "未找到可处理此操作的应用", Toast.LENGTH_SHORT).show()
    }
}
