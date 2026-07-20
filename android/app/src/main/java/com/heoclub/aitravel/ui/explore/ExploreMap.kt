package com.heoclub.aitravel.ui.explore

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
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
import com.amap.api.maps.model.LatLngBounds
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.maps.model.PolylineOptions
import com.heoclub.aitravel.R
import com.heoclub.aitravel.data.location.CurrentLocation
import com.heoclub.aitravel.data.model.ExploreCategories
import com.heoclub.aitravel.data.model.PlaceSummary
import com.heoclub.aitravel.data.model.RouteCoordinate
import com.heoclub.aitravel.ui.components.loadMapMarkerImage
import kotlinx.coroutines.flow.SharedFlow
import android.graphics.Color as AndroidColor

class ExploreMapViewHolder(
    private val context: Context,
) {
    private var mapView: MapView? = null
    private var resumed = false
    private var renderedContent: RenderedMapContent? = null
    private var lastAnimatedPlaceId: String? = null
    private var lastAutoFitSignature: String? = null

    fun obtain(): MapView {
        return mapView ?: MapView(context).apply {
            onCreate(Bundle())
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
        }.also { mapView = it }
    }

    fun resume() {
        if (resumed) return
        obtain().onResume()
        resumed = true
    }

    fun pause() {
        if (!resumed) return
        mapView?.onPause()
        resumed = false
    }

    fun destroy() {
        pause()
        mapView?.onDestroy()
        mapView = null
        renderedContent = null
        lastAnimatedPlaceId = null
        lastAutoFitSignature = null
    }

    fun needsContentUpdate(
        places: List<PlaceSummary>,
        selectedPlaceId: String?,
        routePlaces: List<PlaceSummary>,
        routePolylines: List<List<RouteCoordinate>>,
        currentLocation: CurrentLocation?,
        showAllPlaces: Boolean,
    ): Boolean {
        val content = RenderedMapContent(
            places = places.toList(),
            selectedPlaceId = selectedPlaceId,
            routePlaces = routePlaces.toList(),
            routePolylines = routePolylines.map { it.toList() },
            currentLocation = currentLocation,
            showAllPlaces = showAllPlaces,
        )
        if (content == renderedContent) return false
        renderedContent = content
        return true
    }

    fun needsSelectedPlaceAnimation(selectedPlaceId: String?): Boolean {
        if (selectedPlaceId == null) {
            lastAnimatedPlaceId = null
            return false
        }
        if (selectedPlaceId == lastAnimatedPlaceId) return false
        lastAnimatedPlaceId = selectedPlaceId
        return true
    }

    fun needsAutoFit(signature: String): Boolean {
        if (signature == lastAutoFitSignature) return false
        lastAutoFitSignature = signature
        return true
    }

    private data class RenderedMapContent(
        val places: List<PlaceSummary>,
        val selectedPlaceId: String?,
        val routePlaces: List<PlaceSummary>,
        val routePolylines: List<List<RouteCoordinate>>,
        val currentLocation: CurrentLocation?,
        val showAllPlaces: Boolean,
    )
}

@Composable
internal fun rememberExploreMapViewHolder(): ExploreMapViewHolder {
    val context = LocalContext.current
    val holder = remember(context) { ExploreMapViewHolder(context) }
    DisposableEffect(holder) {
        onDispose(holder::destroy)
    }
    return holder
}

@Composable
private fun rememberMapViewHolder(providedHolder: ExploreMapViewHolder?): ExploreMapViewHolder {
    val context = LocalContext.current
    val holder = remember(context, providedHolder) {
        providedHolder ?: ExploreMapViewHolder(context)
    }
    DisposableEffect(holder, providedHolder) {
        onDispose {
            if (providedHolder == null) holder.destroy()
        }
    }
    return holder
}

@Composable
fun ExploreMap(
    places: List<PlaceSummary>,
    selectedPlaceId: String?,
    mapCommands: SharedFlow<MapCameraCommand>,
    onMarkerClick: (String) -> Unit,
    mapViewHolder: ExploreMapViewHolder? = null,
    routePlaces: List<PlaceSummary> = emptyList(),
    routePolylines: List<List<RouteCoordinate>> = emptyList(),
    currentLocation: CurrentLocation? = null,
    showAllPlaces: Boolean = false,
    autoFitPlaces: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    if (!isAmapNativeRuntimeSupported(context)) {
        AmapUnsupportedRuntimeNotice(modifier = modifier)
        return
    }

    val lifecycleOwner = LocalLifecycleOwner.current
    val activeMapViewHolder = rememberMapViewHolder(mapViewHolder)
    val mapView = remember(activeMapViewHolder) { activeMapViewHolder.obtain() }

    DisposableEffect(lifecycleOwner, mapView, activeMapViewHolder) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> activeMapViewHolder.resume()
                Lifecycle.Event.ON_PAUSE -> activeMapViewHolder.pause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            activeMapViewHolder.resume()
        }
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            activeMapViewHolder.pause()
        }
    }

    Box(modifier = modifier) {
        AndroidView(
            factory = { mapView },
            modifier = Modifier.fillMaxSize(),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .background(Color.White.copy(alpha = 0.42f)),
        )
    }

    LaunchedEffect(places, selectedPlaceId, routePlaces, routePolylines, currentLocation, showAllPlaces, autoFitPlaces) {
        val amap = mapView.map
        amap.setOnMarkerClickListener { marker ->
            (marker.`object` as? String)?.let(onMarkerClick)
            true
        }
        if (!activeMapViewHolder.needsContentUpdate(
                places = places,
                selectedPlaceId = selectedPlaceId,
                routePlaces = routePlaces,
                routePolylines = routePolylines,
                currentLocation = currentLocation,
                showAllPlaces = showAllPlaces,
            )
        ) {
            return@LaunchedEffect
        }
        amap.clear()
        currentLocation?.let { location ->
            amap.addMarker(
                MarkerOptions()
                    .position(LatLng(location.latitude, location.longitude))
                    .icon(BitmapDescriptorFactory.fromBitmap(createCurrentLocationMarkerBitmap(context)))
                    .anchor(0.5f, 0.5f)
                    .zIndex(50f),
            )
        }
        val routePoints = routePlaces.mapNotNull { place ->
            val latitude = place.latitude ?: return@mapNotNull null
            val longitude = place.longitude ?: return@mapNotNull null
            LatLng(latitude, longitude)
        }
        val actualRouteLines = routePolylines.filter { it.size >= 2 }
        if (actualRouteLines.isNotEmpty()) {
            actualRouteLines.forEach { line ->
                amap.addPolyline(
                    PolylineOptions()
                        .addAll(line.map { LatLng(it.latitude, it.longitude) })
                        .width(12f)
                        .color(AndroidColor.rgb(42, 169, 230))
                        .zIndex(6f),
                )
            }
        } else if (routePoints.size >= 2) {
            amap.addPolyline(
                PolylineOptions()
                    .addAll(routePoints)
                    .width(12f)
                    .color(AndroidColor.rgb(42, 169, 230))
                    .zIndex(6f),
            )
        }
        val photoMarkers = mutableListOf<Pair<com.amap.api.maps.model.Marker, PlaceSummary>>()
        visibleMapPlaces(places, selectedPlaceId, showAllPlaces).forEach { place ->
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
            if (marker != null && place.displayCoverImageUrl != null) {
                photoMarkers += marker to place
            }
        }
        val markerPhotoSize = (64f * context.resources.displayMetrics.density).toInt()
        photoMarkers.forEach { (marker, place) ->
            val photo = loadMapMarkerImage(context, place.displayCoverImageUrl, markerPhotoSize)
            if (photo != null) {
                marker.setIcon(
                    BitmapDescriptorFactory.fromBitmap(
                        createPlaceMarkerBitmap(context, place, place.id == selectedPlaceId, photo),
                    ),
                )
            }
        }
        if (autoFitPlaces) {
            val visiblePoints = visibleMapPlaces(places, selectedPlaceId, showAllPlaces)
                .mapNotNull { place ->
                    val latitude = place.latitude ?: return@mapNotNull null
                    val longitude = place.longitude ?: return@mapNotNull null
                    LatLng(latitude, longitude)
                }
            val signature = visiblePoints.joinToString("|") { "${it.latitude},${it.longitude}" }
            if (visiblePoints.isNotEmpty() && activeMapViewHolder.needsAutoFit(signature)) {
                mapView.post {
                    if (visiblePoints.size == 1) {
                        amap.animateCamera(CameraUpdateFactory.newLatLngZoom(visiblePoints.first(), 14.2f))
                    } else {
                        val bounds = LatLngBounds.builder().also { builder ->
                            visiblePoints.forEach(builder::include)
                        }.build()
                        amap.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, 88))
                    }
                }
            }
        }
    }

    LaunchedEffect(selectedPlaceId) {
        if (!activeMapViewHolder.needsSelectedPlaceAnimation(selectedPlaceId)) {
            return@LaunchedEffect
        }
        val selectedPlace = places.firstOrNull { it.id == selectedPlaceId }
        val latitude = selectedPlace?.latitude
        val longitude = selectedPlace?.longitude
        if (latitude != null && longitude != null) {
            mapView.map.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(latitude, longitude), 14.2f))
        }
    }

    LaunchedEffect(currentLocation?.updateSequence) {
        currentLocation?.let { location ->
            mapView.map.animateCamera(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(location.latitude, location.longitude),
                    16.2f,
                ),
            )
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
    showAllPlaces: Boolean,
): List<PlaceSummary> {
    val mappablePlaces = places.filter { it.latitude != null && it.longitude != null }
    val selectedPlace = mappablePlaces.firstOrNull { it.id == selectedPlaceId }
    val limit = if (showAllPlaces) mappablePlaces.size else 8
    return (listOfNotNull(selectedPlace) + mappablePlaces.filterNot { it.id == selectedPlaceId }.take(limit))
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
    photo: Bitmap? = null,
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

    if (photo != null) {
        val inset = dp(3f)
        val radius = iconSize / 2f - inset
        val clipPath = Path().apply { addCircle(centerX, iconCenterY, radius, Path.Direction.CW) }
        val destination = RectF(centerX - radius, iconCenterY - radius, centerX + radius, iconCenterY + radius)
        canvas.save()
        canvas.clipPath(clipPath)
        canvas.drawBitmap(photo, null, destination, Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG))
        canvas.restore()
    }

    if (selected) {
        val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = dp(2.5f)
            color = AndroidColor.rgb(31, 122, 224)
        }
        canvas.drawCircle(centerX, iconCenterY, iconSize / 2f - dp(1.5f), ringPaint)
    }

    if (photo == null) {
        val markerIcon = context.getDrawable(categoryMarkerIconRes(place.categoryId))?.mutate()
        val markerIconSize = iconSize * if (selected) 0.58f else 0.54f
        markerIcon?.setTint(AndroidColor.rgb(31, 122, 224))
        markerIcon?.setBounds(
            (centerX - markerIconSize / 2f).toInt(),
            (iconCenterY - markerIconSize / 2f).toInt(),
            (centerX + markerIconSize / 2f).toInt(),
            (iconCenterY + markerIconSize / 2f).toInt(),
        )
        markerIcon?.draw(canvas)
    }

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

private fun createCurrentLocationMarkerBitmap(context: Context): Bitmap {
    val density = context.resources.displayMetrics.density
    val size = (42f * density).toInt()
    val center = size / 2f
    val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)

    val outerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
        setShadowLayer(5f * density, 0f, 2f * density, AndroidColor.argb(70, 31, 72, 120))
    }
    canvas.drawCircle(center, center, 15f * density, outerPaint)

    val locationPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.rgb(31, 122, 224)
    }
    canvas.drawCircle(center, center, 10f * density, locationPaint)

    val centerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = AndroidColor.WHITE
    }
    canvas.drawCircle(center, center, 3.5f * density, centerPaint)
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

private fun categoryMarkerIconRes(categoryId: String): Int {
    return when (categoryId) {
        ExploreCategories.FOOD -> R.drawable.ic_marker_food
        ExploreCategories.DRINK -> R.drawable.ic_marker_drink
        ExploreCategories.SHOPPING -> R.drawable.ic_marker_shopping
        ExploreCategories.LODGING -> R.drawable.ic_marker_lodging
        ExploreCategories.TRANSPORT -> R.drawable.ic_marker_transport
        else -> R.drawable.ic_marker_scenic
    }
}
