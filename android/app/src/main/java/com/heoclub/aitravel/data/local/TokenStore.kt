package com.heoclub.aitravel.data.local

import android.content.Context
import android.content.SharedPreferences

class TokenStore(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences(
        "auth_tokens",
        Context.MODE_PRIVATE,
    )

    fun saveTokens(accessToken: String, refreshToken: String) {
        prefs.edit()
            .putString(KEY_ACCESS, accessToken)
            .putString(KEY_REFRESH, refreshToken)
            .apply()
    }

    fun getAccessToken(): String? = prefs.getString(KEY_ACCESS, null)

    fun getRefreshToken(): String? = prefs.getString(KEY_REFRESH, null)

    fun clearTokens() {
        prefs.edit()
            .remove(KEY_ACCESS)
            .remove(KEY_REFRESH)
            .apply()
    }

    val isLoggedIn: Boolean get() = getAccessToken() != null

    companion object {
        private const val KEY_ACCESS = "access_token"
        private const val KEY_REFRESH = "refresh_token"
    }
}
