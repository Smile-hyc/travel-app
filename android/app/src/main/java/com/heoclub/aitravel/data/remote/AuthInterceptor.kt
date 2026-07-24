package com.heoclub.aitravel.data.remote

import com.heoclub.aitravel.data.local.TokenStore
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(
    private val tokenStore: TokenStore,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()
        val path = originalRequest.url.encodedPath

        val accessToken = tokenStore.getAccessToken()
        if (accessToken.isNullOrBlank()) {
            android.util.Log.w("AuthInterceptor", "NO TOKEN for $path")
            return chain.proceed(originalRequest)
        }

        android.util.Log.d("AuthInterceptor", "TOKEN OK for $path (${accessToken.take(20)}…)")
        val authenticatedRequest = originalRequest.newBuilder()
            .header("Authorization", "Bearer $accessToken")
            .build()

        return chain.proceed(authenticatedRequest)
    }
}
