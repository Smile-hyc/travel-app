package com.heoclub.aitravel.data.repository

import com.google.gson.Gson
import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiChatResponse
import com.heoclub.aitravel.data.model.AiPlanGenerationRequest
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.AiPlanJobStatusResponse
import com.heoclub.aitravel.data.remote.ApiService
import retrofit2.HttpException
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn

interface AiRepository {
    suspend fun chat(request: AiChatRequest): Result<AiChatResponse>

    suspend fun generatePlan(request: AiPlanGenerationRequest): Result<AiPlanGenerationResponse>

    fun streamPlan(request: AiPlanGenerationRequest): Flow<AiPlanJobStatusResponse>

    suspend fun createPlanJob(request: AiPlanGenerationRequest): Result<AiPlanJobStatusResponse>

    suspend fun getPlanJob(jobId: String): Result<AiPlanJobStatusResponse>

    suspend fun cancelPlanJob(jobId: String): Result<AiPlanJobStatusResponse>
}

class RemoteAiRepository(
    private val apiService: ApiService,
) : AiRepository {
    private val gson = Gson()
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

    override suspend fun generatePlan(request: AiPlanGenerationRequest): Result<AiPlanGenerationResponse> {
        return runCatching {
            apiService.generateTravelPlan(request)
        }.recoverCatching { throwable ->
            throw mapAiError(throwable, "智能行程生成")
        }
    }

    override fun streamPlan(request: AiPlanGenerationRequest): Flow<AiPlanJobStatusResponse> = flow {
        val body = try {
            apiService.streamTravelPlan(request)
        } catch (throwable: Throwable) {
            throw mapAiError(throwable, "建立智能规划流")
        }
        body.use { responseBody ->
            responseBody.charStream().buffered().use { reader ->
                val data = StringBuilder()
                while (true) {
                    val line = reader.readLine() ?: break
                    when {
                        line.startsWith("data:") -> data.append(line.removePrefix("data:").trim())
                        line.isBlank() && data.isNotEmpty() -> {
                            val snapshot = runCatching {
                                gson.fromJson(data.toString(), AiPlanJobStatusResponse::class.java)
                            }.getOrElse { cause ->
                                throw RuntimeException("智能规划流返回了无法解析的数据。", cause)
                            }
                            emit(snapshot)
                            data.clear()
                        }
                    }
                }
                if (data.isNotEmpty()) {
                    emit(gson.fromJson(data.toString(), AiPlanJobStatusResponse::class.java))
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun createPlanJob(request: AiPlanGenerationRequest): Result<AiPlanJobStatusResponse> {
        return runCatching { apiService.createTravelPlanJob(request) }
            .recoverCatching { throw mapAiError(it, "创建智能规划任务") }
    }

    override suspend fun getPlanJob(jobId: String): Result<AiPlanJobStatusResponse> {
        return runCatching { apiService.getTravelPlanJob(jobId) }
            .recoverCatching { throw mapAiError(it, "获取智能规划进度") }
    }

    override suspend fun cancelPlanJob(jobId: String): Result<AiPlanJobStatusResponse> {
        return runCatching { apiService.cancelTravelPlanJob(jobId) }
            .recoverCatching { throw mapAiError(it, "取消智能规划") }
    }

    private fun mapAiError(throwable: Throwable, action: String): RuntimeException {
        if (throwable is CancellationException) throw throwable
        return when (throwable) {
            is HttpException -> RuntimeException(
                when (throwable.code()) {
                    401, 403 -> "${action}鉴权失败，请检查后端服务权限。"
                    422 -> "目的地或日期信息不可用，请修改后重试。"
                    429 -> "AI 调用频率或额度受限，请稍后重试。"
                    502 -> "${action}失败，请检查后端配置或火山方舟状态。"
                    503 -> "${action}服务尚未配置，请检查后端 .env。"
                    504 -> "${action}超时，请稍后重试或缩短行程天数。"
                    else -> "${action}服务异常：HTTP ${throwable.code()}"
                },
                throwable,
            )

            is IOException -> RuntimeException(
                "无法连接后端，请确认 FastAPI 已启动。",
                throwable,
            )

            else -> RuntimeException(
                throwable.message ?: "${action}暂时不可用，请稍后重试。",
                throwable,
            )
        }
    }
}
