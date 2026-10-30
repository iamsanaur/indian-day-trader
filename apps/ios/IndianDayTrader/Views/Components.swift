import SwiftUI

struct Card<Content: View>: View {
    var title: String? = nil
    var trailing: AnyView? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if title != nil || trailing != nil {
                HStack {
                    if let title { Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Palette.text2) }
                    Spacer()
                    trailing
                }
            }
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Palette.border))
        .shadow(color: .black.opacity(0.04), radius: 8, y: 2)
    }
}

struct Pill: View {
    var text: String
    var tone: Tone = .neutral
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 9).padding(.vertical, 4)
            .foregroundStyle(tone.fg)
            .background(tone.bg, in: Capsule())
            .lineLimit(1)
    }
}

struct StatView: View {
    var label: String
    var value: String
    var tone: Tone = .neutral
    var hint: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(Palette.muted)
            Text(value).font(.title3.weight(.semibold)).monospacedDigit()
                .foregroundStyle(tone == .neutral ? Palette.text : tone.fg)
                .lineLimit(1).minimumScaleFactor(0.7)
            if let hint { Text(hint).font(.caption2).foregroundStyle(Palette.muted).lineLimit(2) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct StatGrid: View {
    var items: [StatView]
    var columns = 2
    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), alignment: .topLeading), count: columns), alignment: .leading, spacing: 14) {
            ForEach(items.indices, id: \.self) { items[$0] }
        }
    }
}

struct ErrorBanner: View {
    var error: Error?
    var body: some View {
        if let error {
            Text(error.localizedDescription)
                .font(.callout.weight(.medium))
                .foregroundStyle(Palette.down)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Palette.downSoft, in: RoundedRectangle(cornerRadius: 12))
        }
    }
}

struct Banner: View {
    var title: String
    var message: String
    var tone: Tone
    var icon: String
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).font(.title2.weight(.semibold)).foregroundStyle(tone.fg)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(message).font(.footnote).foregroundStyle(Palette.text2)
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .background(tone.bg, in: RoundedRectangle(cornerRadius: 14))
    }
}

struct PrimaryButton: View {
    var title: String
    var busy = false
    var disabled = false
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack { if busy { ProgressView().tint(.white) }; Text(title).fontWeight(.semibold) }
                .frame(maxWidth: .infinity, minHeight: 46)
        }
        .buttonStyle(.borderedProminent)
        .buttonBorderShape(.roundedRectangle(radius: 12))
        .disabled(disabled || busy)
    }
}

struct OrbPill: View {
    var orb: Orb?
    var body: some View {
        switch orb?.state {
        case "triggered": Pill(text: "\(orb?.side == "short" ? "▼" : "▲") ORB \(orb?.side ?? "")", tone: orb?.side == "short" ? .down : .up)
        case "expired": Pill(text: "ORB expired")
        default: Pill(text: "ORB waiting", tone: .warn)
        }
    }
}

struct TrendPill: View {
    var trend: String?
    var body: some View {
        switch trend {
        case "up": Pill(text: "Trend up", tone: .up)
        case "down": Pill(text: "Trend down", tone: .down)
        default: Pill(text: "Trend mixed")
        }
    }
}

struct LegendDot: View {
    var color: Color
    var label: String
    var line = false
    var body: some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: line ? 1 : 3).fill(color).frame(width: line ? 14 : 10, height: line ? 2 : 10)
            Text(label).font(.caption).foregroundStyle(Palette.text2)
        }
    }
}

/// Async load state for a screen.
@MainActor
final class Loader<T>: ObservableObject {
    @Published var value: T?
    @Published var error: Error?
    @Published var loading = false

    func run(_ work: @escaping () async throws -> T) async {
        loading = true
        defer { loading = false }
        do { value = try await work(); error = nil } catch { if !(error is CancellationError) { self.error = error } }
    }
}

extension View {
    func screen() -> some View {
        self.scrollContentBackground(.hidden).background(Palette.bg.ignoresSafeArea())
    }
}
