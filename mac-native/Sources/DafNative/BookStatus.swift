import AppKit
import IOKit.ps
import SwiftUI

/// The status bar under a book's pages, as KOReader has it (web/book.js drawStatus): the things picked
/// in Themes & Settings › Status Bar, in their order, one at a time (a click on the bar goes on to the
/// next) or all at once; beside them a thin line of the book with its chapters marked, or of the
/// chapter. It's the same for every book.
@MainActor
@Observable
final class StatusBar {
    static let shared = StatusBar()

    static let items = [("page", "Page"), ("chpage", "Page in Chapter"), ("chleft", "Pages Left in Chapter"), ("bookleft", "Pages Left in Book"),
                        ("pct", "Percent"), ("chtime", "Time Left in Chapter"), ("booktime", "Time Left in Book"), ("chapter", "Chapter"),
                        ("title", "Book Title"), ("clock", "Clock"), ("battery", "Battery")]
    /// KOReader's, in its order: the page, the clock, the pages left in the chapter, the battery, the
    /// percent, and the time left in the book and in the chapter, one at a time, beside the book's line.
    static let defaults = ["page", "clock", "chleft", "battery", "pct", "booktime", "chtime"]

    /// off, one (at a time), all (at once).
    var show: String { didSet { save() } }
    /// off, book, chapter.
    var bar: String { didSet { save() } }
    var chosen: [String] { didSet { save() } }
    /// The one shown, one at a time.
    var at: String { didSet { UserDefaults.standard.set(at, forKey: "statusBarAt") } }

    private init() {
        let d = UserDefaults.standard.dictionary(forKey: "statusBar") ?? [:]
        show = d["show"] as? String ?? "one"
        bar = d["bar"] as? String ?? "book"
        chosen = (d["items"] as? [String] ?? Self.defaults).filter { k in Self.items.contains { $0.0 == k } }
        at = UserDefaults.standard.string(forKey: "statusBarAt") ?? Self.defaults[0]
    }

    private func save() {
        UserDefaults.standard.set(["show": show, "bar": bar, "items": chosen], forKey: "statusBar")
    }

    /// A click on an item: off the bar, or onto its end.
    func flip(_ k: String) {
        if chosen.contains(k) { chosen.removeAll { $0 == k } } else { chosen.append(k) }
    }

    /// The battery, when the Mac has one and it isn't plugged in and full.
    static func battery() -> Double? {
        guard let info = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let list = IOPSCopyPowerSourcesList(info)?.takeRetainedValue() as? [CFTypeRef] else { return nil }
        for ps in list {
            guard let d = IOPSGetPowerSourceDescription(info, ps)?.takeUnretainedValue() as? [String: Any],
                  let cur = d[kIOPSCurrentCapacityKey] as? Int, let max = d[kIOPSMaxCapacityKey] as? Int, max > 0 else { continue }
            let level = Double(cur) / Double(max)
            let charging = (d[kIOPSIsChargingKey] as? Bool) ?? false
            let onAC = (d[kIOPSPowerSourceStateKey] as? String) == kIOPSACPowerValue
            if (charging || onAC) && level >= 0.995 { return nil }
            return level
        }
        return nil
    }
}

/// Where I am in the book, for the bar: worked out as the pages change (BookModel.relocated).
struct BookPlace: Equatable {
    var fraction = 0.0
    /// In the chapter: the pages, the first and the last on the screen (a page a column).
    var chAt = 1, chLast = 1, chPages = 1
    /// Pages, not Scroll: a page is a column there.
    var paged = true
    /// In the book: the page (the printed book's, when the EPUB has its page list), the last on the screen, how many, how many after.
    var cur: String?
    var to: String?
    var total: String?
    var left: Int?
    var printed = false
    /// Minutes left.
    var chMinutes = 0.0, bookMinutes = 0.0
    var chapter = ""
    /// Where the chapters start, as fractions of the book, for the marks on the line; and the chapter's own span.
    var marks: [Double] = []
    var chStart = 0.0, chEnd = 1.0
}

/// The bar itself.
struct BookStatusBar: View {
    let m: BookModel
    private let sb = StatusBar.shared

    var body: some View {
        if sb.show != "off" {
            TimelineView(.periodic(from: .now, by: 15)) { _ in          // the clock and the battery move on while the page stays
                let p = m.status
                let items = sb.chosen.compactMap { k in text(k, p).map { (k, $0) } }
                let shown = sb.show == "one" ? Array(items.first { sb.chosen.firstIndex(of: $0.0) ?? 0 >= (sb.chosen.firstIndex(of: sb.at) ?? 0) }.map { [$0] } ?? items.prefix(1)) : items
                VStack(spacing: 5) {
                    if sb.bar != "off" { line(p) }
                    if !shown.isEmpty {
                        shown.enumerated().reduce(Text("")) { acc, x in
                            let t = x.element.0 == "battery" ? Text(Image(systemName: Self.batterySymbol)) + Text(" " + x.element.1) : Text(x.element.1)
                            return x.offset == 0 ? t : acc + Text("  ·  ") + t
                        }
                            .font(.caption)
                            .monospacedDigit()
                            .lineLimit(1)
                            .help(shown.first?.0 == "page" && p.printed ? "The printed book's page" : "")
                    }
                }
                .foregroundStyle(Color(nsColor: m.look.quiet))
                .frame(maxWidth: 520)
                .padding(.horizontal, 40)
                .contentShape(Rectangle())
                .onTapGesture { next(p) }
                .contextMenu { StatusBarMenu() }
                .environment(\.layoutDirection, m.pages?.rtl == true ? .rightToLeft : .leftToRight)
            }
        }
    }

    private static var batterySymbol: String {
        let l = StatusBar.battery() ?? 1
        return l > 0.88 ? "battery.100percent" : l > 0.62 ? "battery.75percent" : l > 0.37 ? "battery.50percent" : l > 0.12 ? "battery.25percent" : "battery.0percent"
    }

    /// The line: the book, its chapters marked, or the chapter I'm in.
    private func line(_ p: BookPlace) -> some View {
        let chapter = sb.bar == "chapter"
        let x = max(0, min(1, chapter ? Double(p.chLast) / Double(max(1, p.chPages)) : p.fraction))
        return GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Color(nsColor: m.look.quiet).opacity(0.25)).frame(height: 2)
                Capsule().fill(Color(nsColor: m.look.quiet).opacity(0.8)).frame(width: g.size.width * x, height: 2)
                if !chapter {
                    ForEach(p.marks, id: \.self) { f in
                        Rectangle().fill(Color(nsColor: m.look.quiet).opacity(f <= x ? 0.9 : 0.5)).frame(width: 1, height: 6).offset(x: g.size.width * f)
                    }
                }
            }
            .frame(height: 6)
        }
        .frame(height: 6)
    }

    private func text(_ k: String, _ p: BookPlace) -> String? {
        func plural(_ n: Int, _ w: String) -> String { "\(n) \(w)" + (n == 1 ? "" : "s") }
        func mins(_ m: Double) -> String { let n = Int(m.rounded()); return n >= 60 ? "\(n / 60) h \(n % 60) min" : "\(max(1, n)) min" }
        switch k {
        case "page":
            guard let c = p.cur, let t = p.total else { return nil }
            return c + (p.to.map { $0 != c ? "–" + $0 : "" } ?? "") + " of " + t
        case "chpage": return p.paged ? "\(p.chAt)" + (p.chLast > p.chAt ? "–\(p.chLast)" : "") + " of \(p.chPages) in the chapter" : nil
        case "chleft":
            guard p.paged else { return nil }
            let n = p.chPages - p.chLast
            return n > 0 ? plural(n, "page") + " left in the chapter" : "Last page in the chapter"
        case "bookleft": return p.left.map { $0 > 0 ? plural($0, "page") + " left in the book" : "Last page" }
        case "pct": return "\(Int((p.fraction * 100).rounded()))%"
        case "chtime": return (p.chMinutes < 0.5 ? "Under a minute" : mins(p.chMinutes)) + " left in the chapter"
        case "booktime": return (p.bookMinutes < 0.5 ? "Under a minute" : mins(p.bookMinutes)) + " left in the book"
        case "chapter": return p.chapter.isEmpty ? nil : p.chapter
        case "title": return m.title.components(separatedBy: ": ").first
        case "clock": return Date().formatted(date: .omitted, time: .shortened)
        case "battery": return StatusBar.battery().map { "\(Int(($0 * 100).rounded()))%" }
        default: return nil
        }
    }

    /// A click: the next thing (one at a time), else the settings.
    private func next(_ p: BookPlace) {
        guard sb.show == "one", sb.chosen.count > 1 else { return }
        let i = sb.chosen.firstIndex(of: sb.at) ?? 0
        for j in 1..<sb.chosen.count {
            let k = sb.chosen[(i + j) % sb.chosen.count]
            if text(k, p) != nil { sb.at = k; return }
        }
    }
}

/// Themes & Settings › Status Bar, and the bar's right-click: off, one at a time or all at once; the
/// line; and the things on it, those shown first in their order (a click takes one off, or puts it at the end).
struct StatusBarSettings: View {
    private let sb = StatusBar.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Status Bar", selection: Binding(get: { sb.show }, set: { sb.show = $0 })) {
                Text("Off").tag("off")
                Text("One at a Time").tag("one")
                Text("All at Once").tag("all")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            HStack {
                Text("Progress Bar").font(.callout)
                Spacer()
                Picker("Progress Bar", selection: Binding(get: { sb.bar }, set: { sb.bar = $0 })) {
                    Text("Off").tag("off")
                    Text("Book").tag("book")
                    Text("Chapter").tag("chapter")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
            }
            FlowChips(on: sb.chosen, all: StatusBar.items.map(\.0), name: { k in StatusBar.items.first { $0.0 == k }?.1 ?? k }) { sb.flip($0) }
        }
    }
}

/// The bar's right-click: the same settings, as a menu.
struct StatusBarMenu: View {
    private let sb = StatusBar.shared
    var body: some View {
        Picker("Status Bar", selection: Binding(get: { sb.show }, set: { sb.show = $0 })) {
            Text("Off").tag("off")
            Text("One at a Time").tag("one")
            Text("All at Once").tag("all")
        }
        Picker("Progress Bar", selection: Binding(get: { sb.bar }, set: { sb.bar = $0 })) {
            Text("Off").tag("off")
            Text("Book").tag("book")
            Text("Chapter").tag("chapter")
        }
        Divider()
        ForEach(StatusBar.items, id: \.0) { k, name in
            Toggle(name, isOn: Binding(get: { sb.chosen.contains(k) }, set: { _ in sb.flip(k) }))
        }
    }
}

/// Chips that wrap: those on first, in their order, then the rest.
struct FlowChips: View {
    let on: [String]
    let all: [String]
    let name: (String) -> String
    let flip: (String) -> Void

    var body: some View {
        let list = on + all.filter { !on.contains($0) }
        FlowLayout(spacing: 6) {
            ForEach(list, id: \.self) { k in
                let lit = on.contains(k)
                Button { flip(k) } label: {
                    Text(name(k)).font(.caption)
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Capsule().fill(lit ? Theme.shared.accent.opacity(0.2) : Color.secondary.opacity(0.1)))
                        .overlay(Capsule().stroke(lit ? Theme.shared.accent : .clear, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// Views laid out in rows, wrapping at the width.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let w = proposal.width ?? 300
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0
        for s in subviews {
            let z = s.sizeThatFits(.unspecified)
            if x > 0, x + z.width > w { x = 0; y += row + spacing; row = 0 }
            x += z.width + spacing
            row = max(row, z.height)
        }
        return CGSize(width: w, height: y + row)
    }

    func placeSubviews(in b: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = b.minX, y = b.minY, row: CGFloat = 0
        for s in subviews {
            let z = s.sizeThatFits(.unspecified)
            if x > b.minX, x + z.width > b.maxX { x = b.minX; y += row + spacing; row = 0 }
            s.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(z))
            x += z.width + spacing
            row = max(row, z.height)
        }
    }
}
