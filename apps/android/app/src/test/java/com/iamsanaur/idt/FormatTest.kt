package com.iamsanaur.idt

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FormatTest {
    @Test fun indianGrouping() {
        assertEquals("1,23,45,678.90", Fmt.num(12345678.9))
        assertEquals("999.00", Fmt.num(999.0))
        assertEquals("₹5,404", Fmt.rupees(5404.1))
        assertEquals("−₹2,702", Fmt.signedRupees(-2702.05))
        assertEquals("+0.31%", Fmt.pct(0.314))
        assertEquals("40.03 L", Fmt.compact(4_003_220.0))
        assertEquals("12.35 Cr", Fmt.compact(123_456_789.0))
    }

    @Test fun istTimes() {
        assertEquals("09:45", Fmt.time("2026-10-29T09:45:00+05:30"))
        assertEquals("09:45", Fmt.time("2026-10-29T04:15:00Z"))
        assertEquals("—", Fmt.time(null))
    }

    @Test fun pairingUri() {
        assertEquals(Connection("http://192.168.1.5:8742", "abc123"), Connection.fromPairing("idt://pair?u=http%3A%2F%2F192.168.1.5%3A8742&t=abc123"))
        assertNull(Connection.fromPairing("https://example.com/?u=x&t=y"))
        assertNull(Connection.fromPairing("idt://pair?u=http%3A%2F%2Fh"))
    }
}
