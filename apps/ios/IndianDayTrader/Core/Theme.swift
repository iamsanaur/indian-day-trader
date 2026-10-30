import SwiftUI
import UIKit

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}

extension Color {
    /// A color that follows the system (or in-app) light/dark appearance.
    static func dynamic(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
}

/// Design tokens shared with the web app (clean light, dark optional).
enum Palette {
    static let bg = Color.dynamic(0xF6F7F9, 0x0F1115)
    static let surface = Color.dynamic(0xFFFFFF, 0x171A21)
    static let surface2 = Color.dynamic(0xF1F3F6, 0x1E222B)
    static let border = Color.dynamic(0xE6E8EC, 0x262A33)
    static let text = Color.dynamic(0x0F172A, 0xE7E9EE)
    static let text2 = Color.dynamic(0x475569, 0xA3AAB8)
    static let muted = Color.dynamic(0x8A94A6, 0x6F7787)
    static let accent = Color.dynamic(0x4F46E5, 0x818CF8)
    static let accentSoft = Color.dynamic(0xEEF0FF, 0x23264A)
    static let up = Color.dynamic(0x0B7A45, 0x3CCB84)
    static let upMark = Color.dynamic(0x12925B, 0x2FB874)
    static let upSoft = Color.dynamic(0xE7F6EE, 0x12261C)
    static let down = Color.dynamic(0xC62F2F, 0xF37272)
    static let downMark = Color.dynamic(0xD03B3B, 0xE66767)
    static let downSoft = Color.dynamic(0xFDECEC, 0x2C1617)
    static let warn = Color.dynamic(0x9A6200, 0xF0B74A)
    static let warnSoft = Color.dynamic(0xFFF4DC, 0x2B2312)
    // Validated categorical slots (CVD-safe in both modes)
    static let series1 = Color.dynamic(0x2A78D6, 0x3987E5)   // calls, EMA 9, today curve
    static let series2 = Color.dynamic(0xEB6834, 0xD95926)   // puts, EMA 21
    static let series3 = Color.dynamic(0x6250D6, 0x9085E9)   // VWAP
}

enum Tone {
    case up, down, warn, accent, neutral

    static func of(_ v: Double?) -> Tone {
        guard let v, v != 0 else { return .neutral }
        return v > 0 ? .up : .down
    }

    var fg: Color {
        switch self {
        case .up: Palette.up
        case .down: Palette.down
        case .warn: Palette.warn
        case .accent: Palette.accent
        case .neutral: Palette.text2
        }
    }

    var bg: Color {
        switch self {
        case .up: Palette.upSoft
        case .down: Palette.downSoft
        case .warn: Palette.warnSoft
        case .accent: Palette.accentSoft
        case .neutral: Palette.surface2
        }
    }
}
