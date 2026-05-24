package com.oznens.poseprequel.capture

import android.content.ContentResolver
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.net.Uri
import android.provider.MediaStore
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import com.oznens.poseprequel.filter.Filter
import java.util.concurrent.Executor

/**
 * Takes an in-memory photo with [ImageCapture], applies the current [Filter]
 * to the resulting bitmap (so the saved file matches what the user saw in
 * preview — RenderEffect only colors the preview surface, not captures),
 * then writes a JPEG into MediaStore under `Pictures/PosePrequel/`.
 */
object PhotoSaver {

    fun capture(
        imageCapture: ImageCapture,
        executor: Executor,
        filter: Filter,
        contentResolver: ContentResolver,
        onResult: (Result<Uri>) -> Unit,
    ) {
        imageCapture.takePicture(
            executor,
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(image: ImageProxy) {
                    try {
                        val raw = decodeJpeg(image)
                        val upright = rotate(raw, image.imageInfo.rotationDegrees)
                        val processed = applyFilter(upright, filter)
                        val uri = saveJpeg(contentResolver, processed)
                        onResult(Result.success(uri))
                    } catch (t: Throwable) {
                        onResult(Result.failure(t))
                    } finally {
                        image.close()
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    onResult(Result.failure(exception))
                }
            },
        )
    }

    private fun decodeJpeg(image: ImageProxy): Bitmap {
        // ImageCapture.OUTPUT_FORMAT_JPEG packs the whole JPEG into planes[0].
        val buffer = image.planes[0].buffer
        val bytes = ByteArray(buffer.remaining()).also { buffer.get(it) }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: error("BitmapFactory.decodeByteArray returned null")
    }

    private fun rotate(src: Bitmap, degrees: Int): Bitmap {
        if (degrees % 360 == 0) return src
        val matrix = Matrix().apply { postRotate(degrees.toFloat()) }
        val out = Bitmap.createBitmap(src, 0, 0, src.width, src.height, matrix, true)
        if (out !== src) src.recycle()
        return out
    }

    private fun applyFilter(src: Bitmap, filter: Filter): Bitmap {
        if (filter.id == "orig") return src
        val out = Bitmap.createBitmap(src.width, src.height, Bitmap.Config.ARGB_8888)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            colorFilter = filter.colorFilter()
        }
        Canvas(out).drawBitmap(src, 0f, 0f, paint)
        src.recycle()
        return out
    }

    private fun saveJpeg(resolver: ContentResolver, bitmap: Bitmap): Uri {
        val name = "PP_${System.currentTimeMillis()}.jpg"
        val pending = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PosePrequel")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val collection = MediaStore.Images.Media
            .getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = resolver.insert(collection, pending)
            ?: error("MediaStore insert returned null")
        try {
            resolver.openOutputStream(uri).use { os ->
                requireNotNull(os) { "openOutputStream returned null" }
                bitmap.compress(Bitmap.CompressFormat.JPEG, 92, os)
            }
            val publish = ContentValues().apply {
                put(MediaStore.Images.Media.IS_PENDING, 0)
            }
            resolver.update(uri, publish, null, null)
        } catch (t: Throwable) {
            // Roll back the half-created MediaStore row so we don't leave a
            // stuck IS_PENDING=1 entry the user can't see.
            runCatching { resolver.delete(uri, null, null) }
            throw t
        } finally {
            bitmap.recycle()
        }
        return uri
    }
}
