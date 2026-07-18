package com.heoclub.aitravel.ui.plan

import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import com.heoclub.aitravel.R
import com.heoclub.aitravel.data.location.CurrentLocationUiState
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.ui.components.PlaceCoverImage

@Composable
fun PlanHomeScreen(
    viewModel: PlanHomeViewModel,
    locationState: CurrentLocationUiState,
    onLocate: () -> Unit,
    onCreatePlan: () -> Unit,
    onOpenPlan: (String) -> Unit,
    onAskAi: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val plans by viewModel.plans.collectAsState()
    val context = LocalContext.current

    LazyColumn(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF7F9FC))
            .padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        item {
            Spacer(modifier = Modifier.height(12.dp))
            PlanHeader(
                onSearch = {
                    Toast.makeText(context, "搜索功能后续接入", Toast.LENGTH_SHORT).show()
                },
                onCreatePlan = onCreatePlan,
            )
        }
        item {
            WelcomeSection(
                locationState = locationState,
                onLocate = onLocate,
                onAskAi = onAskAi,
            )
        }
        item {
            PlansHeading(planCount = plans.size)
        }
        itemsIndexed(plans, key = { _, plan -> plan.id }) { index, plan ->
            TravelPlanItem(
                plan = plan,
                featured = index == 0,
                onClick = { onOpenPlan(plan.id) },
            )
        }
        item {
            Spacer(modifier = Modifier.height(92.dp))
        }
    }
}

@Composable
private fun PlanHeader(
    onSearch: () -> Unit,
    onCreatePlan: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(42.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(MaterialTheme.colorScheme.primary),
            contentAlignment = Alignment.Center,
        ) {
            Image(
                painter = painterResource(id = R.drawable.tuling_logo),
                contentDescription = "途灵",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
        Text(
            text = "途灵",
            modifier = Modifier
                .weight(1f)
                .padding(start = 12.dp),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
        CircleIconButton(
            icon = Icons.Outlined.Search,
            contentDescription = "搜索",
            onClick = onSearch,
        )
        CircleIconButton(
            icon = Icons.Outlined.Add,
            contentDescription = "新建计划",
            onClick = onCreatePlan,
        )
    }
}

@Composable
private fun WelcomeSection(
    locationState: CurrentLocationUiState,
    onLocate: () -> Unit,
    onAskAi: (String) -> Unit,
) {
    val cityText = locationState.location?.cityName ?: when {
        locationState.isLocating -> "定位中…"
        locationState.errorMessage != null -> "点击获取定位"
        else -> "等待定位"
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(
            text = "下一站，想去哪里？",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF071A3D),
        )
        Row(
            modifier = Modifier
                .clip(RoundedCornerShape(10.dp))
                .clickable(onClick = onLocate)
                .padding(vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.LocationOn,
                contentDescription = "刷新当前位置",
                modifier = Modifier.size(19.dp),
                tint = MaterialTheme.colorScheme.primary,
            )
            Text(
                text = "当前城市  $cityText",
                modifier = Modifier.padding(start = 7.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Column {
            AiActionRow(
                text = "介绍一下今天的行程",
                onClick = { onAskAi("帮我介绍今天的行程") },
            )
            HorizontalDivider(
                modifier = Modifier.padding(start = 48.dp),
                color = Color(0xFFDDE5EE),
            )
            AiActionRow(
                text = "发现目的地值得去的地方",
                onClick = { onAskAi("目的地有哪些值得去的地方？") },
            )
        }
    }
}

@Composable
private fun AiActionRow(
    text: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            modifier = Modifier.size(36.dp),
            color = Color(0xFFE5F0FF),
            shape = CircleShape,
        ) {
            Icon(
                imageVector = Icons.Outlined.SmartToy,
                contentDescription = null,
                modifier = Modifier.padding(8.dp),
                tint = MaterialTheme.colorScheme.primary,
            )
        }
        Text(
            text = text,
            modifier = Modifier
                .weight(1f)
                .padding(start = 12.dp),
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.Medium,
            color = Color(0xFF14243A),
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        Icon(
            imageVector = Icons.AutoMirrored.Outlined.ArrowForward,
            contentDescription = null,
            modifier = Modifier.size(20.dp),
            tint = Color(0xFF718096),
        )
    }
}

@Composable
private fun PlansHeading(planCount: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(
            text = "我的计划",
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF071A3D),
        )
        Text(
            text = "$planCount 段旅程",
            color = Color(0xFF718096),
            style = MaterialTheme.typography.labelLarge,
        )
    }
}

@Composable
private fun TravelPlanItem(
    plan: TravelPlan,
    featured: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        color = Color(0xFFFCFDFE),
        border = BorderStroke(1.dp, Color(0xFFDDE6F0)),
        tonalElevation = 0.dp,
        shadowElevation = 3.dp,
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            TravelPlanCover(
                plan = plan,
                height = if (featured) 196.dp else 164.dp,
            )

            Column(
                modifier = Modifier.padding(
                    start = 8.dp,
                    top = 14.dp,
                    end = 8.dp,
                    bottom = 8.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = plan.title,
                        modifier = Modifier.weight(1f),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF071A3D),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Surface(
                        modifier = Modifier.size(36.dp),
                        shape = CircleShape,
                        color = MaterialTheme.colorScheme.primary.copy(alpha = 0.10f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Outlined.ArrowForward,
                                contentDescription = "打开${plan.title}",
                                modifier = Modifier.size(19.dp),
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }

                HorizontalDivider(
                    thickness = 1.dp,
                    color = Color(0xFFE8EDF3),
                )

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Outlined.CalendarMonth,
                        contentDescription = null,
                        modifier = Modifier.size(19.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = plan.dateRange,
                        modifier = Modifier.padding(start = 7.dp),
                        color = Color(0xFF365F8D),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                    )
                    Spacer(modifier = Modifier.weight(1f))
                    Text(
                        text = "${plan.dayCount.coerceAtLeast(0)}天  ·  ${plan.placeCount}个地点",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }

                if (plan.preferences.isNotEmpty()) {
                    Text(
                        text = plan.preferences.take(3).joinToString("  ·  "),
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.labelLarge,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
private fun TravelPlanCover(
    plan: TravelPlan,
    height: androidx.compose.ui.unit.Dp,
) {
    val shape = RoundedCornerShape(20.dp)
    val remoteCover = plan.firstRemoteCoverUrl()
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(height)
            .clip(shape)
            .background(Color(0xFFE3EDF7)),
    ) {
        when {
            remoteCover != null -> PlaceCoverImage(
                imageUrl = remoteCover,
                placeName = plan.destination,
                modifier = Modifier.fillMaxSize(),
                shape = shape,
                contentScale = ContentScale.Crop,
            )

            plan.destination.contains("成都") -> Image(
                painter = painterResource(id = R.drawable.plan_cover_chengdu),
                contentDescription = "成都安顺桥旅行封面",
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )

            else -> PlaceCoverImage(
                imageUrl = null,
                placeName = plan.destination,
                modifier = Modifier.fillMaxSize(),
                shape = shape,
            )
        }
    }
}

private fun TravelPlan.firstRemoteCoverUrl(): String? {
    val items = days
        .sortedBy { it.dayIndex }
        .flatMap { day -> day.items.sortedBy { it.visitOrder } } + unplannedItems
    return items.asSequence()
        .flatMap { item -> (item.imageUrls + listOfNotNull(item.thumbnailUrl)).asSequence() }
        .map(String::trim)
        .firstOrNull { url ->
            url.startsWith("http://", ignoreCase = true) ||
                url.startsWith("https://", ignoreCase = true)
        }
}

@Composable
private fun CircleIconButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .padding(start = 8.dp)
            .size(46.dp),
        color = Color.White,
        shape = CircleShape,
        shadowElevation = 2.dp,
    ) {
        IconButton(onClick = onClick) {
            Icon(
                imageVector = icon,
                contentDescription = contentDescription,
                tint = Color(0xFF071A3D),
            )
        }
    }
}
