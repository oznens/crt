package com.oznens.poseprequel.pose

import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.pose.Pose
import com.google.mlkit.vision.pose.PoseDetection
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions

/**
 * CameraX ImageAnalysis.Analyzer that runs ML Kit pose detection on each frame
 * and dispatches the latest [Pose] (plus frame width/height) to [onResult].
 *
 * Backpressure: configure the bound [ImageAnalysis] with
 * [ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST] — we close every proxy and only
 * detect on whatever frame is current.
 */
class PoseAnalyzer(
    private val onResult: (Pose, width: Int, height: Int) -> Unit,
) : ImageAnalysis.Analyzer {

    private val detector by lazy {
        PoseDetection.getClient(
            PoseDetectorOptions.Builder()
                .setDetectorMode(PoseDetectorOptions.STREAM_MODE)
                .build()
        )
    }

    @OptIn(ExperimentalGetImage::class)
    override fun analyze(proxy: ImageProxy) {
        val mediaImage = proxy.image
        if (mediaImage == null) {
            proxy.close()
            return
        }
        val rotation = proxy.imageInfo.rotationDegrees
        val input = InputImage.fromMediaImage(mediaImage, rotation)
        // For a sideways (90/270) rotated frame, the *upright* image flips W/H.
        val upright = rotation == 90 || rotation == 270
        val w = if (upright) proxy.height else proxy.width
        val h = if (upright) proxy.width else proxy.height
        detector.process(input)
            .addOnSuccessListener { pose -> onResult(pose, w, h) }
            .addOnCompleteListener { proxy.close() }
    }

    fun close() {
        runCatching { detector.close() }
    }
}
