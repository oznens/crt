package com.oznens.poseprequel.pose

import com.google.mlkit.vision.pose.PoseLandmark

/**
 * Hand-tuned pose templates in normalized image space (portrait 9:16-ish, 0..1).
 *
 * These are starter values — in production you'd capture real poses and
 * cluster them into a library. Coordinates are designed for a person framed
 * roughly center, head near y=0.15, feet near y=0.95.
 */
object PoseTemplates {

    private fun pt(x: Float, y: Float) = Pair(x, y)

    /** Hands on hips, slight contrapposto. */
    val HANDS_ON_HIPS = PoseTemplate(
        id = "hands_hips",
        label = "Elleri Belde",
        points = mapOf(
            PoseLandmark.NOSE to pt(0.50f, 0.18f),
            PoseLandmark.LEFT_SHOULDER to pt(0.40f, 0.30f),
            PoseLandmark.RIGHT_SHOULDER to pt(0.60f, 0.30f),
            PoseLandmark.LEFT_ELBOW to pt(0.30f, 0.45f),
            PoseLandmark.RIGHT_ELBOW to pt(0.70f, 0.45f),
            PoseLandmark.LEFT_WRIST to pt(0.40f, 0.52f),
            PoseLandmark.RIGHT_WRIST to pt(0.60f, 0.52f),
            PoseLandmark.LEFT_HIP to pt(0.42f, 0.55f),
            PoseLandmark.RIGHT_HIP to pt(0.58f, 0.55f),
            PoseLandmark.LEFT_KNEE to pt(0.42f, 0.75f),
            PoseLandmark.RIGHT_KNEE to pt(0.58f, 0.75f),
            PoseLandmark.LEFT_ANKLE to pt(0.42f, 0.93f),
            PoseLandmark.RIGHT_ANKLE to pt(0.58f, 0.93f),
        ),
    )

    /** One hand raised in greeting / "peace". */
    val ONE_HAND_UP = PoseTemplate(
        id = "one_hand_up",
        label = "Bir El Yukarıda",
        points = mapOf(
            PoseLandmark.NOSE to pt(0.50f, 0.18f),
            PoseLandmark.LEFT_SHOULDER to pt(0.40f, 0.30f),
            PoseLandmark.RIGHT_SHOULDER to pt(0.60f, 0.30f),
            PoseLandmark.LEFT_ELBOW to pt(0.32f, 0.45f),
            PoseLandmark.RIGHT_ELBOW to pt(0.65f, 0.18f),
            PoseLandmark.LEFT_WRIST to pt(0.30f, 0.58f),
            PoseLandmark.RIGHT_WRIST to pt(0.68f, 0.05f),
            PoseLandmark.LEFT_HIP to pt(0.43f, 0.55f),
            PoseLandmark.RIGHT_HIP to pt(0.57f, 0.55f),
            PoseLandmark.LEFT_KNEE to pt(0.43f, 0.75f),
            PoseLandmark.RIGHT_KNEE to pt(0.57f, 0.75f),
            PoseLandmark.LEFT_ANKLE to pt(0.43f, 0.93f),
            PoseLandmark.RIGHT_ANKLE to pt(0.57f, 0.93f),
        ),
    )

    /** Arms crossed, confident stance. */
    val ARMS_CROSSED = PoseTemplate(
        id = "arms_crossed",
        label = "Kollar Kavuşuk",
        points = mapOf(
            PoseLandmark.NOSE to pt(0.50f, 0.18f),
            PoseLandmark.LEFT_SHOULDER to pt(0.40f, 0.32f),
            PoseLandmark.RIGHT_SHOULDER to pt(0.60f, 0.32f),
            PoseLandmark.LEFT_ELBOW to pt(0.35f, 0.48f),
            PoseLandmark.RIGHT_ELBOW to pt(0.65f, 0.48f),
            PoseLandmark.LEFT_WRIST to pt(0.55f, 0.42f),
            PoseLandmark.RIGHT_WRIST to pt(0.45f, 0.42f),
            PoseLandmark.LEFT_HIP to pt(0.43f, 0.58f),
            PoseLandmark.RIGHT_HIP to pt(0.57f, 0.58f),
            PoseLandmark.LEFT_KNEE to pt(0.43f, 0.77f),
            PoseLandmark.RIGHT_KNEE to pt(0.57f, 0.77f),
            PoseLandmark.LEFT_ANKLE to pt(0.43f, 0.94f),
            PoseLandmark.RIGHT_ANKLE to pt(0.57f, 0.94f),
        ),
    )

    /** Looking over shoulder, three-quarter turn. */
    val OVER_SHOULDER = PoseTemplate(
        id = "over_shoulder",
        label = "Omuz Üstünden",
        points = mapOf(
            PoseLandmark.NOSE to pt(0.45f, 0.20f),
            PoseLandmark.LEFT_SHOULDER to pt(0.38f, 0.32f),
            PoseLandmark.RIGHT_SHOULDER to pt(0.55f, 0.30f),
            PoseLandmark.LEFT_ELBOW to pt(0.36f, 0.50f),
            PoseLandmark.RIGHT_ELBOW to pt(0.58f, 0.50f),
            PoseLandmark.LEFT_WRIST to pt(0.34f, 0.65f),
            PoseLandmark.RIGHT_WRIST to pt(0.60f, 0.65f),
            PoseLandmark.LEFT_HIP to pt(0.42f, 0.60f),
            PoseLandmark.RIGHT_HIP to pt(0.56f, 0.60f),
            PoseLandmark.LEFT_KNEE to pt(0.42f, 0.78f),
            PoseLandmark.RIGHT_KNEE to pt(0.56f, 0.78f),
            PoseLandmark.LEFT_ANKLE to pt(0.42f, 0.94f),
            PoseLandmark.RIGHT_ANKLE to pt(0.56f, 0.94f),
        ),
    )

    val ALL: List<PoseTemplate> = listOf(
        HANDS_ON_HIPS,
        ONE_HAND_UP,
        ARMS_CROSSED,
        OVER_SHOULDER,
    )
}
