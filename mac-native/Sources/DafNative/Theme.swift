import AppKit
import SwiftUI

/// Daf's themes, as the page's (web/themes.js): each a light and a dark version, one chosen for light
/// and one for dark, and when each applies (with the Mac, always light, always dark). The choice is
/// kept in Daf (settings.appearance), so the page, the phone and this Mac read alike. A theme is a
/// handful of colours; the pages, the lists, the reader and the highlights take theirs from it.
/// Books keep their own themes (the Aa panel), as on the page.
struct Palette: Sendable {
    var bg: String
    var side: String? = nil
    var fg: String
    var read: String? = nil
    var accent: String
    var hls: [String: String] = [:]
    /// Absolute's: the quiet text and the cards in the text's and the page's own colours, nothing grey.
    var pure = false
}

struct Family: Identifiable, Sendable {
    let id: String
    let name: String
    let note: String
    let light: Palette
    let dark: Palette
}

@MainActor
@Observable
final class Theme {
    static let shared = Theme()

    nonisolated static let families: [Family] = [
        Family(id: "daf", name: "Daf", note: "Teal on white; a warm, softer dark",
               light: Palette(bg: "#ffffff", side: "#f7f7f8", fg: "#1d2127", accent: "#1a7da4"),
               dark: Palette(bg: "#141519", side: "#1a1b20", fg: "#e8e6e1", read: "#d9d6cf", accent: "#62b6da")),
        Family(id: "paper", name: "Paper", note: "Sepia, like a printed page",
               light: Palette(bg: "#f7f0e3", side: "#f0e7d6", fg: "#3a3127", accent: "#9a5b1f", hls: ["yellow": "#d9ae35", "green": "#7fae66", "blue": "#7a9fc4", "pink": "#d4839a", "purple": "#a68bc2"]),
               dark: Palette(bg: "#1d1915", side: "#241f19", fg: "#e8dcc6", read: "#dccfb6", accent: "#d39a5b")),
        Family(id: "nord", name: "Nord", note: "Arctic blues",
               light: Palette(bg: "#eceff4", side: "#e5e9f0", fg: "#2e3440", accent: "#5e81ac", hls: ["yellow": "#ebcb8b", "green": "#a3be8c", "blue": "#81a1c1", "pink": "#d08770", "purple": "#b48ead"]),
               dark: Palette(bg: "#2e3440", side: "#3b4252", fg: "#e5e9f0", read: "#d8dee9", accent: "#88c0d0", hls: ["yellow": "#ebcb8b", "green": "#a3be8c", "blue": "#81a1c1", "pink": "#d08770", "purple": "#b48ead"])),
        Family(id: "github", name: "GitHub", note: "Primer, light and dark",
               light: Palette(bg: "#ffffff", side: "#f6f8fa", fg: "#1f2328", accent: "#0969da"),
               dark: Palette(bg: "#0d1117", side: "#161b22", fg: "#e6edf3", read: "#d1d9e0", accent: "#4493f8")),
        Family(id: "github-dimmed", name: "GitHub dimmed", note: "GitHub’s softer dark",
               light: Palette(bg: "#ffffff", side: "#f6f8fa", fg: "#1f2328", accent: "#0969da"),
               dark: Palette(bg: "#22272e", side: "#2d333b", fg: "#cdd9e5", read: "#adbac7", accent: "#539bf5")),
        Family(id: "cupertino", name: "Cupertino", note: "Apple’s system colours",
               light: Palette(bg: "#ffffff", side: "#f2f2f7", fg: "#1c1c1e", accent: "#007aff", hls: ["yellow": "#ffcc00", "green": "#34c759", "blue": "#5ac8fa", "pink": "#ff2d55", "purple": "#af52de"]),
               dark: Palette(bg: "#1c1c1e", side: "#2c2c2e", fg: "#f2f2f7", read: "#e5e5ea", accent: "#0a84ff", hls: ["yellow": "#ffd60a", "green": "#30d158", "blue": "#64d2ff", "pink": "#ff375f", "purple": "#bf5af2"])),
        Family(id: "solarized", name: "Solarized", note: "Ethan Schoonover’s",
               light: Palette(bg: "#fdf6e3", side: "#eee8d5", fg: "#475b62", accent: "#268bd2", hls: ["yellow": "#b58900", "green": "#859900", "blue": "#268bd2", "pink": "#d33682", "purple": "#6c71c4"]),
               dark: Palette(bg: "#002b36", side: "#073642", fg: "#a3b1b1", read: "#93a1a1", accent: "#268bd2", hls: ["yellow": "#b58900", "green": "#859900", "blue": "#268bd2", "pink": "#d33682", "purple": "#6c71c4"])),
        Family(id: "gruvbox", name: "Gruvbox", note: "Retro, warm",
               light: Palette(bg: "#fbf1c7", side: "#f2e5bc", fg: "#3c3836", accent: "#076678", hls: ["yellow": "#d79921", "green": "#98971a", "blue": "#458588", "pink": "#b16286", "purple": "#8f3f71"]),
               dark: Palette(bg: "#282828", side: "#32302f", fg: "#ebdbb2", read: "#e1d2a9", accent: "#83a598", hls: ["yellow": "#fabd2f", "green": "#b8bb26", "blue": "#83a598", "pink": "#d3869b", "purple": "#b16286"])),
        Family(id: "catppuccin", name: "Catppuccin", note: "Latte and Mocha",
               light: Palette(bg: "#eff1f5", side: "#e6e9ef", fg: "#4c4f69", accent: "#1e66f5", hls: ["yellow": "#df8e1d", "green": "#40a02b", "blue": "#1e66f5", "pink": "#ea76cb", "purple": "#8839ef"]),
               dark: Palette(bg: "#1e1e2e", side: "#181825", fg: "#cdd6f4", accent: "#89b4fa", hls: ["yellow": "#f9e2af", "green": "#a6e3a1", "blue": "#89b4fa", "pink": "#f5c2e7", "purple": "#cba6f7"])),
        Family(id: "rose-pine", name: "Rosé Pine", note: "Dawn and Moon",
               light: Palette(bg: "#faf4ed", side: "#f2e9e1", fg: "#575279", accent: "#286983", hls: ["yellow": "#ea9d34", "green": "#56949f", "blue": "#286983", "pink": "#d7827e", "purple": "#907aa9"]),
               dark: Palette(bg: "#232136", side: "#2a273f", fg: "#e0def4", accent: "#c4a7e7", hls: ["yellow": "#f6c177", "green": "#9ccfd8", "blue": "#3e8fb0", "pink": "#ea9a97", "purple": "#c4a7e7"])),
        Family(id: "tokyo", name: "Tokyo Night", note: "Day and Night",
               light: Palette(bg: "#e1e2e7", side: "#d5d6db", fg: "#343b58", accent: "#2e7de9", hls: ["yellow": "#8c6c3e", "green": "#587539", "blue": "#2e7de9", "pink": "#f52a65", "purple": "#9854f1"]),
               dark: Palette(bg: "#1a1b26", side: "#16161e", fg: "#c0caf5", read: "#a9b1d6", accent: "#7aa2f7", hls: ["yellow": "#e0af68", "green": "#9ece6a", "blue": "#7aa2f7", "pink": "#f7768e", "purple": "#bb9af7"])),
        Family(id: "one", name: "One", note: "Atom’s One Light and One Dark",
               light: Palette(bg: "#fafafa", side: "#f0f0f1", fg: "#383a42", accent: "#4078f2", hls: ["yellow": "#c18401", "green": "#50a14f", "blue": "#4078f2", "pink": "#e45649", "purple": "#a626a4"]),
               dark: Palette(bg: "#282c34", side: "#21252b", fg: "#d7dae0", read: "#abb2bf", accent: "#61afef", hls: ["yellow": "#e5c07b", "green": "#98c379", "blue": "#61afef", "pink": "#e06c75", "purple": "#c678dd"])),
        Family(id: "dracula", name: "Dracula", note: "and Alucard, its light one",
               light: Palette(bg: "#fffbeb", side: "#f5f0d8", fg: "#1f1f1f", accent: "#644ac9", hls: ["yellow": "#846e15", "green": "#14710a", "blue": "#036a96", "pink": "#a3144d", "purple": "#644ac9"]),
               dark: Palette(bg: "#282a36", side: "#21222c", fg: "#f8f8f2", read: "#e9e9e2", accent: "#bd93f9", hls: ["yellow": "#f1fa8c", "green": "#50fa7b", "blue": "#8be9fd", "pink": "#ff79c6", "purple": "#bd93f9"])),
        Family(id: "everforest", name: "Everforest", note: "Green and calm",
               light: Palette(bg: "#fdf6e3", side: "#f4f0d9", fg: "#4d5a61", accent: "#3a94c5", hls: ["yellow": "#dfa000", "green": "#8da101", "blue": "#3a94c5", "pink": "#f85552", "purple": "#df69ba"]),
               dark: Palette(bg: "#2d353b", side: "#343f44", fg: "#d3c6aa", accent: "#a7c080", hls: ["yellow": "#dbbc7f", "green": "#a7c080", "blue": "#7fbbb3", "pink": "#e67e80", "purple": "#d699b6"])),
        Family(id: "eink", name: "E-ink", note: "Greys, like the Kindle",
               light: Palette(bg: "#f4f1ea", side: "#ebe7de", fg: "#1a1a1a", accent: "#2f2f2f", hls: ["yellow": "#b9a24a", "green": "#7f9a72", "blue": "#7890a8", "pink": "#b5848f", "purple": "#9789ad"]),
               dark: Palette(bg: "#121212", side: "#1a1a1a", fg: "#e8e4da", read: "#ddd8cc", accent: "#c9c9c9")),
        Family(id: "contrast", name: "High contrast", note: "Black and white, for bright light",
               light: Palette(bg: "#ffffff", side: "#f3f3f3", fg: "#000000", accent: "#0040c0"),
               dark: Palette(bg: "#000000", side: "#0c0c0c", fg: "#ffffff", accent: "#7ab8ff")),
        Family(id: "oled", name: "Black", note: "Pure black for OLED screens; Daf’s light by day",
               light: Palette(bg: "#ffffff", side: "#f7f7f8", fg: "#1d2127", accent: "#1a7da4"),
               dark: Palette(bg: "#000000", side: "#0b0b0c", fg: "#e8e6e1", read: "#d6d3cc", accent: "#62b6da")),
        Family(id: "absolute", name: "Absolute", note: "Pure black on white and pure white on black, nothing grey",
               light: Palette(bg: "#ffffff", side: "#ffffff", fg: "#000000", accent: "#000000", pure: true),
               dark: Palette(bg: "#000000", side: "#000000", fg: "#ffffff", accent: "#ffffff", pure: true)),
    ]

    var mode = "system"        // system, light, dark
    var light = "daf"
    var dark = "daf"
    /// Goes up with every change, so what's drawn from the theme is drawn again.
    private(set) var revision = 0

    /// What the colours are made from (read from AppKit's drawing too, so not tied to the main actor).
    nonisolated(unsafe) static var palettes = (light: families[0].light, dark: families[0].dark)

    private init() {
        if let d = UserDefaults.standard.dictionary(forKey: "appearance") { take(d, save: false) } else { Self.make() }
    }

    nonisolated static func family(_ id: String) -> Family { families.first { $0.id == id } ?? families[0] }

    /// Daf's choice (settings.appearance), when it differs from this Mac's (and not while a choice
    /// made here is still on its way to Daf).
    func adopt(_ a: J?) {
        guard let a, Date() > choosing else { return }
        let m = a.s("mode") ?? "system", l = a.s("light") ?? "daf", d = a.s("dark") ?? "daf"
        guard m != mode || l != light || d != dark else { return }
        take(["mode": m, "light": l, "dark": d], save: false)
    }

    /// A new choice: put on now, and kept in Daf for every device.
    func choose(mode m: String? = nil, light l: String? = nil, dark d: String? = nil) {
        take(["mode": m ?? mode, "light": l ?? light, "dark": d ?? dark], save: true)
    }

    @ObservationIgnored private var choosing = Date.distantPast

    private func take(_ a: [String: Any], save: Bool) {
        if save { choosing = Date().addingTimeInterval(10) }
        mode = a["mode"] as? String ?? "system"
        light = a["light"] as? String ?? "daf"
        dark = a["dark"] as? String ?? "daf"
        Self.palettes = (Self.family(light).light, Self.family(dark).dark)
        UserDefaults.standard.set(["mode": mode, "light": light, "dark": dark], forKey: "appearance")
        NSApp?.appearance = mode == "light" ? NSAppearance(named: .aqua) : mode == "dark" ? NSAppearance(named: .darkAqua) : nil
        Self.make()
        revision += 1
        NotificationCenter.default.post(name: .dafTheme, object: nil)
        if save {
            let body: [String: Any] = ["appearance": ["mode": mode, "light": light, "dark": dark]]
            Task { try? await API.shared.send("PUT", "/api/settings", body) }
        }
    }

    // MARK: the colours

    /// "#rrggbb" as a colour.
    nonisolated static func rgb(_ h: String) -> NSColor {
        let v = UInt32(h.dropFirst(), radix: 16) ?? 0
        return NSColor(srgbRed: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255, blue: CGFloat(v & 255) / 255, alpha: 1)
    }

    /// a, moved toward b by t (as the page mixes them).
    nonisolated static func mix(_ a: NSColor, _ b: NSColor, _ t: CGFloat) -> NSColor {
        let x = a.usingColorSpace(.sRGB) ?? a, y = b.usingColorSpace(.sRGB) ?? b
        return NSColor(srgbRed: x.redComponent + (y.redComponent - x.redComponent) * t, green: x.greenComponent + (y.greenComponent - x.greenComponent) * t,
                       blue: x.blueComponent + (y.blueComponent - x.blueComponent) * t, alpha: 1)
    }

    nonisolated static func isDark(_ a: NSAppearance) -> Bool { a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua }

    /// A colour that follows light and dark, from the palette in use for each.
    nonisolated static func dynamic(_ f: @escaping @Sendable (Palette, Bool) -> NSColor) -> NSColor {
        NSColor(name: nil) { a in
            let dark = isDark(a)
            return f(dark ? palettes.dark : palettes.light, dark)
        }
    }

    // made again with every change, so SwiftUI sees new colours
    nonisolated(unsafe) private(set) static var nsBG = NSColor.textBackgroundColor
    nonisolated(unsafe) private(set) static var nsSide = NSColor.windowBackgroundColor
    nonisolated(unsafe) private(set) static var nsCard = NSColor.controlBackgroundColor
    nonisolated(unsafe) private(set) static var nsFG = NSColor.textColor
    nonisolated(unsafe) private(set) static var nsRead = NSColor.textColor
    nonisolated(unsafe) private(set) static var nsQuiet = NSColor.secondaryLabelColor
    nonisolated(unsafe) private(set) static var nsAccent = NSColor.controlAccentColor

    nonisolated static func make() {
        nsBG = dynamic { p, _ in rgb(p.bg) }
        nsSide = dynamic { p, dark in p.side.map(rgb) ?? mix(rgb(p.bg), rgb(p.fg), dark ? 0.04 : 0.025) }
        nsCard = dynamic { p, dark in p.pure ? rgb(p.bg) : mix(rgb(p.bg), rgb(p.fg), dark ? 0.06 : 0.04) }
        nsFG = dynamic { p, _ in rgb(p.fg) }
        nsRead = dynamic { p, _ in rgb(p.read ?? p.fg) }
        nsQuiet = dynamic { p, _ in p.pure ? rgb(p.fg) : mix(rgb(p.fg), rgb(p.bg), 0.34) }
        nsAccent = dynamic { p, _ in rgb(p.accent) }
    }

    nonisolated static let hues = ["yellow": "#f0c232", "green": "#62b862", "blue": "#4f8fe6", "pink": "#e8679a", "purple": "#9b72d9"]

    /// A highlight's colour on this theme's page, as the page mixes it.
    nonisolated static func highlight(_ c: String?) -> NSColor {
        let k = c == "red" ? "pink" : (c.flatMap { hues[$0] != nil ? $0 : nil } ?? "yellow")
        return dynamic { p, dark in mix(rgb(p.bg), rgb(p.hls[k] ?? hues[k]!), p.pure ? (dark ? 0.42 : 0.5) : dark ? 0.32 : 0.38) }
    }

    // SwiftUI's, read through `revision` so a change draws them again
    var bg: Color { _ = revision; return Color(nsColor: Self.nsBG) }
    var side: Color { _ = revision; return Color(nsColor: Self.nsSide) }
    var card: Color { _ = revision; return Color(nsColor: Self.nsCard) }
    var accent: Color { _ = revision; return Color(nsColor: Self.nsAccent) }

    /// A family's swatch: its page, its text and its accent.
    static func swatch(_ p: Palette) -> (Color, Color, Color) { (Color(nsColor: rgb(p.bg)), Color(nsColor: rgb(p.fg)), Color(nsColor: rgb(p.accent))) }
}

extension Color {
    /// The theme's accent (links, the ring, what's chosen), where the Mac's own was.
    static var daf: Color { Color(nsColor: Theme.nsAccent) }
}

extension Notification.Name {
    static let dafTheme = Notification.Name("dafTheme")
}

/// A page on the theme's background (and a list's, without its own).
struct Themed: ViewModifier {
    var list = false
    @ViewBuilder func body(content: Content) -> some View {
        let t = Theme.shared
        if list { content.scrollContentBackground(.hidden).background(t.bg) } else { content.background(t.bg) }
    }
}

extension View {
    func themed(list: Bool = false) -> some View { modifier(Themed(list: list)) }
}

/// Settings › Appearance: when it's light and when dark, and the theme for each.
struct AppearancePrefs: View {
    @State private var theme = Theme.shared

    var body: some View {
        Form {
            Section {
                Picker("Appearance", selection: Binding(get: { theme.mode }, set: { theme.choose(mode: $0) })) {
                    Text("With the Mac").tag("system")
                    Text("Light").tag("light")
                    Text("Dark").tag("dark")
                }
                .pickerStyle(.segmented)
            } footer: {
                Text("Kept in Daf, so the page and the phone look the same. Books keep their own themes, in the Aa panel.").foregroundStyle(.secondary)
            }
            Section("When it's light") { families(dark: false) }
            Section("When it's dark") { families(dark: true) }
        }
        .formStyle(.grouped)
    }

    private func families(dark: Bool) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
            ForEach(Theme.families) { f in
                let p = dark ? f.dark : f.light, chosen = (dark ? theme.dark : theme.light) == f.id
                let (bg, fg, ac) = Theme.swatch(p)
                Button { if dark { theme.choose(dark: f.id) } else { theme.choose(light: f.id) } } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 4) {
                            Text("Aa").font(.system(.title3, design: .serif).weight(.semibold)).foregroundStyle(fg)
                            Spacer()
                            Circle().fill(ac).frame(width: 10, height: 10)
                        }
                        RoundedRectangle(cornerRadius: 2).fill(fg.opacity(0.35)).frame(height: 3)
                        RoundedRectangle(cornerRadius: 2).fill(fg.opacity(0.2)).frame(width: 70, height: 3)
                    }
                    .padding(10)
                    .background(bg, in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(chosen ? Color.accentColor : Color.secondary.opacity(0.25), lineWidth: chosen ? 2.5 : 1))
                    .overlay(alignment: .bottomLeading) {
                        Text(f.name).font(.caption).foregroundStyle(.secondary).offset(y: 18)
                    }
                    .padding(.bottom, 18)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(f.note)
            }
        }
        .padding(.vertical, 4)
    }
}
