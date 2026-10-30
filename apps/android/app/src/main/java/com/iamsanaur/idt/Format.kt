package com.iamsanaur.idt

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs

/** Indian number formatting (1,23,456.78), rupees, percentages and IST times. */
object Fmt {
    private val IST: ZoneId = ZoneId.of("Asia/Kolkata")

    /** Indian grouping: last three digits, then groups of two. Locale-independent. */
    fun num(v: Double?, dp: Int = 2): String {
        if (v == null || v.isNaN() || v.isInfinite()) return "—"
        val pattern = if (dp > 0) "0." + "0".repeat(dp) else "0"
        val fixed = DecimalFormat(pattern, DecimalFormatSymbols(Locale.US)).format(abs(v))
        val intPart = fixed.substringBefore('.')
        val frac = if (dp > 0) "." + fixed.substringAfter('.') else ""
        val grouped = if (intPart.length <= 3) intPart else {
            val head = intPart.dropLast(3)
            head.reversed().chunked(2).joinToString(",").reversed() + "," + intPart.takeLast(3)
        }
        return (if (v < 0) "-" else "") + grouped + frac
    }

    fun rupees(v: Double?, dp: Int = 0): String =
        if (v == null || v.isNaN()) "—" else "${if (v < 0) "−" else ""}₹${num(abs(v), dp)}"

    fun signedRupees(v: Double?, dp: Int = 0): String =
        if (v == null || v.isNaN()) "—" else "${if (v > 0) "+" else if (v < 0) "−" else ""}₹${num(abs(v), dp)}"

    fun pct(v: Double?, dp: Int = 2): String =
        if (v == null || v.isNaN()) "—" else "${if (v > 0) "+" else ""}${String.format(Locale.US, "%.${dp}f", v)}%"

    fun compact(v: Double?): String {
        if (v == null || v.isNaN()) return "—"
        val a = abs(v)
        val s = if (v < 0) "−" else ""
        return when {
            a >= 1e7 -> "$s${String.format(Locale.US, "%.2f", a / 1e7)} Cr"
            a >= 1e5 -> "$s${String.format(Locale.US, "%.2f", a / 1e5)} L"
            a >= 1e3 -> "$s${String.format(Locale.US, "%.1f", a / 1e3)} K"
            else -> "$s${String.format(Locale.US, "%.0f", a)}"
        }
    }

    fun time(iso: String?): String = format(iso, "HH:mm")
    fun dayTime(iso: String?): String = format(iso, "d MMM, HH:mm")

    private fun format(iso: String?, pattern: String): String = try {
        OffsetDateTime.parse(iso).atZoneSameInstant(IST).format(DateTimeFormatter.ofPattern(pattern, Locale.ENGLISH))
    } catch (e: Exception) {
        "—"
    }
}
