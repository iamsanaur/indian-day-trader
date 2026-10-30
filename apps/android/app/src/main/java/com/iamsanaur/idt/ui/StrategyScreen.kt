package com.iamsanaur.idt.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Fmt
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.d
import com.iamsanaur.idt.doubles
import com.iamsanaur.idt.keysList
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import com.iamsanaur.idt.strings
import kotlinx.coroutines.launch
import org.json.JSONObject
import kotlin.math.abs

private val DELTA_STRATS = setOf("short-strangle", "long-strangle", "iron-condor", "short-call", "short-put")

@Composable
fun Stepper(label: String, value: Int, range: IntRange, onChange: (Int) -> Unit) {
    val p = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = p.text, modifier = Modifier.weight(1f))
        SecondaryButton("−", value > range.first) { onChange(value - 1) }
        Text("$value", fontWeight = FontWeight.SemiBold, color = p.text, modifier = Modifier.width(40.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        SecondaryButton("+", value < range.last) { onChange(value + 1) }
    }
}

@Composable
fun StrategyScreen(onUse: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("bull-call-spread") }
    var underlying by remember { mutableStateOf("NIFTY") }
    var lots by remember { mutableIntStateOf(1) }
    var offset by remember { mutableIntStateOf(0) }
    var width by remember { mutableIntStateOf(4) }
    var delta by remember { mutableDoubleStateOf(0.0) }
    var saving by remember { mutableStateOf(false) }
    var saveError by remember { mutableStateOf<String?>(null) }
    val templates = rememberLoad<JSONObject>()
    val result = rememberLoad<JSONObject>()
    fun body(write: Boolean) = JSONObject().apply {
        put("name", name); put("underlying", underlying); put("lots", lots); put("offset", offset); put("width", width); put("write", write)
        if (delta > 0 && name in DELTA_STRATS) put("delta", delta)
    }
    LaunchedEffect(Unit) { templates.run { app.api.obj("/strategies") } }
    LaunchedEffect(name, underlying, lots, offset, width, delta) { result.run { app.api.post("/strategy", body(false)) } }

    Screen("Strategy") {
        item {
            Card("Setup") {
                Choice("Underlying", underlying, UNDERLYINGS.map { it to it }) { underlying = it }
                Choice("Strategy", name, (templates.value?.keysList()?.sorted() ?: listOf(name)).map { it to it.replace("-", " ") }) { name = it }
                templates.value?.s(name)?.let { Text(it, fontSize = 12.sp, color = p.muted) }
                Stepper("Lots", lots, 1..50) { lots = it }
                Stepper("Offset (strikes)", offset, -10..20) { offset = it }
                Stepper("Width (strikes)", width, 1..20) { width = it }
                if (name in DELTA_STRATS) Choice("Short strikes", delta, listOf(0.0 to "By steps", 0.1 to "0.10 Δ", 0.15 to "0.15 Δ", 0.2 to "0.20 Δ", 0.3 to "0.30 Δ")) { delta = it }
            }
        }
        item { ErrorBox(result.error ?: saveError) }
        val r = result.value
        if (r != null) {
            val a = r.getJSONObject("analysis")
            r.s("warning")?.let { w -> item { Banner("Naked short options", "${a.getJSONArray("naked").strings().joinToString(" · ")}. $w", Tone.Warn) } }
            item {
                Card("${r.s("name")?.replace("-", " ")} · ${r.s("underlying")} ${r.s("expiry")}", trailing = { Pill("lot ${r.optInt("lot_size")}", Tone.Accent) }) {
                    r.optJSONObject("curve")?.let { c ->
                        val xs = c.getJSONArray("x").doubles(); val ex = c.getJSONArray("expiry").doubles(); val td = c.getJSONArray("today").doubles()
                        val idx = xs.indices.filter { xs[it] != null && ex[it] != null && td[it] != null }
                        PayoffChart(idx.map { xs[it]!! }, idx.map { ex[it]!! }, idx.map { td[it]!! }, r.getDouble("spot"), a.getJSONArray("breakevens").doubles().filterNotNull())
                    }
                    Legend(p.text to "At expiry", p.series1 to "Today (model)", p.warn to "Breakeven")
                }
            }
            item {
                val g = r.getJSONObject("greeks"); val m = r.getJSONObject("margin")
                Card {
                    StatGrid(listOf(
                        Triple(if (a.s("premium_type") == "debit") "Net debit" else "Net credit", Fmt.rupees(abs(a.d("net_premium") ?: 0.0)), Tone.Neutral),
                        Triple("Max profit", if (a.optBoolean("unlimited_profit")) "Unlimited" else Fmt.signedRupees(a.d("max_profit")), Tone.Up),
                        Triple("Max loss", if (a.optBoolean("unlimited_loss")) "Unlimited" else Fmt.signedRupees(a.d("max_loss")), Tone.Down),
                        Triple("Breakevens", a.getJSONArray("breakevens").doubles().joinToString(" · ") { Fmt.num(it, 0) }, Tone.Neutral),
                        Triple("Margin", Fmt.rupees(m.d("total")), Tone.Neutral),
                        Triple("Theta / day", Fmt.signedRupees(g.d("theta")), Tone.of(g.d("theta"))),
                        Triple("Delta", Fmt.num(g.d("delta"), 1), Tone.Neutral),
                        Triple("Vega / IV pt", Fmt.signedRupees(g.d("vega")), Tone.Neutral),
                    ), hints = mapOf("Margin" to (m.s("source") ?: m.s("error") ?: ""), "Delta" to "units of underlying"))
                }
            }
            item {
                Card("Legs") {
                    r.getJSONArray("legs").objects().forEach { l ->
                        val buy = l.optInt("side") > 0
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Pill(if (buy) "BUY" else "SELL", if (buy) Tone.Up else Tone.Down)
                            Text("${l.optInt("lots")} × ${Fmt.num(l.d("strike"), 0)} ${l.s("kind")}", color = p.text, modifier = Modifier.weight(1f))
                            Text(Fmt.num(l.d("premium")), color = p.text)
                        }
                    }
                }
            }
        }
        item {
            PrimaryButton("Use for trade", saving, r != null) {
                scope.launch {
                    saving = true
                    runCatching { app.api.post("/strategy", body(true)) }.onSuccess { saveError = null; onUse() }.onFailure { saveError = it.message }
                    saving = false
                }
            }
            Spacer(Modifier.width(1.dp))
        }
    }
}
