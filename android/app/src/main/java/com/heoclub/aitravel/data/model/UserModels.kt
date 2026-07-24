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

// ── User Plans (cloud) ──

data class UserPlanResponse(
    val id: String,
    @SerializedName("user_id") val userId: String,
    val title: String,
    val destination: String,
    @SerializedName("date_range") val dateRange: String,
    @SerializedName("day_count") val dayCount: Int,
    val preferences: String,  // JSON list string
    @SerializedName("plan_data") val planData: String,  // full TravelPlan JSON
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class UserPlanCreateRequest(
    val title: String,
    val destination: String,
    @SerializedName("date_range") val dateRange: String = "",
    @SerializedName("day_count") val dayCount: Int = 1,
    val preferences: String = "[]",
    @SerializedName("plan_data") val planData: String = "{}",
)

data class UserPlanUpdateRequest(
    val title: String? = null,
    val destination: String? = null,
    @SerializedName("date_range") val dateRange: String? = null,
    @SerializedName("day_count") val dayCount: Int? = null,
    val preferences: String? = null,
    @SerializedName("plan_data") val planData: String? = null,
)

// ── User Journals (cloud) ──

data class UserJournalResponse(
    val id: String,
    @SerializedName("user_id") val userId: String,
    val title: String,
    val location: String,
    val date: String,
    val body: String,
    val photos: String,  // JSON string
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
)

data class UserJournalCreateRequest(
    val title: String,
    val location: String = "",
    val date: String = "",
    val body: String = "",
    val photos: String = "[]",
)

data class UserJournalUpdateRequest(
    val title: String? = null,
    val location: String? = null,
    val date: String? = null,
    val body: String? = null,
    val photos: String? = null,
)

// ── User Footprints (cloud) ──

data class UserFootprintResponse(
    val id: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("city_name") val cityName: String,
    @SerializedName("province_name") val provinceName: String,
    val latitude: Double?,
    val longitude: Double?,
    @SerializedName("visit_count") val visitCount: Int,
    @SerializedName("first_visited_at") val firstVisitedAt: String,
    @SerializedName("last_visited_at") val lastVisitedAt: String,
)

data class UserFootprintCreateRequest(
    @SerializedName("city_name") val cityName: String,
    @SerializedName("province_name") val provinceName: String = "",
    val latitude: Double? = null,
    val longitude: Double? = null,
)
