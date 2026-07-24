package com.heoclub.aitravel.data.remote

import com.heoclub.aitravel.data.local.TokenStore
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

data class ApiClient(
    val apiService: ApiService,
    val okHttpClient: OkHttpClient,
)

object RetrofitClient {
    fun create(
        baseUrl: String,
        isDebug: Boolean,
        tokenStore: TokenStore? = null,
    ): ApiClient {
        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = if (isDebug) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }

        val builder = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            // AI planning uses SSE and may legitimately take several minutes.
            // Keep reading until the server emits its complete event.
            .readTimeout(0, TimeUnit.SECONDS)
            .writeTimeout(120, TimeUnit.SECONDS)
            .addInterceptor(loggingInterceptor)

        if (tokenStore != null) {
            builder.addInterceptor(AuthInterceptor(tokenStore))
        }

        val okHttpClient = builder.build()

        val apiService = Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)

        return ApiClient(
            apiService = apiService,
            okHttpClient = okHttpClient,
        )
    }
}
