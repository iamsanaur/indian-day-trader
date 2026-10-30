package com.iamsanaur.idt

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.net.URLDecoder
import java.util.concurrent.TimeUnit

data class Connection(val url: String, val token: String) {
    val configured get() = url.isNotBlank() && token.isNotBlank()

    companion object {
        /** Parses `idt://pair?u=<url>&t=<token>` printed as a QR code by `idt serve`. */
        fun fromPairing(uri: String): Connection? = try {
            val u = URI(uri)
            if (u.scheme != "idt" || u.host != "pair") null else {
                val q = (u.rawQuery ?: "").split("&").mapNotNull {
                    val i = it.indexOf('=')
                    if (i <= 0) null else it.substring(0, i) to URLDecoder.decode(it.substring(i + 1), "UTF-8")
                }.toMap()
                val url = q["u"].orEmpty()
                val token = q["t"].orEmpty()
                if (url.isBlank() || token.isBlank()) null else Connection(url, token)
            }
        } catch (e: Exception) {
            null
        }
    }
}

/** Stored in app-private SharedPreferences (sandboxed per app). */
class ConnectionStore(context: Context) {
    private val prefs = context.getSharedPreferences("idt", Context.MODE_PRIVATE)
    fun load() = Connection(prefs.getString("url", "").orEmpty(), prefs.getString("token", "").orEmpty())
    fun save(c: Connection) = prefs.edit().putString("url", c.url).putString("token", c.token).apply()
    var theme: String
        get() = prefs.getString("theme", "system").orEmpty()
        set(v) = prefs.edit().putString("theme", v).apply()
}

class ApiException(message: String, val status: Int) : Exception(message)

class Api(private val conn: Connection) {
    private val base get() = conn.url.trim().trimEnd('/')
    private val json = "application/json".toMediaType()

    private fun request(path: String, method: String, body: JSONObject?): Request {
        if (!conn.configured) throw ApiException("Not paired. Open More › Settings, or scan the QR from idt serve with your camera.", 0)
        val b = Request.Builder().url("$base/api$path").header("Authorization", "Bearer ${conn.token}")
        return when (method) {
            "GET" -> b.get()
            "DELETE" -> b.delete()
            else -> b.method(method, (body ?: JSONObject()).toString().toRequestBody(json))
        }.build()
    }

    private suspend fun raw(path: String, method: String, body: JSONObject?): String = withContext(Dispatchers.IO) {
        client.newCall(request(path, method, body)).execute().use { r ->
            val text = r.body?.string().orEmpty()
            if (!r.isSuccessful) {
                val obj = runCatching { JSONObject(text) }.getOrNull()
                val msg = if (r.code == 401) "Token rejected. Re-pair in Settings."
                else obj?.optString("error")?.takeIf { it.isNotBlank() } ?: obj?.optString("detail")?.takeIf { it.isNotBlank() } ?: "HTTP ${r.code}"
                throw ApiException(msg, r.code)
            }
            text
        }
    }

    suspend fun obj(path: String, method: String = "GET", body: JSONObject? = null) = JSONObject(raw(path, method, body))
    suspend fun arr(path: String, method: String = "GET", body: JSONObject? = null) = JSONArray(raw(path, method, body))
    suspend fun post(path: String, body: JSONObject = JSONObject()) = obj(path, "POST", body)

    /** Server-sent events; calls onEvent(event, data) until the call is cancelled. */
    suspend fun events(onEvent: (String, String) -> Unit) = withContext(Dispatchers.IO) {
        val streaming = client.newBuilder().readTimeout(0, TimeUnit.SECONDS).build()
        streaming.newCall(request("/events?interval=15", "GET", null)).execute().use { r ->
            val source = r.body?.source() ?: return@use
            var event = "message"
            while (!source.exhausted()) {
                val line = source.readUtf8Line() ?: break
                when {
                    line.startsWith("event:") -> event = line.removePrefix("event:").trim()
                    line.startsWith("data:") -> { onEvent(event, line.removePrefix("data:").trim()); event = "message" }
                }
            }
        }
    }

    companion object {
        private val client = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
    }
}

// --- org.json helpers -------------------------------------------------------------------

fun JSONObject.d(key: String): Double? = if (!has(key) || isNull(key)) null else optDouble(key).takeIf { !it.isNaN() }
fun JSONObject.s(key: String): String? = if (!has(key) || isNull(key)) null else optString(key)
fun JSONObject.o(key: String): JSONObject? = optJSONObject(key)
fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
fun JSONArray.doubles(): List<Double?> = (0 until length()).map { if (isNull(it)) null else optDouble(it) }
fun JSONArray.strings(): List<String> = (0 until length()).map { optString(it) }
fun JSONObject.keysList(): List<String> = keys().asSequence().toList()

fun jsonOf(vararg pairs: Pair<String, Any?>) = JSONObject().apply { pairs.forEach { (k, v) -> if (v != null) put(k, v) } }
