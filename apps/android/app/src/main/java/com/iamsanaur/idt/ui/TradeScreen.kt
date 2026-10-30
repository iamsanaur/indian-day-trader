package com.iamsanaur.idt.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Fmt
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.d
import com.iamsanaur.idt.jsonOf
import com.iamsanaur.idt.o
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import com.iamsanaur.idt.strings
import kotlinx.coroutines.launch
import org.json.JSONObject

private val STEPS = listOf("Setup", "Plan", "Odds", "Size", "Risk", "Ticket")

private val STOPS = mapOf(
    "option" to listOf("or-mid" to "Underlying at OR mid", "or-low" to "Underlying at far side of OR", "premium-pct:30" to "Premium −30%", "premium-pct:50" to "Premium −50%"),
    "equity" to listOf("or-mid" to "OR mid", "or-low" to "Far side of OR", "atr:1" to "1 × ATR", "pct:0.5" to "0.5%"),
    "future" to listOf("or-mid" to "OR mid", "or-low" to "Far side of OR", "atr:1" to "1 × ATR"),
    "strategy" to listOf("maxloss-pct:50" to "50% of max loss", "credit-x:1" to "Loss = 1 × credit", "pnl:-2000" to "−₹2,000 per set"),
)
private val TARGETS = mapOf(
    "option" to listOf("1.5R" to "1.5 R", "2R" to "2 R", "1R" to "1 R"),
    "equity" to listOf("1.5R" to "1.5 R", "2R" to "2 R", "1R" to "1 R"),
    "future" to listOf("1.5R" to "1.5 R", "2R" to "2 R"),
    "strategy" to listOf("1.5R" to "1.5 R", "maxprofit-pct:60" to "60% of max profit", "credit-pct:50" to "Keep 50% of credit"),
)

@Composable
fun TradeScreen() {
    val app = LocalApp.current
    val state = rememberLoad<JSONObject>()
    LaunchedEffect(app.tradeStep, app.conn) { state.run { app.api.obj("/plan") } }
    val next = { app.tradeStep = (app.tradeStep + 1).coerceAtMost(STEPS.size - 1) }
    val p = LocalPalette.current

    Screen("Trade") {
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                STEPS.forEachIndexed { i, s ->
                    FilterChip(selected = i == app.tradeStep, onClick = { app.tradeStep = i }, label = { Text("${i + 1} $s") },
                        shape = RoundedCornerShape(20.dp),
                        colors = FilterChipDefaults.filterChipColors(selectedContainerColor = p.accent, selectedLabelColor = androidx.compose.ui.graphics.Color.White))
                }
            }
        }
        item { ErrorBox(state.error) }
        if (state.value == null) { item { if (state.loading) CircularProgressIndicator() }; return@Screen }
        val s = state.value!!
        item {
            when (app.tradeStep) {
                0 -> SetupStep(s, next)
                1 -> PlanStep(s, next)
                2 -> OddsStep(next)
                3 -> SizeStep(next)
                4 -> RiskStep(next)
                else -> TicketStep()
            }
        }
    }
}

@Composable
private fun SetupStep(state: JSONObject, next: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var symbol by remember { mutableStateOf(state.o("setup")?.s("symbol") ?: "NIFTY") }
    var setup by remember { mutableStateOf("orb") }
    val check = rememberLoad<JSONObject>()
    val s = check.value ?: state.o("setup")
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card("Check the entry trigger") {
            OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            Choice("Setup", setup, listOf("orb" to "Opening-range breakout", "pdh" to "Previous-day high/low")) { setup = it }
            PrimaryButton("Check", check.loading) { scope.launch { check.run { app.api.post("/entry/$symbol", jsonOf("setup" to setup, "write" to true)) } } }
            ErrorBox(check.error)
            s?.let {
                val trig = it.s("state") == "triggered"
                Banner("${it.s("symbol")}: ${it.s("state")} ${it.s("side").orEmpty()}",
                    if (trig) "Entry ${Fmt.num(it.d("entry"))} on the ${Fmt.time(it.s("trigger_time"))} bar" else "Only completed 5-minute bars count.",
                    if (trig) Tone.Up else Tone.Warn)
            }
        }
        Card("Or trade a saved strategy") {
            val st = state.o("strategy")
            if (st != null) {
                Text("${st.s("name")?.replace("-", " ")} · ${st.s("underlying")} ${st.s("expiry")}", fontWeight = FontWeight.Medium, color = p.text)
                Text("Choose “Saved strategy” in the next step.", fontSize = 12.sp, color = p.text2)
            } else Text("Build one in More › Strategy and tap “Use for trade”.", fontSize = 13.sp, color = p.muted)
        }
        PrimaryButton("Next: plan the exit", enabled = s != null || state.o("strategy") != null, onClick = next)
    }
}

@Composable
private fun PlanStep(state: JSONObject, next: () -> Unit) {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    val isIndex = state.o("setup")?.s("symbol") in UNDERLYINGS
    val initial = state.o("plan")?.s("kind") ?: if (state.o("strategy") != null && state.o("setup") == null) "strategy" else if (isIndex || state.o("setup") == null) "option" else "equity"
    var kind by remember { mutableStateOf(initial) }
    var stop by remember { mutableStateOf(STOPS.getValue(initial).first().first) }
    var target by remember { mutableStateOf(TARGETS.getValue(initial).first().first) }
    var option by remember { mutableStateOf("auto") }
    var offset by remember { mutableIntStateOf(0) }
    val save = rememberLoad<JSONObject>()
    val pick = { k: String -> kind = k; stop = STOPS.getValue(k).first().first; target = TARGETS.getValue(k).first().first }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card("Stop and target — set before entry") {
            Choice("Instrument", kind, listOfNotNull("option" to "Long option (CE/PE)", "equity" to "Cash equity (MIS)", "future" to "Future",
                if (state.o("strategy") != null) "strategy" to "Saved strategy" else null), pick)
            if (kind == "option") {
                Segmented(option, listOf("auto" to "Auto", "CE" to "CE", "PE" to "PE"), { option = it })
                Stepper("Strikes OTM", offset, -5..10) { offset = it }
            }
            Choice("Stop", stop, STOPS.getValue(kind)) { stop = it }
            Choice("Target", target, TARGETS.getValue(kind)) { target = it }
            PrimaryButton("Save plan", save.loading) {
                scope.launch { save.run { app.api.post("/plan", jsonOf("kind" to kind, "stop" to stop, "target" to target, "option" to option, "strike_offset" to offset)) } }
            }
            ErrorBox(save.error)
        }
        (save.value ?: state.o("plan"))?.let { PlanCard(it) }
        PrimaryButton("Next: check the odds", enabled = (save.value ?: state.o("plan")) != null, onClick = next)
    }
}

@Composable
fun PlanCard(plan: JSONObject) {
    val p = LocalPalette.current
    val strat = plan.s("basis") == "pnl"
    val title = if (strat) plan.s("strategy")?.replace("-", " ") else plan.s("contract")
    Card("$title · ${plan.s("side")}", trailing = { Pill("R:R ${Fmt.num(plan.d("rr"))}", Tone.Accent) }) {
        val unit = plan.s("unit")
        StatGrid(if (strat) listOf(
            Triple(if ((plan.d("entry") ?: 0.0) > 0) "Debit / set" else "Credit / set", Fmt.rupees(kotlin.math.abs(plan.d("entry") ?: 0.0)), Tone.Neutral),
            Triple("Stop (P/L)", Fmt.signedRupees(plan.d("stop_pnl")), Tone.Down),
            Triple("Target (P/L)", Fmt.signedRupees(plan.d("target_pnl")), Tone.Up),
            Triple("Risk / $unit", Fmt.rupees(plan.d("risk_per_unit")), Tone.Neutral),
        ) else listOf(
            Triple("Entry", Fmt.num(plan.d("entry")), Tone.Neutral),
            Triple("Stop", Fmt.num(plan.d("stop")), Tone.Down),
            Triple("Target", Fmt.num(plan.d("target")), Tone.Up),
            Triple("Risk / $unit", Fmt.rupees(plan.d("risk_per_unit")), Tone.Neutral),
        ), hints = if (plan.s("kind") == "option") mapOf("Stop" to "underlying ${Fmt.num(plan.d("underlying_stop"))}", "Target" to "underlying ${Fmt.num(plan.d("underlying_target"))}") else emptyMap())
        Text("Square off by ${plan.s("squareoff")} IST · ${plan.s("stop_rule")} / ${plan.s("target_rule")}", fontSize = 12.sp, color = p.muted)
    }
}

@Composable
private fun OddsStep(next: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    val run = rememberLoad<JSONObject>()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card("Time Machine") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                listOf(2000, 10000).forEach { n -> SecondaryButton("Run ${Fmt.num(n.toDouble(), 0)} paths", !run.loading) { scope.launch { run.run { app.api.post("/timemachine", jsonOf("paths" to n)) } } } }
                if (run.loading) CircularProgressIndicator(Modifier.width(20.dp), strokeWidth = 2.dp)
            }
            ErrorBox(run.error)
            run.value?.let { r ->
                val mc = r.getJSONObject("monte_carlo"); val pnl = mc.getJSONObject("pnl_per_unit")
                ProbBar(mc.getDouble("p_target"), mc.getDouble("p_flat"), mc.getDouble("p_stop"))
                Row {
                    listOf(Triple("Target", mc.getDouble("p_target"), p.upMark), Triple("Open at 15:15", mc.getDouble("p_flat"), p.muted), Triple("Stop", mc.getDouble("p_stop"), p.downMark)).forEach { (l, v, c) ->
                        Column(Modifier.weight(1f)) { Legend(c to l); Text(String.format(java.util.Locale.US, "%.1f%%", v * 100), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = p.text) }
                    }
                }
                StatGrid(listOf(
                    Triple("Mean P/L / unit", Fmt.signedRupees(pnl.d("mean")), Tone.of(pnl.d("mean"))),
                    Triple("Median", Fmt.signedRupees(pnl.d("median")), Tone.Neutral),
                    Triple("5th pct", Fmt.signedRupees(pnl.d("p5")), Tone.Neutral),
                    Triple("95th pct", Fmt.signedRupees(pnl.d("p95")), Tone.Neutral),
                ))
                r.getJSONObject("replay").let { rp ->
                    if (rp.has("fired")) Text("Replay: fired on ${rp.optInt("fired")} of ${rp.optInt("sessions")} prior sessions · win rate ${rp.d("win_rate")?.let { "${(it * 100).toInt()}%" } ?: "—"} · avg ${Fmt.num(rp.d("avg_r"))} R", fontSize = 13.sp, color = p.text2)
                }
                Text(r.s("caveat").orEmpty(), fontSize = 12.sp, color = p.muted)
            } ?: if (!run.loading) Text("Simulate thousands of sessions from the same time of day before risking money.", fontSize = 13.sp, color = p.muted) else Unit
        }
        PrimaryButton("Next: size the position", onClick = next)
    }
}

@Composable
private fun SizeStep(next: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var maxLoss by remember { mutableStateOf("") }
    val size = rememberLoad<JSONObject>()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Card("Budget") {
            OutlinedTextField(maxLoss, { maxLoss = it.filter { c -> c.isDigit() || c == '.' } }, label = { Text("Max loss ₹ (blank = config)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            PrimaryButton("Size it", size.loading) { scope.launch { size.run { app.api.post("/size", JSONObject().apply { maxLoss.toDoubleOrNull()?.let { put("max_loss", it) } }) } } }
            ErrorBox(size.error)
            size.value?.let { o ->
                val unit = o.s("unit")
                StatGrid(listOf(
                    Triple(if (unit == "share") "Shares" else if (unit == "lot") "Lots" else "Sets", "${o.optInt("units")}", Tone.Neutral),
                    Triple("Loss at stop", Fmt.rupees(o.d("loss_at_stop")), Tone.Down),
                    Triple("Profit at target", Fmt.rupees(o.d("profit_at_target")), Tone.Up),
                    Triple("Margin", Fmt.rupees(o.getJSONObject("margin").d("total")), Tone.Neutral),
                ), hints = mapOf("Loss at stop" to "incl. ₹${Fmt.num(o.getJSONObject("charges").d("if_stopped"), 0)} charges"))
                o.getJSONArray("legs").objects().forEach { l ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Pill(l.optString("side"), if (l.optString("side") == "BUY") Tone.Up else Tone.Down)
                        Text(l.optString("symbol"), fontSize = 13.sp, color = p.text, modifier = Modifier.weight(1f), maxLines = 1)
                        Text("${l.optInt("quantity")} @ ${Fmt.num(l.d("price"))}", fontSize = 13.sp, color = p.text)
                    }
                }
                o.getJSONArray("notes").strings().forEach { Text(it, fontSize = 12.sp, color = p.muted) }
            }
        }
        PrimaryButton("Next: risk check", enabled = size.value != null, onClick = next)
    }
}

@Composable
private fun RiskStep(next: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    val risk = rememberLoad<JSONObject>()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        PrimaryButton("Run risk check", risk.loading) { scope.launch { risk.run { app.api.post("/risk") } } }
        ErrorBox(risk.error)
        risk.value?.let { r ->
            val pass = r.s("verdict") == "PASS"
            Banner(r.s("verdict").orEmpty(), if (pass) "Every rule passed. The verdict is bound to this exact order for 10 minutes."
                else "${r.getJSONArray("reasons").length()} rule(s) failed. Fix them, then re-size and re-check.", if (pass) Tone.Up else Tone.Down)
            Card("Checks") {
                r.getJSONArray("checks").objects().forEach { c ->
                    Row(verticalAlignment = Alignment.Top) {
                        Text(if (c.optBoolean("ok")) "✓" else "✕", color = if (c.optBoolean("ok")) p.up else p.down, fontWeight = FontWeight.Bold, modifier = Modifier.width(22.dp))
                        Column { Text(c.optString("rule"), fontWeight = FontWeight.SemiBold, color = p.text); Text(c.optString("detail"), fontSize = 12.sp, color = p.text2) }
                    }
                }
            }
            PrimaryButton("Next: ticket", enabled = pass, onClick = next)
        }
    }
}

@Composable
private fun TicketStep() {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var typed by remember { mutableStateOf("") }
    var alertsAdded by remember { mutableStateOf(false) }
    val ticket = rememberLoad<JSONObject>()
    val confirm = rememberLoad<JSONObject>()
    LaunchedEffect(Unit) { ticket.run { app.api.obj("/ticket") } }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        ErrorBox(ticket.error)
        val t = ticket.value ?: return@Column
        Card("Ticket · ${t.s("order_hash")}", trailing = { Pill("${t.s("mode")} mode", if (t.s("mode") == "paper") Tone.Warn else Tone.Accent) }) {
            t.getJSONArray("entries").objects().forEach { e ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pill(e.optString("action"), if (e.optString("action") == "BUY") Tone.Up else Tone.Down)
                    Column(Modifier.weight(1f)) {
                        Text(e.optString("symbol"), fontWeight = FontWeight.Medium, color = p.text)
                        Text("${e.optString("order_type")} · ${e.optString("product")}", fontSize = 12.sp, color = p.muted)
                    }
                    Column(horizontalAlignment = Alignment.End) { Text("${e.optInt("quantity")}", color = p.text); Text("@ ${Fmt.num(e.d("price"))}", fontSize = 12.sp, color = p.text2) }
                }
            }
            Text("Exits", fontWeight = FontWeight.SemiBold, color = p.text)
            t.getJSONArray("exits").objects().forEach { x ->
                val parts = listOf("action", "order_type", "trigger_price", "price", "condition").mapNotNull { k -> x.opt(k)?.takeIf { it != JSONObject.NULL }?.toString() }
                Text("• ${x.optString("note", x.optString("action"))}: ${parts.joinToString(" · ")}", fontSize = 12.sp, color = p.text2)
            }
            Text(t.optString("oco"), fontSize = 12.sp, color = p.muted)
            StatGrid(listOf(Triple("Loss at stop", Fmt.rupees(t.d("loss_at_stop")), Tone.Down), Triple("Profit at target", Fmt.rupees(t.d("profit_at_target")), Tone.Up)))
        }
        val done = confirm.value
        if (done != null) {
            Banner("Confirmed ${done.s("confirmed")}", done.s("next").orEmpty(), Tone.Up)
            SecondaryButton(if (alertsAdded) "Alerts added ✓" else "Add stop / target / square-off alerts", !alertsAdded) {
                scope.launch { runCatching { app.api.arr("/alerts", "POST", jsonOf("from_plan" to true)) }; alertsAdded = true }
            }
        } else {
            Card("Confirm") {
                Text("This records your decision. Nothing is sent to a broker — you place the order yourself.", fontSize = 13.sp, color = p.text2)
                OutlinedTextField(typed, { typed = it }, label = { Text("Type \"yes\" to confirm") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                PrimaryButton("Confirm order", confirm.loading, typed.trim().lowercase() == "yes") {
                    scope.launch {
                        confirm.run { app.api.post("/ticket/confirm", jsonOf("hash" to t.s("order_hash"), "typed" to typed)) }
                        app.refreshStatus()
                    }
                }
                ErrorBox(confirm.error)
            }
        }
        Spacer(Modifier.width(1.dp))
    }
}
