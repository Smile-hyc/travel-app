package com.heoclub.aitravel.ui.explore

sealed interface MapCameraCommand {
    data class MoveToCity(
        val latitude: Double,
        val longitude: Double,
        val zoom: Float,
    ) : MapCameraCommand

    data class MoveToPlace(
        val latitude: Double,
        val longitude: Double,
        val zoom: Float = 15.5f,
    ) : MapCameraCommand
}
