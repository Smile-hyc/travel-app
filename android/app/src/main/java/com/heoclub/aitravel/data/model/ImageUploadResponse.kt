package com.heoclub.aitravel.data.model

import com.google.gson.annotations.SerializedName

data class ImageUploadResponse(
    @SerializedName("url") val url: String,
    @SerializedName("filename") val filename: String,
)
