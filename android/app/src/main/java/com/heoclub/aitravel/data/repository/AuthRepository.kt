package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.local.TokenStore
import com.heoclub.aitravel.data.model.CaptchaResponse
import com.heoclub.aitravel.data.model.LoginRequest
import com.heoclub.aitravel.data.model.RegisterRequest
import com.heoclub.aitravel.data.model.TokenResponse
import com.heoclub.aitravel.data.model.User
import com.heoclub.aitravel.data.model.UserUpdateRequest
import com.heoclub.aitravel.data.remote.ApiService
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

class AuthRepository(
    private val apiService: ApiService,
    private val tokenStore: TokenStore,
) {
    private val _currentUser = MutableStateFlow<User?>(null)
    val currentUser: Flow<User?> = _currentUser.asStateFlow()

    val isLoggedIn: Boolean get() = tokenStore.isLoggedIn

    suspend fun getCaptcha(): Result<CaptchaResponse> = runCatching {
        apiService.getCaptcha()
    }

    suspend fun register(
        phone: String,
        password: String,
        nickname: String?,
        captchaId: String,
        captchaText: String,
    ): Result<TokenResponse> = runCatching {
        val response = apiService.register(
            RegisterRequest(
                phone = phone,
                password = password,
                nickname = nickname,
                captchaId = captchaId,
                captchaText = captchaText,
            ),
        )
        tokenStore.saveTokens(response.accessToken, response.refreshToken)
        _currentUser.value = response.user
        response
    }

    suspend fun login(phone: String, password: String): Result<TokenResponse> = runCatching {
        val response = apiService.login(LoginRequest(phone = phone, password = password))
        tokenStore.saveTokens(response.accessToken, response.refreshToken)
        _currentUser.value = response.user
        response
    }

    suspend fun refreshToken(): Result<TokenResponse> = runCatching {
        val refresh = tokenStore.getRefreshToken() ?: throw IllegalStateException("未登录")
        val response = apiService.refreshToken(mapOf("refresh_token" to refresh))
        tokenStore.saveTokens(response.accessToken, response.refreshToken)
        _currentUser.value = response.user
        response
    }

    suspend fun fetchCurrentUser(): Result<User> = runCatching {
        val user = apiService.getCurrentUser()
        _currentUser.value = user
        user
    }

    suspend fun updateUser(nickname: String?, avatarUrl: String?): Result<User> = runCatching {
        val user = apiService.updateCurrentUser(UserUpdateRequest(nickname = nickname, avatarUrl = avatarUrl))
        _currentUser.value = user
        user
    }

    fun logout() {
        tokenStore.clearTokens()
        _currentUser.value = null
    }

    /** Call on app startup to restore session */
    suspend fun restoreSession(): Boolean {
        if (!tokenStore.isLoggedIn) return false
        return fetchCurrentUser().isSuccess
    }
}
