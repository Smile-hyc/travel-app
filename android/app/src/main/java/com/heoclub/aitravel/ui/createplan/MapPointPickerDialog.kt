package com.heoclub.aitravel.ui.createplan

import android.os.Bundle
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.amap.api.maps.AMap
import com.amap.api.maps.CameraUpdateFactory
import com.amap.api.maps.MapView
import com.amap.api.maps.model.BitmapDescriptorFactory
import com.amap.api.maps.model.LatLng
import com.amap.api.maps.model.MarkerOptions
import com.amap.api.services.core.AMapException
import com.amap.api.services.core.LatLonPoint
import com.amap.api.services.geocoder.GeocodeResult
import com.amap.api.services.geocoder.GeocodeSearch
import com.amap.api.services.geocoder.RegeocodeQuery
import com.amap.api.services.geocoder.RegeocodeResult

data class PickedMapPoint(
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
)

@Composable
fun MapPointPickerDialog(
    title: String,
    initialLatitude: Double,
    initialLongitude: Double,
    onDismiss: () -> Unit,
    onConfirm: (PickedMapPoint) -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var pickedLatLng by remember { mutableStateOf<LatLng?>(null) }
    var pickedName by remember { mutableStateOf("") }
    var pickedAddress by remember { mutableStateOf("点击地图选择具体位置") }
    var isResolving by remember { mutableStateOf(false) }
    val mapView = remember {
        MapView(context).apply {
            onCreate(Bundle())
            map.mapType = AMap.MAP_TYPE_NORMAL
            map.uiSettings.isZoomControlsEnabled = false
            map.uiSettings.isMyLocationButtonEnabled = false
            map.moveCamera(
                CameraUpdateFactory.newLatLngZoom(
                    LatLng(initialLatitude, initialLongitude),
                    13.2f,
                ),
            )
        }
    }
    val geocodeSearch = remember(context) { GeocodeSearch(context) }

    fun selectPoint(latLng: LatLng) {
        pickedLatLng = latLng
        pickedName = ""
        pickedAddress = "正在获取位置名称…"
        isResolving = true
        mapView.map.clear()
        mapView.map.addMarker(
            MarkerOptions()
                .position(latLng)
                .icon(BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_AZURE)),
        )
        mapView.map.animateCamera(CameraUpdateFactory.newLatLng(latLng))
        geocodeSearch.getFromLocationAsyn(
            RegeocodeQuery(
                LatLonPoint(latLng.latitude, latLng.longitude),
                250f,
                GeocodeSearch.AMAP,
            ),
        )
    }

    DisposableEffect(lifecycleOwner, mapView) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) mapView.onResume()
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            mapView.onPause()
            mapView.onDestroy()
        }
    }

    DisposableEffect(mapView, geocodeSearch) {
        geocodeSearch.setOnGeocodeSearchListener(object : GeocodeSearch.OnGeocodeSearchListener {
            override fun onRegeocodeSearched(result: RegeocodeResult?, resultCode: Int) {
                isResolving = false
                val address = result?.regeocodeAddress
                if (resultCode == AMapException.CODE_AMAP_SUCCESS && address != null) {
                    pickedName = address.pois.firstOrNull()?.title
                        ?: address.building
                        ?: address.neighborhood
                        ?: address.township
                        ?: "地图选定位置"
                    pickedAddress = address.formatAddress?.takeIf(String::isNotBlank) ?: pickedName
                } else {
                    pickedName = "地图选定位置"
                    pickedAddress = "位置名称获取失败，可重新选择"
                }
            }

            override fun onGeocodeSearched(result: GeocodeResult?, resultCode: Int) = Unit
        })
        mapView.map.setOnMapClickListener { latLng ->
            selectPoint(latLng)
        }
        onDispose {
            mapView.map.setOnMapClickListener(null)
            geocodeSearch.setOnGeocodeSearchListener(null)
        }
    }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier.fillMaxSize().padding(top = 24.dp),
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text("点击地图选择，系统会识别附近地点", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Outlined.Close, contentDescription = "关闭地图选点")
                    }
                }
                Box(modifier = Modifier.fillMaxWidth().weight(1f)) {
                    AndroidView(factory = { mapView }, modifier = Modifier.fillMaxSize())
                    Surface(
                        modifier = Modifier.align(Alignment.TopCenter).padding(14.dp),
                        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.94f),
                        shape = RoundedCornerShape(16.dp),
                        shadowElevation = 3.dp,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Icon(Icons.Outlined.LocationOn, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Text("在地图上点选具体位置", fontWeight = FontWeight.SemiBold)
                        }
                    }
                }
                Column(
                    modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(
                        text = if (isResolving) "正在识别位置…" else pickedName.ifBlank { "尚未选择地点" },
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        pickedAddress,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    OutlinedButton(
                        onClick = { selectPoint(mapView.map.cameraPosition.target) },
                        enabled = !isResolving,
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        Icon(Icons.Outlined.LocationOn, contentDescription = null)
                        Text("选择地图中心位置", modifier = Modifier.padding(start = 6.dp))
                    }
                    Button(
                        onClick = {
                            val point = pickedLatLng ?: return@Button
                            onConfirm(
                                PickedMapPoint(
                                    name = pickedName.ifBlank { "地图选定位置" },
                                    address = pickedAddress,
                                    latitude = point.latitude,
                                    longitude = point.longitude,
                                ),
                            )
                        },
                        enabled = pickedLatLng != null && !isResolving,
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        Text("使用这个位置")
                    }
                }
            }
        }
    }
}
