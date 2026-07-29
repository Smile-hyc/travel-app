package com.heoclub.aitravel.data.local

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * 最近搜索词的本地存储。按写入时间倒序保存，最多保留 [MAX_ENTRIES] 条。
 */
class SearchHistoryStore(
    context: Context,
    prefsName: String,
) {
    private val preferences = context.applicationContext.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    private val gson = Gson()
    private val listType = object : TypeToken<List<String>>() {}.type

    @Synchronized
    fun load(): List<String> {
        val json = preferences.getString(KEY_KEYWORDS, null) ?: return emptyList()
        return runCatching {
            gson.fromJson<List<String>>(json, listType)
                .orEmpty()
                .map(String::trim)
                .filter(String::isNotBlank)
                .take(MAX_ENTRIES)
        }.getOrDefault(emptyList())
    }

    /** 写入一条搜索词并返回更新后的完整列表。已存在的词会被提到最前面。 */
    @Synchronized
    fun add(keyword: String): List<String> {
        val trimmed = keyword.trim().take(MAX_KEYWORD_LENGTH)
        if (trimmed.isBlank()) return load()
        val updated = (listOf(trimmed) + load().filterNot { it.equals(trimmed, ignoreCase = true) })
            .take(MAX_ENTRIES)
        return persist(updated)
    }

    @Synchronized
    fun remove(keyword: String): List<String> {
        return persist(load().filterNot { it.equals(keyword.trim(), ignoreCase = true) })
    }

    @Synchronized
    fun clear(): List<String> = persist(emptyList())

    private fun persist(keywords: List<String>): List<String> {
        preferences.edit().putString(KEY_KEYWORDS, gson.toJson(keywords)).apply()
        return keywords
    }

    private companion object {
        const val KEY_KEYWORDS = "keywords_json"
        const val MAX_ENTRIES = 12
        const val MAX_KEYWORD_LENGTH = 60
    }
}
