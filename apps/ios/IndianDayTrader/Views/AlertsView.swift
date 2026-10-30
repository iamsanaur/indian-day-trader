import SwiftUI
import UserNotifications

struct AlertsView: View {
    @EnvironmentObject var app: AppModel
    @StateObject private var list = Loader<[AlertItem]>()
    @State private var symbol = "NIFTY"
    @State private var above = true
    @State private var price = ""
    @State private var actionError: Error?

    var body: some View {
        NavigationStack {
            List {
                if let e = list.error ?? actionError { ErrorBanner(error: e).listRowBackground(Color.clear) }
                let items = list.value ?? []
                Section("Pending") {
                    if items.filter({ !$0.fired }).isEmpty { Text("No pending alerts").foregroundStyle(Palette.muted) }
                    ForEach(items.filter { !$0.fired }) { a in AlertRow(alert: a) }
                }
                Section("Fired") {
                    if items.filter(\.fired).isEmpty { Text("Nothing has fired yet").foregroundStyle(Palette.muted) }
                    ForEach(items.filter(\.fired)) { a in AlertRow(alert: a) }
                }
                Section("Add") {
                    Button("Add stop / target / square-off from plan") { act(["from_plan": true]) }
                    TextField("Symbol or contract", text: $symbol).textInputAutocapitalization(.characters)
                    Picker("Direction", selection: $above) { Text("Crosses above").tag(true); Text("Crosses below").tag(false) }
                    TextField("Price", text: $price).keyboardType(.decimalPad)
                    Button("Add price alert") { act(["symbol": symbol, above ? "above" : "below": Double(price) ?? 0]) }
                        .disabled(Double(price) == nil || symbol.isEmpty)
                }
            }
            .screen()
            .navigationTitle("Alerts")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("Check now") { Task { let _: JSONValue? = try? await app.api.post("/alerts/check"); await load() } }
                        Button("Clear all", role: .destructive) { Task { let _: JSONValue? = try? await app.api.call("/alerts", method: "DELETE"); await load() } }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
            .refreshable { await load() }
            .task { await load() }
            .onChange(of: app.lastAlert) { _, _ in Task { await load() } }
        }
    }

    func load() async { await list.run { try await app.api.call("/alerts") } }

    func act(_ body: [String: Any]) {
        Task {
            // Ask for notification permission when the user first sets an alert, not at launch.
            _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
            do { let _: [AlertItem] = try await app.api.post("/alerts", body); actionError = nil; price = "" } catch { actionError = error }
            await load()
        }
    }
}

struct AlertRow: View {
    var alert: AlertItem
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(alert.label).font(.callout.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(Palette.text2).monospacedDigit()
            }
            Spacer()
            if alert.fired {
                Pill(text: Fmt.time(alert.firedAt), tone: alert.label.hasPrefix("STOP") ? .down : alert.label.hasPrefix("TARGET") ? .up : .neutral)
            } else {
                Pill(text: "watching", tone: .warn)
            }
        }
    }

    var detail: String {
        switch alert.kind {
        case "time": "at \(alert.value) IST"
        case "pnl": "combined P/L \(alert.op ?? "") \(Fmt.rupees(alert.value.double))"
        default: "\(alert.symbol ?? "") \(alert.op ?? "") \(Fmt.num(alert.value.double))" + (alert.observed.map { " · observed \($0)" } ?? "")
        }
    }
}

/// Listens to the server's alert stream while the app is open and posts local notifications.
struct AlertStream: ViewModifier {
    @EnvironmentObject var app: AppModel

    func body(content: Content) -> some View {
        content.task(id: app.connection) {
            guard app.connection.isConfigured else { return }
            while !Task.isCancelled {
                do {
                    for try await (event, data) in app.api.events() where event == "alert" {
                        guard let a = try? APIClient.decoder.decode(AlertItem.self, from: data) else { continue }
                        app.lastAlert = a
                        let n = UNMutableNotificationContent()
                        n.title = a.label
                        n.body = "Observed \(a.observed?.description ?? "")"
                        n.sound = .default
                        try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: a.id, content: n, trigger: nil))
                    }
                } catch {}
                try? await Task.sleep(for: .seconds(10)) // reconnect
            }
        }
    }
}
