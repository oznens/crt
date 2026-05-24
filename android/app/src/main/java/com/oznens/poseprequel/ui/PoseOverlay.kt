package com.oznens.poseprequel.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import com.oznens.poseprequel.pose.PoseTemplate

/**
 * Renders the template skeleton (dashed, semi-transparent — the "ghost"
 * Huawei shows you to match) and the live detected skeleton (solid pink).
 */
@Composable
fun PoseOverlay(
    template: PoseTemplate,
    detected: Map<Int, Pair<Float, Float>>,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) {
        val w = size.width
        val h = size.height

        // Template ghost — dashed white outline
        val dash = PathEffect.dashPathEffect(floatArrayOf(18f, 12f), 0f)
        for ((aId, bId) in PoseTemplate.EDGES) {
            val a = template.points[aId] ?: continue
            val b = template.points[bId] ?: continue
            drawLine(
                color = Color.White.copy(alpha = 0.55f),
                start = Offset(a.first * w, a.second * h),
                end = Offset(b.first * w, b.second * h),
                strokeWidth = 6f,
                pathEffect = dash,
            )
        }
        for ((_, pt) in template.points) {
            drawCircle(
                color = Color.White.copy(alpha = 0.55f),
                radius = 8f,
                center = Offset(pt.first * w, pt.second * h),
                style = Stroke(width = 3f),
            )
        }

        // Detected skeleton — solid magenta
        for ((aId, bId) in PoseTemplate.EDGES) {
            val a = detected[aId] ?: continue
            val b = detected[bId] ?: continue
            drawLine(
                color = Color(0xFFFF4D8D),
                start = Offset(a.first * w, a.second * h),
                end = Offset(b.first * w, b.second * h),
                strokeWidth = 6f,
            )
        }
        for ((_, pt) in detected) {
            drawCircle(
                color = Color(0xFFFF4D8D),
                radius = 10f,
                center = Offset(pt.first * w, pt.second * h),
            )
        }
    }
}
