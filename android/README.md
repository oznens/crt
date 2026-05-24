# PosePrequel — Android MVP

Prequel benzeri kamera filtreleri + Huawei tarzı AI poz öneri prototipi.
Tek aktivite, Jetpack Compose, CameraX, ML Kit Pose Detection.

> **Not:** Bu klasör, `crt` deposunun içine geçici olarak konuldu çünkü
> bu oturumda yeni bir GitHub reposu açma yetkisi yoktu. Üretken hâle
> getirildiğinde ayrı bir repoya taşımanız tavsiye edilir.

## Mimari

```
app/src/main/java/com/oznens/poseprequel/
├── MainActivity.kt           # tek aktivite, Compose host
├── ui/
│   ├── AppRoot.kt            # tema + kamera izni kapısı
│   ├── CameraScreen.kt       # CameraX preview + UI kontroller
│   ├── PoseOverlay.kt        # Canvas: şablon + tespit edilen iskelet
│   └── theme/Theme.kt
├── filter/
│   └── Filter.kt             # ColorMatrix tabanlı 6 filtre + RenderEffect
└── pose/
    ├── PoseAnalyzer.kt       # CameraX ImageAnalysis -> ML Kit
    ├── PoseTemplate.kt       # şablon veri tipi + scored landmarks/edges
    ├── PoseTemplates.kt      # 4 hazır poz (eller belde, el yukarı, vb.)
    └── PoseSuggester.kt      # normalize + skor (0-100 cosine-style)
```

## Nasıl Çalışıyor

1. **CameraX** önizlemesi `PreviewView` üzerinden çiziliyor.
2. **Filtreler:** API 31+ üzerinde `PreviewView.setRenderEffect(...)` ile
   GPU'da uygulanıyor (zero-copy). Daha eski cihazlarda ColorMatrix
   fallback'i eklemek için TODO bırakıldı.
3. **Poz tespiti:** ML Kit `pose-detection` (bundled model, internetsiz).
   Her frame için en güncel `Pose` üretiliyor (KEEP_ONLY_LATEST).
4. **Poz önerisi (Huawei tarzı):** Ekranda dashed beyaz "ghost" şablon
   görünüyor (`PoseTemplates`), kullanıcının iskeleti pembeyle çiziliyor.
   `PoseSuggester` her frame için:
   - Yüksek güvenli landmark'ları normalize ediyor (görsel boyuta böl).
   - Detected + template hip midpoint'lerini hizalıyor, torso uzunluğuna
     göre ölçek normalize ediyor.
   - Ortalama Euclidean hatayı 0..100 skora çeviriyor.
   - 80+ yeşil, 60+ sarı, altı kırmızı.

## Build

```bash
cd android
# Android Studio Ladybug+ ile aç → Sync → Run.
# Komut satırı için:
./gradlew :app:assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

Wrapper JAR (`gradle/wrapper/gradle-wrapper.jar`) repoda yok — ilk
açılışta Android Studio veya `gradle wrapper` ile üretilir.

## Sürüm Notları

- minSdk 29 — scoped storage sayesinde foto kaydı için ekstra
  izin gerekmiyor (MediaStore Pictures/PosePrequel klasörüne yazar).
- RenderEffect API 31+. Daha düşük sürüm için
  `Filter.colorFilter()` ile bir overlay Compose `Image`'ı çizmek gerek.
  Çekilen foto her cihazda filtreyi alır — RenderEffect sadece preview
  içindir, biz `PhotoSaver` içinde aynı ColorMatrix'i bitmap'e uyguluyoruz.

## Sonraki Adımlar (MVP'den sonra)

- [x] `ImageCapture.takePicture(...)` ile çekim, MediaStore'a kayıt
- [x] Çekim öncesi filtreyi yakalanan bitmap'e de uygula (PreviewView
      RenderEffect sadece preview'da çalışıyor)
- [ ] Daha fazla şablon poz — gerçek görsellerden ML Kit ile keypoint
      çıkartıp `PoseTemplates`'a düşür
- [ ] Şablon önerisi: kullanıcının mevcut pozuna en yakın şablonu
      otomatik seç (`bestMatch` zaten yazıldı, sadece UI'ya bağla)
- [ ] Video kaydı (CameraX VideoCapture)
- [ ] Sticker / metin overlay
- [ ] Vibe / preset kombinasyonları (filtre + poz + müzik)
- [ ] Filtreleri OpenGL ES shader'ları ile yazıp efekt zenginleştirme
      (grain, vignette, halation, chromatic aberration vb.)
