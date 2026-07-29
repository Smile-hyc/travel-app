package com.heoclub.aitravel.ui.auth

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.heoclub.aitravel.R
import com.heoclub.aitravel.data.repository.AuthRepository
import com.heoclub.aitravel.data.repository.HealthRepository
import com.heoclub.aitravel.ui.home.HomeUiState
import com.heoclub.aitravel.ui.profile.ProfileViewModel

@Composable
fun AuthScreen(
    authRepository: AuthRepository,
    healthRepository: HealthRepository,
    viewModelKey: Int,
    onAuthSuccess: () -> Unit,
) {
    // Force fresh ViewModel each time AuthScreen appears (key changes on each entry)
    val viewModel: ProfileViewModel = viewModel(
        key = "auth_$viewModelKey",
        factory = ProfileViewModel.Factory(authRepository, healthRepository),
    )
    val state by viewModel.uiState.collectAsState()
    var passwordVisible by rememberSaveable { mutableStateOf(false) }

    LaunchedEffect(state.isLoggedIn) {
        if (state.isLoggedIn) {
            onAuthSuccess()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            Spacer(modifier = Modifier.height(40.dp))

            // ── Header ──
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Image(
                    painter = painterResource(R.drawable.tuling_logo),
                    contentDescription = "途灵 Logo",
                    modifier = Modifier
                        .size(68.dp)
                        .clip(RoundedCornerShape(18.dp)),
                    contentScale = ContentScale.Crop,
                )
                Text(
                    text = "Touring",
                    fontSize = 32.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            Text(
                text = "途灵——智能旅行助手",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(modifier = Modifier.height(8.dp))

            // ── Auth Form Card ──
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                shape = RoundedCornerShape(22.dp),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    // Tab selector
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                    ) {
                        TextButton(
                            onClick = {
                                if (!state.isLoginForm) viewModel.toggleForm()
                            },
                        ) {
                            Text(
                                text = "登录",
                                fontWeight = if (state.isLoginForm) FontWeight.Bold else FontWeight.Normal,
                                style = MaterialTheme.typography.titleMedium,
                                color = if (state.isLoginForm) MaterialTheme.colorScheme.primary else Color.Gray,
                            )
                        }
                        Text(
                            text = "|",
                            modifier = Modifier.padding(horizontal = 12.dp),
                            style = MaterialTheme.typography.titleMedium,
                            color = Color.LightGray,
                        )
                        TextButton(
                            onClick = {
                                if (state.isLoginForm) viewModel.toggleForm()
                            },
                        ) {
                            Text(
                                text = "注册",
                                fontWeight = if (!state.isLoginForm) FontWeight.Bold else FontWeight.Normal,
                                style = MaterialTheme.typography.titleMedium,
                                color = if (!state.isLoginForm) MaterialTheme.colorScheme.primary else Color.Gray,
                            )
                        }
                    }

                    // Phone
                    OutlinedTextField(
                        value = state.phone,
                        onValueChange = viewModel::onPhoneChanged,
                        label = { Text("手机号") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !state.isLoading,
                        shape = RoundedCornerShape(14.dp),
                    )

                    // Password
                    OutlinedTextField(
                        value = state.password,
                        onValueChange = viewModel::onPasswordChanged,
                        label = { Text("密码") },
                        singleLine = true,
                        visualTransformation = if (passwordVisible) {
                            VisualTransformation.None
                        } else {
                            PasswordVisualTransformation()
                        },
                        trailingIcon = {
                            IconButton(onClick = { passwordVisible = !passwordVisible }) {
                                Icon(
                                    imageVector = if (passwordVisible) {
                                        Icons.Outlined.VisibilityOff
                                    } else {
                                        Icons.Outlined.Visibility
                                    },
                                    contentDescription = if (passwordVisible) "隐藏密码" else "显示密码",
                                )
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !state.isLoading,
                        shape = RoundedCornerShape(14.dp),
                    )

                    // Register-only fields
                    if (!state.isLoginForm) {
                        OutlinedTextField(
                            value = state.nickname,
                            onValueChange = viewModel::onNicknameChanged,
                            label = { Text("昵称（选填）") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !state.isLoading,
                            shape = RoundedCornerShape(14.dp),
                        )

                        // Captcha
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            OutlinedTextField(
                                value = state.captchaText,
                                onValueChange = viewModel::onCaptchaTextChanged,
                                label = { Text("验证码") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                                enabled = !state.isLoading,
                                shape = RoundedCornerShape(14.dp),
                            )
                            if (state.captchaImageBase64 != null) {
                                val bytes = Base64.decode(state.captchaImageBase64, Base64.DEFAULT)
                                val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                                Surface(
                                    onClick = { if (!state.isLoading) viewModel.refreshCaptcha() },
                                    shape = RoundedCornerShape(8.dp),
                                    color = Color(0xFFF0F0F0),
                                ) {
                                    Image(
                                        bitmap = bitmap.asImageBitmap(),
                                        contentDescription = "验证码",
                                        modifier = Modifier.size(width = 100.dp, height = 44.dp),
                                        contentScale = ContentScale.FillBounds,
                                    )
                                }
                            } else {
                                TextButton(
                                    onClick = { if (!state.isLoading) viewModel.refreshCaptcha() },
                                    enabled = !state.isLoading,
                                ) {
                                    Text("获取\n验证码", textAlign = TextAlign.Center)
                                }
                            }
                        }
                    }

                    // Error
                    state.errorMessage?.let { error ->
                        Text(
                            text = error,
                            color = Color(0xFF9B2C2C),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }

                    // Submit
                    Button(
                        onClick = {
                            if (state.isLoginForm) viewModel.login() else viewModel.register()
                        },
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        enabled = !state.isLoading,
                        shape = RoundedCornerShape(50),
                    ) {
                        if (state.isLoading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                color = Color.White,
                                strokeWidth = 2.dp,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        Text(if (state.isLoginForm) "登录" else "注册", fontSize = 16.sp)
                    }
                }
            }

            // ── Backend status indicator ──
            BackendStatusMini(state.healthState, onRetry = viewModel::checkHealth)

            Spacer(modifier = Modifier.weight(1f))
        }
    }
}

@Composable
private fun BackendStatusMini(
    uiState: HomeUiState,
    onRetry: () -> Unit,
) {
    val (text, color) = when (uiState) {
        HomeUiState.Loading -> "后端检测中..." to Color.Gray
        is HomeUiState.Success -> "后端连接正常" to Color(0xFF21A67A)
        is HomeUiState.Error -> "后端连接失败" to MaterialTheme.colorScheme.error
    }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(RoundedCornerShape(4.dp))
                .background(color),
        )
        Text(
            text = text,
            color = color,
            style = MaterialTheme.typography.bodySmall,
        )
        if (uiState is HomeUiState.Error) {
            TextButton(onClick = onRetry) {
                Text("重试", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
