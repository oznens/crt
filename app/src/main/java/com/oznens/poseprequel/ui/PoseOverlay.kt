package com.oznens.poseprequel.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.graphicsLayer
import com.google.mlkit.vision.pose.PoseLandmark
import com.oznens.poseprequel.pose.PoseTemplate
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * Huawei-style pose target rendered as a single uniform-thickness outline
 * (no internal seams), plus a very faint live skeleton for "detection is
 * working" feedback.
 *
 * Outline trick: every body part is a capsule or circle. We render the
 * full silhouette filled white on an offscreen layer, then redraw the same
 * silhouette with limb widths/head radius reduced by `2 * outlinePx` using
 * `BlendMode.Clear` — the interior is erased, leaving a clean outline.
 *
 * Coordinates are 0..1 image-normalized (already mirrored upstream for the
 * front camera). This composable applies the FILL_CENTER transform from
 * image space to view space, matching the PreviewView's scaleType.
 */
@Composable
fun PoseOverlay(
    template: PoseTemplate,
    detected: Map<Int, Pair<Float, Float>>,
    imageAspect: Float,
    modifier: Modifier = Modifier,
) {
    Box(modifier = modifier) {

        Canvas(
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer { compositingStrategy = CompositingStrategy.Offscreen },
        ) {
            val outline = min(size.width, size.height) * 0.006f // ~7px on 1080w
            // Outer filled silhouette
            drawSilhouette(
                points = template.points,
                imageAspect = imageAspect,
                color = Color.White.copy(alpha = 0.9f),
            )
            // Erase interior to leave only the outline ring
            drawSilhouette(
                points = template.points,
                imageAspect = imageAspect,
                color = Color.White,            // ignored for Clear
                widthDelta = -outline * 2f,
                blendMode = BlendMode.Clear,
            )
        }

        // Faint live skeleton — smoothed upstream, drawn behind the outline.
        Canvas(modifier = Modifier.fillMaxSize()) {
            drawLiveSkeleton(
                points = detected,
                imageAspect = imageAspect,
                color = Color(0xFFFF4D8D).copy(alpha = 0.30f),
            )
        }
    }
}

/**
 * Maps a normalized image-space point (0..1, top-left origin) to view-space
 * using the same FILL_CENTER scaling the PreviewView applies. Returns view
 * pixels.
 */
private fun DrawScope.mapPoint(nx: Float, ny: Float, imageAspect: Float): Offset {
    val viewW = size.width
    val viewH = size.height
    // Unit-height image (h=1, w=imageAspect) scaled to cover the view.
    val scale = max(viewW / imageAspect, viewH)
    val scaledW = imageAspect * scale
    val scaledH = scale
    return Offset(
        (nx - 0.5f) * scaledW + viewW / 2f,
        (ny - 0.5f) * scaledH + viewH / 2f,
    )
}

/**
 * Draws the silhouette as a union of capsules + a head circle. Pass a
 * negative [widthDelta] together with `BlendMode.Clear` to erase the
 * interior and leave only an outline.
 */
private fun DrawScope.drawSilhouette(
    points: Map<Int, Pair<Float, Float>>,
    imageAspect: Float,
    color: Color,
    widthDelta: Float = 0f,
    blendMode: BlendMode = DrawScope.DefaultBlendMode,
) {
    fun p(id: Int): Offset? = points[id]?.let { mapPoint(it.first, it.second, imageAspect) }

    val ls = p(PoseLandmark.LEFT_SHOULDER) ?: return
    val rs = p(PoseLandmark.RIGHT_SHOULDER) ?: return
    val lh = p(PoseLandmark.LEFT_HIP) ?: return
    val rh = p(PoseLandmark.RIGHT_HIP) ?: return
    val nose = p(PoseLandmark.NOSE) ?: return

    val short = min(size.width, size.height)
    val shoulderSpan = hypot(rs.x - ls.x, rs.y - ls.y)

    fun w(base: Float) = (base + widthDelta).coerceAtLeast(0f)
    fun r(base: Float) = (base + widthDelta / 2f).coerceAtLeast(0f)

    val torsoW = w(shoulderSpan * 1.05f)
    val armW = w(short * 0.085f)
    val legW = w(short * 0.105f)
    val neckW = w(short * 0.075f)
    val headR = r(short * 0.075f)

    val shoulderMid = Offset((ls.x + rs.x) / 2f, (ls.y + rs.y) / 2f)
    val hipMid = Offset((lh.x + rh.x) / 2f, (lh.y + rh.y) / 2f)

    // Torso pill — vertical capsule between shoulder-mid and hip-mid.
    if (torsoW > 0f) drawLine(
        color, shoulderMid, hipMid, strokeWidth = torsoW,
        cap = StrokeCap.Round, blendMode = blendMode,
    )

    // Neck capsule
    if (neckW > 0f) drawLine(
        color, shoulderMid, nose, strokeWidth = neckW,
        cap = StrokeCap.Round, blendMode = blendMode,
    )

    // Head circle
    if (headR > 0f) drawCircle(color, headR, nose, blendMode = blendMode)

    val limbs = listOf(
        Triple(PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW, armW),
        Triple(PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST, armW),
        Triple(PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_ELBOW, armW),
        Triple(PoseLandmark.RIGHT_ELBOW, PoseLandmark.RIGHT_WRIST, armW),
        Triple(PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE, legW),
        Triple(PoseLandmark.LEFT_KNEE, PoseLandmark.LEFT_ANKLE, legW),
        Triple(PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE, legW),
        Triple(PoseLandmark.RIGHT_KNEE, PoseLandmark.RIGHT_ANKLE, legW),
    )
    for ((a, b, sw) in limbs) {
        if (sw <= 0f) continue
        val pa = p(a) ?: continue
        val pb = p(b) ?: continue
        drawLine(color, pa, pb, strokeWidth = sw, cap = StrokeCap.Round, blendMode = blendMode)
    }
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
