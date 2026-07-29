package com.heoclub.aitravel.data.repository

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.heoclub.aitravel.data.model.AiRecommendedPlace

data class AiConversationMessageRecord(
    val id: String,
    val text: String,
    val fromUser: Boolean,
    val recommendedPlaces: List<AiRecommendedPlace> = emptyList(),
    val retrievalCity: String? = null,
    val offerPlan: Boolean = false,
    val originalQuestion: String? = null,
)

data class AiConversationRecord(
    val id: String,
    val title: String,
    val messages: List<AiConversationMessageRecord>,
    val remoteConversationId: String? = null,
    val planId: String? = null,
    val updatedAt: Long = System.currentTimeMillis(),
)

class AiConversationHistoryStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val gson = Gson()
    private val listType = object : TypeToken<List<AiConversationRecord>>() {}.type

    @Synchronized
    fun loadAll(): List<AiConversationRecord> {
        val json = preferences.getString(KEY_CONVERSATIONS, null) ?: return emptyList()
        return runCatching {
            gson.fromJson<List<AiConversationRecord>>(json, listType)
                .orEmpty()
                .filter { it.id.isNotBlank() && it.messages.isNotEmpty() }
                .sortedByDescending { it.updatedAt }
        }.getOrDefault(emptyList())
    }

    @Synchronized
    fun upsert(conversation: AiConversationRecord) {
        val sanitized = conversation.copy(messages = conversation.messages.takeLast(MAX_MESSAGES_PER_CONVERSATION))
        val updated = (listOf(sanitized) + loadAll().filterNot { it.id == sanitized.id })
            .sortedByDescending { it.updatedAt }
            .take(MAX_CONVERSATIONS)
        preferences.edit().putString(KEY_CONVERSATIONS, gson.toJson(updated)).apply()
    }

    @Synchronized
    fun delete(conversationId: String) {
        val updated = loadAll().filterNot { it.id == conversationId }
        preferences.edit().putString(KEY_CONVERSATIONS, gson.toJson(updated)).apply()
    }

    private companion object {
        const val PREFS_NAME = "ai_assistant_conversations"
        const val KEY_CONVERSATIONS = "conversation_history_json"
        const val MAX_CONVERSATIONS = 30
        const val MAX_MESSAGES_PER_CONVERSATION = 120
    }
}
