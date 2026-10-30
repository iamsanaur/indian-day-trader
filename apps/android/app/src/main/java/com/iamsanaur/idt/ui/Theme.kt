package com.iamsanaur.idt.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/** Design tokens shared with the web and iOS apps (clean light, dark optional). */
@Immutable
data class Palette(
    val bg: Color, val surface: Color, val surface2: Color, val border: Color,
    val text: Color, val text2: Color, val muted: Color,
    val accent: Color, val accentSoft: Color,
    val up: Color, val upMark: Color, val upSoft: Color,
    val down: Color, val downMark: Color, val downSoft: Color,
    val warn: Color, val warnSoft: Color,
    val series1: Color, val series2: Color, val series3: Color,
)

val LightPalette = Palette(
    bg = Color(0xFFF6F7F9), surface = Color.White, surface2 = Color(0xFFF1F3F6), border = Color(0xFFE6E8EC),
    text = Color(0xFF0F172A), text2 = Color(0xFF475569), muted = Color(0xFF8A94A6),
    accent = Color(0xFF4F46E5), accentSoft = Color(0xFFEEF0FF),
    up = Color(0xFF0B7A45), upMark = Color(0xFF12925B), upSoft = Color(0xFFE7F6EE),
    down = Color(0xFFC62F2F), downMark = Color(0xFFD03B3B), downSoft = Color(0xFFFDECEC),
    warn = Color(0xFF9A6200), warnSoft = Color(0xFFFFF4DC),
    series1 = Color(0xFF2A78D6), series2 = Color(0xFFEB6834), series3 = Color(0xFF6250D6),
)

val DarkPalette = Palette(
    bg = Color(0xFF0F1115), surface = Color(0xFF171A21), surface2 = Color(0xFF1E222B), border = Color(0xFF262A33),
    text = Color(0xFFE7E9EE), text2 = Color(0xFFA3AAB8), muted = Color(0xFF6F7787),
    accent = Color(0xFF818CF8), accentSoft = Color(0xFF23264A),
    up = Color(0xFF3CCB84), upMark = Color(0xFF2FB874), upSoft = Color(0xFF12261C),
    down = Color(0xFFF37272), downMark = Color(0xFFE66767), downSoft = Color(0xFF2C1617),
    warn = Color(0xFFF0B74A), warnSoft = Color(0xFF2B2312),
    series1 = Color(0xFF3987E5), series2 = Color(0xFFD95926), series3 = Color(0xFF9085E9),
)

val LocalPalette = staticCompositionLocalOf { LightPalette }

enum class Tone { Up, Down, Warn, Accent, Neutral;
    companion object { fun of(v: Double?) = if (v == null || v == 0.0) Neutral else if (v > 0) Up else Down }
}

@Composable
fun Tone.fg(): Color = LocalPalette.current.let { p ->
    when (this) { Tone.Up -> p.up; Tone.Down -> p.down; Tone.Warn -> p.warn; Tone.Accent -> p.accent; Tone.Neutral -> p.text2 }
}

@Composable
fun Tone.bg(): Color = LocalPalette.current.let { p ->
    when (this) { Tone.Up -> p.upSoft; Tone.Down -> p.downSoft; Tone.Warn -> p.warnSoft; Tone.Accent -> p.accentSoft; Tone.Neutral -> p.surface2 }
}

@Composable
fun IdtTheme(theme: String, content: @Composable () -> Unit) {
    val dark = when (theme) { "light" -> false; "dark" -> true; else -> isSystemInDarkTheme() }
    val p = if (dark) DarkPalette else LightPalette
    val scheme = (if (dark) darkColorScheme() else lightColorScheme()).copy(
        primary = p.accent, onPrimary = if (dark) p.bg else Color.White, background = p.bg, surface = p.surface,
        surfaceContainer = p.surface, surfaceVariant = p.surface2, onSurface = p.text, onSurfaceVariant = p.text2,
        outline = p.border, outlineVariant = p.border, secondaryContainer = p.accentSoft, onSecondaryContainer = p.accent,
        error = p.down,
    )
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
