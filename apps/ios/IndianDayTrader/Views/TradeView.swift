import SwiftUI

private let steps = ["Setup", "Plan", "Odds", "Size", "Risk", "Ticket"]

private let stopRules: [String: [(String, String)]] = [
    "option": [("or-mid", "Underlying at OR mid"), ("or-low", "Underlying at far side of OR"), ("premium-pct:30", "Premium −30%"), ("premium-pct:50", "Premium −50%")],
    "equity": [("or-mid", "OR mid"), ("or-low", "Far side of OR"), ("atr:1", "1 × ATR"), ("pct:0.5", "0.5%")],
    "future": [("or-mid", "OR mid"), ("or-low", "Far side of OR"), ("atr:1", "1 × ATR")],
    "strategy": [("maxloss-pct:50", "50% of max loss"), ("credit-x:1", "Loss = 1 × credit"), ("pnl:-2000", "−₹2,000 per set")],
]
private let targetRules: [String: [(String, String)]] = [
    "option": [("1.5R", "1.5 R"), ("2R", "2 R"), ("1R", "1 R")],
    "equity": [("1.5R", "1.5 R"), ("2R", "2 R"), ("1R", "1 R")],
    "future": [("1.5R", "1.5 R"), ("2R", "2 R")],
    "strategy": [("1.5R", "1.5 R"), ("maxprofit-pct:60", "60% of max profit"), ("credit-pct:50", "Keep 50% of credit")],
]

struct TradeView: View {
    @EnvironmentObject var app: AppModel
    @Binding var step: Int
    @StateObject private var state = Loader<PlanState>()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(steps.indices, id: \.self) { i in
                                Button { step = i } label: {
                                    Text("\(i + 1) \(steps[i])").font(.footnote.weight(.semibold))
                                        .padding(.horizontal, 12).padding(.vertical, 8)
                                        .foregroundStyle(i == step ? Color.white : Palette.text2)
                                        .background(i == step ? Palette.accent : Palette.surface, in: Capsule())
                                        .overlay(Capsule().stroke(i == step ? .clear : Palette.border))
                                }
                            }
                        }
                    }
                    ErrorBanner(error: state.error)
                    if state.value == nil && state.error == nil {
                        ProgressView().frame(maxWidth: .infinity)
                    } else {
                        switch step {
                        case 0: SetupStep(state: state.value, reload: reload, next: next)
                        case 1: PlanStep(state: state.value, reload: reload, next: next)
                        case 2: OddsStep(next: next)
                        case 3: SizeStep(next: next)
                        case 4: RiskStep(next: next)
                        default: TicketStep()
                        }
                    }
                }
                .padding(16)
            }
            .screen()
            .navigationTitle("Trade")
            .task(id: step) { await reload() }
        }
    }

    func reload() async { await state.run { try await app.api.call("/plan") } }
    func next() { step = min(step + 1, steps.count - 1) }
}

private struct SetupStep: View {
    @EnvironmentObject var app: AppModel
    var state: PlanState?
    var reload: () async -> Void
    var next: () -> Void
    @State private var symbol = "NIFTY"
    @State private var setup = "orb"
    @StateObject private var check = Loader<SetupState>()

    var body: some View {
        let s = check.value ?? state?.setup
        Card(title: "Check the entry trigger") {
            TextField("Symbol", text: $symbol).textInputAutocapitalization(.characters).textFieldStyle(.roundedBorder)
            LabeledContent("Setup") { Picker("Setup", selection: $setup) { Text("Opening-range breakout").tag("orb"); Text("Previous-day high/low").tag("pdh") }.labelsHidden() }
            PrimaryButton(title: "Check", busy: check.loading) {
                Task { await check.run { try await app.api.post("/entry/\(symbol.uppercased())", ["setup": setup, "write": true]) }; await reload() }
            }
            ErrorBanner(error: check.error)
            if let s {
                Banner(title: "\(s.symbol): \(s.state) \(s.side ?? "")",
                       message: s.state == "triggered" ? "Entry \(Fmt.num(s.entry)) on the \(Fmt.time(s.triggerTime)) bar" : "Only completed 5-minute bars count.",
                       tone: s.state == "triggered" ? .up : .warn, icon: s.state == "triggered" ? "bolt.fill" : "clock")
            }
        }
        Card(title: "Or trade a saved strategy") {
            if let st = state?.strategy {
                Text("\(st.name.replacingOccurrences(of: "-", with: " ")) · \(st.underlying) \(st.expiry)").font(.callout.weight(.medium))
                Text("Choose “Saved strategy” in the next step.").font(.caption).foregroundStyle(Palette.text2)
            } else {
                Text("Build one in More › Strategy and tap “Use for trade”.").font(.footnote).foregroundStyle(Palette.muted)
            }
        }
        PrimaryButton(title: "Next: plan the exit", disabled: s == nil && state?.strategy == nil, action: next)
    }
}

private struct PlanStep: View {
    @EnvironmentObject var app: AppModel
    var state: PlanState?
    var reload: () async -> Void
    var next: () -> Void
    @State private var kind = ""
    @State private var stop = ""
    @State private var target = ""
    @State private var option = "auto"
    @State private var offset = 0
    @StateObject private var save = Loader<Plan>()

    var body: some View {
        Card(title: "Stop and target — set before entry") {
            LabeledContent("Instrument") {
                Picker("Instrument", selection: $kind) {
                    Text("Long option (CE/PE)").tag("option")
                    Text("Cash equity (MIS)").tag("equity")
                    Text("Future").tag("future")
                    if state?.strategy != nil { Text("Saved strategy").tag("strategy") }
                }
                .labelsHidden()
            }
            if kind == "option" {
                Picker("Option", selection: $option) { Text("Auto").tag("auto"); Text("CE").tag("CE"); Text("PE").tag("PE") }.pickerStyle(.segmented)
                Stepper("Strikes OTM: \(offset)", value: $offset, in: -5...10)
            }
            LabeledContent("Stop") { Picker("Stop", selection: $stop) { ForEach(stopRules[kind] ?? [], id: \.0) { Text($0.1).tag($0.0) } }.labelsHidden() }
            LabeledContent("Target") { Picker("Target", selection: $target) { ForEach(targetRules[kind] ?? [], id: \.0) { Text($0.1).tag($0.0) } }.labelsHidden() }
            PrimaryButton(title: "Save plan", busy: save.loading, disabled: kind.isEmpty) {
                Task {
                    await save.run { try await app.api.post("/plan", ["kind": kind, "stop": stop, "target": target, "option": option, "strike_offset": offset]) }
                    await reload()
                }
            }
            ErrorBanner(error: save.error)
        }
        .onAppear {
            guard kind.isEmpty else { return }
            let isIndex = underlyings.contains(state?.setup?.symbol ?? "")
            pick(state?.plan?.kind ?? (state?.strategy != nil && state?.setup == nil ? "strategy" : (isIndex || state?.setup == nil ? "option" : "equity")))
        }
        .onChange(of: kind) { _, k in pick(k) }
        if let p = save.value ?? state?.plan { PlanCard(plan: p) }
        PrimaryButton(title: "Next: check the odds", disabled: (save.value ?? state?.plan) == nil, action: next)
    }

    func pick(_ k: String) {
        kind = k
        if !(stopRules[k] ?? []).contains(where: { $0.0 == stop }) { stop = stopRules[k]?.first?.0 ?? "" }
        if !(targetRules[k] ?? []).contains(where: { $0.0 == target }) { target = targetRules[k]?.first?.0 ?? "" }
    }
}

struct PlanCard: View {
    var plan: Plan
    var body: some View {
        let strat = plan.basis == "pnl"
        Card(title: "\(strat ? (plan.strategy ?? "strategy").replacingOccurrences(of: "-", with: " ") : plan.contract ?? plan.symbol) · \(plan.side)",
             trailing: AnyView(Pill(text: "R:R \(Fmt.num(plan.rr))", tone: .accent))) {
            StatGrid(items: strat ? [
                StatView(label: plan.entry > 0 ? "Debit / set" : "Credit / set", value: Fmt.rupees(abs(plan.entry))),
                StatView(label: "Stop (P/L)", value: Fmt.signedRupees(plan.stopPnl), tone: .down),
                StatView(label: "Target (P/L)", value: Fmt.signedRupees(plan.targetPnl), tone: .up),
                StatView(label: "Risk / \(plan.unit)", value: Fmt.rupees(plan.riskPerUnit)),
            ] : [
                StatView(label: "Entry", value: Fmt.num(plan.entry)),
                StatView(label: "Stop", value: Fmt.num(plan.stop), tone: .down, hint: plan.kind == "option" ? plan.underlyingStop.map { "underlying \(Fmt.num($0))" } : nil),
                StatView(label: "Target", value: Fmt.num(plan.target), tone: .up, hint: plan.kind == "option" ? plan.underlyingTarget.map { "underlying \(Fmt.num($0))" } : nil),
                StatView(label: "Risk / \(plan.unit)", value: Fmt.rupees(plan.riskPerUnit)),
            ])
            Text("Square off by \(plan.squareoff) IST · \(plan.stopRule) / \(plan.targetRule)").font(.caption).foregroundStyle(Palette.muted)
        }
    }
}

private struct OddsStep: View {
    @EnvironmentObject var app: AppModel
    var next: () -> Void
    @StateObject private var run = Loader<TimeMachine>()

    var body: some View {
        Card(title: "Time Machine") {
            HStack {
                ForEach([2000, 10000], id: \.self) { n in
                    Button("Run \(Fmt.num(Double(n), 0)) paths") { Task { await run.run { try await app.api.post("/timemachine", ["paths": n]) } } }
                        .buttonStyle(.bordered).disabled(run.loading)
                }
                if run.loading { ProgressView() }
            }
            ErrorBanner(error: run.error)
            if let r = run.value {
                let mc = r.monteCarlo
                ProbabilityBar(target: mc.pTarget, flat: mc.pFlat, stop: mc.pStop)
                StatGrid(items: [
                    StatView(label: "Mean P/L / unit", value: Fmt.signedRupees(mc.pnlPerUnit.mean), tone: Tone.of(mc.pnlPerUnit.mean)),
                    StatView(label: "Median", value: Fmt.signedRupees(mc.pnlPerUnit.median)),
                    StatView(label: "5th pct", value: Fmt.signedRupees(mc.pnlPerUnit.p5)),
                    StatView(label: "95th pct", value: Fmt.signedRupees(mc.pnlPerUnit.p95)),
                    StatView(label: "Expected R", value: Fmt.num(mc.expectedR)),
                ])
                if let f = r.replay.fired, let s = r.replay.sessions {
                    Text("Replay: fired on \(f) of \(s) prior sessions · win rate \(r.replay.winRate.map { "\(Int($0 * 100))%" } ?? "—") · avg \(Fmt.num(r.replay.avgR)) R")
                        .font(.footnote).foregroundStyle(Palette.text2)
                }
                Text(r.caveat).font(.caption).foregroundStyle(Palette.muted)
            } else if !run.loading {
                Text("Simulate thousands of sessions from the same time of day before risking money.").font(.footnote).foregroundStyle(Palette.muted)
            }
        }
        PrimaryButton(title: "Next: size the position", action: next)
    }
}

struct ProbabilityBar: View {
    var target: Double
    var flat: Double
    var stop: Double
    var body: some View {
        let parts: [(String, Double, Color)] = [("Target", target, Palette.upMark), ("Open at square-off", flat, Palette.muted), ("Stop", stop, Palette.downMark)]
        VStack(alignment: .leading, spacing: 10) {
            GeometryReader { g in
                HStack(spacing: 2) {
                    ForEach(parts, id: \.0) { p in Rectangle().fill(p.2).frame(width: max(0, (g.size.width - 4) * p.1)) }
                }
            }
            .frame(height: 14).clipShape(RoundedRectangle(cornerRadius: 4))
            .accessibilityLabel("Target \(Int(target * 100)) percent, stop \(Int(stop * 100)) percent")
            HStack(alignment: .top) {
                ForEach(parts, id: \.0) { p in
                    VStack(alignment: .leading, spacing: 2) {
                        LegendDot(color: p.2, label: p.0)
                        Text(String(format: "%.1f%%", p.1 * 100)).font(.headline).monospacedDigit()
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }
}

private struct SizeStep: View {
    @EnvironmentObject var app: AppModel
    var next: () -> Void
    @State private var maxLoss = ""
    @StateObject private var size = Loader<Orders>()

    var body: some View {
        Card(title: "Budget") {
            TextField("Max loss ₹ (blank = config)", text: $maxLoss).keyboardType(.numberPad).textFieldStyle(.roundedBorder)
            PrimaryButton(title: "Size it", busy: size.loading) {
                Task {
                    var body: [String: Any] = [:]
                    if let v = Double(maxLoss) { body["max_loss"] = v }
                    await size.run { try await app.api.post("/size", body) }
                }
            }
            ErrorBanner(error: size.error)
            if let o = size.value {
                StatGrid(items: [
                    StatView(label: o.unit == "share" ? "Shares" : o.unit == "lot" ? "Lots" : "Sets", value: "\(o.units)", hint: o.unit == "share" ? nil : "lot size \(o.lotSize)"),
                    StatView(label: "Loss at stop", value: Fmt.rupees(o.lossAtStop), tone: .down, hint: "incl. ₹\(Fmt.num(o.charges.ifStopped, 0)) charges"),
                    StatView(label: "Profit at target", value: Fmt.rupees(o.profitAtTarget), tone: .up),
                    StatView(label: "Margin", value: Fmt.rupees(o.margin.total), hint: o.margin.source),
                ])
                ForEach(o.legs, id: \.self) { l in
                    HStack {
                        Pill(text: l.side, tone: l.side == "BUY" ? .up : .down)
                        Text(l.symbol).font(.footnote).lineLimit(1)
                        Spacer()
                        Text("\(l.quantity) @ \(Fmt.num(l.price))").font(.footnote).monospacedDigit()
                    }
                }
                ForEach(o.notes, id: \.self) { Text($0).font(.caption).foregroundStyle(Palette.muted) }
            }
        }
        PrimaryButton(title: "Next: risk check", disabled: size.value == nil, action: next)
    }
}

private struct RiskStep: View {
    @EnvironmentObject var app: AppModel
    var next: () -> Void
    @StateObject private var risk = Loader<RiskVerdict>()

    var body: some View {
        PrimaryButton(title: "Run risk check", busy: risk.loading) { Task { await risk.run { try await app.api.post("/risk") } } }
        ErrorBanner(error: risk.error)
        if let r = risk.value {
            let pass = r.verdict == "PASS"
            Banner(title: r.verdict,
                   message: pass ? "Every rule passed. The verdict is bound to this exact order for 10 minutes." : "\(r.reasons.count) rule(s) failed. Fix them, then re-size and re-check.",
                   tone: pass ? .up : .down, icon: pass ? "checkmark.shield.fill" : "xmark.octagon.fill")
            Card(title: "Checks") {
                ForEach(r.checks, id: \.rule) { c in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: c.ok ? "checkmark.circle.fill" : "xmark.circle.fill").foregroundStyle(c.ok ? Palette.up : Palette.down)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(c.rule).font(.callout.weight(.semibold))
                            Text(c.detail).font(.caption).foregroundStyle(Palette.text2)
                        }
                    }
                }
            }
            PrimaryButton(title: "Next: ticket", disabled: !pass, action: next)
        }
    }
}

private struct TicketStep: View {
    @EnvironmentObject var app: AppModel
    @State private var typed = ""
    @State private var alertsAdded = false
    @StateObject private var ticket = Loader<Ticket>()
    @StateObject private var confirm = Loader<Confirmation>()

    var body: some View {
        Group {
            ErrorBanner(error: ticket.error)
            if let t = ticket.value {
                Card(title: "Ticket · \(t.orderHash)", trailing: AnyView(Pill(text: "\(t.mode) mode", tone: t.mode == "paper" ? .warn : .accent))) {
                    ForEach(t.entries, id: \.self) { e in
                        HStack {
                            Pill(text: e.action, tone: e.action == "BUY" ? .up : .down)
                            VStack(alignment: .leading) {
                                Text(e.symbol).font(.callout.weight(.medium))
                                Text("\(e.orderType) · \(e.product)").font(.caption).foregroundStyle(Palette.muted)
                            }
                            Spacer()
                            VStack(alignment: .trailing) {
                                Text("\(e.quantity)").monospacedDigit()
                                Text("@ \(Fmt.num(e.price))").font(.caption).monospacedDigit().foregroundStyle(Palette.text2)
                            }
                        }
                    }
                    Divider()
                    Text("Exits").font(.subheadline.weight(.semibold))
                    ForEach(t.exits.indices, id: \.self) { i in
                        let x = t.exits[i]
                        Text("• \(x["note"]?.description ?? x["action"]?.description ?? ""): \(["action", "orderType", "triggerPrice", "price", "condition"].compactMap { x[$0].map { "\($0)" } }.joined(separator: " · "))")
                            .font(.caption).foregroundStyle(Palette.text2)
                    }
                    Text(t.oco).font(.caption).foregroundStyle(Palette.muted)
                    StatGrid(items: [
                        StatView(label: "Loss at stop", value: Fmt.rupees(t.lossAtStop), tone: .down),
                        StatView(label: "Profit at target", value: Fmt.rupees(t.profitAtTarget), tone: .up),
                    ])
                }
                if let c = confirm.value {
                    Banner(title: "Confirmed \(c.confirmed)", message: c.next, tone: .up, icon: "checkmark.seal.fill")
                    Button(alertsAdded ? "Alerts added ✓" : "Add stop / target / square-off alerts") {
                        Task { let _: [AlertItem]? = try? await app.api.post("/alerts", ["from_plan": true]); alertsAdded = true }
                    }
                    .buttonStyle(.bordered).disabled(alertsAdded)
                } else {
                    Card(title: "Confirm") {
                        Text("This records your decision. Nothing is sent to a broker — you place the order yourself.")
                            .font(.footnote).foregroundStyle(Palette.text2)
                        TextField("Type \"yes\" to confirm", text: $typed).textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.roundedBorder)
                        PrimaryButton(title: "Confirm order", busy: confirm.loading, disabled: typed.trimmingCharacters(in: .whitespaces).lowercased() != "yes") {
                            Task {
                                await confirm.run { try await app.api.post("/ticket/confirm", ["hash": t.orderHash, "typed": typed]) }
                                await app.refreshStatus()
                            }
                        }
                        ErrorBanner(error: confirm.error)
                    }
                }
            } else if ticket.loading {
                ProgressView()
            }
        }
        .task { await ticket.run { try await app.api.call("/ticket") } }
    }
}
