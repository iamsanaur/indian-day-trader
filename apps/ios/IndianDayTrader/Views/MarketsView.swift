import Charts
import SwiftUI

let indexNames: [String: String] = [
    "NIFTY": "Nifty 50", "BANKNIFTY": "Nifty Bank", "FINNIFTY": "Nifty Financial",
    "MIDCPNIFTY": "Nifty Midcap Select", "SENSEX": "BSE Sensex", "INDIAVIX": "India VIX",
]
let boardOrder = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "INDIAVIX"]

struct MarketsView: View {
    @EnvironmentObject var app: AppModel
    @StateObject private var board = Loader<Board>()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    ErrorBanner(error: board.error)
                    if let b = board.value {
                        ForEach(boardOrder.filter { b.indices[$0] != nil }, id: \.self) { sym in
                            NavigationLink(value: sym) { IndexCard(symbol: sym, entry: b.indices[sym]!) }
                                .buttonStyle(.plain)
                        }
                    } else if board.loading {
                        ForEach(0..<4, id: \.self) { _ in RoundedRectangle(cornerRadius: 16).fill(Palette.surface2).frame(height: 170) }
                    }
                }
                .padding(16)
            }
            .screen()
            .navigationTitle("Markets")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { ModeBadge() } }
            .navigationDestination(for: String.self) { IndexDetailView(symbol: $0) }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    func load() async { await board.run { try await app.api.call("/indices") } }
}

struct ModeBadge: View {
    @EnvironmentObject var app: AppModel
    var body: some View {
        if let s = app.status {
            HStack(spacing: 6) {
                Pill(text: s.mode, tone: s.mode == "paper" ? .warn : .accent)
                if s.demo == true { Pill(text: "demo") }
            }
        }
    }
}

struct IndexCard: View {
    var symbol: String
    var entry: BoardEntry

    var body: some View {
        Card {
            if let err = entry.error {
                Text(symbol).font(.headline)
                Text(err).font(.footnote).foregroundStyle(Palette.down)
            } else {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(symbol).font(.headline)
                        Text(indexNames[symbol] ?? "").font(.caption).foregroundStyle(Palette.muted)
                    }
                    Spacer()
                    Pill(text: Fmt.pct(entry.changePct), tone: Tone.of(entry.changePct))
                }
                Text(Fmt.num(entry.last)).font(.system(size: 30, weight: .bold)).monospacedDigit()
                if let d = entry.day, let last = entry.last { DayRangeBar(day: d, last: last) }
                if symbol != "INDIAVIX" {
                    HStack { OrbPill(orb: entry.orb); TrendPill(trend: entry.ema?.trend) }
                } else {
                    Text("Implied volatility gauge — higher means richer option premiums.").font(.caption).foregroundStyle(Palette.text2)
                }
            }
        }
    }
}

struct DayRangeBar: View {
    var day: DayRange
    var last: Double
    var body: some View {
        VStack(spacing: 6) {
            GeometryReader { geo in
                let span = max(day.high - day.low, 0.0001)
                let x = min(max((last - day.low) / span, 0), 1) * geo.size.width
                ZStack(alignment: .leading) {
                    Capsule().fill(Palette.surface2).frame(height: 6)
                    Circle().fill(Palette.text).overlay(Circle().stroke(Palette.surface, lineWidth: 2))
                        .frame(width: 12, height: 12).offset(x: x - 6)
                }
            }
            .frame(height: 12)
            HStack {
                Text("L \(Fmt.num(day.low))"); Spacer(); Text("H \(Fmt.num(day.high))")
            }
            .font(.caption).monospacedDigit().foregroundStyle(Palette.muted)
        }
    }
}

struct IndexDetailView: View {
    @EnvironmentObject var app: AppModel
    var symbol: String
    @State private var interval = 5
    @State private var days = 2
    @State private var future = false
    @State private var planning = false
    @State private var planError: Error?
    @StateObject private var view = Loader<IndexView>()

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Picker("Interval", selection: $interval) { ForEach([1, 5, 15], id: \.self) { Text("\($0)m").tag($0) } }
                    .pickerStyle(.segmented)
                HStack {
                    Picker("Days", selection: $days) { ForEach([1, 2, 5], id: \.self) { Text("\($0)D").tag($0) } }.pickerStyle(.segmented)
                    if symbol != "INDIAVIX" {
                        Picker("Instrument", selection: $future) { Text("Spot").tag(false); Text("Future").tag(true) }.pickerStyle(.segmented)
                    }
                }
                ErrorBanner(error: view.error ?? planError)
                if let v = view.value {
                    Card {
                        HStack(alignment: .firstTextBaseline) {
                            Text(Fmt.num(v.last)).font(.title.bold()).monospacedDigit()
                            Text(Fmt.pct(v.changePct)).foregroundStyle(Tone.of(v.changePct).fg).font(.headline)
                            Spacer()
                            Text("\(Fmt.time(v.asOf)) IST").font(.caption).foregroundStyle(Palette.muted)
                        }
                        CandleChartView(view: v).frame(height: 300)
                        FlowLegend(hasVwap: v.vwap != nil)
                    }
                    Card(title: "Opening range", trailing: AnyView(OrbPill(orb: v.orb))) {
                        if let r = v.openingRange {
                            StatGrid(items: [StatView(label: "High", value: Fmt.num(r.high)), StatView(label: "Low", value: Fmt.num(r.low)),
                                             StatView(label: "Mid", value: Fmt.num(r.mid))], columns: 3)
                        }
                        if v.orb.state == "triggered" {
                            Text("Triggered \(v.orb.side ?? "") at \(Fmt.num(v.orb.entry)) on the \(Fmt.time(v.orb.triggerTime)) bar")
                                .font(.footnote).foregroundStyle(Palette.text2)
                        }
                        PrimaryButton(title: "Plan a trade from this setup", busy: planning) { Task { await planTrade() } }
                    }
                    Card(title: "Levels") {
                        let rows: [(String, Double?)] = [
                            ("Prev high (PDH)", v.prevDay?.high), ("Prev low (PDL)", v.prevDay?.low), ("Prev close", v.prevDay?.close),
                            ("R1", v.cpr["r1"]), ("CPR top (TC)", v.cpr["tc"]), ("Pivot", v.cpr["pivot"]), ("CPR bottom (BC)", v.cpr["bc"]),
                            ("S1", v.cpr["s1"]), ("EMA 9", v.ema.ema9), ("EMA 21", v.ema.ema21), ("VWAP", v.vwap),
                        ]
                        ForEach(rows, id: \.0) { row in
                            HStack { Text(row.0).foregroundStyle(Palette.text2); Spacer(); Text(Fmt.num(row.1)).monospacedDigit() }
                                .font(.callout)
                            Divider()
                        }
                        HStack { TrendPill(trend: v.ema.trend); Spacer() }
                        if let read = v.cprRead { Text(read).font(.footnote).foregroundStyle(Palette.text2) }
                        if v.vwap == nil && !future {
                            Text("Spot indices have no volume, so VWAP is blank. Switch to Future for VWAP.").font(.caption).foregroundStyle(Palette.muted)
                        }
                    }
                } else if view.loading {
                    RoundedRectangle(cornerRadius: 16).fill(Palette.surface2).frame(height: 340)
                }
            }
            .padding(16)
        }
        .screen()
        .navigationTitle(future ? "\(symbol) FUT" : symbol)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: "\(interval)-\(days)-\(future)") {
            await view.run { try await app.api.call("/index/\(symbol)?interval=\(interval)&days=\(days)&future=\(future)") }
        }
    }

    func planTrade() async {
        planning = true
        defer { planning = false }
        do {
            let _: SetupState = try await app.api.post("/entry/\(symbol)", ["setup": "orb", "write": true])
            planError = nil
            NotificationCenter.default.post(name: .openTradeTab, object: nil)
        } catch { planError = error }
    }
}

extension Notification.Name {
    static let openTradeTab = Notification.Name("idt.openTradeTab")
}

struct FlowLegend: View {
    var hasVwap: Bool
    var body: some View {
        ViewThatFits {
            HStack(spacing: 12) { items }
            VStack(alignment: .leading, spacing: 6) { items }
        }
    }
    @ViewBuilder var items: some View {
        LegendDot(color: Palette.series1, label: "EMA 9", line: true)
        LegendDot(color: Palette.series2, label: "EMA 21", line: true)
        if hasVwap { LegendDot(color: Palette.series3, label: "VWAP", line: true) }
        LegendDot(color: Palette.accent, label: "Opening range", line: true)
        LegendDot(color: Palette.muted, label: "PDH / PDL", line: true)
    }
}

/// Candlesticks with EMA overlays and level lines. X is the bar index so overnight gaps collapse.
struct CandleChartView: View {
    var view: IndexView
    @State private var selected: Int?

    var body: some View {
        let c = view.candles
        let lows = c.map(\.l) + [view.openingRange?.low, view.prevDay?.low].compactMap { $0 }
        let highs = c.map(\.h) + [view.openingRange?.high, view.prevDay?.high].compactMap { $0 }
        let lo = lows.min() ?? 0, hi = highs.max() ?? 1
        let pad = (hi - lo) * 0.04

        Chart {
            ForEach(Array(c.enumerated()), id: \.offset) { i, k in
                RuleMark(x: .value("Bar", i), yStart: .value("Low", k.l), yEnd: .value("High", k.h))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .foregroundStyle(k.c >= k.o ? Palette.upMark : Palette.downMark)
                RectangleMark(x: .value("Bar", i), yStart: .value("Open", k.o), yEnd: .value("Close", k.c == k.o ? k.o + (hi - lo) * 0.001 : k.c), width: .ratio(0.7))
                    .foregroundStyle(k.c >= k.o ? Palette.upMark : Palette.downMark)
            }
            ForEach(lineSeries(), id: \.id) { p in
                LineMark(x: .value("Bar", p.i), y: .value("Value", p.v), series: .value("Series", p.name))
                    .foregroundStyle(p.color)
                    .lineStyle(StrokeStyle(lineWidth: 1.6))
            }
            if let r = view.openingRange {
                RuleMark(y: .value("OR high", r.high)).foregroundStyle(Palette.accent).lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                RuleMark(y: .value("OR low", r.low)).foregroundStyle(Palette.accent).lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
            }
            if let p = view.prevDay {
                RuleMark(y: .value("PDH", p.high)).foregroundStyle(Palette.muted).lineStyle(StrokeStyle(lineWidth: 1, dash: [1, 3]))
                RuleMark(y: .value("PDL", p.low)).foregroundStyle(Palette.muted).lineStyle(StrokeStyle(lineWidth: 1, dash: [1, 3]))
            }
            if let s = selected, s < c.count {
                RuleMark(x: .value("Bar", s)).foregroundStyle(Palette.muted.opacity(0.6))
                    .annotation(position: .top, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(Fmt.dayTime(ISO8601DateFormatter().string(from: Date(timeIntervalSince1970: c[s].t)))).font(.caption2.bold())
                            Text("O \(Fmt.num(c[s].o))  H \(Fmt.num(c[s].h))").font(.caption2)
                            Text("L \(Fmt.num(c[s].l))  C \(Fmt.num(c[s].c))").font(.caption2)
                        }
                        .monospacedDigit().padding(6)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Palette.border))
                    }
            }
        }
        .chartYScale(domain: (lo - pad)...(hi + pad))
        .chartXAxis(.hidden)
        .chartYAxis { AxisMarks(position: .trailing) { AxisGridLine().foregroundStyle(Palette.border); AxisValueLabel().font(.caption2) } }
        .chartXSelection(value: $selected)
        .accessibilityLabel("\(view.symbol) candlestick chart")
    }

    struct Pt { let id: String; let i: Int; let v: Double; let name: String; let color: Color }

    func lineSeries() -> [Pt] {
        var out: [Pt] = []
        for (name, vals, color) in [("EMA 9", view.series.ema9, Palette.series1), ("EMA 21", view.series.ema21, Palette.series2),
                                    ("VWAP", view.series.vwap, Palette.series3)] {
            for (i, v) in vals.enumerated() { if let v { out.append(Pt(id: "\(name)\(i)", i: i, v: v, name: name, color: color)) } }
        }
        return out
    }
}
