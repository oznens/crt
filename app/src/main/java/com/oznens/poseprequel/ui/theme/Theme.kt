package com.oznens.poseprequel.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Dark = darkColorScheme(
    primary = Color(0xFFFF4D8D),
    secondary = Color(0xFFFFD166),
    background = Color(0xFF050505),
    surface = Color(0xFF101013),
)
private val Light = lightColorScheme(
    primary = Color(0xFFE63971),
    secondary = Color(0xFFE0A800),
)

@Composable
fun PosePrequelTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) Dark else Light
    MaterialTheme(colorScheme = colors, content = content)
}
