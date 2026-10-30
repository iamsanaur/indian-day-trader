package com.iamsanaur.idt.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException

/** Async state for one request. */
class Load<T> {
    var value by mutableStateOf<T?>(null)
    var error by mutableStateOf<String?>(null)
    var loading by mutableStateOf(false)

    suspend fun run(block: suspend () -> T) {
        loading = true
        try {
            value = block(); error = null
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            error = e.message ?: e.toString()
        } finally {
            loading = false
        }
    }
}

@Composable
fun <T> rememberLoad() = remember { Load<T>() }

@Composable
fun Screen(title: String, actions: @Composable () -> Unit = {}, content: LazyListScope.() -> Unit) {
    val p = LocalPalette.current
    LazyColumn(
        modifier = Modifier.fillMaxWidth().background(p.bg),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp, bottom = 2.dp)) {
                Text(title, fontSize = 30.sp, fontWeight = FontWeight.Bold, color = p.text, modifier = Modifier.weight(1f))
                actions()
            }
        }
        content()
    }
}

@Composable
fun Card(title: String? = null, trailing: (@Composable () -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val p = LocalPalette.current
    Surface(
        shape = RoundedCornerShape(16.dp), color = p.surface, border = BorderStroke(1.dp, p.border),
        shadowElevation = 1.dp, modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (title != null || trailing != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(title.orEmpty(), color = p.text2, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    trailing?.invoke()
                }
            }
            content()
        }
    }
}

@Composable
fun Pill(text: String, tone: Tone = Tone.Neutral) {
    Text(
        text, color = tone.fg(), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
        modifier = Modifier.clip(CircleShape).background(tone.bg()).padding(horizontal = 9.dp, vertical = 4.dp),
    )
}

@Composable
fun Stat(label: String, value: String, tone: Tone = Tone.Neutral, hint: String? = null, modifier: Modifier = Modifier) {
    val p = LocalPalette.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, color = p.muted, fontSize = 12.sp)
        Text(value, color = if (tone == Tone.Neutral) p.text else tone.fg(), fontSize = 19.sp, fontWeight = FontWeight.SemiBold,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (hint != null) Text(hint, color = p.muted, fontSize = 11.sp, maxLines = 2)
    }
}

/** Stats laid out in rows of `columns`. */
@Composable
fun StatGrid(items: List<Triple<String, String, Tone>>, columns: Int = 2, hints: Map<String, String> = emptyMap()) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items.chunked(columns).forEach { row ->
            Row(Modifier.fillMaxWidth()) {
                row.forEach { (l, v, t) -> Stat(l, v, t, hints[l], Modifier.weight(1f)) }
                repeat(columns - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
fun ErrorBox(error: String?) {
    if (error == null) return
    val p = LocalPalette.current
    Text(error, color = p.down, fontWeight = FontWeight.Medium, fontSize = 14.sp,
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(p.downSoft).padding(12.dp))
}

@Composable
fun Banner(title: String, message: String, tone: Tone) {
    val p = LocalPalette.current
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(tone.bg()).padding(14.dp), verticalAlignment = Alignment.Top) {
        Box(Modifier.padding(top = 4.dp).size(10.dp).clip(CircleShape).background(tone.fg()))
        Spacer(Modifier.width(12.dp))
        Column {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = p.text)
            Text(message, fontSize = 13.sp, color = p.text2)
        }
    }
}

@Composable
fun PrimaryButton(text: String, busy: Boolean = false, enabled: Boolean = true, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, shape = RoundedCornerShape(12.dp),
        modifier = Modifier.fillMaxWidth().height(48.dp)) {
        if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
        else Text(text, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun SecondaryButton(text: String, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(10.dp)) { Text(text, fontWeight = FontWeight.SemiBold) }
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun <T> Segmented(value: T, options: List<Pair<T, String>>, onChange: (T) -> Unit, modifier: Modifier = Modifier) {
    SingleChoiceSegmentedButtonRow(modifier.fillMaxWidth()) {
        options.forEachIndexed { i, (v, label) ->
            SegmentedButton(selected = v == value, onClick = { onChange(v) }, shape = SegmentedButtonDefaults.itemShape(i, options.size),
                icon = {}) { Text(label, fontSize = 13.sp, maxLines = 1) }
        }
    }
}

/** Label on the left, dropdown value on the right. */
@Composable
fun <T> Choice(label: String, value: T, options: List<Pair<T, String>>, onChange: (T) -> Unit) {
    val p = LocalPalette.current
    var open by remember { mutableStateOf(false) }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Text(label, color = p.text, modifier = Modifier.weight(1f))
        Box {
            TextButton(onClick = { open = true }) { Text((options.firstOrNull { it.first == value }?.second ?: "—") + "  ▾", color = p.accent) }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { (v, l) -> DropdownMenuItem(text = { Text(l) }, onClick = { onChange(v); open = false }) }
            }
        }
    }
}

@Composable
fun OrbPill(state: String?, side: String?) = when (state) {
    "triggered" -> Pill("${if (side == "short") "▼" else "▲"} ORB ${side.orEmpty()}", if (side == "short") Tone.Down else Tone.Up)
    "expired" -> Pill("ORB expired")
    else -> Pill("ORB waiting", Tone.Warn)
}

@Composable
fun TrendPill(trend: String?) = when (trend) {
    "up" -> Pill("Trend up", Tone.Up)
    "down" -> Pill("Trend down", Tone.Down)
    else -> Pill("Trend mixed")
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Legend(vararg items: Pair<Color, String>) {
    val p = LocalPalette.current
    FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items.forEach { (c, l) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(width = 12.dp, height = 3.dp).clip(RoundedCornerShape(2.dp)).background(c))
                Spacer(Modifier.width(6.dp))
                Text(l, fontSize = 12.sp, color = p.text2)
            }
        }
    }
}
