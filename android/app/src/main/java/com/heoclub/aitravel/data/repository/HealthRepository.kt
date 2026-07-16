package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.HealthResponse
import com.heoclub.aitravel.data.remote.ApiService
import java.io.IOException
import java.net.SocketTimeoutException

interface HealthRepository {
    suspend fun checkHealth(): Result<HealthResponse>
}

class DefaultHealthRepository(
    private val apiService: ApiService,
) : HealthRepository {
    override suspend fun checkHealth(): Result<HealthResponse> {
        return runCatching { apiService.getHealth() }.fold(
            onSuccess = { Result.success(it) },
            onFailure = { throwable ->
                Result.failure(mapNetworkError(throwable))
            },
        )
    }

    private fun mapNetworkError(throwable: Throwable): Throwable {
        val message = when (throwable) {
            is SocketTimeoutException -> "连接后端超时，请确认服务正在运行。"
            is IOException -> "暂时无法连接后端，请先启动 FastAPI 服务。"
            else -> throwable.message ?: "后端状态检查失败，请稍后重试。"
        }

        return IllegalStateException(message, throwable)
    }
}

