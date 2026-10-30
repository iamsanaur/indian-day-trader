package com.iamsanaur.idt.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Fmt
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.d
import com.iamsanaur.idt.o
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import com.iamsanaur.idt.strings
import org.json.JSONObject

val UNDERLYINGS = listOf("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX")

@Composable
fun OptionsScreen() {
    val app = LocalApp.current
    var underlying by remember { mutableStateOf("NIFTY") }
    var expiry by remember { mutableStateOf("") }
    var change by remember { mutableStateOf(false) }
    val expiries = rememberLoad<List<String>>()
    val chain = rememberLoad<JSONObject>()
    LaunchedEffect(underlying) { expiry = ""; expiries.run { app.api.obj("/expiries/$underlying").getJSONArray("expiries").strings() } }
    LaunchedEffect(underlying, expiry) { chain.run { app.api.obj("/chain/$underlying?strikes=12" + if (expiry.isEmpty()) "" else "&expiry=$expiry") } }

    Screen("Option chain") {
        item {
            Row(Modifier.horizontalScroll(rememberScrollState())) {
                Segmented(underlying, UNDERLYINGS.map { it to it }, { underlying = it }, Modifier.width(520.dp))
            }
        }
        item { Choice("Expiry", expiry, listOf("" to "Nearest") + (expiries.value ?: emptyList()).map { it to it }) { expiry = it } }
        item { ErrorBox(chain.error) }
        val c = chain.value ?: return@Screen
        val p0 = c.getJSONObject("pcr"); val em = c.getJSONObject("expected_move"); val range = em.getJSONArray("range")
        item {
            Card("${c.s("underlying")} · ${c.s("expiry")} · ${Fmt.num(c.d("days_to_expiry"), 1)} days · lot ${c.optInt("lot_size")}") {
                StatGrid(listOf(
                    Triple("Spot", Fmt.num(c.d("spot")), Tone.Neutral),
                    Triple("ATM IV", c.d("atm_iv")?.let { "${Fmt.num(it, 1)}%" } ?: "—", Tone.Neutral),
                    Triple("PCR (OI)", Fmt.num(p0.d("oi")), Tone.Neutral),
                    Triple("Max pain", Fmt.num(c.d("max_pain"), 0), Tone.Neutral),
                    Triple("Expected move", "± ${Fmt.num(em.d("points"), 0)}", Tone.Neutral),
                    Triple("ATM straddle", Fmt.num(c.d("atm_straddle")), Tone.Neutral),
                ), columns = 3, hints = mapOf("PCR (OI)" to "Δ OI PCR ${Fmt.num(p0.d("oi_change"))}", "Max pain" to Fmt.pct(c.d("max_pain_distance_pct")),
                    "Expected move" to "${Fmt.num(range.optDouble(0), 0)} – ${Fmt.num(range.optDouble(1), 0)}"))
                Text("Positioning: ${c.s("bias")}. Describes where open interest sits — not a prediction.", fontSize = 12.sp, color = LocalPalette.current.text2)
            }
        }
        item {
            val walls = c.getJSONObject("walls")
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.weight(1f)) { WallCard("Resistance", "call writers", walls.getJSONArray("resistance").objects()) }
                Box(Modifier.weight(1f)) { WallCard("Support", "put writers", walls.getJSONArray("support").objects()) }
            }
        }
        val rows = c.getJSONArray("table").objects()
        item {
            val p = LocalPalette.current
            Card("Open interest by strike") {
                Segmented(change, listOf(false to "OI", true to "Change"), { change = it })
                OIChart(rows.map { it.getDouble("strike") },
                    rows.map { it.o("ce")?.d(if (change) "oi_change" else "oi") ?: 0.0 },
                    rows.map { it.o("pe")?.d(if (change) "oi_change" else "oi") ?: 0.0 }, c.getDouble("atm"))
                Legend(p.series1 to "Calls (CE)", p.series2 to "Puts (PE)")
            }
        }
        item {
            val p = LocalPalette.current
            val maxOI = rows.maxOf { maxOf(it.o("ce")?.d("oi") ?: 0.0, it.o("pe")?.d("oi") ?: 0.0) }
            Card("Chain") {
                Row {
                    Text("Call LTP · OI", fontSize = 12.sp, color = p.muted, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    Text("Strike", fontSize = 12.sp, color = p.muted, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(72.dp))
                    Text("Put LTP · OI", fontSize = 12.sp, color = p.muted, fontWeight = FontWeight.SemiBold)
                }
                rows.forEach { r ->
                    ChainRow(r, r.getDouble("strike") == c.getDouble("atm"), r.getDouble("strike") < c.getDouble("spot"), maxOI)
                    HorizontalDivider(color = p.border)
                }
            }
        }
    }
}

@Composable
private fun WallCard(title: String, subtitle: String, walls: List<JSONObject>) {
    val p = LocalPalette.current
    Card(title) {
        Text(subtitle, fontSize = 12.sp, color = p.muted)
        walls.forEach { w ->
            Row { Text(Fmt.num(w.d("strike"), 0), fontWeight = FontWeight.Bold, color = p.text, modifier = Modifier.weight(1f)); Text(Fmt.compact(w.d("oi")), color = p.text2) }
        }
    }
}

@Composable
private fun ChainRow(r: JSONObject, atm: Boolean, belowSpot: Boolean, maxOI: Double) {
    val p = LocalPalette.current
    Row(Modifier.fillMaxWidth().background(if (atm) p.accentSoft else Color.Transparent).padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Side(r.o("ce"), p.series1, Alignment.Start, maxOI, Modifier.weight(1f))
        Column(Modifier.width(72.dp).clip(RoundedCornerShape(6.dp)).background(if (belowSpot) p.surface2 else Color.Transparent).padding(vertical = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text(Fmt.num(r.d("strike"), 0), fontWeight = FontWeight.Bold, color = p.text)
            if (atm) Pill("ATM", Tone.Accent)
        }
        Side(r.o("pe"), p.series2, Alignment.End, maxOI, Modifier.weight(1f))
    }
}

@Composable
private fun Side(s: JSONObject?, color: Color, align: Alignment.Horizontal, maxOI: Double, modifier: Modifier) {
    val p = LocalPalette.current
    Column(modifier, horizontalAlignment = align, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        if (s == null) { Text("—", color = p.muted); return@Column }
        Text(Fmt.num(s.d("ltp")), fontWeight = FontWeight.SemiBold, color = p.text)
        val frac = ((s.d("oi") ?: 0.0) / maxOI).toFloat().coerceIn(0.02f, 1f)
        Box(Modifier.fillMaxWidth(frac).height(5.dp).clip(RoundedCornerShape(3.dp)).background(color))
        val chg = s.d("oi_change") ?: 0.0
        Text("${Fmt.compact(s.d("oi"))} · ${if (chg >= 0) "+" else ""}${Fmt.compact(chg)}", fontSize = 11.sp, color = if (chg >= 0) p.up else p.down)
        Text(s.s("buildup").orEmpty(), fontSize = 11.sp, color = p.muted)
    }
}
