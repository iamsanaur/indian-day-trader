import Foundation

/// Decodes any JSON value (used for loosely-typed fields such as ticket exits and config).
enum JSONValue: Codable, Hashable, CustomStringConvertible {
    case string(String), number(Double), bool(Bool), null, array([JSONValue]), object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([JSONValue].self) { self = .array(a) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let n): try c.encode(n)
        case .bool(let b): try c.encode(b)
        case .null: try c.encodeNil()
        case .array(let a): try c.encode(a)
        case .object(let o): try c.encode(o)
        }
    }

    var double: Double? { if case .number(let n) = self { n } else if case .string(let s) = self { Double(s) } else { nil } }
    var bool: Bool? { if case .bool(let b) = self { b } else { nil } }

    var description: String {
        switch self {
        case .string(let s): s
        case .number(let n): n.rounded() == n && abs(n) < 1e15 ? String(Int(n)) : String(format: "%.2f", n)
        case .bool(let b): b ? "yes" : "no"
        case .null: "—"
        case .array(let a): a.map(\.description).joined(separator: ", ")
        case .object: "{…}"
        }
    }
}

// MARK: - Markets

struct Orb: Codable, Hashable { var state: String; var side: String?; var triggerTime: String?; var entry: Double?; var detail: String? }
struct Ema: Codable, Hashable { var ema9: Double; var ema21: Double; var trend: String }
struct DayRange: Codable, Hashable { var open: Double; var high: Double; var low: Double }

struct BoardEntry: Codable, Hashable {
    var last: Double?
    var changePct: Double?
    var orb: Orb?
    var ema: Ema?
    var cprRead: String?
    var day: DayRange?
    var error: String?
}

struct Board: Codable { var asOf: String; var indices: [String: BoardEntry] }

struct Candle: Codable, Hashable { var t: Double; var o: Double; var h: Double; var l: Double; var c: Double; var v: Double }
struct OpeningRange: Codable, Hashable { var high: Double; var low: Double; var mid: Double; var width: Double }
struct PrevDay: Codable, Hashable { var date: String; var high: Double; var low: Double; var close: Double }
struct Series: Codable, Hashable { var ema9: [Double?]; var ema21: [Double?]; var vwap: [Double?] }

struct IndexView: Codable {
    var symbol: String
    var asOf: String
    var last: Double
    var changePct: Double?
    var day: DayRange
    var openingRange: OpeningRange?
    var orb: Orb
    var prevDay: PrevDay?
    var cpr: [String: Double]
    var cprRead: String?
    var ema: Ema
    var vwap: Double?
    var candles: [Candle]
    var series: Series
}

// MARK: - Options

struct OptionSide: Codable, Hashable { var ltp: Double; var iv: Double; var oi: Double; var oiChange: Double; var volume: Double; var delta: Double; var buildup: String }
struct ChainRow: Codable, Hashable, Identifiable { var strike: Double; var ce: OptionSide?; var pe: OptionSide?; var id: Double { strike } }
struct Wall: Codable, Hashable { var strike: Double; var oi: Double; var oiChange: Double }
struct Walls: Codable, Hashable { var resistance: [Wall]; var support: [Wall] }
struct PCR: Codable, Hashable { var oi: Double?; var volume: Double?; var oiChange: Double? }
struct ExpectedMove: Codable, Hashable { var points: Double; var range: [Double] }

struct Chain: Codable {
    var underlying: String
    var expiry: String
    var spot: Double
    var daysToExpiry: Double
    var atm: Double
    var atmIv: Double?
    var atmStraddle: Double
    var expectedMove: ExpectedMove
    var pcr: PCR
    var maxPain: Double
    var maxPainDistancePct: Double
    var walls: Walls
    var bias: String
    var lotSize: Int
    var table: [ChainRow]
}

struct Expiries: Codable { var expiries: [String] }

// MARK: - Strategy

struct Leg: Codable, Hashable { var kind: String; var strike: Double; var side: Int; var lots: Int; var premium: Double; var expiry: String; var iv: Double; var symbol: String }
struct Analysis: Codable, Hashable {
    var netPremium: Double
    var premiumType: String
    var maxProfit: Double?
    var maxLoss: Double?
    var unlimitedProfit: Bool
    var unlimitedLoss: Bool
    var breakevens: [Double]
    var naked: [String]
}
struct Greeks: Codable, Hashable { var delta: Double; var gamma: Double; var theta: Double; var vega: Double }
struct Margin: Codable, Hashable { var total: Double?; var source: String?; var error: String? }
struct Curve: Codable, Hashable { var x: [Double?]; var expiry: [Double?]; var today: [Double?] }

struct StrategyResult: Codable {
    var name: String
    var underlying: String
    var expiry: String
    var spot: Double
    var lotSize: Int
    var legs: [Leg]
    var analysis: Analysis
    var greeks: Greeks
    var margin: Margin
    var warning: String?
    var curve: Curve?
}

// MARK: - Trade flow

struct Plan: Codable {
    var symbol: String
    var kind: String
    var side: String
    var basis: String
    var contract: String?
    var unit: String
    var lotSize: Int
    var entry: Double
    var stop: Double?
    var target: Double?
    var stopPnl: Double?
    var targetPnl: Double?
    var underlyingStop: Double?
    var underlyingTarget: Double?
    var riskPerUnit: Double
    var rewardPerUnit: Double
    var rr: Double
    var stopRule: String
    var targetRule: String
    var squareoff: String
    var strategy: String?
}

struct SetupState: Codable { var symbol: String; var state: String; var side: String?; var entry: Double?; var triggerTime: String?; var range: OpeningRange? }
struct SavedStrategy: Codable { var name: String; var underlying: String; var expiry: String }
struct PlanState: Codable { var plan: Plan?; var setup: SetupState?; var strategy: SavedStrategy? }

struct OrderLeg: Codable, Hashable { var symbol: String; var side: String; var quantity: Int; var lots: Int?; var price: Double; var product: String }
struct Charges: Codable, Hashable { var ifStopped: Double; var ifTarget: Double }
struct Orders: Codable {
    var units: Int
    var unit: String
    var lotSize: Int
    var legs: [OrderLeg]
    var lossAtStop: Double
    var profitAtTarget: Double
    var charges: Charges
    var margin: Margin
    var notes: [String]
    var hash: String
}

struct RiskCheck: Codable, Hashable { var rule: String; var ok: Bool; var detail: String }
struct RiskVerdict: Codable { var verdict: String; var reasons: [String]; var checks: [RiskCheck]; var orderHash: String }

struct TicketEntry: Codable, Hashable { var action: String; var symbol: String; var product: String; var orderType: String; var price: Double; var quantity: Int; var lots: Int? }
struct Ticket: Codable {
    var mode: String
    var orderHash: String
    var symbol: String
    var entries: [TicketEntry]
    var exits: [[String: JSONValue]]
    var oco: String
    var squareOff: String?
    var lossAtStop: Double
    var profitAtTarget: Double
    var margin: Margin
}
struct Confirmation: Codable { var confirmed: String; var next: String }

struct PnlStats: Codable { var mean: Double; var median: Double; var p5: Double; var p95: Double }
struct MonteCarlo: Codable { var paths: Int; var pTarget: Double; var pStop: Double; var pFlat: Double; var pnlPerUnit: PnlStats; var expectedR: Double?; var sessionsSampled: Int }
struct Replay: Codable { var fired: Int?; var winRate: Double?; var avgR: Double?; var sessions: Int?; var skipped: String? }
struct TimeMachine: Codable { var monteCarlo: MonteCarlo; var replay: Replay; var caveat: String }

// MARK: - Alerts, journal, status

struct AlertItem: Codable, Identifiable, Hashable {
    var id: String
    var kind: String
    var symbol: String?
    var op: String?
    var value: JSONValue
    var label: String
    var fired: Bool
    var firedAt: String?
    var observed: JSONValue?
}

struct DhanStatus: Codable, Equatable {
    var connected: Bool
    var source: String?
    var clientIdSet: Bool
    var pinSet: Bool
    var totpLoginAvailable: Bool
    var clientName: String?
    var expiresAt: String?
    var expiresInSeconds: Int?
    var message: String

    var timeLeft: String {
        guard let s = expiresInSeconds, s > 0 else { return "" }
        return "\(s / 3600)h \(s % 3600 / 60)m left"
    }
}

struct Status: Codable {
    var now: String
    var phase: String
    var mode: String
    var dataProvider: String
    var tradesToday: Int
    var realisedToday: Double
    var limits: [String: JSONValue]
    var demo: Bool?
    var dhan: DhanStatus?
}

struct JournalEntry: Codable, Hashable { var type: String; var ts: String; var symbol: String?; var pnl: Double?; var kind: String?; var lossAtStop: Double?; var note: String? }

struct ConfigResponse: Codable { var config: [String: JSONValue]; var editable: [String] }

// MARK: - Research

struct Announcement: Codable, Hashable { var symbol: String?; var subject: String?; var detail: String?; var time: String? }
struct NewsResponse: Codable { var announcements: [Announcement]; var symbols: [String] }
struct BanResponse: Codable { var banList: [String] }
struct Deal: Codable, Hashable { var symbol: String?; var clientName: String?; var buySell: String?; var qty: String?; var watp: String? }
struct Deals: Codable { var bulk: [Deal]; var block: [Deal] }
struct Quarter: Codable, Hashable { var periodEnd: String?; var revenue: Double?; var netProfit: Double?; var eps: Double?; var revenueYoyPct: Double?; var netProfitYoyPct: Double? }
struct ResultsResponse: Codable { var quarters: [Quarter]; var note: String }
struct Health: Codable { var ok: Bool; var version: String; var demo: Bool }
