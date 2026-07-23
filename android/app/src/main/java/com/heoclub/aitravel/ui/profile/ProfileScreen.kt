package com.heoclub.aitravel.ui.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.heoclub.aitravel.ui.home.HomeUiState

@Composable
fun ProfileScreen(
    viewModel: ProfileViewModel,
    onLoggedOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val state by viewModel.uiState.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = "我的",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )

        UserInfoCard(
            user = state.user,
            onLogout = {
                viewModel.logout()
                onLoggedOut()
            },
        )

        BackendStatusCard(
            uiState = state.healthState,
            onRetry = viewModel::checkHealth,
        )
    }
}

@Composable
private fun UserInfoCard(
    user: com.heoclub.aitravel.data.model.User?,
    onLogout: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(22.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    color = Color(0xFFEAF2FF),
                    shape = CircleShape,
                ) {
                    Icon(
                        imageVector = Icons.Outlined.Person,
                        contentDescription = null,
                        modifier = Modifier.padding(14.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
                Column(modifier = Modifier.padding(start = 14.dp)) {
                    Text(
                        text = user?.nickname?.takeIf { it.isNotBlank() } ?: "旅行者",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = user?.phone ?: "",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
            OutlinedButton(
                onClick = onLogout,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(50),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Outlined.Logout,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text("退出登录")
            }
        }
    }
}

@Composable
private fun BackendStatusCard(
    uiState: HomeUiState,
    onRetry: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(containerColor = Color.White),
        shape = RoundedCornerShape(22.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("开发环境", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("FastAPI 后端连接状态", color = MaterialTheme.colorScheme.onSurfaceVariant)
            when (uiState) {
                HomeUiState.Loading -> Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.padding(end = 10.dp))
                    Text("正在检测后端服务...")
                }
                is HomeUiState.Success -> {
                    Text("连接成功", color = Color(0xFF21A67A), fontWeight = FontWeight.Bold)
                    Text(uiState.message, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                is HomeUiState.Error -> {
                    Text("连接失败", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Bold)
                    Text(uiState.message, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            OutlinedButton(onClick = onRetry) {
                Icon(Icons.Outlined.Refresh, contentDescription = null)
                Text("重新检测", modifier = Modifier.padding(start = 8.dp))
            }
        }
    }
}
