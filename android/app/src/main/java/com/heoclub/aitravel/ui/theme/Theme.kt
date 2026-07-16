package com.heoclub.aitravel.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val TravelColorScheme: ColorScheme = lightColorScheme(
    primary = Color(0xFF1F7AE0),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD8E9FF),
    onPrimaryContainer = Color(0xFF052B55),
    secondary = Color(0xFF21A67A),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFD8F4EA),
    onSecondaryContainer = Color(0xFF05372A),
    background = Color(0xFFF6F8FB),
    onBackground = Color(0xFF162235),
    surface = Color.White,
    onSurface = Color(0xFF162235),
    surfaceVariant = Color(0xFFEAF0F7),
    onSurfaceVariant = Color(0xFF526173),
    error = Color(0xFFD64545),
)

@Composable
fun AITravelTheme(
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = TravelColorScheme,
        typography = MaterialTheme.typography,
        content = content,
    )
}
