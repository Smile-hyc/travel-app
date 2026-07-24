package com.heoclub.aitravel.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.model.User
import com.heoclub.aitravel.data.model.UserPreference
import com.heoclub.aitravel.data.repository.AuthRepository
import com.heoclub.aitravel.data.repository.HealthRepository
import com.heoclub.aitravel.ui.home.HomeUiState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException

data class ProfileUiState(
    val isLoggedIn: Boolean = false,
    val user: User? = null,
    val isLoginForm: Boolean = true,      // true=登录, false=注册
    val phone: String = "",
    val password: String = "",
    val nickname: String = "",
    val captchaId: String? = null,
    val captchaImageBase64: String? = null,
    val captchaText: String = "",
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val successMessage: String? = null,
    val healthState: HomeUiState = HomeUiState.Loading,
    // Nickname editing
    val showNicknameEdit: Boolean = false,
    val editingNickname: String = "",
    val isSavingNickname: Boolean = false,
    // Debug preferences panel (server-side user_preferences)
    val showDebugPrefs: Boolean = false,
    val userPreference: UserPreference? = null,
    val isLoadingPreferences: Boolean = false,
)

class ProfileViewModel(
    private val authRepository: AuthRepository,
    private val healthRepository: HealthRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

    init {
        checkHealth()
    }

    fun toggleForm() {
        _uiState.update {
            it.copy(
                isLoginForm = !it.isLoginForm,
                errorMessage = null,
                captchaText = "",
                captchaId = null,
                captchaImageBase64 = null,
            )
        }
    }

    fun onPhoneChanged(phone: String) {
        _uiState.update { it.copy(phone = phone, errorMessage = null) }
    }

    fun onPasswordChanged(password: String) {
        _uiState.update { it.copy(password = password, errorMessage = null) }
    }

    fun onNicknameChanged(nickname: String) {
        _uiState.update { it.copy(nickname = nickname) }
    }

    fun onCaptchaTextChanged(text: String) {
        _uiState.update { it.copy(captchaText = text, errorMessage = null) }
    }

    fun refreshCaptcha() {
        viewModelScope.launch {
            _uiState.update { it.copy(captchaText = "", captchaId = null, captchaImageBase64 = null) }
            authRepository.getCaptcha().onSuccess { captcha ->
                _uiState.update {
                    it.copy(
                        captchaId = captcha.captchaId,
                        captchaImageBase64 = captcha.imageBase64,
                    )
                }
            }.onFailure { e ->
                _uiState.update { it.copy(errorMessage = "获取验证码失败: ${e.message}") }
            }
        }
    }

    fun login() {
        val state = _uiState.value
        val phone = state.phone.trim()
        val password = state.password

        if (phone.length < 11) {
            _uiState.update { it.copy(errorMessage = "请输入有效的手机号") }
            return
        }
        if (password.length < 6) {
            _uiState.update { it.copy(errorMessage = "密码至少需要6位") }
            return
        }

        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            authRepository.login(phone, password).onSuccess { response ->
                _uiState.update {
                    it.copy(
                        isLoggedIn = true,
                        user = response.user,
                        isLoading = false,
                        phone = "",
                        password = "",
                        errorMessage = null,
                    )
                }
            }.onFailure { e ->
                _uiState.update {
                    it.copy(isLoading = false, errorMessage = e.message ?: "登录失败")
                }
            }
        }
    }

    fun register() {
        val state = _uiState.value
        val phone = state.phone.trim()
        val password = state.password
        val captchaId = state.captchaId
        val captchaText = state.captchaText.trim()

        if (phone.length < 11) {
            _uiState.update { it.copy(errorMessage = "请输入有效的手机号") }
            return
        }
        if (password.length < 6) {
            _uiState.update { it.copy(errorMessage = "密码至少需要6位") }
            return
        }
        if (captchaId == null) {
            _uiState.update { it.copy(errorMessage = "请先获取验证码") }
            return
        }
        if (captchaText.length < 4) {
            _uiState.update { it.copy(errorMessage = "请输入验证码") }
            return
        }

        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            authRepository.register(
                phone = phone,
                password = password,
                nickname = state.nickname.takeIf { it.isNotBlank() }?.trim(),
                captchaId = captchaId,
                captchaText = captchaText,
            ).onSuccess { response ->
                _uiState.update {
                    it.copy(
                        isLoggedIn = true,
                        user = response.user,
                        isLoading = false,
                        phone = "",
                        password = "",
                        nickname = "",
                        captchaId = null,
                        captchaImageBase64 = null,
                        captchaText = "",
                        errorMessage = null,
                    )
                }
            }.onFailure { e ->
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        errorMessage = e.message ?: "注册失败",
                        captchaText = "",
                    )
                }
                // Refresh captcha on failure
                refreshCaptcha()
            }
        }
    }

    fun logout() {
        authRepository.logout()
        _uiState.update {
            ProfileUiState(
                isLoggedIn = false,
                healthState = it.healthState,
            )
        }
    }

    fun checkHealth() {
        viewModelScope.launch {
            _uiState.update { it.copy(healthState = HomeUiState.Loading) }
            healthRepository.checkHealth()
                .onSuccess { response ->
                    _uiState.update {
                        it.copy(healthState = HomeUiState.Success(message = response.message))
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(healthState = HomeUiState.Error(message = e.message ?: "连接失败"))
                    }
                }
        }
    }

    fun toggleNicknameEdit() {
        _uiState.update {
            val next = !it.showNicknameEdit
            it.copy(
                showNicknameEdit = next,
                showDebugPrefs = false,
                editingNickname = if (next && it.editingNickname.isBlank()) it.user?.nickname.orEmpty() else it.editingNickname,
                errorMessage = null,
            )
        }
    }

    fun toggleDebugPrefs() {
        _uiState.update {
            val next = !it.showDebugPrefs
            it.copy(
                showDebugPrefs = next,
                showNicknameEdit = false,
                errorMessage = null,
            )
        }
        if (!_uiState.value.showDebugPrefs) return
        viewModelScope.launch {
            _uiState.update { it.copy(isLoadingPreferences = true) }
            authRepository.fetchUserPreferences()
                .onSuccess { prefs ->
                    _uiState.update { it.copy(userPreference = prefs, isLoadingPreferences = false) }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(isLoadingPreferences = false, errorMessage = "偏好加载失败: ${extractErrorMessage(e)}")
                    }
                }
        }
    }

    fun onDebugNicknameChanged(value: String) {
        _uiState.update { it.copy(editingNickname = value) }
    }

    fun saveNickname() {
        val state = _uiState.value
        val newName = state.editingNickname.trim()
        if (newName.isBlank() || newName == state.user?.nickname) return

        _uiState.update { it.copy(isSavingNickname = true, errorMessage = null) }
        viewModelScope.launch {
            authRepository.updateUser(nickname = newName, avatarUrl = null)
                .onSuccess { user ->
                    _uiState.update {
                        it.copy(user = user, isSavingNickname = false, successMessage = "昵称已更新")
                    }
                }
                .onFailure { e ->
                    _uiState.update {
                        it.copy(isSavingNickname = false, errorMessage = "保存失败: ${extractErrorMessage(e)}")
                    }
                }
        }
    }

    private fun extractErrorMessage(e: Throwable): String {
        if (e is HttpException) {
            try {
                val body = e.response()?.errorBody()?.string() ?: ""
                return body.ifBlank { e.message() ?: "HTTP ${e.code()}" }
            } catch (_: Exception) {
                // fall through
            }
        }
        return e.message ?: "未知错误"
    }

    class Factory(
        private val authRepository: AuthRepository,
        private val healthRepository: HealthRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(ProfileViewModel::class.java)) {
                return ProfileViewModel(authRepository, healthRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
