package com.heoclub.aitravel.ui.place

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Favorite
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Navigation
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.model.PlaceDetail
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.data.repository.AddPlaceTarget
import com.heoclub.aitravel.ui.components.AddPlaceToPlanDialog
import com.heoclub.aitravel.ui.components.PlaceCoverImage
import com.heoclub.aitravel.ui.components.PlaceImageCarousel

@Composable
fun PlaceDetailScreen(
    viewModel: PlaceDetailViewModel,
    travelPlans: List<TravelPlan>,
    onBack: () -> Unit,
    onCreatePlan: () -> Unit,
    onAddToPlan: (TravelPlan, AddPlaceTarget) -> AddPlaceResult,
    modifier: Modifier = Modifier,
) {
    val placeDetail by viewModel.placeDetail.collectAsState()
    var showPlanDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current

    if (placeDetail == null) {
        MissingPlace(onBack = onBack, modifier = modifier)
        return
    }

    val detail = requireNotNull(placeDetail)
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item {
                DetailHeader(detail = detail, onBack = onBack)
            }
            item {
                DetailContentCard(detail = detail, modifier = Modifier.padding(horizontal = 20.dp))
            }
            item {
                ReviewCard(detail = detail, modifier = Modifier.padding(horizontal = 20.dp))
            }
            item {
                InfoCard(detail = detail, modifier = Modifier.padding(horizontal = 20.dp))
            }
            item {
                Spacer(modifier = Modifier.height(92.dp))
            }
        }

        BottomActions(
            favorite = detail.summary.isFavorite,
            onAdd = { showPlanDialog = true },
            onFavorite = { viewModel.toggleFavorite() },
            onCheckIn = {
                Toast.makeText(context, "打卡功能后续接入", Toast.LENGTH_SHORT).show()
            },
            onNavigate = {
                Toast.makeText(context, "接入路线导航后开放", Toast.LENGTH_SHORT).show()
            },
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
            onResult = { message ->
                Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
            },
        )
    }
}

@Composable
private fun MissingPlace(
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("没有找到这个地点")
        Button(onClick = onBack, modifier = Modifier.padding(top = 16.dp)) {
            Text("返回")
        }
    }
}

@Composable
private fun DetailHeader(
    detail: PlaceDetail,
    onBack: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(270.dp),
    ) {
        PlaceCoverImage(
            imageUrl = detail.summary.displayCoverImageUrl,
            placeName = detail.summary.name,
            modifier = Modifier.fillMaxSize(),
            shape = RoundedCornerShape(0.dp),
        )
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = 0.16f),
                            Color.White.copy(alpha = 0.58f),
                            Color.White.copy(alpha = 0.96f),
                        ),
                    ),
                ),
        )
        Surface(
            modifier = Modifier.padding(20.dp),
            color = Color.White,
            shape = CircleShape,
            shadowElevation = 3.dp,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
            }
        }
        Column(
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = detail.summary.name,
                style = MaterialTheme.typography.headlineLarge,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF071A3D),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                InfoChip(detail.summary.rankingText, Color(0xFFFFF0D5), Color(0xFFFF8A00))
                InfoChip(detail.summary.popularity, Color(0xFFEFEFF3), Color(0xFF526173))
                InfoChip("AI 生成", Color(0xFFEAF2FF), MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun DetailContentCard(
    detail: PlaceDetail,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(24.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            PlaceImageCarousel(
                images = detail.images,
                fallbackUrls = detail.summary.displayImageUrls,
                placeName = detail.summary.name,
            )
            if (detail.summary.displayImageUrls.isNotEmpty()) {
                Text(
                    text = "图片来源：高德地图",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Text("地点介绍", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(detail.description, style = MaterialTheme.typography.bodyLarge, color = Color(0xFF162235))
            Text("热门计划", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                detail.relatedPlans.forEach { plan ->
                    InfoChip(plan, Color(0xFFEAF2FF), MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}

@Composable
private fun ReviewCard(
    detail: PlaceDetail,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Color(0xFFF1F9E9)),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("真实评价", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            detail.positiveHighlights.forEach {
                Text("• $it", color = Color(0xFF213221))
            }
            Spacer(modifier = Modifier.height(4.dp))
            detail.negativeHighlights.forEach {
                Text("• $it", color = Color(0xFF6B4A43))
            }
        }
    }
}

@Composable
private fun InfoCard(
    detail: PlaceDetail,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            InfoLine("营业时间", detail.openingHours)
            InfoLine("地址", detail.summary.displayAddress)
            InfoLine("电话", detail.phone)
            InfoLine("内容来源", detail.sourceLabels.joinToString(" / "))
            InfoLine("反馈问题", "发现错误信息后续可在这里提交")
        }
    }
}

@Composable
private fun InfoLine(label: String, value: String) {
    Column {
        Text(label, fontWeight = FontWeight.Bold)
        Text(value, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun BottomActions(
    favorite: Boolean,
    onAdd: () -> Unit,
    onFavorite: () -> Unit,
    onCheckIn: () -> Unit,
    onNavigate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = Color.White,
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            OutlinedButton(onClick = onAdd, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.Add, contentDescription = null)
                Text("添加至")
            }
            OutlinedButton(onClick = onFavorite, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.Favorite, contentDescription = null)
                Text(if (favorite) "已收藏" else "收藏")
            }
            OutlinedButton(onClick = onCheckIn, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.CheckCircle, contentDescription = null)
                Text("打卡")
            }
            OutlinedButton(onClick = onNavigate, modifier = Modifier.weight(1f)) {
                Icon(Icons.Outlined.Navigation, contentDescription = null)
                Text("导航")
            }
        }
    }
}

@Composable
private fun InfoChip(
    text: String,
    containerColor: Color,
    textColor: Color,
) {
    Surface(color = containerColor, shape = RoundedCornerShape(50)) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = textColor,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
