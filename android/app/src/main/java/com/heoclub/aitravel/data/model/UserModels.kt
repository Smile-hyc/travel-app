package com.heoclub.aitravel.data.model

import com.google.gson.annotations.SerializedName

data class User(
    val id: String,
    val phone: String,
    val nickname: String,
    @SerializedName("avatar_url") val avatarUrl: String?,
    @SerializedName("created_at") val createdAt: String,
)

data class LoginRequest(
    val phone: String,
    val password: String,
)

data class RegisterRequest(
    val phone: String,
    val password: String,
    val nickname: String? = null,
    @SerializedName("captcha_id") val captchaId: String,
    @SerializedName("captcha_text") val captchaText: String,
)

data class TokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String,
    val user: User,
)

data class CaptchaResponse(
    @SerializedName("captcha_id") val captchaId: String,
    @SerializedName("image_base64") val imageBase64: String,
)

data class UserUpdateRequest(
    val nickname: String? = null,
    @SerializedName("avatar_url") val avatarUrl: String? = null,
)

data class UserPreference(
    val id: String,
    @SerializedName("user_id") val userId: String,
    val language: String,
    val theme: String,
    @SerializedName("travel_style") val travelStyle: String,
    @SerializedName("budget_level") val budgetLevel: String,
    @SerializedName("notification_enabled") val notificationEnabled: Int,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class UserPreferenceUpdateRequest(
    val language: String? = null,
    val theme: String? = null,
    @SerializedName("travel_style") val travelStyle: String? = null,
    @SerializedName("budget_level") val budgetLevel: String? = null,
    @SerializedName("notification_enabled") val notificationEnabled: Int? = null,
)
