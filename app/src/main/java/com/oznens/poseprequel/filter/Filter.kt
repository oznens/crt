package com.oznens.poseprequel.filter

import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Build
import androidx.annotation.RequiresApi

/**
 * Visual filter applied to the live camera preview.
 *
 * On API 31+ we use [RenderEffect] (GPU, applied to the PreviewView at zero copy cost).
 * Below that we fall back to a [ColorMatrixColorFilter] applied via a software overlay.
 */
data class Filter(
    val id: String,
    val label: String,
    val matrix: FloatArray,
) {
    fun colorMatrix(): ColorMatrix = ColorMatrix(matrix)
    fun colorFilter(): ColorMatrixColorFilter = ColorMatrixColorFilter(colorMatrix())

    @RequiresApi(Build.VERSION_CODES.S)
    fun renderEffect(): RenderEffect =
        RenderEffect.createColorFilterEffect(colorFilter())

    @RequiresApi(Build.VERSION_CODES.S)
    fun renderEffectWith(blurPx: Float): RenderEffect = if (blurPx <= 0f) {
        renderEffect()
    } else {
        RenderEffect.createColorFilterEffect(
            colorFilter(),
            RenderEffect.createBlurEffect(blurPx, blurPx, Shader.TileMode.CLAMP),
        )
    }

    override fun equals(other: Any?) = other is Filter && other.id == id
    override fun hashCode() = id.hashCode()
}

object Filters {

    private val identity = floatArrayOf(
        1f, 0f, 0f, 0f, 0f,
        0f, 1f, 0f, 0f, 0f,
        0f, 0f, 1f, 0f, 0f,
        0f, 0f, 0f, 1f, 0f,
    )

    private val mono = floatArrayOf(
        0.299f, 0.587f, 0.114f, 0f, 0f,
        0.299f, 0.587f, 0.114f, 0f, 0f,
        0.299f, 0.587f, 0.114f, 0f, 0f,
        0f,     0f,     0f,     1f, 0f,
    )

    private val sepia = floatArrayOf(
        0.393f, 0.769f, 0.189f, 0f, 0f,
        0.349f, 0.686f, 0.168f, 0f, 0f,
        0.272f, 0.534f, 0.131f, 0f, 0f,
        0f,     0f,     0f,     1f, 0f,
    )

    // Vintage: lifted blacks, warm midtones, slight cyan in shadows
    private val vintage = floatArrayOf(
        0.9f, 0.05f, 0.05f, 0f, 20f,
        0.05f, 0.85f, 0.10f, 0f, 18f,
        0.05f, 0.10f, 0.75f, 0f, 10f,
        0f,    0f,    0f,    1f, 0f,
    )

    private val cool = floatArrayOf(
        0.85f, 0f,    0.15f, 0f, 0f,
        0f,    0.95f, 0.05f, 0f, 0f,
        0.10f, 0.05f, 1.20f, 0f, 10f,
        0f,    0f,    0f,    1f, 0f,
    )

    private val warm = floatArrayOf(
        1.20f, 0.05f, 0f,    0f, 10f,
        0.05f, 1.05f, 0f,    0f, 5f,
        0f,    0f,    0.85f, 0f, 0f,
        0f,    0f,    0f,    1f, 0f,
    )

    val all: List<Filter> = listOf(
        Filter("orig", "Orijinal", identity),
        Filter("mono", "Mono", mono),
        Filter("sepia", "Sepya", sepia),
        Filter("vintage", "Vintage", vintage),
        Filter("cool", "Soğuk", cool),
        Filter("warm", "Sıcak", warm),
    )

    val default: Filter = all.first()
}
