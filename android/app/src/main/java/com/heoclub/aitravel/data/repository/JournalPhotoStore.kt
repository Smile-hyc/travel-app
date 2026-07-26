package com.heoclub.aitravel.data.repository

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import java.io.File
import java.util.UUID

class JournalPhotoStore(context: Context) {
    private val directory = File(context.applicationContext.filesDir, "journal_photos").apply {
        mkdirs()
    }

    fun save(bitmap: Bitmap): String? {
        val fileName = "journal-${UUID.randomUUID()}.jpg"
        val target = File(directory, fileName)
        return runCatching {
            target.outputStream().buffered().use { output ->
                check(bitmap.compress(Bitmap.CompressFormat.JPEG, 90, output))
            }
            fileName
        }.getOrElse {
            target.delete()
            null
        }
    }

    fun load(fileName: String?): Bitmap? {
        val safeName = fileName
            ?.takeIf { it.isNotBlank() && it == File(it).name }
            ?: return null
        val file = File(directory, safeName)
        if (!file.isFile) return null
        return runCatching { BitmapFactory.decodeFile(file.absolutePath) }.getOrNull()
    }

    fun delete(fileName: String?) {
        val safeName = fileName
            ?.takeIf { it.isNotBlank() && it == File(it).name }
            ?: return
        runCatching { File(directory, safeName).delete() }
    }
}
