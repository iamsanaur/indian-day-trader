import SwiftUI
import VisionKit

struct MoreView: View {
    var body: some View {
        NavigationStack {
            List {
                NavigationLink { StrategyView() } label: { Label("Strategy builder", systemImage: "chart.line.uptrend.xyaxis") }
                NavigationLink { JournalView() } label: { Label("Journal", systemImage: "book.closed") }
                NavigationLink { ResearchView() } label: { Label("Research", systemImage: "magnifyingglass") }
                NavigationLink { SettingsView() } label: { Label("Settings", systemImage: "gearshape") }
                Section {
                    Text("Indian Day Trader never places orders. Tickets are for you to place in your own broker.")
                        .font(.footnote).foregroundStyle(Palette.muted)
                }
            }
            .screen()
            .navigationTitle("More")
        }
    }
}

struct JournalView: View {
    @EnvironmentObject var app: AppModel
    @StateObject private var entries = Loader<[JournalEntry]>()
    @State private var pnl = ""
    @State private var symbol = ""
    @State private var note = ""

    var body: some View {
        List {
            if let s = app.status {
                Section("Today") {
                    HStack {
                        StatView(label: "Trades confirmed", value: "\(s.tradesToday)", hint: "limit \(s.limits["maxTradesPerDay"]?.description ?? "—")")
                        StatView(label: "Realised P/L", value: Fmt.signedRupees(s.realisedToday), tone: Tone.of(s.realisedToday))
                    }
                    if let cap = s.limits["dailyLossCap"]?.double, cap > 0 {
                        let used = max(0, -s.realisedToday)
                        VStack(alignment: .leading) {
                            Text("Daily loss cap used \(Fmt.rupees(used)) / \(Fmt.rupees(cap))").font(.caption).foregroundStyle(Palette.text2)
                            ProgressView(value: min(used / cap, 1)).tint(used / cap > 0.75 ? Palette.downMark : Palette.accent)
                        }
                    }
                }
            }
            Section("Record a closed trade") {
                TextField("Realised P/L ₹ (negative for a loss)", text: $pnl).keyboardType(.numbersAndPunctuation)
                TextField("Symbol", text: $symbol).textInputAutocapitalization(.characters)
                TextField("Note", text: $note)
                Button("Save") {
                    Task {
                        let _: [JournalEntry]? = try? await app.api.post("/journal/close", ["pnl": Double(pnl) ?? 0, "symbol": symbol, "note": note])
                        pnl = ""; note = ""
                        await load(); await app.refreshStatus()
                    }
                }
                .disabled(Double(pnl) == nil)
            }
            Section("History") {
                ErrorBanner(error: entries.error)
                ForEach(Array((entries.value ?? []).reversed().enumerated()), id: \.offset) { _, e in
                    HStack {
                        Pill(text: e.type == "close" ? "Closed" : "Confirmed", tone: e.type == "close" ? Tone.of(e.pnl) : .accent)
                        VStack(alignment: .leading) {
                            Text(e.symbol ?? "—").font(.callout.weight(.semibold))
                            Text(Fmt.dayTime(e.ts)).font(.caption).foregroundStyle(Palette.muted)
                        }
                        Spacer()
                        Text(e.type == "close" ? Fmt.signedRupees(e.pnl) : "risk \(Fmt.rupees(e.lossAtStop))")
                            .monospacedDigit().foregroundStyle(e.type == "close" ? Tone.of(e.pnl).fg : Palette.text2)
                    }
                }
            }
        }
        .screen()
        .navigationTitle("Journal")
        .task { await load(); await app.refreshStatus() }
    }

    func load() async { await entries.run { try await app.api.call("/journal?tail=100") } }
}

struct ResearchView: View {
    @EnvironmentObject var app: AppModel
    @State private var tab = "news"
    @State private var symbol = "RELIANCE"
    @StateObject private var news = Loader<NewsResponse>()
    @StateObject private var ban = Loader<BanResponse>()
    @StateObject private var deals = Loader<Deals>()
    @StateObject private var results = Loader<ResultsResponse>()

    var body: some View {
        List {
            Picker("Section", selection: $tab) {
                Text("News").tag("news"); Text("Ban").tag("ban"); Text("Deals").tag("deals"); Text("Results").tag("results")
            }
            .pickerStyle(.segmented).listRowBackground(Color.clear)
            switch tab {
            case "news":
                ErrorBanner(error: news.error)
                ForEach(news.value?.announcements ?? [], id: \.self) { a in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack { Pill(text: a.symbol ?? "", tone: .accent); Spacer(); Text(Fmt.dayTime(a.time)).font(.caption).foregroundStyle(Palette.muted) }
                        Text(a.subject ?? "").font(.callout.weight(.semibold))
                        Text(a.detail ?? "").font(.caption).foregroundStyle(Palette.text2)
                    }
                }
            case "ban":
                ErrorBanner(error: ban.error)
                Section("F&O ban list — no fresh positions today") {
                    if ban.value?.banList.isEmpty == true { Text("No securities in ban") }
                    ForEach(ban.value?.banList ?? [], id: \.self) { Text($0).foregroundStyle(Palette.down).bold() }
                }
            case "deals":
                ErrorBanner(error: deals.error)
                Section("Bulk deals") { ForEach(deals.value?.bulk ?? [], id: \.self) { DealRow(d: $0) } }
                Section("Block deals") { ForEach(deals.value?.block ?? [], id: \.self) { DealRow(d: $0) } }
            default:
                TextField("Symbol", text: $symbol).textInputAutocapitalization(.characters).onSubmit { Task { await loadResults() } }
                ErrorBanner(error: results.error)
                ForEach(results.value?.quarters ?? [], id: \.self) { q in
                    HStack {
                        Text(q.periodEnd ?? "").font(.callout.weight(.semibold))
                        Spacer()
                        VStack(alignment: .trailing) {
                            Text("Rev \(Fmt.num(q.revenue, 0)) · \(Fmt.pct(q.revenueYoyPct, 1)) YoY").font(.caption).monospacedDigit()
                            Text("PAT \(Fmt.num(q.netProfit, 0)) · EPS \(Fmt.num(q.eps))").font(.caption).monospacedDigit().foregroundStyle(Palette.text2)
                        }
                    }
                }
                if let n = results.value?.note { Text(n).font(.caption).foregroundStyle(Palette.muted) }
            }
        }
        .screen()
        .navigationTitle("Research")
        .task(id: tab) {
            switch tab {
            case "news": await news.run { try await app.api.call("/news?hours=72") }
            case "ban": await ban.run { try await app.api.call("/ban") }
            case "deals": await deals.run { try await app.api.call("/insider/deals") }
            default: await loadResults()
            }
        }
    }

    func loadResults() async { await results.run { try await app.api.call("/results/\(symbol.uppercased())") } }
}

struct DealRow: View {
    var d: Deal
    var body: some View {
        HStack {
            VStack(alignment: .leading) {
                Text(d.symbol ?? "").bold()
                Text(d.clientName ?? "").font(.caption).foregroundStyle(Palette.text2)
            }
            Spacer()
            Pill(text: d.buySell ?? "", tone: d.buySell == "BUY" ? .up : .down)
            Text(Fmt.compact(Double(d.qty ?? ""))).monospacedDigit()
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject var app: AppModel
    @AppStorage("idt.theme") private var theme = "system"
    @State private var url = ""
    @State private var token = ""
    @State private var scanning = false
    @State private var health: Health?
    @State private var healthError: Error?
    @StateObject private var config = Loader<ConfigResponse>()
    @State private var draft: [String: JSONValue] = [:]
    @State private var saveError: Error?

    private let labels: [(String, String)] = [
        ("capital", "Paper capital (₹)"), ("max_loss_per_trade", "Max loss per trade (₹)"), ("daily_loss_cap", "Daily loss cap (₹)"),
        ("max_trades_per_day", "Max trades per day"), ("leverage_cap", "Leverage cap (×)"), ("min_premium", "Min option premium (₹)"),
        ("entry_cutoff", "No new entries after"), ("squareoff", "Square off by"),
        ("allow_short", "Allow shorting"), ("allow_naked", "Allow naked short options"), ("block_expiry_day_selling", "Block expiry-day selling"),
    ]

    var body: some View {
        Form {
            Section {
                if DataScannerViewController.isSupported {
                    Button { scanning = true } label: { Label("Scan pairing QR", systemImage: "qrcode.viewfinder") }
                }
                TextField("Server URL, e.g. http://192.168.1.10:8742", text: $url).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                SecureField("Access token", text: $token)
                Button("Save & connect") { app.pair(Connection(url: url, token: token)); Task { await check() } }
                if let h = health {
                    Label("Connected · v\(h.version)\(h.demo ? " · demo" : "")", systemImage: "checkmark.circle.fill").foregroundStyle(Palette.up)
                } else if let e = healthError {
                    Label(e.localizedDescription, systemImage: "xmark.circle.fill").foregroundStyle(Palette.down)
                }
            } header: { Text("Server") } footer: { Text("Run `idt serve` on your computer and scan the QR it prints, or open the idt:// link on this phone.") }

            DhanSessionSection()

            Section("Appearance") {
                Picker("Theme", selection: $theme) { Text("System").tag("system"); Text("Light").tag("light"); Text("Dark").tag("dark") }.pickerStyle(.segmented)
            }

            if config.value != nil {
                Section {
                    Picker("Mode", selection: binding("mode")) { Text("Paper").tag(JSONValue.string("paper")); Text("Live").tag(JSONValue.string("live")) }
                        .pickerStyle(.segmented)
                    ForEach(labels, id: \.0) { key, label in
                        let k = camel(key)
                        if case .bool = draft[k] {
                            Toggle(label, isOn: Binding(get: { draft[k]?.bool ?? false }, set: { draft[k] = .bool($0) }))
                        } else if draft[k] != nil {
                            HStack {
                                Text(label)
                                Spacer()
                                TextField("", text: Binding(get: { draft[k]?.description ?? "" }, set: { v in
                                    if case .string = config.value?.config[k] { draft[k] = .string(v) } else { draft[k] = .number(Double(v) ?? 0) }
                                }))
                                .multilineTextAlignment(.trailing).monospacedDigit().frame(width: 110)
                            }
                        }
                    }
                    if draft["allowNaked"]?.bool == true {
                        Text("Naked short options can lose far more than the premium collected.").font(.caption).foregroundStyle(Palette.warn)
                    }
                    Button("Save limits") { Task { await saveConfig() } }.disabled(changes.isEmpty)
                    ErrorBanner(error: saveError)
                } header: { Text("Risk limits") } footer: { Text("Live mode reads available funds from your broker for the margin check. Orders are never placed either way.") }
            }
        }
        .screen()
        .navigationTitle("Settings")
        .sheet(isPresented: $scanning) {
            QRScanner { code in
                scanning = false
                if let u = URL(string: code), let c = Connection.fromPairing(u) {
                    url = c.url; token = c.token
                    app.pair(c)
                    Task { await check() }
                }
            }
            .ignoresSafeArea()
        }
        .onAppear { url = app.connection.url; token = app.connection.token }
        .task { await check() }
    }

    /// The API decoder camel-cases dictionary keys; convert back for PATCH.
    func camel(_ snake: String) -> String {
        let parts = snake.split(separator: "_")
        return ([String(parts.first ?? "")] + parts.dropFirst().map { $0.capitalized }).joined()
    }

    func snake(_ camel: String) -> String {
        camel.reduce(into: "") { s, ch in if ch.isUppercase { s += "_" + ch.lowercased() } else { s.append(ch) } }
    }

    func binding(_ key: String) -> Binding<JSONValue> {
        Binding(get: { draft[key] ?? .null }, set: { draft[key] = $0 })
    }

    var changes: [String: Any] {
        guard let cfg = config.value?.config else { return [:] }
        var out: [String: Any] = [:]
        for (k, v) in draft where cfg[k] != v {
            switch v {
            case .bool(let b): out[snake(k)] = b
            case .number(let n): out[snake(k)] = n.rounded() == n ? Int(n) as Any : n
            case .string(let s): out[snake(k)] = s
            default: break
            }
        }
        return out
    }

    func check() async {
        do {
            health = try await app.api.call("/health"); healthError = nil
            await config.run { try await app.api.call("/config") }
            draft = config.value?.config ?? [:]
            await app.refreshStatus()
        } catch { health = nil; healthError = error }
    }

    func saveConfig() async {
        do {
            let r: ConfigResponse = try await app.api.call("/config", method: "PATCH", body: changes)
            config.value = r; draft = r.config; saveError = nil
            await app.refreshStatus()
        } catch { saveError = error }
    }
}

/// VisionKit QR scanner for the `idt://pair` code.
struct QRScanner: UIViewControllerRepresentable {
    var onCode: (String) -> Void

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let vc = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])], qualityLevel: .balanced,
                                           isHighlightingEnabled: true)
        vc.delegate = context.coordinator
        try? vc.startScanning()
        return vc
    }

    func updateUIViewController(_ vc: DataScannerViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onCode: (String) -> Void
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ scanner: DataScannerViewController, didAdd items: [RecognizedItem], allItems: [RecognizedItem]) {
            for case .barcode(let b) in items { if let s = b.payloadStringValue, s.hasPrefix("idt://") { scanner.stopScanning(); onCode(s); return } }
        }
    }
}
