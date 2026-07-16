package com.heoclub.aitravel

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.Surface
import androidx.compose.ui.graphics.Color
import com.heoclub.aitravel.navigation.AiTravelNavHost
import com.heoclub.aitravel.ui.theme.AITravelTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AITravelTheme {
                Surface(color = Color(0xFFF6F8FB)) {
                    AiTravelNavHost()
                }
            }
        }
    }
}

