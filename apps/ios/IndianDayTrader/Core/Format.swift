import Foundation

/// Indian number formatting (1,23,456.78), rupees, percentages and IST times.
enum Fmt {
    private static func grouped(_ dp: Int) -> NumberFormatter {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "en_IN")
        f.numberStyle = .decimal
        f.minimumFractionDigits = dp
        f.maximumFractionDigits = dp
        return f
    }

    static func num(_ v: Double?, _ dp: Int = 2) -> String {
        guard let v, v.isFinite else { return "—" }
        return grouped(dp).string(from: NSNumber(value: v)) ?? "—"
    }

    static func rupees(_ v: Double?, _ dp: Int = 0) -> String {
        guard let v, v.isFinite else { return "—" }
        return "\(v < 0 ? "−" : "")₹\(num(abs(v), dp))"
    }

    static func signedRupees(_ v: Double?, _ dp: Int = 0) -> String {
        guard let v, v.isFinite else { return "—" }
        return "\(v > 0 ? "+" : v < 0 ? "−" : "")₹\(num(abs(v), dp))"
    }

    static func pct(_ v: Double?, _ dp: Int = 2) -> String {
        guard let v, v.isFinite else { return "—" }
        return "\(v > 0 ? "+" : "")\(String(format: "%.\(dp)f", v))%"
    }

    /// Lakh / crore shorthand.
    static func compact(_ v: Double?) -> String {
        guard let v, v.isFinite else { return "—" }
        let a = abs(v), s = v < 0 ? "−" : ""
        if a >= 1e7 { return "\(s)\(String(format: "%.2f", a / 1e7)) Cr" }
        if a >= 1e5 { return "\(s)\(String(format: "%.2f", a / 1e5)) L" }
        if a >= 1e3 { return "\(s)\(String(format: "%.1f", a / 1e3)) K" }
        return "\(s)\(String(format: "%.0f", a))"
    }

    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let isoPlain = ISO8601DateFormatter()
    private static let ist = TimeZone(identifier: "Asia/Kolkata")!

    static func date(_ s: String?) -> Date? {
        guard let s else { return nil }
        return iso.date(from: s) ?? isoPlain.date(from: s)
    }

    static func time(_ s: String?) -> String {
        guard let d = date(s) else { return "—" }
        let f = DateFormatter()
        f.timeZone = ist
        f.dateFormat = "HH:mm"
        return f.string(from: d)
    }

    static func dayTime(_ s: String?) -> String {
        guard let d = date(s) else { return "—" }
        let f = DateFormatter()
        f.timeZone = ist
        f.locale = Locale(identifier: "en_IN")
        f.dateFormat = "d MMM, HH:mm"
        return f.string(from: d)
    }
}
