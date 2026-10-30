package com.iamsanaur.idt.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.Connection
import com.iamsanaur.idt.Fmt
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.d
import com.iamsanaur.idt.jsonOf
import com.iamsanaur.idt.keysList
import com.iamsanaur.idt.o
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import com.iamsanaur.idt.strings
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun MoreScreen(open: (String) -> Unit) {
    val p = LocalPalette.current
    Screen("More") {
        listOf("strategy" to "Strategy builder", "journal" to "Journal", "research" to "Research", "settings" to "Settings").forEach { (route, label) ->
            item(route) {
                Card {
                    Row(Modifier.fillMaxWidth().clickable { open(route) }, verticalAlignment = Alignment.CenterVertically) {
                        Text(label, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = p.text, modifier = Modifier.weight(1f))
                        Text("›", fontSize = 22.sp, color = p.muted)
                    }
                }
            }
        }
        item { Text("Indian Day Trader never places orders. Tickets are for you to place in your own broker.", fontSize = 12.sp, color = p.muted) }
    }
}

@Composable
fun JournalScreen() {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    val entries = rememberLoad<List<JSONObject>>()
    var pnl by remember { mutableStateOf("") }
    var symbol by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    suspend fun load() { entries.run { app.api.arr("/journal?tail=100").objects() }; app.refreshStatus() }
    LaunchedEffect(Unit) { load() }
    Screen("Journal") {
        app.status?.let { s ->
            item {
                Card("Today") {
                    val realised = s.d("realised_today") ?: 0.0
                    val limits = s.getJSONObject("limits")
                    StatGrid(listOf(Triple("Trades confirmed", "${s.optInt("trades_today")}", Tone.Neutral), Triple("Realised P/L", Fmt.signedRupees(realised), Tone.of(realised))),
                        hints = mapOf("Trades confirmed" to "limit ${limits.optInt("max_trades_per_day")}"))
                    val cap = limits.d("daily_loss_cap") ?: 0.0
                    if (cap > 0) {
                        val used = maxOf(0.0, -realised)
                        Text("Daily loss cap used ${Fmt.rupees(used)} / ${Fmt.rupees(cap)}", fontSize = 12.sp, color = p.text2)
                        LinearProgressIndicator(progress = { (used / cap).toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth(),
                            color = if (used / cap > 0.75) p.downMark else p.accent, trackColor = p.surface2)
                    }
                }
            }
        }
        item {
            Card("Record a closed trade") {
                OutlinedTextField(pnl, { pnl = it.filter { c -> c.isDigit() || c == '.' || c == '-' } }, label = { Text("Realised P/L ₹ (negative for a loss)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(note, { note = it }, label = { Text("Note") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                PrimaryButton("Save", enabled = pnl.toDoubleOrNull() != null) {
                    scope.launch { runCatching { app.api.arr("/journal/close", "POST", jsonOf("pnl" to pnl.toDouble(), "symbol" to symbol, "note" to note)) }; pnl = ""; note = ""; load() }
                }
            }
        }
        item {
            Card("History") {
                ErrorBox(entries.error)
                (entries.value ?: emptyList()).reversed().forEach { e ->
                    val close = e.s("type") == "close"
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Pill(if (close) "Closed" else "Confirmed", if (close) Tone.of(e.d("pnl")) else Tone.Accent)
                        Column(Modifier.weight(1f)) { Text(e.s("symbol") ?: "—", fontWeight = FontWeight.SemiBold, color = p.text); Text(Fmt.dayTime(e.s("ts")), fontSize = 12.sp, color = p.muted) }
                        Text(if (close) Fmt.signedRupees(e.d("pnl")) else "risk ${Fmt.rupees(e.d("loss_at_stop"))}", color = if (close) Tone.of(e.d("pnl")).fg() else p.text2)
                    }
                    HorizontalDivider(color = p.border)
                }
            }
        }
    }
}

@Composable
fun ResearchScreen() {
    val app = LocalApp.current
    val p = LocalPalette.current
    var tab by remember { mutableStateOf("news") }
    var symbol by remember { mutableStateOf("RELIANCE") }
    val data = rememberLoad<JSONObject>()
    LaunchedEffect(tab, symbol) {
        data.run {
            when (tab) {
                "news" -> app.api.obj("/news?hours=72")
                "ban" -> app.api.obj("/ban")
                "deals" -> app.api.obj("/insider/deals")
                else -> app.api.obj("/results/$symbol")
            }
        }
    }
    Screen("Research") {
        item { Segmented(tab, listOf("news" to "News", "ban" to "Ban", "deals" to "Deals", "results" to "Results"), { tab = it }) }
        item { ErrorBox(data.error) }
        val d = data.value ?: return@Screen
        when (tab) {
            "news" -> d.optJSONArray("announcements")?.objects()?.forEachIndexed { i, a ->
                item("n$i") {
                    Card {
                        Row { Pill(a.s("symbol").orEmpty(), Tone.Accent); Text(Fmt.dayTime(a.s("time")), fontSize = 12.sp, color = p.muted, modifier = Modifier.weight(1f).padding(start = 8.dp)) }
                        Text(a.s("subject").orEmpty(), fontWeight = FontWeight.SemiBold, color = p.text)
                        Text(a.s("detail").orEmpty(), fontSize = 12.sp, color = p.text2)
                    }
                }
            }
            "ban" -> item {
                Card("F&O ban list — no fresh positions today") {
                    val list = d.optJSONArray("ban_list")?.strings().orEmpty()
                    if (list.isEmpty()) Text("No securities in ban", color = p.muted)
                    list.forEach { Text(it, color = p.down, fontWeight = FontWeight.Bold) }
                }
            }
            "deals" -> listOf("bulk" to "Bulk deals", "block" to "Block deals").forEach { (k, title) ->
                item(k) {
                    Card(title) {
                        d.optJSONArray(k)?.objects()?.forEach { x ->
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Column(Modifier.weight(1f)) { Text(x.optString("symbol"), fontWeight = FontWeight.Bold, color = p.text); Text(x.optString("clientName"), fontSize = 12.sp, color = p.text2) }
                                Pill(x.optString("buySell"), if (x.optString("buySell") == "BUY") Tone.Up else Tone.Down)
                                Text(Fmt.compact(x.optString("qty").toDoubleOrNull()), color = p.text)
                            }
                        }
                    }
                }
            }
            else -> {
                item { OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol") }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
                item {
                    Card("Quarterly results") {
                        d.optJSONArray("quarters")?.objects()?.forEach { q ->
                            Row {
                                Text(q.s("period_end").orEmpty(), fontWeight = FontWeight.SemiBold, color = p.text, modifier = Modifier.weight(1f))
                                Column(horizontalAlignment = Alignment.End) {
                                    Text("Rev ${Fmt.num(q.d("revenue"), 0)} · ${Fmt.pct(q.d("revenue_yoy_pct"), 1)} YoY", fontSize = 12.sp, color = p.text)
                                    Text("PAT ${Fmt.num(q.d("net_profit"), 0)} · EPS ${Fmt.num(q.d("eps"))}", fontSize = 12.sp, color = p.text2)
                                }
                            }
                            HorizontalDivider(color = p.border)
                        }
                        Text(d.s("note").orEmpty(), fontSize = 12.sp, color = p.muted)
                    }
                }
            }
        }
    }
}

private val LIMIT_LABELS = listOf(
    "capital" to "Paper capital (₹)", "max_loss_per_trade" to "Max loss per trade (₹)", "daily_loss_cap" to "Daily loss cap (₹)",
    "max_trades_per_day" to "Max trades per day", "leverage_cap" to "Leverage cap (×)", "min_premium" to "Min option premium (₹)",
    "entry_cutoff" to "No new entries after", "squareoff" to "Square off by",
    "allow_short" to "Allow shorting", "allow_naked" to "Allow naked short options", "block_expiry_day_selling" to "Block expiry-day selling",
)

@Composable
fun SettingsScreen() {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(app.conn.url) }
    var token by remember { mutableStateOf(app.conn.token) }
    val health = rememberLoad<JSONObject>()
    val config = rememberLoad<JSONObject>()
    val draft = remember { mutableStateMapOf<String, Any>() }
    var saveError by remember { mutableStateOf<String?>(null) }
    suspend fun check() {
        health.run { app.api.obj("/health") }
        config.run { app.api.obj("/config") }
        draft.clear()
        config.value?.getJSONObject("config")?.let { c -> c.keysList().forEach { k -> draft[k] = c.get(k) } }
        app.refreshStatus()
    }
    LaunchedEffect(app.conn) { check() }

    Screen("Settings") {
        item {
            Card("Server") {
                Text("Run `idt serve` on your computer and scan its QR with your phone camera, or enter the URL and token.", fontSize = 12.sp, color = p.text2)
                OutlinedTextField(url, { url = it.trim() }, label = { Text("Server URL, e.g. http://192.168.1.10:8742") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(token, { token = it.trim() }, label = { Text("Access token") }, singleLine = true, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                PrimaryButton("Save & connect") { app.pair(Connection(url, token)) }
                health.value?.let { h -> Pill("Connected · v${h.s("version")}${if (h.optBoolean("demo")) " · demo" else ""}", Tone.Up) }
                ErrorBox(health.error)
            }
        }
        item { DhanSessionCard() }
        item {
            Card("Appearance") { Segmented(app.theme, listOf("system" to "System", "light" to "Light", "dark" to "Dark"), { app.setThemePref(it) }) }
        }
        val cfg = config.value?.getJSONObject("config") ?: return@Screen
        item {
            Card("Risk limits") {
                Segmented(draft["mode"]?.toString() ?: "paper", listOf("paper" to "Paper", "live" to "Live"), { draft["mode"] = it })
                LIMIT_LABELS.filter { cfg.has(it.first) }.forEach { (k, label) ->
                    when (val v = draft[k]) {
                        is Boolean -> Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(label, color = p.text, modifier = Modifier.weight(1f)); Switch(v, { draft[k] = it })
                        }
                        else -> OutlinedTextField(v?.toString().orEmpty(), { s -> draft[k] = if (cfg.get(k) is String) s else (s.toDoubleOrNull() ?: 0.0) },
                            label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    }
                }
                if (draft["allow_naked"] == true) Text("Naked short options can lose far more than the premium collected.", fontSize = 12.sp, color = p.warn)
                val changes = JSONObject().apply {
                    draft.forEach { (k, v) ->
                        val orig = cfg.opt(k)
                        val same = if (orig is Number && v is Number) orig.toDouble() == v.toDouble() else orig == v
                        if (!same) put(k, if (v is Double && v % 1.0 == 0.0) v.toLong() else v)
                    }
                }
                PrimaryButton("Save limits", enabled = changes.length() > 0) {
                    scope.launch {
                        runCatching { app.api.obj("/config", "PATCH", changes) }.onSuccess { saveError = null; check() }.onFailure { saveError = it.message }
                    }
                }
                ErrorBox(saveError)
                Text("Live mode reads available funds from your broker for the margin check. Orders are never placed either way.", fontSize = 12.sp, color = p.muted)
            }
        }
    }
}
