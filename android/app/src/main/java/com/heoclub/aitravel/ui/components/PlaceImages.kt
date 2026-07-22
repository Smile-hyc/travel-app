package com.heoclub.aitravel.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.DirectionsTransit
import androidx.compose.material.icons.outlined.Hotel
import androidx.compose.material.icons.outlined.LocalCafe
import androidx.compose.material.icons.outlined.Museum
import androidx.compose.material.icons.outlined.Park
import androidx.compose.material.icons.outlined.Restaurant
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.SubcomposeAsyncImage
import coil.request.ImageRequest
import com.heoclub.aitravel.data.model.PlaceImage

@Composable
fun PlaceCoverImage(
    imageUrl: String?,
    placeName: String,
    category: String? = null,
    modifier: Modifier = Modifier,
    shape: Shape = RoundedCornerShape(16.dp),
    contentScale: ContentScale = ContentScale.Crop,
) {
    val cleanUrl = imageUrl?.trim()?.takeIf { it.isRemoteImageUrl() }
    Box(
        modifier = modifier
            .clip(shape)
            .background(placeholderBrush()),
        contentAlignment = Alignment.Center,
    ) {
        if (cleanUrl == null) {
            PlaceImagePlaceholder(placeName = placeName, category = category)
        } else {
            SubcomposeAsyncImage(
                model = ImageRequest.Builder(LocalContext.current)
                    .data(cleanUrl)
                    .crossfade(true)
                    .build(),
                contentDescription = placeName,
                contentScale = contentScale,
                loading = {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    }
                },
                error = {
                    PlaceImagePlaceholder(placeName = placeName, category = category)
                },
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

@Composable
fun PlaceImageCarousel(
    images: List<PlaceImage>,
    fallbackUrls: List<String>,
    placeName: String,
    category: String? = null,
    modifier: Modifier = Modifier,
    itemHeight: Dp = 132.dp,
) {
    val urls = (images.mapNotNull { it.url } + fallbackUrls)
        .map { it.trim() }
        .filter { it.isRemoteImageUrl() }
        .distinct()

    if (urls.isEmpty()) {
        PlaceCoverImage(
            imageUrl = null,
            placeName = placeName,
            category = category,
            modifier = modifier
                .fillMaxWidth()
                .height(itemHeight),
            shape = RoundedCornerShape(20.dp),
        )
        return
    }

    LazyRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(end = 2.dp),
    ) {
        itemsIndexed(urls, key = { _, url -> url }) { index, url ->
            PlaceCoverImage(
                imageUrl = url,
                placeName = placeName,
                category = category,
                modifier = Modifier
                    .width(if (index == 0) 220.dp else 132.dp)
                    .height(itemHeight),
                shape = RoundedCornerShape(20.dp),
            )
        }
    }
}

@Composable
private fun PlaceImagePlaceholder(placeName: String, category: String?) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(placeholderBrush())
            .padding(8.dp),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = when (category?.lowercase()) {
                "food" -> Icons.Outlined.Restaurant
                "drink" -> Icons.Outlined.LocalCafe
                "lodging" -> Icons.Outlined.Hotel
                "transport" -> Icons.Outlined.DirectionsTransit
                "shopping" -> Icons.Outlined.ShoppingBag
                "nature" -> Icons.Outlined.Park
                "culture", "museum" -> Icons.Outlined.Museum
                else -> Icons.Outlined.LocationOn
            },
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = placeName.take(2),
            modifier = Modifier.align(Alignment.BottomCenter),
            color = Color(0xFF4E6D8F),
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun placeholderBrush(): Brush {
    return Brush.linearGradient(listOf(Color(0xFFD9ECFF), Color(0xFFBFE8D7)))
}

private fun String.isRemoteImageUrl(): Boolean {
    return startsWith("http://", ignoreCase = true) || startsWith("https://", ignoreCase = true)
}
