package com.oznens.poseprequel.pose

import com.google.mlkit.vision.pose.PoseLandmark
import kotlin.math.hypot

/**
 * Scores a normalized keypoint map against a [PoseTemplate].
 *
 * Both inputs live in the same 0..1 space — for the front camera this is the
 * *mirrored* image-normalized space (so detected.right_wrist sits on the same
 * side of the frame the user sees their right wrist).
 *
 * Pipeline:
 *  1. Align the hip midpoint of detected onto the template's hip midpoint.
 *  2. Scale by torso-length ratio so closer/further users score the same.
 *  3. Mean Euclidean error → 0..100 score (0.25 frame-width off = 0).
 */
class PoseSuggester {

    /** Result of comparing a detected pose against a template. */
    data class Match(
        val score: Int,              // 0..100, higher = closer to template
        val perLandmarkError: Map<Int, Float>, // normalized-space distance per scored landmark
    )

    fun matchPoints(
        points: Map<Int, Pair<Float, Float>>,
        template: PoseTemplate,
    ): Match? {
        if (points.size < template.points.size / 2) return null

        val (dHipX, dHipY) = midpoint(points, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
            ?: return null
        val (tHipX, tHipY) = midpoint(template.points, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
            ?: return null
        val dTorso = torsoLength(points) ?: return null
        val tTorso = torsoLength(template.points) ?: return null
        val scale = if (dTorso > 1e-6f) tTorso / dTorso else 1f

        var totalErr = 0f
        var count = 0
        val perLandmark = HashMap<Int, Float>(points.size)
        for ((id, dPt) in points) {
            val tPt = template.points[id] ?: continue
            val alignedX = (dPt.first - dHipX) * scale + tHipX
            val alignedY = (dPt.second - dHipY) * scale + tHipY
            val err = hypot(alignedX - tPt.first, alignedY - tPt.second)
            perLandmark[id] = err
            totalErr += err
            count++
        }
        if (count == 0) return null
        val meanErr = totalErr / count
        val score = (100f * (1f - (meanErr / 0.25f)).coerceIn(0f, 1f)).toInt()
        return Match(score = score, perLandmarkError = perLandmark)
    }

    fun bestMatchPoints(
        points: Map<Int, Pair<Float, Float>>,
        templates: List<PoseTemplate>,
    ): Pair<PoseTemplate, Match>? {
        var best: Pair<PoseTemplate, Match>? = null
        for (t in templates) {
            val m = matchPoints(points, t) ?: continue
            val b = best
            if (b == null || m.score > b.second.score) best = t to m
        }
        return best
    }

    private fun midpoint(
        pts: Map<Int, Pair<Float, Float>>,
        a: Int,
        b: Int,
    ): Pair<Float, Float>? {
        val pa = pts[a] ?: return null
        val pb = pts[b] ?: return null
        return Pair((pa.first + pb.first) / 2f, (pa.second + pb.second) / 2f)
    }

    private fun torsoLength(pts: Map<Int, Pair<Float, Float>>): Float? {
        val shoulder = midpoint(pts, PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER)
            ?: return null
        val hip = midpoint(pts, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
            ?: return null
        return hypot(shoulder.first - hip.first, shoulder.second - hip.second)
    }
}
