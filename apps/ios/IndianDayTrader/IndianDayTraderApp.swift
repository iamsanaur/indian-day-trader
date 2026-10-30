import SwiftUI

@main
struct IndianDayTraderApp: App {
    @StateObject private var app = AppModel()
    @AppStorage("idt.theme") private var theme = "system"

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .preferredColorScheme(theme == "light" ? .light : theme == "dark" ? .dark : nil)
                .tint(Palette.accent)
                .onOpenURL { url in
                    if let c = Connection.fromPairing(url) { app.pair(c) }
                }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppModel
    @State private var tab = 0
    @State private var tradeStep = 0

    var body: some View {
        TabView(selection: $tab) {
            MarketsView().tabItem { Label("Markets", systemImage: "chart.xyaxis.line") }.tag(0)
            OptionsView().tabItem { Label("Options", systemImage: "tablecells") }.tag(1)
            TradeView(step: $tradeStep).tabItem { Label("Trade", systemImage: "arrow.right.circle") }.tag(2)
            AlertsView().tabItem { Label("Alerts", systemImage: "bell") }.tag(3)
            MoreView().tabItem { Label("More", systemImage: "ellipsis") }.tag(4)
        }
        .modifier(AlertStream())
        .task { await app.refreshStatus() }
        .onReceive(NotificationCenter.default.publisher(for: .openTradeTab)) { note in
            tradeStep = (note.object as? String) == "strategy" ? 1 : 0
            tab = 2
        }
        .onAppear {
            // Screenshot automation: -idtTab N -idtStep N
            let d = UserDefaults.standard
            if d.object(forKey: "idtTab") != nil { tab = d.integer(forKey: "idtTab") }
            if d.object(forKey: "idtStep") != nil { tradeStep = d.integer(forKey: "idtStep") }
        }
    }
}
