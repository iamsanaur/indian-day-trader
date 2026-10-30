import Charts
import SwiftUI

struct StrategyView: View {
    @EnvironmentObject var app: AppModel
    @State private var name = "bull-call-spread"
    @State private var underlying = "NIFTY"
    @State private var lots = 1
    @State private var offset = 0
    @State private var width = 4
    @State private var delta = 0.0
    @State private var saving = false
    @State private var saveError: Error?
    @StateObject private var templates = Loader<[String: String]>()
    @StateObject private var result = Loader<StrategyResult>()

    private let deltaStrats: Set<String> = ["short-strangle", "long-strangle", "iron-condor", "short-call", "short-put"]

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Card(title: "Setup") {
                    LabeledContent("Underlying") { Picker("Underlying", selection: $underlying) { ForEach(underlyings, id: \.self) { Text($0).tag($0) } }.labelsHidden() }
                    LabeledContent("Strategy") {
                        Picker("Strategy", selection: $name) {
                            ForEach((templates.value ?? [:]).keys.sorted(), id: \.self) { Text($0.replacingOccurrences(of: "-", with: " ")).tag($0) }
                        }
                        .labelsHidden()
                    }
                    if let d = templates.value?[name] { Text(d).font(.caption).foregroundStyle(Palette.muted) }
                    Stepper("Lots: \(lots)", value: $lots, in: 1...50)
                    Stepper("Offset: \(offset) strikes", value: $offset, in: -10...20)
                    Stepper("Width: \(width) strikes", value: $width, in: 1...20)
                    if deltaStrats.contains(name) {
                        LabeledContent("Short strikes") {
                            Picker("Short strikes", selection: $delta) {
                                Text("By steps").tag(0.0); Text("0.10 Δ").tag(0.1); Text("0.15 Δ").tag(0.15); Text("0.20 Δ").tag(0.2); Text("0.30 Δ").tag(0.3)
                            }
                            .labelsHidden()
                        }
                    }
                }
                ErrorBanner(error: result.error ?? saveError)
                if let r = result.value { resultView(r) }
                PrimaryButton(title: "Use for trade", busy: saving, disabled: result.value == nil) { Task { await useForTrade() } }
            }
            .padding(16)
        }
        .screen()
        .navigationTitle("Strategy")
        .task { await templates.run { try await app.api.call("/strategies") } }
        .task(id: "\(name)|\(underlying)|\(lots)|\(offset)|\(width)|\(delta)") { await result.run { try await app.api.post("/strategy", body(write: false)) } }
    }

    func body(write: Bool) -> [String: Any] {
        var b: [String: Any] = ["name": name, "underlying": underlying, "lots": lots, "offset": offset, "width": width, "write": write]
        if delta > 0 && deltaStrats.contains(name) { b["delta"] = delta }
        return b
    }

    func useForTrade() async {
        saving = true
        defer { saving = false }
        do {
            let _: StrategyResult = try await app.api.post("/strategy", body(write: true))
            saveError = nil
            NotificationCenter.default.post(name: .openTradeTab, object: "strategy")
        } catch { saveError = error }
    }

    @ViewBuilder func resultView(_ r: StrategyResult) -> some View {
        let a = r.analysis
        if let w = r.warning {
            Banner(title: "Naked short options", message: "\(a.naked.joined(separator: " · ")). \(w)", tone: .warn, icon: "exclamationmark.triangle.fill")
        }
        Card(title: "\(r.name.replacingOccurrences(of: "-", with: " ")) · \(r.underlying) \(r.expiry)", trailing: AnyView(Pill(text: "lot \(r.lotSize)", tone: .accent))) {
            if let c = r.curve { PayoffChartView(curve: c, spot: r.spot, breakevens: a.breakevens).frame(height: 240) }
            HStack(spacing: 14) {
                LegendDot(color: Palette.text, label: "At expiry", line: true)
                LegendDot(color: Palette.series1, label: "Today (model)", line: true)
            }
        }
        Card {
            StatGrid(items: [
                StatView(label: a.premiumType == "debit" ? "Net debit" : "Net credit", value: Fmt.rupees(abs(a.netPremium))),
                StatView(label: "Max profit", value: a.unlimitedProfit ? "Unlimited" : Fmt.signedRupees(a.maxProfit), tone: .up),
                StatView(label: "Max loss", value: a.unlimitedLoss ? "Unlimited" : Fmt.signedRupees(a.maxLoss), tone: .down),
                StatView(label: "Breakevens", value: a.breakevens.map { Fmt.num($0, 0) }.joined(separator: " · ")),
                StatView(label: "Margin", value: Fmt.rupees(r.margin.total), hint: r.margin.source ?? r.margin.error),
                StatView(label: "Theta / day", value: Fmt.signedRupees(r.greeks.theta), tone: Tone.of(r.greeks.theta)),
                StatView(label: "Delta", value: Fmt.num(r.greeks.delta, 1), hint: "units of underlying"),
                StatView(label: "Vega / IV pt", value: Fmt.signedRupees(r.greeks.vega)),
            ])
        }
        Card(title: "Legs") {
            ForEach(r.legs, id: \.self) { l in
                HStack {
                    Pill(text: l.side > 0 ? "BUY" : "SELL", tone: l.side > 0 ? .up : .down)
                    Text("\(l.lots) × \(Fmt.num(l.strike, 0)) \(l.kind)").font(.callout.weight(.medium))
                    Spacer()
                    Text(Fmt.num(l.premium)).monospacedDigit()
                }
            }
        }
    }
}

struct PayoffChartView: View {
    var curve: Curve
    var spot: Double
    var breakevens: [Double]
    @State private var selected: Double?

    struct P: Identifiable { let id: Int; let x: Double; let expiry: Double; let today: Double }

    var points: [P] {
        curve.x.indices.compactMap { i in
            guard let x = curve.x[i], let e = curve.expiry[i], let t = curve.today[i] else { return nil }
            return P(id: i, x: x, expiry: e, today: t)
        }
    }

    var body: some View {
        let pts = points
        let near = selected.flatMap { s in pts.min { abs($0.x - s) < abs($1.x - s) } }
        Chart {
            ForEach(pts) { p in
                AreaMark(x: .value("Underlying", p.x), yStart: .value("Zero", 0), yEnd: .value("P/L", max(p.expiry, 0)))
                    .foregroundStyle(Palette.upSoft)
                AreaMark(x: .value("Underlying", p.x), yStart: .value("Zero", 0), yEnd: .value("P/L", min(p.expiry, 0)))
                    .foregroundStyle(Palette.downSoft)
            }
            ForEach(pts) { p in
                LineMark(x: .value("Underlying", p.x), y: .value("P/L", p.today), series: .value("Curve", "Today"))
                    .foregroundStyle(Palette.series1).lineStyle(StrokeStyle(lineWidth: 2, dash: [6, 4]))
            }
            ForEach(pts) { p in
                LineMark(x: .value("Underlying", p.x), y: .value("P/L", p.expiry), series: .value("Curve", "Expiry"))
                    .foregroundStyle(Palette.text).lineStyle(StrokeStyle(lineWidth: 2))
            }
            RuleMark(y: .value("Zero", 0)).foregroundStyle(Palette.border)
            RuleMark(x: .value("Spot", spot)).foregroundStyle(Palette.text2).lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 3]))
            ForEach(breakevens, id: \.self) { b in
                PointMark(x: .value("BE", b), y: .value("Zero", 0)).foregroundStyle(Palette.warn).symbolSize(50)
            }
            if let n = near {
                RuleMark(x: .value("Sel", n.x)).foregroundStyle(Palette.muted)
                    .annotation(position: .top, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("At \(Fmt.num(n.x, 0))").font(.caption2.bold())
                            Text("Expiry \(Fmt.signedRupees(n.expiry))").font(.caption2).foregroundStyle(Tone.of(n.expiry).fg)
                            Text("Today \(Fmt.signedRupees(n.today))").font(.caption2).foregroundStyle(Tone.of(n.today).fg)
                        }
                        .monospacedDigit().padding(6)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Palette.border))
                    }
            }
        }
        .chartXScale(domain: (pts.first?.x ?? 0)...(pts.last?.x ?? 1))
        .chartXSelection(value: $selected)
        .chartYAxis { AxisMarks { v in AxisGridLine().foregroundStyle(Palette.border); AxisValueLabel { Text(Fmt.signedRupees(v.as(Double.self))).font(.caption2) } } }
        .chartXAxis { AxisMarks(values: .automatic(desiredCount: 5)) { v in AxisValueLabel { Text(Fmt.num(v.as(Double.self), 0)).font(.caption2) } } }
        .accessibilityLabel("Strategy payoff at expiry and today")
    }
}
