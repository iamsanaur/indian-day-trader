import Charts
import SwiftUI

let underlyings = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"]

struct OptionsView: View {
    @EnvironmentObject var app: AppModel
    @State private var underlying = "NIFTY"
    @State private var expiry = ""
    @State private var showChange = false
    @StateObject private var chain = Loader<Chain>()
    @StateObject private var expiries = Loader<Expiries>()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        Picker("Underlying", selection: $underlying) { ForEach(underlyings, id: \.self) { Text($0).tag($0) } }
                            .pickerStyle(.segmented).frame(minWidth: 460)
                    }
                    HStack {
                        Text("Expiry").font(.subheadline).foregroundStyle(Palette.text2)
                        Spacer()
                        Picker("Expiry", selection: $expiry) {
                            Text("Nearest").tag("")
                            ForEach(expiries.value?.expiries ?? [], id: \.self) { Text($0).tag($0) }
                        }
                    }
                    ErrorBanner(error: chain.error)
                    if let c = chain.value { content(c) } else if chain.loading {
                        RoundedRectangle(cornerRadius: 16).fill(Palette.surface2).frame(height: 300)
                    }
                }
                .padding(16)
            }
            .screen()
            .navigationTitle("Option chain")
            .task(id: underlying) {
                expiry = ""
                await expiries.run { try await app.api.call("/expiries/\(underlying)") }
            }
            .task(id: "\(underlying)|\(expiry)") {
                await chain.run { try await app.api.call("/chain/\(underlying)?strikes=12\(expiry.isEmpty ? "" : "&expiry=\(expiry)")") }
            }
            .refreshable { await chain.run { try await app.api.call("/chain/\(underlying)?strikes=12\(expiry.isEmpty ? "" : "&expiry=\(expiry)")") } }
        }
    }

    @ViewBuilder func content(_ c: Chain) -> some View {
        Card(title: "\(c.underlying) · \(c.expiry) · \(Fmt.num(c.daysToExpiry, 1)) days · lot \(c.lotSize)") {
            StatGrid(items: [
                StatView(label: "Spot", value: Fmt.num(c.spot)),
                StatView(label: "ATM IV", value: c.atmIv.map { "\(Fmt.num($0, 1))%" } ?? "—"),
                StatView(label: "PCR (OI)", value: Fmt.num(c.pcr.oi), hint: "Δ OI PCR \(Fmt.num(c.pcr.oiChange))"),
                StatView(label: "Max pain", value: Fmt.num(c.maxPain, 0), hint: Fmt.pct(c.maxPainDistancePct)),
                StatView(label: "Expected move", value: "± \(Fmt.num(c.expectedMove.points, 0))",
                         hint: "\(Fmt.num(c.expectedMove.range.first, 0)) – \(Fmt.num(c.expectedMove.range.last, 0))"),
                StatView(label: "ATM straddle", value: Fmt.num(c.atmStraddle)),
            ], columns: 3)
            Text("Positioning: \(c.bias). Describes where open interest sits — not a prediction.")
                .font(.caption).foregroundStyle(Palette.text2)
        }
        HStack(alignment: .top, spacing: 12) {
            WallCard(title: "Resistance", subtitle: "call writers", walls: c.walls.resistance)
            WallCard(title: "Support", subtitle: "put writers", walls: c.walls.support)
        }
        Card(title: "Open interest by strike", trailing: AnyView(
            Picker("", selection: $showChange) { Text("OI").tag(false); Text("Change").tag(true) }.pickerStyle(.segmented).frame(width: 140)
        )) {
            OIChartView(chain: c, change: showChange).frame(height: 220)
            HStack(spacing: 14) { LegendDot(color: Palette.series1, label: "Calls (CE)"); LegendDot(color: Palette.series2, label: "Puts (PE)") }
        }
        Card(title: "Chain") {
            HStack {
                Text("Call LTP · OI").frame(maxWidth: .infinity, alignment: .leading)
                Text("Strike").frame(width: 70)
                Text("Put LTP · OI").frame(maxWidth: .infinity, alignment: .trailing)
            }
            .font(.caption.weight(.semibold)).foregroundStyle(Palette.muted)
            let maxOI = c.table.flatMap { [$0.ce?.oi ?? 0, $0.pe?.oi ?? 0] }.max() ?? 1
            ForEach(c.table) { r in
                ChainRowView(row: r, atm: r.strike == c.atm, belowSpot: r.strike < c.spot, maxOI: maxOI)
                Divider()
            }
        }
    }
}

struct WallCard: View {
    var title: String
    var subtitle: String
    var walls: [Wall]
    var body: some View {
        Card(title: title) {
            Text(subtitle).font(.caption).foregroundStyle(Palette.muted)
            ForEach(walls, id: \.strike) { w in
                HStack { Text(Fmt.num(w.strike, 0)).bold(); Spacer(); Text(Fmt.compact(w.oi)).foregroundStyle(Palette.text2) }
                    .font(.callout).monospacedDigit()
            }
        }
    }
}

struct ChainRowView: View {
    var row: ChainRow
    var atm: Bool
    var belowSpot: Bool
    var maxOI: Double

    var body: some View {
        HStack(spacing: 8) {
            side(row.ce, color: Palette.series1, alignment: .leading)
            VStack(spacing: 2) {
                Text(Fmt.num(row.strike, 0)).font(.callout.bold()).monospacedDigit()
                if atm { Pill(text: "ATM", tone: .accent) }
            }
            .frame(width: 70)
            .padding(.vertical, 4)
            .background(belowSpot ? Palette.surface2 : .clear, in: RoundedRectangle(cornerRadius: 6))
            side(row.pe, color: Palette.series2, alignment: .trailing)
        }
        .padding(.vertical, 2)
        .background(atm ? Palette.accentSoft.opacity(0.6) : .clear)
    }

    @ViewBuilder func side(_ s: OptionSide?, color: Color, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 3) {
            if let s {
                Text(Fmt.num(s.ltp)).font(.callout.weight(.semibold)).monospacedDigit()
                GeometryReader { g in
                    HStack {
                        if alignment == .trailing { Spacer(minLength: 0) }
                        Capsule().fill(color).frame(width: max(2, g.size.width * s.oi / maxOI), height: 5)
                        if alignment == .leading { Spacer(minLength: 0) }
                    }
                }
                .frame(height: 5)
                Text("\(Fmt.compact(s.oi)) · \(s.oiChange >= 0 ? "+" : "")\(Fmt.compact(s.oiChange))")
                    .font(.caption2).monospacedDigit().foregroundStyle(s.oiChange >= 0 ? Palette.up : Palette.down)
                Text(s.buildup).font(.caption2).foregroundStyle(Palette.muted)
            } else {
                Text("—").foregroundStyle(Palette.muted)
            }
        }
        .frame(maxWidth: .infinity, alignment: alignment == .leading ? .leading : .trailing)
    }
}

struct OIChartView: View {
    var chain: Chain
    var change: Bool

    struct Bar: Identifiable {
        let id: String
        let strike: Double
        let value: Double
        let side: String
        var label: String { String(Int(strike)) }
        var color: Color { side == "Calls" ? Palette.series1 : Palette.series2 }
    }

    @ChartContentBuilder func mark(_ b: Bar) -> some ChartContent {
        BarMark(x: .value("Strike", b.label), y: .value("OI", b.value))
            .position(by: .value("Side", b.side))
            .foregroundStyle(b.color)
            .cornerRadius(2)
    }

    var body: some View {
        let bars = chain.table.flatMap { r -> [Bar] in
            [Bar(id: "c\(r.strike)", strike: r.strike, value: change ? (r.ce?.oiChange ?? 0) : (r.ce?.oi ?? 0), side: "Calls"),
             Bar(id: "p\(r.strike)", strike: r.strike, value: change ? (r.pe?.oiChange ?? 0) : (r.pe?.oi ?? 0), side: "Puts")]
        }
        Chart {
            ForEach(bars) { b in mark(b) }
            RuleMark(x: .value("Strike", String(Int(chain.atm))))
                .foregroundStyle(Palette.text2).lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                .annotation(position: .top, alignment: .leading) { Text("ATM").font(.caption2).foregroundStyle(Palette.text2) }
        }
        .chartLegend(.hidden)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 6)) { AxisValueLabel().font(.caption2) }
        }
        .chartYAxis { AxisMarks { v in AxisGridLine().foregroundStyle(Palette.border); AxisValueLabel { Text(Fmt.compact(v.as(Double.self))).font(.caption2) } } }
        .accessibilityLabel(change ? "Change in open interest by strike" : "Open interest by strike")
    }
}
