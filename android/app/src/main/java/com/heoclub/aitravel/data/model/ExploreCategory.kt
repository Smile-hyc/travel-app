package com.heoclub.aitravel.data.model

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Coffee
import androidx.compose.material.icons.outlined.DirectionsTransit
import androidx.compose.material.icons.outlined.Hotel
import androidx.compose.material.icons.outlined.LocalDining
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material.icons.outlined.TempleBuddhist
import androidx.compose.ui.graphics.vector.ImageVector

data class ExploreCategory(
    val id: String,
    val title: String,
    val icon: ImageVector,
)

object ExploreCategories {
    const val SCENIC = "scenic"
    const val FOOD = "food"
    const val DRINK = "drink"
    const val SHOPPING = "shopping"
    const val LODGING = "lodging"
    const val TRANSPORT = "transport"

    val all = listOf(
        ExploreCategory(SCENIC, "景点", Icons.Outlined.TempleBuddhist),
        ExploreCategory(FOOD, "美食", Icons.Outlined.LocalDining),
        ExploreCategory(DRINK, "饮品", Icons.Outlined.Coffee),
        ExploreCategory(SHOPPING, "购物", Icons.Outlined.ShoppingBag),
        ExploreCategory(LODGING, "住宿", Icons.Outlined.Hotel),
        ExploreCategory(TRANSPORT, "交通", Icons.Outlined.DirectionsTransit),
    )
}
