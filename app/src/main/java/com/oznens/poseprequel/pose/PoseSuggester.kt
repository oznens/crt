package com.oznens.poseprequel.pose

import com.google.mlkit.vision.pose.Pose
import com.google.mlkit.vision.pose.PoseLandmark
import kotlin.math.hypot

/**
 * Scores a detected [Pose] against the active [PoseTemplate].
 *
 * Pipeline:
 *  1. Drop landmarks with low ML Kit confidence (< 0.5).
 *  2. Normalize the detected pose into the same 0..1 box the templates use,
 *     by mapping the hip midpoint to the template's hip midpoint and scaling
 *     so the shoulder-to-hip distance matches.
 *  3. Compute mean per-landmark Euclidean error; convert to a 0..100 score.
 */
class PoseSuggester(
    /** Image width the detected pose was measured in (pixels). */
    var imageWidth: Int = 1,
    /** Image height the detected pose was measured in (pixels). */
    var imageHeight: Int = 1,
) {

    /** Result of comparing a detected pose against a template. */
    data class Match(
        val score: Int,              // 0..100, higher = closer to template
        val perLandmarkError: Map<Int, Float>, // normalized-space distance per scored landmark
    )

    fun match(pose: Pose, template: PoseTemplate): Match? {
        val w = imageWidth.takeIf { it > 0 } ?: return null
        val h = imageHeight.takeIf { it > 0 } ?: return null

        // 1) collect normalized detected points for the scored landmarks
        val detected = HashMap<Int, Pair<Float, Float>>(template.points.size)
        for (id in template.landmarkIds) {
            val lm = pose.getPoseLandmark(id) ?: continue
            if (lm.inFrameLikelihood < 0.5f) continue
            detected[id] = Pair(lm.position.x / w, lm.position.y / h)
        }
        if (detected.size < template.points.size / 2) return null  // not enough data

        // 2) compute detected vs template hip midpoint + shoulder->hip scale
        val (dHipX, dHipY) = midpoint(detected, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
            ?: return null
        val (tHipX, tHipY) = midpoint(template.points, PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP)
            ?: return null
        val dTorso = torsoLength(detected) ?: return null
        val tTorso = torsoLength(template.points) ?: return null
        val scale = if (dTorso > 1e-6f) tTorso / dTorso else 1f

        // 3) per-landmark error after aligning hip midpoints and scaling
        var totalErr = 0f
        var count = 0
        val perLandmark = HashMap<Int, Float>(detected.size)
        for ((id, dPt) in detected) {
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
        // Map 0.0 err -> 100, 0.25 err -> 0 (quarter of frame off = useless)
        val score = (100f * (1f - (meanErr / 0.25f)).coerceIn(0f, 1f)).toInt()

        return Match(score = score, perLandmarkError = perLandmark)
    }

    /** Picks the template with the highest score for the given pose. */
    fun bestMatch(pose: Pose, templates: List<PoseTemplate>): Pair<PoseTemplate, Match>? {
        var best: Pair<PoseTemplate, Match>? = null
        for (t in templates) {
            val m = match(pose, t) ?: continue
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
