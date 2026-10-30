package com.iamsanaur.idt.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.iamsanaur.idt.LocalApp
import com.iamsanaur.idt.jsonOf
import com.iamsanaur.idt.s
import kotlinx.coroutines.launch
import org.json.JSONObject

fun timeLeft(d: JSONObject): String {
    val s = d.optInt("expires_in_seconds", 0)
    return if (s <= 0) "" else "${s / 3600}h ${s % 3600 / 60}m left"
}

/** Daily Dhan reconnect: the 6-digit TOTP is exchanged for a 24-hour token on your server and never stored. */
@Composable
fun TotpField() {
    val app = LocalApp.current
    val scope = rememberCoroutineScope()
    var totp by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(
                totp, { totp = it.filter(Char::isDigit).take(6) }, label = { Text("6-digit TOTP") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                textStyle = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 3.sp),
                modifier = Modifier.weight(1f),
            )
            Button(onClick = {
                scope.launch {
                    busy = true
                    runCatching { app.api.post("/dhan/login", jsonOf("totp" to totp)) }
                        .onSuccess { totp = ""; error = null; app.refreshStatus() }
                        .onFailure { error = it.message }
                    busy = false
                }
            }, enabled = totp.length == 6 && !busy, shape = RoundedCornerShape(12.dp), modifier = Modifier.height(56.dp)) {
                if (busy) CircularProgressIndicator(Modifier.width(18.dp), strokeWidth = 2.dp) else Text("Connect", fontWeight = FontWeight.SemiBold)
            }
        }
        ErrorBox(error)
    }
}

@Composable
fun DhanBanner() {
    val d = LocalApp.current.status?.optJSONObject("dhan") ?: return
    if (d.optBoolean("connected")) return
    val p = LocalPalette.current
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(p.warnSoft).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Connect Dhan for today", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = p.text)
        Text(d.s("message").orEmpty(), fontSize = 13.sp, color = p.text2)
        if (d.optBoolean("totp_login_available")) TotpField()
    }
}

@Composable
fun DhanSessionCard() {
    val app = LocalApp.current
    val d = app.status?.optJSONObject("dhan") ?: return
    val p = LocalPalette.current
    val scope = rememberCoroutineScope()
    val connected = d.optBoolean("connected")
    Card("Dhan session") {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(if (connected) "Connected" + (d.s("client_name")?.let { " · $it" } ?: "") else "Not connected", if (connected) Tone.Up else Tone.Down)
            if (connected && d.s("source") == "totp") Pill(timeLeft(d))
            if (d.s("source") == "env") Pill("manual token")
        }
        Text(d.s("message").orEmpty(), fontSize = 13.sp, color = p.text2)
        if (d.optBoolean("totp_login_available") && d.s("source") != "env") TotpField()
        Text(if (d.optBoolean("client_id_set") && d.optBoolean("pin_set")) "Your TOTP is used once to get a 24-hour token and is never stored."
             else "Add DHAN_CLIENT_ID and DHAN_PIN to the server's .env and restart it.", fontSize = 12.sp, color = p.muted)
        if (connected && d.s("source") == "totp") {
            TextButton(onClick = { scope.launch { runCatching { app.api.obj("/dhan", "DELETE") }; app.refreshStatus() } }) { Text("Disconnect", color = p.down) }
        }
    }
}
