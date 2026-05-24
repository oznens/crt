package com.oznens.poseprequel.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.graphicsLayer
import com.google.mlkit.vision.pose.PoseLandmark
import com.oznens.poseprequel.pose.PoseTemplate
import kotlin.math.max

/**
 * Renders the pose target as a single smooth silhouette (Huawei-style) plus
 * a faint live skeleton so the user gets feedback that detection is working.
 *
 * All coordinates are expressed in 0..1 image-normalized space, with the
 * mirror already applied upstream for the front camera. This composable
 * handles the FILL_CENTER mapping from image-normalized to view coords.
 *
 * @param imageAspect Source image width / height. The PreviewView uses
 *        FILL_CENTER, so we apply the same scale + center-crop here.
 */
@Composable
fun PoseOverlay(
    template: PoseTemplate,
    detected: Map<Int, Pair<Float, Float>>,
    imageAspect: Float,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier) {
        // 1) Static silhouette ghost — drawn on an offscreen layer so all body
        //    parts composite at uniform alpha (no visible internal seams).
        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    compositingStrategy = CompositingStrategy.Offscreen
                    alpha = 0.5f
                },
        ) {
            drawSilhouette(template.points, imageAspect, Color.White)
        }

        // 2) Faint live skeleton — pink hairlines, ~25% alpha. Smoothed by
        //    PoseSmoother upstream so it shouldn't twitch frame-to-frame.
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawLiveSkeleton(detected, imageAspect, Color(0xFFFF4D8D).copy(alpha = 0.35f))
        }
    }
}

/** FILL_CENTER mapping from image-normalized point to view-space [Offset]. */
private fun DrawScope.mapPoint(nx: Float, ny: Float, imageAspect: Float): Offset {
    val viewW = size.width
    val viewH = size.height
    // Scale so the unit-height image (h=1, w=imageAspect) covers the view.
    val scale = max(viewW / imageAspect, viewH)
    val scaledW = imageAspect * scale
    val scaledH = scale
    val vx = (nx - 0.5f) * scaledW + viewW / 2f
    val vy = (ny - 0.5f) * scaledH + viewH / 2f
    return Offset(vx, vy)
}

private fun DrawScope.drawSilhouette(
    points: Map<Int, Pair<Float, Float>>,
    imageAspect: Float,
    color: Color,
) {
    fun p(id: Int): Offset? = points[id]?.let { mapPoint(it.first, it.second, imageAspect) }

    val ls = p(PoseLandmark.LEFT_SHOULDER) ?: return
    val rs = p(PoseLandmark.RIGHT_SHOULDER) ?: return
    val lh = p(PoseLandmark.LEFT_HIP) ?: return
    val rh = p(PoseLandmark.RIGHT_HIP) ?: return
    val nose = p(PoseLandmark.NOSE) ?: return

    val short = kotlin.math.min(size.width, size.height)
    val armW = short * 0.085f
    val legW = short * 0.105f
    val neckW = short * 0.08f

    // Torso — filled polygon between shoulders and hips.
    val torso = Path().apply {
        moveTo(ls.x, ls.y)
        lineTo(rs.x, rs.y)
        lineTo(rh.x, rh.y)
        lineTo(lh.x, lh.y)
        close()
    }
    drawPath(torso, color)

    // Neck — fat capsule from shoulder midpoint up to the head.
    val neck = Offset((ls.x + rs.x) / 2f, (ls.y + rs.y) / 2f)
    drawLine(color, neck, nose, strokeWidth = neckW, cap = StrokeCap.Round)

    // Head — circle around NOSE.
    val headR = short * 0.07f
    drawCircle(color, headR, nose)

    // Arms — capsules at shoulder→elbow→wrist.
    listOf(
        PoseLandmark.LEFT_SHOULDER to PoseLandmark.LEFT_ELBOW,
        PoseLandmark.LEFT_ELBOW to PoseLandmark.LEFT_WRIST,
        PoseLandmark.RIGHT_SHOULDER to PoseLandmark.RIGHT_ELBOW,
        PoseLandmark.RIGHT_ELBOW to PoseLandmark.RIGHT_WRIST,
    ).forEach { (a, b) ->
        val pa = p(a) ?: return@forEach
        val pb = p(b) ?: return@forEach
        drawLine(color, pa, pb, strokeWidth = armW, cap = StrokeCap.Round)
    }

    // Legs — capsules at hip→knee→ankle.
    listOf(
        PoseLandmark.LEFT_HIP to PoseLandmark.LEFT_KNEE,
        PoseLandmark.LEFT_KNEE to PoseLandmark.LEFT_ANKLE,
        PoseLandmark.RIGHT_HIP to PoseLandmark.RIGHT_KNEE,
        PoseLandmark.RIGHT_KNEE to PoseLandmark.RIGHT_ANKLE,
    ).forEach { (a, b) ->
        val pa = p(a) ?: return@forEach
        val pb = p(b) ?: return@forEach
        drawLine(color, pa, pb, strokeWidth = legW, cap = StrokeCap.Round)
    }

    // Hands & feet caps — small bumps so the limb endpoints look organic.
    p(PoseLandmark.LEFT_WRIST)?.let { drawCircle(color, armW / 2f, it) }
    p(PoseLandmark.RIGHT_WRIST)?.let { drawCircle(color, armW / 2f, it) }
    p(PoseLandmark.LEFT_ANKLE)?.let { drawCircle(color, legW / 2f, it) }
    p(PoseLandmark.RIGHT_ANKLE)?.let { drawCircle(color, legW / 2f, it) }
}

private fun DrawScope.drawLiveSkeleton(
    points: Map<Int, Pair<Float, Float>>,
    imageAspect: Float,
    color: Color,
) {
    for ((aId, bId) in PoseTemplate.EDGES) {
        val a = points[aId] ?: continue
        val b = points[bId] ?: continue
        drawLine(
            color = color,
            start = mapPoint(a.first, a.second, imageAspect),
            end = mapPoint(b.first, b.second, imageAspect),
            strokeWidth = 4f,
            cap = StrokeCap.Round,
        )
    }
}
