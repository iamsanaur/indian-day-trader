import SwiftUI

/// Daily Dhan reconnect: the 6-digit TOTP is exchanged for a 24-hour token on your server and never stored.
struct TotpField: View {
    @EnvironmentObject var app: AppModel
    @State private var totp = ""
    @State private var busy = false
    @State private var error: Error?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField("6-digit TOTP", text: $totp)
                    .keyboardType(.numberPad)
                    .textContentType(.oneTimeCode)
                    .font(.title3.monospacedDigit().weight(.semibold))
                    .padding(.horizontal, 12).frame(height: 44)
                    .background(Palette.surface, in: RoundedRectangle(cornerRadius: 10))
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Palette.border))
                    .onChange(of: totp) { _, v in totp = String(v.filter(\.isNumber).prefix(6)) }
                Button { Task { await connect() } } label: {
                    if busy { ProgressView() } else { Text("Connect").fontWeight(.semibold) }
                }
                .buttonStyle(.borderedProminent).frame(height: 44)
                .disabled(totp.count != 6 || busy)
            }
            ErrorBanner(error: error)
        }
    }

    func connect() async {
        busy = true
        defer { busy = false }
        do {
            let _: DhanStatus = try await app.api.post("/dhan/login", ["totp": totp])
            totp = ""; error = nil
            await app.refreshStatus()
        } catch { self.error = error }
    }
}

struct DhanBanner: View {
    @EnvironmentObject var app: AppModel
    var body: some View {
        if let d = app.status?.dhan, !d.connected {
            VStack(alignment: .leading, spacing: 10) {
                Text("Connect Dhan for today").font(.headline)
                Text(d.message).font(.footnote).foregroundStyle(Palette.text2)
                if d.totpLoginAvailable { TotpField() }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.warnSoft, in: RoundedRectangle(cornerRadius: 14))
        }
    }
}

struct DhanSessionSection: View {
    @EnvironmentObject var app: AppModel
    var body: some View {
        if let d = app.status?.dhan {
            Section {
                HStack {
                    Pill(text: d.connected ? "Connected\(d.clientName.map { " · \($0)" } ?? "")" : "Not connected", tone: d.connected ? .up : .down)
                    if d.connected && d.source == "totp" { Pill(text: d.timeLeft) }
                    if d.source == "env" { Pill(text: "manual token") }
                }
                Text(d.message).font(.footnote).foregroundStyle(Palette.text2)
                if d.totpLoginAvailable && d.source != "env" { TotpField() }
                if d.connected && d.source == "totp" {
                    Button("Disconnect", role: .destructive) {
                        Task { let _: DhanStatus? = try? await app.api.call("/dhan", method: "DELETE"); await app.refreshStatus() }
                    }
                }
            } header: { Text("Dhan session") } footer: {
                Text(d.clientIdSet && d.pinSet
                     ? "Your TOTP is used once to get a 24-hour token and is never stored."
                     : "Add DHAN_CLIENT_ID and DHAN_PIN to the server's .env and restart it.")
            }
        }
    }
}
