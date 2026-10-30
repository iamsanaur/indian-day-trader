import XCTest
@testable import IndianDayTrader

final class FormatTests: XCTestCase {
    func testIndianGrouping() {
        XCTAssertEqual(Fmt.num(12345678.9), "1,23,45,678.90")
        XCTAssertEqual(Fmt.rupees(5404.1), "₹5,404")
        XCTAssertEqual(Fmt.signedRupees(-2702.05), "−₹2,702")
        XCTAssertEqual(Fmt.pct(0.314), "+0.31%")
        XCTAssertEqual(Fmt.compact(4_003_220), "40.03 L")
        XCTAssertEqual(Fmt.compact(123_456_789), "12.35 Cr")
    }

    func testISTTime() {
        XCTAssertEqual(Fmt.time("2026-10-29T09:45:00+05:30"), "09:45")
        XCTAssertEqual(Fmt.time("2026-10-29T04:15:00Z"), "09:45")
    }
}

final class PairingTests: XCTestCase {
    func testParsesPairingURI() {
        let c = Connection.fromPairing(URL(string: "idt://pair?u=http%3A%2F%2F192.168.1.5%3A8742&t=abc123")!)
        XCTAssertEqual(c, Connection(url: "http://192.168.1.5:8742", token: "abc123"))
        XCTAssertNil(Connection.fromPairing(URL(string: "https://example.com/?u=x&t=y")!))
        XCTAssertNil(Connection.fromPairing(URL(string: "idt://pair?u=http%3A%2F%2Fh")!))
    }
}

final class DecodingTests: XCTestCase {
    func testDecodesRiskAndTicketShapes() throws {
        let risk = #"{"verdict":"PASS","reasons":[],"checks":[{"rule":"market open","ok":true,"detail":"phase: open"}],"order_hash":"26cd6fb76850f64e","ts":"x","mode":"paper"}"#
        let r = try APIClient.decoder.decode(RiskVerdict.self, from: Data(risk.utf8))
        XCTAssertEqual(r.orderHash, "26cd6fb76850f64e")
        XCTAssertTrue(r.checks[0].ok)

        let ticket = #"{"mode":"paper","order_hash":"h","symbol":"NIFTY","kind":"strategy","entries":[{"action":"BUY","symbol":"NIFTY 2026-11-03 26000 CE","exchange":"NSE","segment":"FNO","product":"MIS","order_type":"LIMIT","price":156.87,"quantity":65,"lots":1,"validity":"DAY","security_id":"1"}],"exits":[{"action":"CLOSE ALL LEGS","condition":"combined P/L <= Rs -2,702","note":"stop"}],"oco":"o","square_off":"15:15","loss_at_stop":2831.81,"profit_at_target":3923.32,"margin":{"total":3200.0,"source":"fixture"},"charges":{"if_stopped":1,"if_target":1},"confirm":"c"}"#
        let t = try APIClient.decoder.decode(Ticket.self, from: Data(ticket.utf8))
        XCTAssertEqual(t.entries.first?.orderType, "LIMIT")
        XCTAssertEqual(t.exits.first?["note"], .string("stop"))
    }

    func testCurveAllowsNulls() throws {
        let json = #"{"x":[1,2,null],"expiry":[0,1,null],"today":[0,0.5,null]}"#
        let c = try APIClient.decoder.decode(Curve.self, from: Data(json.utf8))
        XCTAssertNil(c.x[2])
    }
}
