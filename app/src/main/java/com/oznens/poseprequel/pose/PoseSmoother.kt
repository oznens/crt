package com.oznens.poseprequel.pose

/**
 * Temporal exponential-moving-average smoother over keypoint maps.
 *
 * ML Kit's per-frame pose detection jitters by a few pixels even when the
 * subject is still. Plain frame-to-frame rendering looks robotic. We blend
 * each new keypoint with the previous smoothed value:
 *
 *     out = alpha * new + (1 - alpha) * prev
 *
 * Lower alpha = smoother but laggier. ~0.4 feels natural for selfie use.
 *
 * Landmarks that disappear (drop below confidence) are not carried forward —
 * we clear them so we don't leave ghost limbs frozen on screen.
 */
class PoseSmoother(private val alpha: Float = 0.4f) {

    private val prev = HashMap<Int, Pair<Float, Float>>()

    @Synchronized
    fun update(raw: Map<Int, Pair<Float, Float>>): Map<Int, Pair<Float, Float>> {
        val out = HashMap<Int, Pair<Float, Float>>(raw.size)
        for ((id, p) in raw) {
            val q = prev[id]
            val (nx, ny) = if (q == null) {
                p
            } else {
                Pair(
                    alpha * p.first + (1f - alpha) * q.first,
                    alpha * p.second + (1f - alpha) * q.second,
                )
            }
            out[id] = nx to ny
        }
        prev.clear()
        prev.putAll(out)
        return out
    }

    @Synchronized
    fun reset() {
        prev.clear()
    }
}
