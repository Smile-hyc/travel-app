package com.heoclub.aitravel.ui.plan

import android.widget.Toast
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ArrowForward
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import com.heoclub.aitravel.data.model.TravelPlan

@Composable
fun PlanHomeScreen(
    viewModel: PlanHomeViewModel,
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
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
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
            WelcomePanel(onAskAi = onAskAi)
        }
        item {
            SectionTitle(title = "我的计划")
        }
        items(plans, key = { it.id }) { plan ->
            TravelPlanCard(
                plan = plan,
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
            Text(
                text = "AI",
                color = Color.White,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
        }
        Text(
            text = "AI旅行助手",
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
private fun WelcomePanel(onAskAi: (String) -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        shape = RoundedCornerShape(28.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    brush = Brush.linearGradient(
                        listOf(Color(0xFFEAF5FF), Color(0xFFFFFFFF)),
                    ),
                    shape = RoundedCornerShape(28.dp),
                )
                .padding(18.dp),
        ) {
            CityLineArt(modifier = Modifier.matchParentSize())
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    text = "陪你规划下一段旅程",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF071A3D),
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Outlined.LocationOn,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = "当前城市：成都市",
                        modifier = Modifier.padding(start = 6.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                AiQuestionPill(
                    text = "帮我介绍今天的行程",
                    onClick = { onAskAi("帮我介绍今天的行程") },
                )
                AiQuestionPill(
                    text = "目的地有哪些值得去的地方？",
                    onClick = { onAskAi("目的地有哪些值得去的地方？") },
                )
            }
        }
    }
}

@Composable
private fun AiQuestionPill(
    text: String,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = Color.White,
        shape = RoundedCornerShape(18.dp),
        shadowElevation = 3.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                color = Color(0xFFE6EDFF),
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
                fontWeight = FontWeight.SemiBold,
            )
            Icon(
                imageVector = Icons.AutoMirrored.Outlined.ArrowForward,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun TravelPlanCard(
    plan: TravelPlan,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(22.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            TravelCover(plan.destination)
            Text(
                text = plan.title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF071A3D),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Outlined.CalendarMonth,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
                Text(
                    text = plan.dateRange,
                    modifier = Modifier.padding(start = 8.dp),
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.SemiBold,
                )
            }
            Text(
                text = "${plan.dayCount.coerceAtLeast(0)}天 · ${plan.placeCount}个地点",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                plan.preferences.take(3).forEach { tag ->
                    TagChip(text = tag)
                }
            }
        }
    }
}

@Composable
private fun TravelCover(destination: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(118.dp)
            .clip(RoundedCornerShape(18.dp))
            .background(Color(0xFFEAF5FF)),
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawCircle(Color(0xFFBFE3FF), radius = size.width * 0.28f, center = Offset(size.width * 0.8f, size.height * 0.2f))
            drawCircle(Color(0xFF91D3C3), radius = size.width * 0.22f, center = Offset(size.width * 0.15f, size.height * 0.95f))
            drawCircle(Color(0xFF5FA8FF), radius = size.width * 0.08f, center = Offset(size.width * 0.75f, size.height * 0.78f))
            drawLine(Color.White.copy(alpha = 0.75f), Offset(size.width * 0.18f, size.height * 0.72f), Offset(size.width * 0.95f, size.height * 0.35f), strokeWidth = 8f)
        }
        Text(
            text = destination,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(16.dp),
            color = Color(0xFF071A3D),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun SectionTitle(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold,
        color = Color(0xFF071A3D),
    )
}

@Composable
private fun TagChip(text: String) {
    Surface(
        color = Color(0xFFEAF2FF),
        shape = RoundedCornerShape(50),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = MaterialTheme.colorScheme.primary,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold,
        )
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

@Composable
private fun CityLineArt(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        drawCircle(Color.White.copy(alpha = 0.65f), radius = size.width * 0.18f, center = Offset(size.width * 0.95f, size.height * 0.1f))
        drawLine(Color(0xFFB7D9FF), Offset(size.width * 0.62f, size.height * 0.78f), Offset(size.width * 0.92f, size.height * 0.35f), strokeWidth = 4f)
        drawLine(Color(0xFFB7D9FF), Offset(size.width * 0.7f, size.height * 0.78f), Offset(size.width * 0.92f, size.height * 0.35f), strokeWidth = 4f)
    }
}
