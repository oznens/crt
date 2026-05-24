package com.oznens.poseprequel.pose

import com.google.mlkit.vision.pose.PoseLandmark

/**
 * A reference pose, defined in *normalized* image space (0..1, top-left origin).
 * We only store the keypoints that we score against — head/torso/limb tips.
 */
data class PoseTemplate(
    val id: String,
    val label: String,
    /** Map of MLKit landmark type -> (x, y) in normalized image space. */
    val points: Map<Int, Pair<Float, Float>>,
) {
    val landmarkIds: Set<Int> get() = points.keys

    /**
     * Returns the template scaled around the frame center and shifted in y.
     * Used to shrink the full-body template into a selfie-framed silhouette
     * for the front camera, where the user typically appears from the waist
     * up rather than head-to-toe.
     */
    fun scaledAndShifted(scale: Float, offsetY: Float): PoseTemplate = copy(
        points = points.mapValues { (_, p) ->
            val nx = 0.5f + (p.first - 0.5f) * scale
            val ny = 0.5f + (p.second - 0.5f) * scale + offsetY
            nx to ny
        },
    )

    companion object {
        // Keypoints we care about across every template.
        val SCORED_LANDMARKS = listOf(
            PoseLandmark.NOSE,
            PoseLandmark.LEFT_SHOULDER,
            PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_ELBOW,
            PoseLandmark.RIGHT_ELBOW,
            PoseLandmark.LEFT_WRIST,
            PoseLandmark.RIGHT_WRIST,
            PoseLandmark.LEFT_HIP,
            PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_KNEE,
            PoseLandmark.RIGHT_KNEE,
            PoseLandmark.LEFT_ANKLE,
            PoseLandmark.RIGHT_ANKLE,
        )

        val EDGES = listOf(
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.LEFT_ELBOW,
            PoseLandmark.LEFT_ELBOW to PoseLandmark.LEFT_WRIST,
            PoseLandmark.RIGHT_SHOULDER to PoseLandmark.RIGHT_ELBOW,
            PoseLandmark.RIGHT_ELBOW to PoseLandmark.RIGHT_WRIST,
            PoseLandmark.LEFT_SHOULDER to PoseLandmark.LEFT_HIP,
            PoseLandmark.RIGHT_SHOULDER to PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_HIP to PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_HIP to PoseLandmark.LEFT_KNEE,
            PoseLandmark.LEFT_KNEE to PoseLandmark.LEFT_ANKLE,
            PoseLandmark.RIGHT_HIP to PoseLandmark.RIGHT_KNEE,
            PoseLandmark.RIGHT_KNEE to PoseLandmark.RIGHT_ANKLE,
        )
    }
}
