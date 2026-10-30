package com.iamsanaur.idt.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import com.iamsanaur.idt.objects
import com.iamsanaur.idt.s
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
fun AlertsScreen(onAsk: () -> Unit) {
    val app = LocalApp.current
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    val list = rememberLoad<List<JSONObject>>()
    var symbol by remember { mutableStateOf("NIFTY") }
    var above by remember { mutableStateOf(true) }
    var price by remember { mutableStateOf("") }
    var actionError by remember { mutableStateOf<String?>(null) }
    suspend fun load() = list.run { app.api.arr("/alerts").objects() }
    LaunchedEffect(app.conn, app.alertsVersion) { load() }
    fun act(body: JSONObject) = scope.launch {
        onAsk() // ask for notification permission when the user sets an alert, not at launch
        runCatching { app.api.arr("/alerts", "POST", body) }.onSuccess { actionError = null; price = "" }.onFailure { actionError = it.message }
        load()
    }

    Screen("Alerts", actions = {
        TextButton(onClick = { scope.launch { runCatching { app.api.post("/alerts/check") }; load() } }) { Text("Check now") }
    }) {
        item { ErrorBox(list.error ?: actionError) }
        val items = list.value ?: emptyList()
        item {
            Card("Pending (${items.count { !it.optBoolean("fired") }})") {
                if (items.none { !it.optBoolean("fired") }) Text("No pending alerts", color = p.muted)
                items.filter { !it.optBoolean("fired") }.forEach { AlertRow(it); HorizontalDivider(color = p.border) }
            }
        }
        item {
            Card("Fired (${items.count { it.optBoolean("fired") }})") {
                if (items.none { it.optBoolean("fired") }) Text("Nothing has fired yet", color = p.muted)
                items.filter { it.optBoolean("fired") }.forEach { AlertRow(it); HorizontalDivider(color = p.border) }
            }
        }
        item {
            Card("Add") {
                SecondaryButton("Add stop / target / square-off from plan") { act(jsonOf("from_plan" to true)) }
                OutlinedTextField(symbol, { symbol = it.uppercase() }, label = { Text("Symbol or contract") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Segmented(above, listOf(true to "Crosses above", false to "Crosses below"), { above = it })
                OutlinedTextField(price, { price = it.filter { c -> c.isDigit() || c == '.' } }, label = { Text("Price") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                PrimaryButton("Add price alert", enabled = price.toDoubleOrNull() != null && symbol.isNotBlank()) {
                    act(jsonOf("symbol" to symbol, (if (above) "above" else "below") to price.toDouble()))
                }
            }
        }
        item {
            TextButton(onClick = { scope.launch { runCatching { app.api.arr("/alerts", "DELETE") }; load() } }) { Text("Clear all alerts", color = p.down) }
        }
    }
}

@Composable
private fun AlertRow(a: JSONObject) {
    val p = LocalPalette.current
    val detail = when (a.s("kind")) {
        "time" -> "at ${a.opt("value")} IST"
        "pnl" -> "combined P/L ${a.s("op")} ${Fmt.rupees(a.d("value"))}"
        else -> "${a.s("symbol")} ${a.s("op")} ${Fmt.num(a.d("value"))}" + (a.opt("observed")?.takeIf { it != JSONObject.NULL }?.let { " · observed $it" } ?: "")
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(a.optString("label"), fontWeight = FontWeight.SemiBold, color = p.text)
            Text(detail, fontSize = 12.sp, color = p.text2)
        }
        val label = a.optString("label")
        if (a.optBoolean("fired")) Pill(Fmt.time(a.s("fired_at")), if (label.startsWith("STOP")) Tone.Down else if (label.startsWith("TARGET")) Tone.Up else Tone.Neutral)
        else Pill("watching", Tone.Warn)
    }
}
