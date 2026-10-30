package com.iamsanaur.idt.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Fmt
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

data class CandleBar(val o: Double, val h: Double, val l: Double, val c: Double)
data class Level(val price: Double, val label: String, val color: Color, val dash: Boolean = true)

private fun DrawScope.label(tm: TextMeasurer, text: String, at: Offset, color: Color, bg: Color? = null) {
    val layout = tm.measure(text, TextStyle(fontSize = 10.sp, color = color))
    val pos = Offset(min(at.x, size.width - layout.size.width - 2f), at.y - layout.size.height / 2f)
    if (bg != null) drawRoundRect(bg, pos - Offset(3f, 1f), Size(layout.size.width + 6f, layout.size.height + 2f), CornerRadius(4f))
    drawText(layout, topLeft = pos)
}

/** Candles + overlays + level lines. X is the bar index so overnight gaps collapse. Drag to inspect. */
@Composable
fun CandleChart(candles: List<CandleBar>, overlays: List<Pair<List<Double?>, Color>>, levels: List<Level>, height: Dp = 300.dp) {
    val p = LocalPalette.current
    val tm = rememberTextMeasurer()
    var sel by remember { mutableStateOf<Int?>(null) }
    if (candles.isEmpty()) return
    val lo = (candles.minOf { it.l }).let { l -> min(l, levels.minOfOrNull { it.price } ?: l) }
    val hi = (candles.maxOf { it.h }).let { h -> max(h, levels.maxOfOrNull { it.price } ?: h) }
    val pad = (hi - lo) * 0.04
    Box(Modifier.fillMaxWidth().height(height).semantics { contentDescription = "Candlestick chart" }) {
        Canvas(Modifier.fillMaxWidth().height(height).pointerInput(candles) {
            detectDragGestures(onDragEnd = { sel = null }) { ch, _ -> sel = ((ch.position.x / (size.width - 56.dp.toPx())) * candles.size).toInt().coerceIn(0, candles.size - 1) }
        }) {
            val right = 56.dp.toPx()
            val w = size.width - right
            val y = { v: Double -> ((hi + pad - v) / (hi - lo + 2 * pad) * size.height).toFloat() }
            val step = w / candles.size
            for (t in 0..4) {
                val v = lo - pad + (hi - lo + 2 * pad) * t / 4
                drawLine(p.border, Offset(0f, y(v)), Offset(w, y(v)), 1f)
                label(tm, Fmt.num(v, 0), Offset(w + 6f, y(v)), p.muted)
            }
            candles.forEachIndexed { i, k ->
                val cx = step * i + step / 2
                val col = if (k.c >= k.o) p.upMark else p.downMark
                drawLine(col, Offset(cx, y(k.h)), Offset(cx, y(k.l)), 1.5f)
                val top = y(max(k.o, k.c)); val bot = y(min(k.o, k.c))
                drawRect(col, Offset(cx - step * 0.35f, top), Size(step * 0.7f, max(bot - top, 1.5f)))
            }
            overlays.forEach { (vals, color) ->
                val path = Path(); var started = false
                vals.forEachIndexed { i, v -> if (v != null) { val pt = Offset(step * i + step / 2, y(v)); if (!started) { path.moveTo(pt.x, pt.y); started = true } else path.lineTo(pt.x, pt.y) } }
                drawPath(path, color, style = Stroke(width = 2.5f))
            }
            levels.forEach { lv ->
                drawLine(lv.color, Offset(0f, y(lv.price)), Offset(w, y(lv.price)), 1.5f,
                    pathEffect = if (lv.dash) PathEffect.dashPathEffect(floatArrayOf(10f, 8f)) else null)
                label(tm, lv.label, Offset(4f, y(lv.price) - 14f), lv.color, p.surface)
            }
            sel?.let { i ->
                val k = candles[i]; val cx = step * i + step / 2
                drawLine(p.muted, Offset(cx, 0f), Offset(cx, size.height), 1f)
                label(tm, "O ${Fmt.num(k.o)}  H ${Fmt.num(k.h)}  L ${Fmt.num(k.l)}  C ${Fmt.num(k.c)}", Offset(8f, 12f), p.text, p.surface)
            }
        }
    }
}

/** Calls vs puts by strike, side by side, with an ATM marker. */
@Composable
fun OIChart(strikes: List<Double>, calls: List<Double>, puts: List<Double>, atm: Double, height: Dp = 220.dp) {
    val p = LocalPalette.current
    val tm = rememberTextMeasurer()
    var sel by remember { mutableStateOf<Int?>(null) }
    if (strikes.isEmpty()) return
    val lo = min(0.0, (calls + puts).min()); val hi = max(0.0, (calls + puts).max()).takeIf { it > lo } ?: 1.0
    Canvas(Modifier.fillMaxWidth().height(height).semantics { contentDescription = "Open interest by strike" }
        .pointerInput(strikes) { detectTapGestures { o -> sel = ((o.x / size.width) * strikes.size).toInt().coerceIn(0, strikes.size - 1) } }) {
        val bottom = size.height - 18.dp.toPx()
        val y = { v: Double -> ((hi - v) / (hi - lo) * (bottom - 8f) + 8f).toFloat() }
        val band = size.width / strikes.size
        val bw = max(2f, band / 2 - 2f)
        drawLine(p.border, Offset(0f, y(0.0)), Offset(size.width, y(0.0)), 1f)
        strikes.forEachIndexed { i, s ->
            val x = band * i + band / 2
            val alpha = if (sel == null || sel == i) 1f else 0.4f
            listOf(calls[i] to (x - bw - 1f) to p.series1, puts[i] to (x + 1f) to p.series2).forEach { (vx, col) ->
                val (v, left) = vx
                val top = min(y(v), y(0.0)); val h = max(abs(y(v) - y(0.0)), 1f)
                drawRoundRect(col.copy(alpha = alpha), Offset(left, top), Size(bw, h), CornerRadius(3f))
            }
            if (i % max(1, strikes.size / 5) == 0) label(tm, Fmt.num(s, 0), Offset(x - 18f, size.height - 8.dp.toPx()), p.muted)
            if (s == atm) {
                drawLine(p.text2, Offset(x, 0f), Offset(x, bottom), 1.5f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 6f)))
                label(tm, "ATM", Offset(x + 4f, 10f), p.text2, p.surface)
            }
        }
        sel?.let { i ->
            label(tm, "${Fmt.num(strikes[i], 0)}  Call ${Fmt.compact(calls[i])}  Put ${Fmt.compact(puts[i])}", Offset(8f, 26f), p.text, p.surface)
        }
    }
}

/** Strategy P/L at expiry (solid) and today (dashed). Drag to inspect. */
@Composable
fun PayoffChart(x: List<Double>, expiry: List<Double>, today: List<Double>, spot: Double, breakevens: List<Double>, height: Dp = 240.dp) {
    val p = LocalPalette.current
    val tm = rememberTextMeasurer()
    var sel by remember { mutableStateOf<Int?>(null) }
    if (x.size < 2) return
    val all = expiry + today + 0.0
    val lo = all.min(); val hi = all.max(); val pad = (hi - lo) * 0.08 + 1
    Canvas(Modifier.fillMaxWidth().height(height).semantics { contentDescription = "Strategy payoff" }
        .pointerInput(x) { detectDragGestures(onDragEnd = { sel = null }) { ch, _ -> sel = ((ch.position.x / size.width) * x.size).toInt().coerceIn(0, x.size - 1) } }) {
        val bottom = size.height - 18.dp.toPx()
        val sx = { v: Double -> ((v - x.first()) / (x.last() - x.first()) * size.width).toFloat() }
        val sy = { v: Double -> ((hi + pad - v) / (hi - lo + 2 * pad) * bottom).toFloat() }
        val zero = sy(0.0)
        // profit / loss fills
        listOf(true, false).forEach { profit ->
            val path = Path().apply {
                moveTo(sx(x.first()), zero)
                x.indices.forEach { i -> lineTo(sx(x[i]), sy(if (profit) max(expiry[i], 0.0) else min(expiry[i], 0.0))) }
                lineTo(sx(x.last()), zero); close()
            }
            drawPath(path, if (profit) p.upSoft else p.downSoft)
        }
        drawLine(p.border, Offset(0f, zero), Offset(size.width, zero), 2f)
        fun line(vals: List<Double>, color: Color, dashed: Boolean) {
            val path = Path(); vals.forEachIndexed { i, v -> if (i == 0) path.moveTo(sx(x[i]), sy(v)) else path.lineTo(sx(x[i]), sy(v)) }
            drawPath(path, color, style = Stroke(width = 4f, pathEffect = if (dashed) PathEffect.dashPathEffect(floatArrayOf(14f, 10f)) else null))
        }
        line(today, p.series1, true)
        line(expiry, p.text, false)
        drawLine(p.text2, Offset(sx(spot), 0f), Offset(sx(spot), bottom), 1.5f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 6f)))
        label(tm, "Spot ${Fmt.num(spot, 0)}", Offset(sx(spot) + 6f, 10f), p.text2, p.surface)
        breakevens.filter { it in x.first()..x.last() }.forEach { b ->
            drawCircle(p.surface, 9f, Offset(sx(b), zero)); drawCircle(p.warn, 9f, Offset(sx(b), zero), style = Stroke(4f))
            label(tm, "BE ${Fmt.num(b, 0)}", Offset(sx(b) - 30f, zero + 24f), p.warn)
        }
        for (t in 0..4) { val v = x.first() + (x.last() - x.first()) * t / 4; label(tm, Fmt.num(v, 0), Offset(sx(v) - (if (t == 4) 60f else if (t == 0) 0f else 30f), size.height - 8.dp.toPx()), p.muted) }
        listOf(hi, lo).forEach { v -> label(tm, Fmt.signedRupees(v), Offset(4f, sy(v) + 8f), p.muted) }
        sel?.let { i ->
            drawLine(p.muted, Offset(sx(x[i]), 0f), Offset(sx(x[i]), bottom), 1f)
            label(tm, "${Fmt.num(x[i], 0)} · expiry ${Fmt.signedRupees(expiry[i])} · today ${Fmt.signedRupees(today[i])}", Offset(8f, 30f), p.text, p.surface)
        }
    }
}

/** Target / open at square-off / stop probabilities as a segmented bar with 2px gaps. */
@Composable
fun ProbBar(target: Double, flat: Double, stop: Double) {
    val p = LocalPalette.current
    Canvas(Modifier.fillMaxWidth().height(14.dp).semantics { contentDescription = "Target ${(target * 100).toInt()}%, stop ${(stop * 100).toInt()}%" }) {
        var x = 0f
        val gap = 2.dp.toPx()
        val usable = size.width - 2 * gap
        listOf(target to p.upMark, flat to p.muted, stop to p.downMark).forEach { (v, c) ->
            val w = (usable * v).toFloat()
            drawRoundRect(c, Offset(x, 0f), Size(w, size.height), CornerRadius(4f))
            x += w + gap
        }
    }
}
