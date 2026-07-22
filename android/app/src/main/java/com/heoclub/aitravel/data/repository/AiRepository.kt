package com.heoclub.aitravel.data.repository

import com.google.gson.Gson
import com.heoclub.aitravel.data.model.AiCard
import com.heoclub.aitravel.data.model.AiChatRequest
import com.heoclub.aitravel.data.model.AiChatResponse
import com.heoclub.aitravel.data.model.AiPlanGenerationRequest
import com.heoclub.aitravel.data.model.AiPlanGenerationResponse
import com.heoclub.aitravel.data.model.AiPlanJobStatusResponse
import com.heoclub.aitravel.data.model.AiSuggestedAction
import com.heoclub.aitravel.data.remote.ApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import retrofit2.HttpException
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn

interface AiRepository {
    suspend fun chat(request: AiChatRequest): Result<AiChatResponse>

    suspend fun chatStream(
        request: AiChatRequest,
        onChunk: (String) -> Unit,
        onDone: (AiChatResponse) -> Unit,
        onError: (String) -> Unit,
    )

    suspend fun generatePlan(request: AiPlanGenerationRequest): Result<AiPlanGenerationResponse>

    fun streamPlan(request: AiPlanGenerationRequest): Flow<AiPlanJobStatusResponse>

    suspend fun createPlanJob(request: AiPlanGenerationRequest): Result<AiPlanJobStatusResponse>

    suspend fun getPlanJob(jobId: String): Result<AiPlanJobStatusResponse>

    suspend fun cancelPlanJob(jobId: String): Result<AiPlanJobStatusResponse>
}

class RemoteAiRepository(
    private val apiService: ApiService,
    private val okHttpClient: OkHttpClient,
    private val apiBaseUrl: String,
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

    override suspend fun chatStream(
        request: AiChatRequest,
        onChunk: (String) -> Unit,
        onDone: (AiChatResponse) -> Unit,
        onError: (String) -> Unit,
    ) {
        withContext(Dispatchers.IO) {
            try {
                val jsonBody = gson.toJson(request)
                    .toRequestBody("application/json".toMediaType())
                val httpRequest = Request.Builder()
                    .url("${apiBaseUrl}api/ai/chat/stream")
                    .post(jsonBody)
                    .header("Content-Type", "application/json")
                    .build()

                val response = okHttpClient.newCall(httpRequest).execute()
                if (!response.isSuccessful) {
                    val errorMsg = when (response.code) {
                        401, 403 -> "AI 鉴权失败，请检查后端 API Key 或模型权限。"
                        429 -> "AI 调用频率或额度受限，请稍后重试。"
                        502 -> "AI 服务调用失败，请检查后端配置。"
                        503 -> "AI 服务尚未配置，请检查后端 .env。"
                        504 -> "AI 回复超时，请稍后再试。"
                        else -> "AI 服务异常：HTTP ${response.code}"
                    }
                    withContext(Dispatchers.Main) { onError(errorMsg) }
                    return@withContext
                }

                val source = response.body?.source() ?: run {
                    withContext(Dispatchers.Main) { onError("AI 返回了空响应") }
                    return@withContext
                }

                while (!source.exhausted()) {
                    val line = source.readUtf8Line() ?: break
                    if (!line.startsWith("data: ")) continue
                    val jsonStr = line.removePrefix("data: ")
                    val json = try {
                        JSONObject(jsonStr)
                    } catch (_: Exception) {
                        continue
                    }

                    when (json.optString("type")) {
                        "chunk" -> {
                            val content = json.optString("content", "")
                            if (content.isNotEmpty()) {
                                withContext(Dispatchers.Main) { onChunk(content) }
                            }
                        }
                        "done" -> {
                            val chatResponse = AiChatResponse(
                                conversationId = json.getString("conversationId"),
                                messageId = json.optString("messageId"),
                                message = json.getString("fullText"),
                                quickReplies = json.optJSONArray("quickReplies")?.let { arr ->
                                    (0 until arr.length()).map { arr.getString(it) }
                                } ?: emptyList(),
                                referencedPlaceItemIds = json.optJSONArray("referencedPlaceItemIds")?.let { arr ->
                                    (0 until arr.length()).map { arr.getString(it) }
                                } ?: emptyList(),
                                actionSetId = json.optString("actionSetId").takeIf { it.isNotEmpty() },
                                planRevision = if (json.has("planRevision") && !json.isNull("planRevision")) json.getLong("planRevision") else null,
                                suggestedActions = json.optJSONArray("suggestedActions")?.let { arr ->
                                    (0 until arr.length()).map { i ->
                                        val a = arr.getJSONObject(i)
                                        AiSuggestedAction(
                                            id = a.getString("id"),
                                            type = a.getString("type"),
                                            placeItemId = a.getString("placeItemId"),
                                            fromDayIndex = a.optInt("fromDayIndex").takeIf { !a.isNull("fromDayIndex") },
                                            toDayIndex = a.optInt("toDayIndex").takeIf { !a.isNull("toDayIndex") },
                                            fromPosition = a.optInt("fromPosition").takeIf { !a.isNull("fromPosition") },
                                            toPosition = a.optInt("toPosition").takeIf { !a.isNull("toPosition") },
                                            reason = a.optString("reason").takeIf { it.isNotEmpty() },
                                            requiresRouteRefresh = a.optBoolean("requiresRouteRefresh", true),
                                            affectedDayIndexes = a.optJSONArray("affectedDayIndexes")?.let { idxArr ->
                                                (0 until idxArr.length()).map { idxArr.getInt(it) }
                                            } ?: emptyList(),
                                        )
                                    }
                                } ?: emptyList(),
                                actionWarnings = json.optJSONArray("actionWarnings")?.let { arr ->
                                    (0 until arr.length()).map { arr.getString(it) }
                                } ?: emptyList(),
                                cards = json.optJSONArray("cards")?.let { arr ->
                                    (0 until arr.length()).map { i ->
                                        val c = arr.getJSONObject(i)
                                        AiCard(
                                            id = c.getString("id"),
                                            type = c.getString("type"),
                                            title = c.optString("title"),
                                            subtitle = c.optString("subtitle").takeIf { it.isNotEmpty() },
                                            payload = c.optJSONObject("payload")?.let { p ->
                                                com.heoclub.aitravel.data.model.AiLinkCardPayload(
                                                    action_type = p.optString("action_type", "NAVIGATE_TO_CREATE_PLAN"),
                                                )
                                            },
                                            days = c.optJSONArray("days")?.let { daysArr ->
                                                (0 until daysArr.length()).map { di ->
                                                    val d = daysArr.getJSONObject(di)
                                                    com.heoclub.aitravel.data.model.AiCardDay(
                                                        day_index = d.getInt("day_index"),
                                                        title = d.optString("title", ""),
                                                        place_refs = d.optJSONArray("place_refs")?.let { refsArr ->
                                                            (0 until refsArr.length()).map { ri ->
                                                                val r = refsArr.getJSONObject(ri)
                                                                com.heoclub.aitravel.data.model.AiCardPlaceRef(
                                                                    itemId = r.getString("itemId"),
                                                                    note = r.optString("note", ""),
                                                                )
                                                            }
                                                        } ?: emptyList(),
                                                    )
                                                }
                                            },
                                        )
                                    }
                                } ?: emptyList(),
                                createdAt = json.optString("createdAt"),
                                model = json.optString("model").takeIf { it.isNotEmpty() },
                            )
                            withContext(Dispatchers.Main) { onDone(chatResponse) }
                            return@withContext
                        }
                    }
                }
                // If we exit the loop without a "done" event
                withContext(Dispatchers.Main) { onError("AI 流式响应意外结束") }
            } catch (e: IOException) {
                withContext(Dispatchers.Main) {
                    onError("无法连接后端 AI 服务，请确认 FastAPI 已启动。")
                }
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                withContext(Dispatchers.Main) {
                    onError(e.message ?: "AI 服务暂时不可用，请稍后重试。")
                }
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
