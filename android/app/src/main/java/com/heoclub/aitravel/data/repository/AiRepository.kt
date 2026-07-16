package com.heoclub.aitravel.data.repository

import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiChatResponse
import com.heoclub.aitravel.data.remote.ApiService
import retrofit2.HttpException
import java.io.IOException

interface AiRepository {
    suspend fun chat(request: AiChatRequest): Result<AiChatResponse>
}

class RemoteAiRepository(
    private val apiService: ApiService,
) : AiRepository {
    override suspend fun chat(request: AiChatRequest): Result<AiChatResponse> {
        return runCatching {
            apiService.chatWithAi(request)
        }.recoverCatching { throwable ->
            throw when (throwable) {
                is HttpException -> RuntimeException(
                    when (throwable.code()) {
                        401, 403 -> "AI 鉴权失败，请检查后端 Ark API Key 或模型权限。"
                        429 -> "AI 调用频率或额度受限，请稍后重试。"
                        502 -> "AI 服务调用失败，请检查后端配置或火山方舟状态。"
                        503 -> "AI 服务尚未配置，请检查后端 .env。"
                        504 -> "AI 回复超时，请稍后再试，或把问题问得更具体一些。"
                        else -> "AI 服务异常：HTTP ${throwable.code()}"
                    },
                    throwable,
                )

                is IOException -> RuntimeException(
                    "无法连接后端 AI 服务，请确认 FastAPI 已启动。",
                    throwable,
                )

                else -> RuntimeException(
                    throwable.message ?: "AI 服务暂时不可用，请稍后重试。",
                    throwable,
                )
            }
        }
    }
}
