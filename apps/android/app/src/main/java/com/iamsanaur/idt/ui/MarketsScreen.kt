package com.iamsanaur.idt.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Fmt
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.d
import com.iamsanaur.idt.doubles
import com.iamsanaur.idt.jsonOf
import com.iamsanaur.idt.o
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import kotlinx.coroutines.launch
import org.json.JSONObject

val INDEX_NAMES = mapOf(
    "NIFTY" to "Nifty 50", "BANKNIFTY" to "Nifty Bank", "FINNIFTY" to "Nifty Financial",
    "MIDCPNIFTY" to "Nifty Midcap Select", "SENSEX" to "BSE Sensex", "INDIAVIX" to "India VIX",
)

@Composable
fun ModeBadges() {
    val s = LocalApp.current.status ?: return
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Pill(s.optString("mode"), if (s.optString("mode") == "paper") Tone.Warn else Tone.Accent)
        if (s.optBoolean("demo")) Pill("demo")
    }
}

@Composable
fun MarketsScreen(open: (String) -> Unit) {
    val app = LocalApp.current
    val board = rememberLoad<JSONObject>()
    val dhanConnected = app.status?.optJSONObject("dhan")?.optBoolean("connected")
    LaunchedEffect(app.conn, dhanConnected) { app.refreshStatus(); board.run { app.api.obj("/indices") } }
    Screen("Markets", actions = { ModeBadges() }) {
        item { DhanBanner() }
        item { ErrorBox(board.error) }
        board.value?.o("indices")?.let { idx ->
            INDEX_NAMES.keys.filter { idx.has(it) }.forEach { sym ->
                item(sym) { IndexCard(sym, idx.getJSONObject(sym)) { open(sym) } }
            }
        }
        if (board.value == null && board.loading) item { Box(Modifier.fillMaxWidth().height(170.dp).clip(RoundedCornerShape(16.dp)).background(LocalPalette.current.surface2)) }
    }
}

@Composable
fun IndexCard(sym: String, e: JSONObject, onClick: () -> Unit) {
    val p = LocalPalette.current
    Box(Modifier.clip(RoundedCornerShape(16.dp)).clickable(onClick = onClick)) {
        Card {
            if (e.s("error") != null) {
                Text(sym, fontWeight = FontWeight.Bold); ErrorBox(e.s("error")); return@Card
            }
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(sym, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = p.text)
                    Text(INDEX_NAMES[sym].orEmpty(), fontSize = 12.sp, color = p.muted)
                }
                Pill(Fmt.pct(e.d("change_pct")), Tone.of(e.d("change_pct")))
            }
            Text(Fmt.num(e.d("last")), fontSize = 30.sp, fontWeight = FontWeight.Bold, color = p.text)
            e.o("day")?.let { DayRange(it.optDouble("low"), it.optDouble("high"), e.optDouble("last")) }
            if (sym != "INDIAVIX") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OrbPill(e.o("orb")?.s("state"), e.o("orb")?.s("side"))
                    TrendPill(e.o("ema")?.s("trend"))
                }
            } else {
                Text("Implied volatility gauge — higher means richer option premiums.", fontSize = 12.sp, color = p.text2)
            }
        }
    }
}

@Composable
fun DayRange(low: Double, high: Double, last: Double) {
    val p = LocalPalette.current
    var width by remember { mutableIntStateOf(0) }
    val frac = ((last - low) / (high - low).coerceAtLeast(0.0001)).coerceIn(0.0, 1.0)
    val dx = with(LocalDensity.current) { (width * frac).toFloat().toDp() - 6.dp }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.fillMaxWidth().height(12.dp).onSizeChanged { width = it.width }, contentAlignment = Alignment.CenterStart) {
            Box(Modifier.fillMaxWidth().height(6.dp).clip(CircleShape).background(p.surface2))
            Box(Modifier.offset(x = dx).size(12.dp).clip(CircleShape).background(p.text))
        }
        Row {
            Text("L ${Fmt.num(low)}", fontSize = 12.sp, color = p.muted, modifier = Modifier.weight(1f))
            Text("H ${Fmt.num(high)}", fontSize = 12.sp, color = p.muted)
        }
    }
}

@Composable
fun IndexDetailScreen(symbol: String, onPlan: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var interval by remember { mutableIntStateOf(5) }
    var days by remember { mutableIntStateOf(2) }
    var future by remember { mutableStateOf(false) }
    var planError by remember { mutableStateOf<String?>(null) }
    val view = rememberLoad<JSONObject>()
    LaunchedEffect(interval, days, future) { view.run { app.api.obj("/index/$symbol?interval=$interval&days=$days&future=$future") } }

    Screen(if (future) "$symbol FUT" else symbol) {
        item { Segmented(interval, listOf(1 to "1m", 5 to "5m", 15 to "15m"), { interval = it }) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Segmented(days, listOf(1 to "1D", 2 to "2D", 5 to "5D"), { days = it }, Modifier.weight(1f))
                if (symbol != "INDIAVIX") Segmented(future, listOf(false to "Spot", true to "Future"), { future = it }, Modifier.weight(1f))
            }
        }
        item { ErrorBox(view.error ?: planError) }
        val v = view.value ?: return@Screen
        item {
            Card {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(Fmt.num(v.d("last")), fontSize = 26.sp, fontWeight = FontWeight.Bold, color = p.text)
                    Text("  ${Fmt.pct(v.d("change_pct"))}", color = Tone.of(v.d("change_pct")).fg(), fontWeight = FontWeight.SemiBold)
                    Text("${Fmt.time(v.s("as_of"))} IST", color = p.muted, fontSize = 12.sp, modifier = Modifier.weight(1f).padding(start = 8.dp))
                }
                val candles = v.getJSONArray("candles").objects().map { CandleBar(it.getDouble("o"), it.getDouble("h"), it.getDouble("l"), it.getDouble("c")) }
                val series = v.getJSONObject("series")
                val levels = buildList {
                    v.o("opening_range")?.let { add(Level(it.getDouble("high"), "OR H", p.accent)); add(Level(it.getDouble("low"), "OR L", p.accent)) }
                    v.o("prev_day")?.let { add(Level(it.getDouble("high"), "PDH", p.muted)); add(Level(it.getDouble("low"), "PDL", p.muted)) }
                }
                CandleChart(candles, listOf(series.getJSONArray("ema9").doubles() to p.series1, series.getJSONArray("ema21").doubles() to p.series2,
                    series.getJSONArray("vwap").doubles() to p.series3), levels)
                Legend(p.series1 to "EMA 9", p.series2 to "EMA 21", p.series3 to "VWAP", p.accent to "Opening range", p.muted to "PDH / PDL")
            }
        }
        item {
            val orb = v.getJSONObject("orb")
            Card("Opening range", trailing = { OrbPill(orb.s("state"), orb.s("side")) }) {
                v.o("opening_range")?.let { r ->
                    StatGrid(listOf(Triple("High", Fmt.num(r.d("high")), Tone.Neutral), Triple("Low", Fmt.num(r.d("low")), Tone.Neutral),
                        Triple("Mid", Fmt.num(r.d("mid")), Tone.Neutral)), columns = 3)
                }
                if (orb.s("state") == "triggered") Text("Triggered ${orb.s("side")} at ${Fmt.num(orb.d("entry"))} on the ${Fmt.time(orb.s("trigger_time"))} bar", fontSize = 13.sp, color = p.text2)
                var busy by remember { mutableStateOf(false) }
                PrimaryButton("Plan a trade from this setup", busy) {
                    scope.launch {
                        busy = true
                        runCatching { app.api.post("/entry/$symbol", jsonOf("setup" to "orb", "write" to true)) }
                            .onSuccess { planError = null; onPlan() }.onFailure { planError = it.message }
                        busy = false
                    }
                }
            }
        }
        item {
            Card("Levels") {
                val cpr = v.getJSONObject("cpr"); val pd = v.o("prev_day"); val ema = v.getJSONObject("ema")
                listOf("Prev high (PDH)" to pd?.d("high"), "Prev low (PDL)" to pd?.d("low"), "Prev close" to pd?.d("close"),
                    "R1" to cpr.d("r1"), "CPR top (TC)" to cpr.d("tc"), "Pivot" to cpr.d("pivot"), "CPR bottom (BC)" to cpr.d("bc"),
                    "S1" to cpr.d("s1"), "EMA 9" to ema.d("ema9"), "EMA 21" to ema.d("ema21"), "VWAP" to v.d("vwap")).forEach { (k, value) ->
                    Row { Text(k, color = p.text2, modifier = Modifier.weight(1f)); Text(Fmt.num(value), color = p.text) }
                    HorizontalDivider(color = p.border)
                }
                TrendPill(ema.s("trend"))
                v.s("cpr_read")?.let { Text(it, fontSize = 13.sp, color = p.text2) }
                if (v.d("vwap") == null && !future) Text("Spot indices have no volume, so VWAP is blank. Switch to Future for VWAP.", fontSize = 12.sp, color = p.muted)
            }
        }
    }
}
