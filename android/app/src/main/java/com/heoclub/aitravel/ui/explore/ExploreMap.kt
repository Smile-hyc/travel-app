package com.heoclub.aitravel.ui.explore

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.amap.api.maps.AMap
import com.amap.api.maps.CameraUpdateFactory
import com.amap.api.maps.MapView
import com.amap.api.maps.model.BitmapDescriptorFactory
import com.amap.api.maps.model.CustomMapStyleOptions
import com.amap.api.maps.model.LatLng
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.maps.model.PolylineOptions
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.PlaceSummary
import kotlinx.coroutines.flow.SharedFlow
import android.graphics.Color as AndroidColor

@Composable
fun ExploreMap(
    places: List<PlaceSummary>,
    selectedPlaceId: String?,
    mapCommands: SharedFlow<MapCameraCommand>,
    onMarkerClick: (String) -> Unit,
    routePlaces: List<PlaceSummary> = emptyList(),
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    if (!isAmapNativeRuntimeSupported(context)) {
        AmapUnsupportedRuntimeNotice(modifier = modifier)
        return
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    val mapView = remember {
        MapView(context).apply { onCreate(Bundle()) }
    }

    DisposableEffect(lifecycleOwner, mapView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_DESTROY -> mapView.onDestroy()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            mapView.onDestroy()
        }
    }

    Box(modifier = modifier) {
        AndroidView(
            factory = {
                mapView.apply {
                    map.mapType = AMap.MAP_TYPE_NORMAL
                    map.showBuildings(false)
                    map.showIndoorMap(false)
                    map.showMapText(true)
                    map.uiSettings.isZoomControlsEnabled = false
                    map.uiSettings.isMyLocationButtonEnabled = false
                    map.uiSettings.isCompassEnabled = false
                    applyTravelMapStyle(context, map)
                    map.moveCamera(
                        CameraUpdateFactory.newLatLngZoom(
                            LatLng(39.9105, 116.3972),
                            13.2f,
                        ),
                    )
                }
            },
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .background(Color.White.copy(alpha = 0.42f)),
        )
    }

    LaunchedEffect(places, selectedPlaceId, routePlaces) {
        val amap = mapView.map
        amap.clear()
        val routePoints = routePlaces.mapNotNull { place ->
            val latitude = place.latitude ?: return@mapNotNull null
            val longitude = place.longitude ?: return@mapNotNull null
            LatLng(latitude, longitude)
        }
        if (routePoints.size >= 2) {
            amap.addPolyline(
                PolylineOptions()
                    .addAll(routePoints)
                    .width(12f)
                    .color(AndroidColor.rgb(42, 169, 230))
                    .zIndex(6f),
            )
        }
        amap.setOnMarkerClickListener { marker ->
            (marker.`object` as? String)?.let(onMarkerClick)
            true
        }
        visibleMapPlaces(places, selectedPlaceId).forEach { place ->
            val latitude = place.latitude ?: return@forEach
            val longitude = place.longitude ?: return@forEach
            val selected = place.id == selectedPlaceId
            val marker = amap.addMarker(
                MarkerOptions()
                    .position(LatLng(latitude, longitude))
                    .icon(BitmapDescriptorFactory.fromBitmap(createPlaceMarkerBitmap(context, place, selected)))
                    .anchor(0.5f, markerAnchorY(context, selected))
                    .zIndex(if (selected) 30f else 10f),
            )
            marker?.`object` = place.id
        }
    }

    LaunchedEffect(selectedPlaceId) {
        val selectedPlace = places.firstOrNull { it.id == selectedPlaceId }
        val latitude = selectedPlace?.latitude
        val longitude = selectedPlace?.longitude
        if (latitude != null && longitude != null) {
            mapView.map.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(latitude, longitude), 14.2f))
        }
    }

    LaunchedEffect(mapCommands) {
        mapCommands.collect { command ->
            when (command) {
                is MapCameraCommand.MoveToCity -> {
                    mapView.map.animateCamera(
                        CameraUpdateFactory.newLatLngZoom(
                            LatLng(command.latitude, command.longitude),
                            command.zoom,
                        ),
                    )
                }

                is MapCameraCommand.MoveToPlace -> {
                    mapView.map.animateCamera(
                        CameraUpdateFactory.newLatLngZoom(
                            LatLng(command.latitude, command.longitude),
                            command.zoom,
                        ),
                    )
                }
            }
        }
    }
}

private fun visibleMapPlaces(
    places: List<PlaceSummary>,
    selectedPlaceId: String?,
): List<PlaceSummary> {
    val mappablePlaces = places.filter { it.latitude != null && it.longitude != null }
    val selectedPlace = mappablePlaces.firstOrNull { it.id == selectedPlaceId }
    return (listOfNotNull(selectedPlace) + mappablePlaces.filterNot { it.id == selectedPlaceId }.take(8))
        .distinctBy { it.id }
}

@Composable
private fun AmapUnsupportedRuntimeNotice(modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFFEAF5FF), Color(0xFFF8FBFF))))
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            shape = RoundedCornerShape(28.dp),
            color = Color.White.copy(alpha = 0.94f),
            tonalElevation = 2.dp,
            shadowElevation = 8.dp,
        ) {
            Column(
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 22.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(Icons.Outlined.Info, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                Text(
                    text = "当前模拟器无法加载真实高德地图",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF071A3D),
                    textAlign = TextAlign.Center,
                )
                Text(
                    text = "这个设备主 ABI 是 ${Build.SUPPORTED_ABIS.firstOrNull().orEmpty()}，高德地图原生库需要 ARM 环境。请使用 Android 真机，或创建 ARM64 系统镜像的模拟器。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

private fun isAmapNativeRuntimeSupported(context: Context): Boolean {
    val nativeLibraryDir = context.applicationInfo.nativeLibraryDir.orEmpty()
    if (nativeLibraryDir.contains("arm64") || nativeLibraryDir.contains("armeabi")) return true
    val primaryAbi = Build.SUPPORTED_ABIS.firstOrNull().orEmpty()
    return primaryAbi == "arm64-v8a" || primaryAbi == "armeabi-v7a"
}

private fun createPlaceMarkerBitmap(
    context: Context,
    place: PlaceSummary,
    selected: Boolean,
): Bitmap {
    val density = context.resources.displayMetrics.density
    fun dp(value: Float): Float = value * density

    val iconSize = dp(if (selected) 44f else 38f)
    val gap = dp(5f)
    val horizontalPadding = dp(10f)
    val verticalPadding = dp(7f)
    val shadowPadding = dp(8f)
    val label = place.name.take(14)

    val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(14, 24, 45)
        textSize = dp(if (selected) 17f else 15f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }
    val labelBounds = Rect()
    labelPaint.getTextBounds(label, 0, label.length, labelBounds)

    val bitmapWidth = maxOf(iconSize, labelPaint.measureText(label) + horizontalPadding * 2f) + shadowPadding * 2f
    val bitmapHeight = iconSize + gap + labelBounds.height() + verticalPadding * 2f + shadowPadding * 2f
    val bitmap = Bitmap.createBitmap(bitmapWidth.toInt(), bitmapHeight.toInt(), Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)

    val centerX = bitmapWidth / 2f
    val iconCenterY = shadowPadding + iconSize / 2f

    val circlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
        setShadowLayer(dp(5f), 0f, dp(2f), AndroidColor.argb(45, 43, 73, 108))
    }
    canvas.drawCircle(centerX, iconCenterY, iconSize / 2f, circlePaint)

    if (selected) {
        val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = dp(2.5f)
            color = AndroidColor.rgb(31, 122, 224)
        }
        canvas.drawCircle(centerX, iconCenterY, iconSize / 2f - dp(1.5f), ringPaint)
    }

    val iconBackgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = categoryBackgroundColor(place.categoryId)
    }
    canvas.drawCircle(centerX, iconCenterY, iconSize * 0.33f, iconBackgroundPaint)

    val iconPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = categoryTextColor(place.categoryId)
        textSize = dp(if (selected) 17f else 15f)
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }
    val iconText = categoryMarkerText(place.categoryId)
    val iconTextY = iconCenterY - (iconPaint.descent() + iconPaint.ascent()) / 2f
    canvas.drawText(iconText, centerX, iconTextY, iconPaint)

    val labelBackgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.argb(if (selected) 238 else 218, 255, 255, 255)
    }
    val labelWidth = labelPaint.measureText(label) + horizontalPadding * 2f
    val labelHeight = labelBounds.height() + verticalPadding * 2f
    val labelLeft = centerX - labelWidth / 2f
    val labelTop = shadowPadding + iconSize + gap
    canvas.drawRoundRect(
        RectF(labelLeft, labelTop, labelLeft + labelWidth, labelTop + labelHeight),
        dp(10f),
        dp(10f),
        labelBackgroundPaint,
    )
    canvas.drawText(
        label,
        centerX - labelPaint.measureText(label) / 2f,
        labelTop + verticalPadding + labelBounds.height(),
        labelPaint,
    )

    return bitmap
}

private fun markerAnchorY(context: Context, selected: Boolean): Float {
    val density = context.resources.displayMetrics.density
    val iconSize = (if (selected) 44f else 38f) * density
    val shadowPadding = 8f * density
    val labelHeightEstimate = 31f * density
    val bitmapHeight = iconSize + 5f * density + labelHeightEstimate + shadowPadding * 2f
    return (shadowPadding + iconSize / 2f) / bitmapHeight
}

private fun applyTravelMapStyle(context: Context, map: AMap) {
    runCatching {
        val styleData = context.assets
            .open("map_custom/style-for-custom_0_25_1757046130.data")
            .use { it.readBytes() }
        val textureData = context.assets
            .open("map_custom/icons-for-custom_5_14.data")
            .use { it.readBytes() }

        map.setCustomMapStyle(
            CustomMapStyleOptions()
                .setEnable(true)
                .setStyleData(styleData)
                .setStyleTextureData(textureData),
        )
        map.setMapCustomEnable(true)
    }
}

private fun categoryMarkerText(categoryId: String): String {
    return when (categoryId) {
        ExploreCategories.FOOD -> "食"
        ExploreCategories.DRINK -> "饮"
        ExploreCategories.SHOPPING -> "购"
        ExploreCategories.LODGING -> "住"
        ExploreCategories.TRANSPORT -> "行"
        else -> "景"
    }
}

private fun categoryBackgroundColor(categoryId: String): Int {
    return when (categoryId) {
        ExploreCategories.FOOD -> AndroidColor.rgb(255, 239, 218)
        ExploreCategories.DRINK -> AndroidColor.rgb(223, 244, 255)
        ExploreCategories.SHOPPING -> AndroidColor.rgb(251, 221, 255)
        ExploreCategories.LODGING -> AndroidColor.rgb(225, 242, 255)
        ExploreCategories.TRANSPORT -> AndroidColor.rgb(232, 238, 255)
        else -> AndroidColor.rgb(222, 246, 224)
    }
}

private fun categoryTextColor(categoryId: String): Int {
    return when (categoryId) {
        ExploreCategories.FOOD -> AndroidColor.rgb(239, 139, 38)
        ExploreCategories.DRINK -> AndroidColor.rgb(57, 160, 211)
        ExploreCategories.SHOPPING -> AndroidColor.rgb(203, 85, 223)
        ExploreCategories.LODGING -> AndroidColor.rgb(75, 145, 210)
        ExploreCategories.TRANSPORT -> AndroidColor.rgb(86, 105, 210)
        else -> AndroidColor.rgb(73, 178, 88)
    }
}
