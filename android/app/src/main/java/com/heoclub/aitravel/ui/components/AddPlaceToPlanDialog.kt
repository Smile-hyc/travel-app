package com.heoclub.aitravel.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.data.model.TravelPlan
import com.heoclub.aitravel.data.repository.AddPlaceResult
import com.heoclub.aitravel.data.repository.AddPlaceTarget

@Composable
fun AddPlaceToPlanDialog(
    plans: List<TravelPlan>,
    placeName: String,
    onDismiss: () -> Unit,
    onCreatePlan: (() -> Unit)? = null,
    onConfirm: (TravelPlan, AddPlaceTarget) -> AddPlaceResult,
    onResult: (String) -> Unit,
) {
    var selectedPlanId by remember(plans) { mutableStateOf(plans.firstOrNull()?.id) }
    var selectedTarget by remember(selectedPlanId) { mutableStateOf<AddPlaceTarget>(AddPlaceTarget.Day(1)) }
    val selectedPlan = plans.firstOrNull { it.id == selectedPlanId }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("添加到旅行计划") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(
                    text = placeName,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )

                if (plans.isEmpty()) {
                    Text("还没有旅行计划，可以先创建一个计划。")
                } else {
                    Text("选择计划", fontWeight = FontWeight.SemiBold)
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        plans.forEach { plan ->
                            SelectableCard(
                                text = "${plan.title} · ${plan.placeCount} 个地点",
                                selected = plan.id == selectedPlanId,
                                onClick = { selectedPlanId = plan.id },
                            )
                        }
                    }

                    selectedPlan?.let { plan ->
                        Text("加入位置", fontWeight = FontWeight.SemiBold)
                        Row(
                            modifier = Modifier.horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            TargetChip(
                                text = "待规划",
                                selected = selectedTarget == AddPlaceTarget.Unplanned,
                                onClick = { selectedTarget = AddPlaceTarget.Unplanned },
                            )
                            plan.days.forEach { day ->
                                val target = AddPlaceTarget.Day(day.dayIndex)
                                TargetChip(
                                    text = day.title,
                                    selected = selectedTarget == target,
                                    onClick = { selectedTarget = target },
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (plans.isEmpty()) {
                if (onCreatePlan != null) {
                    Button(
                        onClick = {
                            onDismiss()
                            onCreatePlan()
                        },
                    ) {
                        Text("创建计划")
                    }
                }
            } else {
                Button(
                    onClick = {
                        val plan = selectedPlan ?: return@Button
                        val result = onConfirm(plan, selectedTarget)
                        onDismiss()
                        onResult(addPlaceResultMessage(result, plan, selectedTarget))
                    },
                ) {
                    Text("添加")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("取消")
            }
        },
    )
}

fun addPlaceResultMessage(
    result: AddPlaceResult,
    plan: TravelPlan?,
    target: AddPlaceTarget,
): String {
    val targetText = when (target) {
        is AddPlaceTarget.Day -> "DAY ${target.dayIndex}"
        AddPlaceTarget.Unplanned -> "待规划"
    }
    return when (result) {
        AddPlaceResult.ADDED -> "已加入「${plan?.title.orEmpty()}」$targetText"
        AddPlaceResult.ALREADY_EXISTS -> "这个地点已经在计划里了"
        AddPlaceResult.MISSING_LOCATION -> "这个地点缺少坐标，不能加入路线 DAY；可以先加入待规划"
        AddPlaceResult.PLAN_NOT_FOUND -> "没有找到可加入的旅行计划"
    }
}

@Composable
private fun SelectableCard(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        color = if (selected) Color(0xFFEAF2FF) else Color(0xFFF6F8FB),
        shape = RoundedCornerShape(16.dp),
        tonalElevation = if (selected) 2.dp else 0.dp,
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(12.dp),
            color = if (selected) MaterialTheme.colorScheme.primary else Color(0xFF344054),
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
        )
    }
}

@Composable
private fun TargetChip(
    text: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val container = if (selected) MaterialTheme.colorScheme.primary else Color(0xFFF4F7FB)
    val content = if (selected) Color.White else Color(0xFF475467)
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        color = container,
        shape = RoundedCornerShape(50),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
            color = content,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
