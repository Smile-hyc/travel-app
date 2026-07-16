package com.heoclub.aitravel.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.heoclub.aitravel.data.repository.HealthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class HomeViewModel(
    private val healthRepository: HealthRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow<HomeUiState>(HomeUiState.Loading)
    val uiState: StateFlow<HomeUiState> = _uiState.asStateFlow()

    init {
        refreshHealth()
    }

    fun refreshHealth() {
        _uiState.value = HomeUiState.Loading
        viewModelScope.launch {
            val result = healthRepository.checkHealth()
            _uiState.value = result.fold(
                onSuccess = { response ->
                    HomeUiState.Success(response.message)
                },
                onFailure = { throwable ->
                    HomeUiState.Error(
                        throwable.message ?: "后端状态检查失败，请稍后重试。",
                    )
                },
            )
        }
    }

    class Factory(
        private val healthRepository: HealthRepository,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(HomeViewModel::class.java)) {
                return HomeViewModel(healthRepository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}

