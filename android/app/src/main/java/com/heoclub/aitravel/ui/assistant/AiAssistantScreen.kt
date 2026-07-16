package com.heoclub.aitravel.ui.assistant

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.SmartToy
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun AiAssistantScreen(
    viewModel: AiAssistantViewModel,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsState()
    var input by remember { mutableStateOf("") }
    val currentPlan = state.currentPlan

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF6FAFF))
            .padding(18.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(color = Color.White, shape = CircleShape, shadowElevation = 2.dp) {
                IconButton(onClick = onClose) {
                    Icon(Icons.Outlined.Close, contentDescription = "关闭")
                }
            }
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 12.dp),
                color = Color.White.copy(alpha = 0.9f),
                shape = RoundedCornerShape(50),
                shadowElevation = 1.dp,
            ) {
                Text(
                    text = currentPlan?.title ?: "AI 旅行助手",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = Color(0xFF13213A),
                )
            }
        }

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .padding(top = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(state.messages, key = { it.id }) { message ->
                ChatBubble(message = message)
            }
            if (state.isSending) {
                item {
                    AssistantStatusBubble(text = "正在分析计划…")
                }
            }
            state.errorMessage?.let { error ->
                item {
                    ErrorBubble(
                        text = error,
                        onRetry = viewModel::retryLastMessage,
                    )
                }
            }
            state.actionSet?.let { actionSet ->
                item {
                    SuggestedActionsPanel(
                        actionSet = actionSet,
                        isApplying = state.isApplyingActions,
                        onToggle = viewModel::toggleAction,
                        onApply = viewModel::applySuggestedActions,
                        onCancel = viewModel::clearSuggestedActions,
                    )
                }
            }
            state.actionMessage?.let { message ->
                item {
                    ActionMessageBubble(
                        text = message,
                        canUndo = state.undoToken != null,
                        onUndo = viewModel::undoLastAiAction,
                    )
                }
            }
        }

        QuickActionRow(
            labels = state.quickReplies,
            enabled = !state.isSending && !state.isApplyingActions,
            onClick = viewModel::sendMessage,
        )
        Spacer(modifier = Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                enabled = !state.isSending && !state.isApplyingActions,
                modifier = Modifier.weight(1f),
                placeholder = { Text("发消息，例如：帮我把待规划地点安排进 DAY 1") },
                shape = RoundedCornerShape(24.dp),
                singleLine = false,
                maxLines = 3,
            )
            Button(
                enabled = input.isNotBlank() && !state.isSending && !state.isApplyingActions,
                onClick = {
                    viewModel.sendMessage(input)
                    input = ""
                },
                modifier = Modifier.padding(start = 10.dp),
                shape = CircleShape,
            ) {
                Icon(Icons.AutoMirrored.Outlined.Send, contentDescription = "发送")
            }
        }
    }
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (message.fromUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (message.fromUser) Color(0xFFBFF4F8) else Color.White,
            shape = RoundedCornerShape(
                topStart = 20.dp,
                topEnd = 20.dp,
                bottomStart = if (message.fromUser) 20.dp else 4.dp,
                bottomEnd = if (message.fromUser) 4.dp else 20.dp,
            ),
            shadowElevation = if (message.fromUser) 0.dp else 2.dp,
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.Top,
            ) {
                if (!message.fromUser) {
                    Icon(
                        imageVector = Icons.Outlined.SmartToy,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(end = 8.dp),
                    )
                }
                Text(
                    text = message.text,
                    color = Color(0xFF162235),
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
        }
    }
}

@Composable
private fun SuggestedActionsPanel(
    actionSet: AiActionSetUi,
    isApplying: Boolean,
    onToggle: (String) -> Unit,
    onApply: () -> Unit,
    onCancel: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color.White,
        shape = RoundedCornerShape(24.dp),
        shadowElevation = 3.dp,
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                text = "AI 建议调整",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF13213A),
            )
            Text(
                text = "这些建议不会自动修改计划，确认后才会应用。",
                style = MaterialTheme.typography.bodySmall,
                color = Color(0xFF66758A),
            )
            actionSet.warnings.forEach { warning ->
                Text(
                    text = "提示：$warning",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color(0xFF9A6A00),
                )
            }
            actionSet.cards.forEach { card ->
                Surface(
                    color = Color(0xFFF3F8FF),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Checkbox(
                            checked = card.selected,
                            onCheckedChange = { onToggle(card.action.id) },
                        )
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = card.summary,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                                color = Color(0xFF13213A),
                            )
                            card.reason?.takeIf { it.isNotBlank() }?.let {
                                Text(
                                    text = it,
                                    modifier = Modifier.padding(top = 4.dp),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Color(0xFF66758A),
                                )
                            }
                        }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onApply,
                    enabled = !isApplying && actionSet.cards.any { it.selected },
                    shape = RoundedCornerShape(50),
                ) {
                    Text(if (isApplying) "正在应用…" else "确认应用")
                }
                OutlinedButton(
                    onClick = onCancel,
                    enabled = !isApplying,
                    shape = RoundedCornerShape(50),
                ) {
                    Text("取消建议")
                }
            }
        }
    }
}

@Composable
private fun AssistantStatusBubble(text: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
        Surface(color = Color.White, shape = RoundedCornerShape(20.dp), shadowElevation = 2.dp) {
            Text(
                text = text,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                color = Color(0xFF627084),
            )
        }
    }
}

@Composable
private fun ErrorBubble(text: String, onRetry: () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFFFFF2F2),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = text,
                modifier = Modifier.weight(1f),
                color = Color(0xFF9B2C2C),
                style = MaterialTheme.typography.bodyMedium,
            )
            TextButton(onClick = onRetry) {
                Text("重试")
            }
        }
    }
}

@Composable
private fun ActionMessageBubble(
    text: String,
    canUndo: Boolean,
    onUndo: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Color(0xFFEFFAF4),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = text,
                modifier = Modifier.weight(1f),
                color = Color(0xFF206B43),
                style = MaterialTheme.typography.bodyMedium,
            )
            if (canUndo) {
                TextButton(onClick = onUndo) {
                    Text("撤销")
                }
            }
        }
    }
}

@Composable
private fun QuickActionRow(
    labels: List<String>,
    enabled: Boolean,
    onClick: (String) -> Unit,
) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(labels.take(4)) { label ->
            Surface(
                color = if (enabled) Color.White else Color.White.copy(alpha = 0.5f),
                shape = RoundedCornerShape(50),
                shadowElevation = 1.dp,
                onClick = {
                    if (enabled) onClick(label)
                },
            ) {
                Text(
                    text = label,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}
