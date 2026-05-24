package com.oznens.poseprequel.ui

import android.os.Build
import android.view.ViewGroup
import android.widget.Toast
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.oznens.poseprequel.capture.PhotoSaver
import com.oznens.poseprequel.filter.Filter
import com.oznens.poseprequel.filter.Filters
import com.oznens.poseprequel.pose.PoseAnalyzer
import com.oznens.poseprequel.pose.PoseSmoother
import com.oznens.poseprequel.pose.PoseSuggester
import com.oznens.poseprequel.pose.PoseTemplate
import com.oznens.poseprequel.pose.PoseTemplates
import kotlinx.coroutines.delay
import java.util.concurrent.Executors

@Composable
fun CameraScreen() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val analysisExecutor = remember { Executors.newSingleThreadExecutor() }
    val captureExecutor = remember { Executors.newSingleThreadExecutor() }
    val suggester = remember { PoseSuggester() }
    val smoother = remember { PoseSmoother(alpha = 0.4f) }

    var filter by remember { mutableStateOf(Filters.default) }
    var template by remember { mutableStateOf<PoseTemplate>(PoseTemplates.ALL.first()) }
    var score by remember { mutableStateOf(0) }
    var detectedPoints by remember { mutableStateOf<Map<Int, Pair<Float, Float>>>(emptyMap()) }
    var imageAspect by remember { mutableStateOf(0.75f) }  // 4:3 portrait default
    var lensFront by remember { mutableStateOf(true) }
    var previewViewRef by remember { mutableStateOf<PreviewView?>(null) }
    var imageCapture by remember { mutableStateOf<ImageCapture?>(null) }
    var isCapturing by remember { mutableStateOf(false) }
    var flashOn by remember { mutableStateOf(false) }

    // When the lens flips, drop the EMA buffer so the skeleton doesn't snap
    // from one mirrored position to the other.
    LaunchedEffect(lensFront) { smoother.reset() }

    // The front camera frames the user from the waist up; the full-body
    // template would tower past the screen edges. Shrink + shift it up so
    // it fits the selfie framing. Back camera uses the full-body template.
    val displayedTemplate = remember(template, lensFront) {
        if (lensFront) template.scaledAndShifted(scale = 0.60f, offsetY = -0.08f)
        else template
    }
    // Captured by reference so the analyzer's long-lived closure always sees
    // the latest template when the user taps a different pose.
    val currentTemplate by rememberUpdatedState(displayedTemplate)

    // Re-apply RenderEffect whenever the filter changes (API 31+).
    LaunchedEffect(filter, previewViewRef) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            previewViewRef?.setRenderEffect(filter.renderEffect())
        }
    }

    // Fade the white flash overlay off shortly after a shot.
    LaunchedEffect(flashOn) {
        if (flashOn) {
            delay(80)
            flashOn = false
        }
    }
    val flashAlpha by animateFloatAsState(
        targetValue = if (flashOn) 0.9f else 0f,
        animationSpec = tween(durationMillis = 180),
        label = "flash",
    )

    DisposableEffect(Unit) {
        onDispose {
            analysisExecutor.shutdown()
            captureExecutor.shutdown()
        }
    }

    Box(modifier = Modifier.fillMaxSize().background(Color.Black)) {

        // 1) Live camera preview
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                PreviewView(ctx).apply {
                    layoutParams = ViewGroup.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT,
                    )
                    scaleType = PreviewView.ScaleType.FILL_CENTER
                    implementationMode = PreviewView.ImplementationMode.COMPATIBLE
                    previewViewRef = this
                }
            },
        )

        // 2) Bind CameraX whenever lens changes
        LaunchedEffect(lensFront, previewViewRef) {
            val view = previewViewRef ?: return@LaunchedEffect
            val providerFuture = ProcessCameraProvider.getInstance(context)
            providerFuture.addListener({
                val provider = providerFuture.get()
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(view.surfaceProvider)
                }
                val analyzer = PoseAnalyzer { pose, w, h ->
                    if (w > 0 && h > 0) imageAspect = w.toFloat() / h.toFloat()
                    // Build a normalized point map in *view-aligned* image space:
                    // mirror x for the front camera so right-hand-up in the
                    // mirrored preview lines up with the template's right-hand.
                    val raw = HashMap<Int, Pair<Float, Float>>()
                    for (lm in pose.allPoseLandmarks) {
                        if (lm.inFrameLikelihood < 0.5f) continue
                        val nx0 = lm.position.x / w
                        val ny = lm.position.y / h
                        val nx = if (lensFront) 1f - nx0 else nx0
                        raw[lm.landmarkType] = nx to ny
                    }
                    val smoothed = smoother.update(raw)
                    detectedPoints = smoothed
                    score = suggester.matchPoints(smoothed, currentTemplate)?.score ?: 0
                }
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                    .also { it.setAnalyzer(analysisExecutor, analyzer) }
                val capture = ImageCapture.Builder()
                    .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                    .build()
                val selector = if (lensFront) CameraSelector.DEFAULT_FRONT_CAMERA
                else CameraSelector.DEFAULT_BACK_CAMERA

                runCatching {
                    provider.unbindAll()
                    provider.bindToLifecycle(
                        lifecycleOwner, selector, preview, analysis, capture,
                    )
                    imageCapture = capture
                }
            }, ContextCompat.getMainExecutor(context))
        }

        // 3) Pose template silhouette + faint live skeleton
        PoseOverlay(
            template = displayedTemplate,
            detected = detectedPoints,
            imageAspect = imageAspect,
            modifier = Modifier.fillMaxSize(),
        )

        // 4) Top HUD: score + active template
        ScoreHud(
            templateLabel = template.label,
            score = score,
            modifier = Modifier.align(Alignment.TopCenter).padding(top = 48.dp),
        )

        // 5) Bottom controls: pose chooser + filter strip + shutter
        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            PoseStrip(
                templates = PoseTemplates.ALL,
                selected = template,
                onSelect = { template = it },
            )
            FilterStrip(
                filters = Filters.all,
                selected = filter,
                onSelect = { filter = it },
            )
            ShutterRow(
                enabled = imageCapture != null && !isCapturing,
                onFlip = { lensFront = !lensFront },
                onCapture = {
                    val capture = imageCapture ?: return@ShutterRow
                    isCapturing = true
                    flashOn = true
                    PhotoSaver.capture(
                        imageCapture = capture,
                        executor = captureExecutor,
                        filter = filter,
                        contentResolver = context.contentResolver,
                    ) { result ->
                        ContextCompat.getMainExecutor(context).execute {
                            isCapturing = false
                            val msg = result.fold(
                                onSuccess = { "Kaydedildi: Pictures/PosePrequel" },
                                onFailure = { "Çekim başarısız: ${it.message}" },
                            )
                            Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
                        }
                    }
                },
            )
        }

        // 6) White flash overlay on top of everything during capture
        if (flashAlpha > 0f) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.White.copy(alpha = flashAlpha)),
            )
        }
    }
}

@Composable
private fun ScoreHud(templateLabel: String, score: Int, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(20.dp),
        color = Color(0xCC000000),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(templateLabel, color = Color.White, fontSize = 12.sp)
            Text("$score%", color = scoreColor(score), fontSize = 22.sp)
        }
    }
}

private fun scoreColor(score: Int): Color = when {
    score >= 80 -> Color(0xFF4CFFA1)
    score >= 60 -> Color(0xFFFFD166)
    else        -> Color(0xFFFF6B6B)
}

@Composable
private fun PoseStrip(
    templates: List<PoseTemplate>,
    selected: PoseTemplate,
    onSelect: (PoseTemplate) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        templates.forEach { t ->
            val isOn = t.id == selected.id
            Button(
                onClick = { onSelect(t) },
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isOn) Color(0xFFFF4D8D) else Color(0x66000000),
                    contentColor = Color.White,
                ),
            ) { Text(t.label, fontSize = 11.sp) }
        }
    }
}

@Composable
private fun FilterStrip(
    filters: List<Filter>,
    selected: Filter,
    onSelect: (Filter) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
            .height(40.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        filters.forEach { f ->
            val isOn = f.id == selected.id
            Button(
                onClick = { onSelect(f) },
                shape = RectangleShape,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isOn) Color.White else Color(0x66000000),
                    contentColor = if (isOn) Color.Black else Color.White,
                ),
            ) { Text(f.label, fontSize = 11.sp) }
        }
    }
}

@Composable
private fun ShutterRow(
    enabled: Boolean,
    onFlip: () -> Unit,
    onCapture: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 32.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Spacer(modifier = Modifier.size(56.dp))
        Surface(
            modifier = Modifier.size(72.dp),
            shape = CircleShape,
            color = if (enabled) Color.White else Color(0xFFBBBBBB),
            onClick = { if (enabled) onCapture() },
        ) {}
        Button(
            onClick = onFlip,
            shape = CircleShape,
            modifier = Modifier.size(56.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Color(0x66000000)),
        ) { Text("⟲", color = Color.White, fontSize = 20.sp) }
    }
}
