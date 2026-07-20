package com.heoclub.aitravel.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Explore
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Work
import androidx.compose.ui.graphics.vector.ImageVector

enum class AppDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
) {
    Plan("plan", "计划", Icons.Outlined.Work),
    Explore("explore", "探索", Icons.Outlined.Explore),
    Journey("journey", "旅程", Icons.Outlined.Map),
    Profile("profile", "我的", Icons.Outlined.Person),
}
