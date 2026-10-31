import AppKit
import SwiftUI

/// An article's type on this Mac, as the page's Themes & Settings keeps it on each device: the size,
/// the typeface, the line spacing and the line's width.
struct ArticleType: Equatable {
    var size: CGFloat = 19
    var font = "New York"
    var spacing: CGFloat = 1.38
    var width = "medium"           // narrow, medium, wide

    /// As kept, read once and again after each change.
    @MainActor static var current = load()

    static func load() -> ArticleType {
        var t = ArticleType()
        guard let d = UserDefaults.standard.dictionary(forKey: "articleType") else { return t }
        t.size = CGFloat((d["size"] as? NSNumber)?.doubleValue ?? Double(t.size))
        t.font = d["font"] as? String ?? t.font
        t.spacing = CGFloat((d["spacing"] as? NSNumber)?.doubleValue ?? Double(t.spacing))
        t.width = d["width"] as? String ?? t.width
        return t
    }

    /// Kept, and every article open set again in it.
    @MainActor func save() {
        UserDefaults.standard.set(["size": size, "font": font, "spacing": spacing, "width": width], forKey: "articleType")
        Self.current = self
        NotificationCenter.default.post(name: .dafType, object: nil)
    }

    /// The text column: narrow, medium or wide.
    var column: CGFloat { ["narrow": 600, "wide": 780][width] ?? 680 }

    /// The typeface at this size (scaled for a heading), as a book sets it.
    func face(scale: CGFloat = 1) -> NSFont {
        var l = BookLook()
        l.font = font
        l.size = size * scale
        return l.font()
    }
}

extension Notification.Name {
    static let dafType = Notification.Name("dafType")
}

/// Themes & Settings (the Aa button), for articles and books, as the page has it: the text bigger
/// or smaller, Pages or Scroll for a book, six looks (three for the day, three for the night, from
/// Daf's themes), when light and dark apply, and below them the typeface and the finer settings.
struct ThemesPanel: View {
    /// The book it's for; nil for an article.
    var book: BookModel?
    @State private var type = ArticleType()
    @State private var look = BookLook()
    @State private var fontOpen = false
    @State private var fineOpen = false

    /// The looks: the theme family, whether it's the night's, and its name.
    static let looks = [("daf", false, "Daf"), ("paper", false, "Paper"), ("eink", false, "E-ink"),
                        ("paper", true, "Dusk"), ("eink", true, "Night"), ("oled", true, "Black")]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Themes & Settings").font(.headline)
            HStack(spacing: 10) {
                HStack(spacing: 0) {
                    Button { bigger(-2) } label: { Text("A").font(.system(size: 13, weight: .medium)).frame(width: 46, height: 28).contentShape(Rectangle()) }
                        .help("Smaller")
                    Divider().frame(height: 18)
                    Button { bigger(2) } label: { Text("A").font(.system(size: 20, weight: .medium)).frame(width: 46, height: 28).contentShape(Rectangle()) }
                        .help("Larger")
                }
                .buttonStyle(.plain)
                .background(RoundedRectangle(cornerRadius: 7).fill(Color.secondary.opacity(0.12)))
                if book != nil {
                    Picker("Layout", selection: Binding(get: { look.flow }, set: { look.flow = $0; restyle() })) {
                        Text("Pages").tag("paginated")
                        Text("Scroll").tag("scrolled")
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(Self.looks, id: \.2) { lookCard($0) }
            }
            Picker("Appearance", selection: Binding(get: { Theme.shared.mode }, set: { Theme.shared.choose(mode: $0) })) {
                Text("Auto").tag("system")
                Text("Light").tag("light")
                Text("Dark").tag("dark")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            DisclosureGroup(isExpanded: $fontOpen) { fonts } label: {
                HStack {
                    Text("Font")
                    Spacer()
                    Text(font).font(sample(font, 13)).foregroundStyle(.secondary)
                }
            }
            DisclosureGroup("Spacing, margins, justify", isExpanded: $fineOpen) { fine }
            Button("All Themes…") { AppModel.shared.openSettings(tab: "appearance") }
                .buttonStyle(.link)
        }
        .padding(16)
        .frame(width: 310)
        .onAppear {
            type = ArticleType.current
            if let book { look = book.look }
        }
    }

    // MARK: the looks

    private func lookCard(_ l: (String, Bool, String)) -> some View {
        let fam = Theme.family(l.0), p = l.1 ? fam.dark : fam.light, th = Theme.shared
        let dark = th.mode == "dark" || (th.mode == "system" && Theme.isDark(NSApp.effectiveAppearance))
        let on = l.1 ? dark && th.dark == l.0 : !dark && th.light == l.0
        return Button { pick(l) } label: {
            VStack(spacing: 1) {
                Text("Aa").font(.system(size: 18, weight: .semibold, design: .serif))
                Text(l.2).font(.caption)
            }
            .foregroundStyle(Color(nsColor: Theme.rgb(p.read ?? p.fg)))
            .frame(maxWidth: .infinity)
            .frame(height: 58)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(nsColor: Theme.rgb(p.bg))))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(on ? th.accent : Color.secondary.opacity(0.3), lineWidth: on ? 2.5 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(l.2)
    }

    /// A day look is the light theme (and light now, if it's dark); a night look the dark one.
    private func pick(_ l: (String, Bool, String)) {
        let th = Theme.shared
        let dark = th.mode == "dark" || (th.mode == "system" && Theme.isDark(NSApp.effectiveAppearance))
        if l.1 { th.choose(mode: dark ? nil : "dark", dark: l.0) } else { th.choose(mode: dark ? "light" : nil, light: l.0) }
        if let book, look.theme != "auto" {          // the book takes the app's look
            look.theme = "auto"
            book.restyle(look)
        }
    }

    // MARK: the type

    private var font: String { book != nil ? look.font : type.font }

    private func sample(_ f: String, _ size: CGFloat) -> Font {
        var l = BookLook()
        l.font = f
        l.size = size
        return Font(l.font() as CTFont)
    }

    private var fonts: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(BookLook.fonts, id: \.self) { f in
                Button {
                    if book != nil { look.font = f; restyle() } else { type.font = f; type.save() }
                } label: {
                    HStack {
                        Text(f).font(sample(f, 15))
                        Spacer()
                        if font == f { Image(systemName: "checkmark").foregroundStyle(Theme.shared.accent) }
                    }
                    .padding(.vertical, 5)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 4)
    }

    private var fine: some View {
        VStack(alignment: .leading, spacing: 10) {
            let size = book != nil ? look.size : type.size, spacing = book != nil ? look.spacing : type.spacing
            stepper("Font size", "\(Int(size)) pt") { bigger(-1) } more: { bigger(1) }
            stepper("Line spacing", String(format: "%.2f", spacing)) { space(-0.05) } more: { space(0.05) }
            Picker("Line width", selection: Binding(get: { book != nil ? look.width : type.width }, set: { w in
                if book != nil { look.width = w; restyle() } else { type.width = w; type.save() }
            })) {
                ForEach(BookLook.widths, id: \.0) { Text($0.1).tag($0.0) }
            }
            .pickerStyle(.segmented)
            if let book {
                Toggle("Justify the text", isOn: Binding(get: { look.justify }, set: { look.justify = $0; restyle() }))
                Toggle("Just for this book", isOn: Binding(get: { book.ownLook }, set: { on in
                    book.ownLook = on
                    if !on { UserDefaults.standard.removeObject(forKey: "book.look." + book.id); look = BookLook.load() }
                    restyle()
                }))
            }
        }
        .padding(.top, 6)
    }

    private func stepper(_ label: String, _ value: String, less: @escaping () -> Void, more: @escaping () -> Void) -> some View {
        HStack {
            Text(label)
            Spacer()
            Button("−", action: less).frame(width: 26)
            Text(value).monospacedDigit().frame(minWidth: 52)
            Button("+", action: more).frame(width: 26)
        }
    }

    private func bigger(_ d: CGFloat) {
        if book != nil { look.size = min(34, max(13, look.size + d)); restyle() }
        else { type.size = min(34, max(13, type.size + d)); type.save() }
    }

    private func space(_ d: CGFloat) {
        if book != nil { look.spacing = min(2.0, max(1.1, ((look.spacing + d) * 20).rounded() / 20)); restyle() }
        else { type.spacing = min(2.0, max(1.1, ((type.spacing + d) * 20).rounded() / 20)); type.save() }
    }

    private func restyle() { book?.restyle(look) }
}

/// "12 min left", quiet under the text, as the page says it.
struct MinutesLeft: View {
    let model: ReaderModel
    var body: some View {
        if let s = model.minutesLeft {
            Text(s)
                .font(.caption)
                .foregroundStyle(Color(nsColor: Theme.nsQuiet))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Capsule().fill(Color(nsColor: Theme.nsBG).opacity(0.85)))
                .padding(.bottom, 10)
                .allowsHitTesting(false)
        }
    }
}
