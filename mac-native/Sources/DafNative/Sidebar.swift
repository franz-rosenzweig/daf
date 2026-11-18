import AppKit
import SwiftUI

/// The sidebar: shown or hidden, and full or mini (its icons) when it shows, kept on this Mac.
/// ⌘\ and the button at the top left show and hide it; View › Sidebar and Settings › General
/// choose full or mini. It stays as it is when something is opened: the list is beside the article,
/// and the way to the rest of Daf shouldn't go with it.
@MainActor
@Observable
final class Side {
    static let shared = Side()
    static let modes = [("full", "Full"), ("mini", "Mini"), ("hidden", "Hidden")]

    /// Its size when it shows.
    var size = UserDefaults.standard.string(forKey: "sideSize") ?? (UserDefaults.standard.string(forKey: "sideMode") == "mini" ? "mini" : "full") {
        didSet { UserDefaults.standard.set(size, forKey: "sideSize"); apply() }
    }
    var hidden = UserDefaults.standard.object(forKey: "sideHidden") as? Bool ?? (UserDefaults.standard.string(forKey: "sideMode") == "hidden") {
        didSet { UserDefaults.standard.set(hidden, forKey: "sideHidden"); apply() }
    }
    /// The mini sidebar: wide enough for each place's name under its icon.
    static let miniWidth: (min: CGFloat, ideal: CGFloat, max: CGFloat) = (68, 74, 84)
    /// The width the split view was last given, so a width dragged by hand stays.
    @ObservationIgnored private var widthFor = ""

    /// Full, mini or hidden, as Settings has it.
    var mode: String {
        get { shown }
        set {
            if newValue == "hidden" { hidden = true; return }
            size = newValue
            hidden = false
        }
    }
    var shown: String { hidden ? "hidden" : size }
    var mini: Bool { shown == "mini" }

    /// ⌘\ and the button at the top left.
    func toggle() { hidden.toggle() }

    /// The main window's sidebar at its width. Shown or hidden is the split view's own
    /// (MainView's columnVisibility): set here in AppKit, SwiftUI put it back as it had it.
    func apply() {
        let want = shown == "hidden" ? "" : mini ? "mini" : "full", changed = want != widthFor
        widthFor = want
        guard !want.isEmpty else { return }
        fit(changed)
        // and once SwiftUI has brought it out (or made its split view again)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { MainActor.assumeIsolated { Side.shared.fit(changed) } }
    }

    /// An open sidebar at its width: as it was dragged, unless it changed size or is out of bounds.
    private func fit(_ changed: Bool) {
        for w in NSApp.windows where Focus.isMain(w) && !Focus.shared.isOn(w) {
            guard let s = Focus.split(w), s.splitViewItems.count > 1, !s.splitViewItems[0].isCollapsed else { continue }
            let item = s.splitViewItems[0]
            item.minimumThickness = size == "mini" ? Self.miniWidth.min : 190
            item.maximumThickness = size == "mini" ? Self.miniWidth.max : 320
            let wide = item.viewController.view.frame.width
            if changed || wide < item.minimumThickness - 1 || wide > item.maximumThickness + 1 {
                s.splitView.setPosition(size == "mini" ? Self.miniWidth.ideal : 220, ofDividerAt: 0)
            }
        }
    }

    /// After the window has made its split view again (a page and a list have different ones).
    func applySoon() {
        widthFor = ""
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { MainActor.assumeIsolated { Side.shared.apply() } }
    }

    // MARK: pinned

    /// What can be pinned: the key Daf keeps (settings.nav_pins), its name, its place, its icon. Podcasts is the
    /// whole of Listen. Sources and Learn can be pinned on the web's old look only: here Sources is in the ⋯ menu.
    static let pinnable: [(String, String, Place, String)] = [
        ("podcasts", "Podcasts", .podcasts, "headphones"), ("manga", "Manga", .manga, "book.pages"), ("torah", "Torah", .torah, "scroll"),
        ("recovery", "Recovery", .recovery, "sunrise"), ("shortlist", "Shortlist", .shortlist, "star"),
        ("paper", "Paper Pages", .paper, "camera.viewfinder"),
    ]
    static let pinnedByDefault = ["podcasts", "manga", "torah", "recovery", "shortlist"]

    /// What's pinned, as Daf keeps it for every device.
    func pins(_ settings: J?) -> [String] {
        (settings?.raw["nav_pins"] as? [Any])?.compactMap { $0 as? String } ?? Self.pinnedByDefault
    }

    func setPins(_ keys: [String]) async {
        // in the order they show; a key only the web knows (sources, learn) is kept as it was
        let known = Self.pinnable.map(\.0)
        let ordered = known.filter(keys.contains) + keys.filter { !known.contains($0) }
        do {
            try await API.shared.send("PUT", "/api/settings", ["nav_pins": ordered])
            AppModel.shared.pinned(ordered)
        } catch { AppModel.shared.error = error.localizedDescription }
    }
}

/// A label's look: its icon and name, or in the mini sidebar the icon with its name under it (the bottom
/// buttons). The name never shrinks to fit: text that scales with the width changes a row's height, and in a
/// list 68–84 wide that fed back into the width until AppKit gave up on the window (the 0.6.6 crash at mini).
struct SideLabelStyle: LabelStyle {
    let mini: Bool
    func makeBody(configuration: Configuration) -> some View {
        if mini {
            VStack(spacing: 2) {
                configuration.icon.font(.title3)
                configuration.title.font(.system(size: 9.5, weight: .medium)).lineLimit(1).truncationMode(.tail)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 2)
        } else { Label(configuration) }
    }
}

/// The sidebar is the web app's map turned on its side: its tabs are the headings, in the same order
/// (Today, Books, Library, Feed, Learn, Listen; web/look2.js tabs()), and each tab's pages are the rows
/// under it. What can be pinned (settings nav_pins) sits under the heading the web keeps it in.
struct Sidebar: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openSettings) private var openSettings
    @AppStorage("libOpen") private var libOpen = false
    @AppStorage("catsOpen") private var catsOpen = true

    /// Listen's pages, as the Podcasts page has them (PodcastCategories.cats), each with its icon.
    static let listen = [("", "Listening", "play.circle"), ("shows", "Shows", "mic"), ("episodes", "Episodes", "list.bullet"),
                         ("recordings", "Recordings", "waveform"), ("audiobooks", "Audiobooks", "headphones"), ("clips", "Clips", "scissors")]

    /// The row chosen. Listen's pages are rows of their own, but being on one is the Podcasts page at that
    /// category: a show sits under Shows and one of Audiobookshelf's recordings under Recordings, as on the web.
    private var chosen: Binding<Place?> {
        Binding(get: {
            guard model.place == .podcasts else { return model.place }
            if Side.shared.mini { return .listen("") }
            switch model.podNav {
            case .cat(let c): return .listen(c)
            case .show: return .listen("shows")
            case .abs: return .listen("recordings")
            }
        }, set: { p in
            if case .listen(let c)? = p { model.podNav = .cat(c); model.place = .podcasts } else { model.place = p }
        })
    }

    var body: some View {
        let mini = Side.shared.mini
        let pins = Side.shared.pins(model.today?.o("settings"))
        Group {
            if mini { rail(pins) } else { list(pins) }
        }
        .labelStyle(SideLabelStyle(mini: mini))
        .safeAreaInset(edge: .top) {
            if mini {                                   // ☰: the full sidebar
                Button { Side.shared.size = "full" } label: { Image(systemName: "line.3.horizontal").font(.title3).frame(maxWidth: .infinity) }
                    .buttonStyle(.borderless)
                    .help("The full sidebar")
                    .padding(.top, 4)
            }
        }
        .safeAreaInset(edge: .bottom) {
            VStack(alignment: .leading, spacing: 2) {
                if Connection.shared.offline {
                    Label(Outbox.shared.ops.isEmpty ? "Offline: what this Mac kept" : "Offline · " + plural(Outbox.shared.ops.count, "change") + " waiting",
                          systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 4)
                }
                // Search, Stats and Sources are in the toolbar now (FrameTools): its Search, its ring and its ⋯
                bottom("Preferences", "gearshape", "⌘,", mini) { openSettings() }
            }
            .labelStyle(SideLabelStyle(mini: mini))
            .padding(.horizontal, mini ? 4 : 10)
            .padding(.vertical, 8)
        }
    }

    /// The full sidebar: a list with the tabs as its headings.
    private func list(_ pins: [String]) -> some View {
        List(selection: chosen) {
            Section("Today") {
                row(.today, "Today", "sun.max")
                if let ed = model.today?.o("edition"), ed.b("on") || (ed.i("total") ?? 0) > 0 {
                    Label("Edition", systemImage: "newspaper")
                        .badge((ed.i("total") ?? 0) == 0 ? nil : Text("\(ed.i("done") ?? 0)/\(ed.i("total") ?? 0)"))
                        .tag(Place.edition)
                }
                row(.recents, "Recents", "clock")
                if pins.contains("recovery") { pinned("recovery") }
            }
            Section("Books") {
                BooksRow()
                row(.catalog, "All Books", "tablecells")
                if pins.contains("manga") { pinned("manga") }
                if pins.contains("torah") { pinned("torah") }
            }
            Section("Library") {
                DisclosureGroup(isExpanded: $libOpen) {
                    ForEach(kinds, id: \.0) { k in row(.kind(k.0), k.1, k.2) }
                    ForEach(model.views, id: \.self) { v in
                        Label(v.s("name") ?? "View", systemImage: "line.3.horizontal.decrease.circle")
                            .tag(Place.view(v.s("id") ?? ""))
                            .contextMenu { Button("Remove the View", role: .destructive) { Task { await model.removeView(v.s("id") ?? "") } } }
                    }
                } label: { row(.home, "Library", "tray.full") }
                if pins.contains("shortlist") { pinned("shortlist") }
            }
            Section("Feed") {
                DisclosureGroup(isExpanded: $catsOpen) {
                    FeedPins()
                } label: {
                    row(.feed(nil), "Feed", "dot.radiowaves.up.forward")
                        .contextMenu { ScopeMenu(place: .feed(nil)) }
                }
            }
            Section("Learn") {
                row(.highlights, "Highlights", "highlighter")
                row(.review, "Review", "rectangle.stack")
                if pins.contains("paper") { pinned("paper") }
            }
            if pins.contains("podcasts") {
                Section("Listen") {
                    ForEach(Self.listen, id: \.0) { p in row(.listen(p.0), p.1, p.2) }
                }
            }
            if model.place == .search {
                Section("Search") { row(.search, "“\(model.query)”", "magnifyingglass") }
            }
        }
        .listStyle(.sidebar)
    }

    /// The mini sidebar: each place's icon with its name under it, in a column of its own making. A list's
    /// rows keep margins for arrows and counts, which left a name five letters wide; and with no list here
    /// there are no rows whose height can chase the sidebar's width (the 0.6.6 crash).
    private func rail(_ pins: [String]) -> some View {
        func pin(_ k: String) -> [(Place, String, String, String?)] {
            Side.pinnable.filter { $0.0 == k && pins.contains(k) }.map { ($0.2, $0.1, $0.3, k) }
        }
        let ed = model.today?.o("edition"), hasEd = ed.map { $0.b("on") || ($0.i("total") ?? 0) > 0 } ?? false
        var groups: [[(Place, String, String, String?)]] = [
            [(.today, "Today", "sun.max", nil)] + (hasEd ? [(.edition, "Edition", "newspaper", nil)] : []) + [(.recents, "Recents", "clock", nil)] + pin("recovery"),
            [(.books, "Books", "books.vertical", nil), (.catalog, "All Books", "tablecells", nil)] + pin("manga") + pin("torah"),
            [(.home, "Library", "tray.full", nil)] + pin("shortlist"),
            [(.feed(nil), "Feed", "dot.radiowaves.up.forward", nil)],
            [(.highlights, "Highlights", "highlighter", nil), (.review, "Review", "rectangle.stack", nil)] + pin("paper"),
        ]
        if pins.contains("podcasts") { groups.append([(.listen(""), "Listen", "headphones", nil)]) }
        if model.place == .search { groups.append([(.search, "Search", "magnifyingglass", nil)]) }
        return ScrollView {
            VStack(spacing: 10) {
                ForEach(Array(groups.enumerated()), id: \.offset) { _, g in
                    VStack(spacing: 1) {
                        ForEach(g, id: \.0) { x in railItem(x.0, x.1, x.2, pin: x.3) }
                    }
                }
            }
            .padding(.horizontal, 5)
            .padding(.vertical, 6)
        }
    }

    private func railItem(_ p: Place, _ title: String, _ icon: String, pin: String?) -> some View {
        let on = railOn(p)
        return Button { chosen.wrappedValue = p } label: {
            VStack(spacing: 2) {
                Image(systemName: icon).font(.title3).frame(height: 22)
                Text(title).font(.system(size: 9.5, weight: .medium)).lineLimit(1).truncationMode(.tail)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 5)
            .foregroundStyle(on ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
            .background(on ? AnyShapeStyle(.tint.opacity(0.16)) : AnyShapeStyle(.clear), in: RoundedRectangle(cornerRadius: 8))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(title)
        .contextMenu {
            if let pin {
                Button("Unpin from the Sidebar") {
                    Task { await Side.shared.setPins(Side.shared.pins(model.today?.o("settings")).filter { $0 != pin }) }
                }
            } else if p == .feed(nil) { ScopeMenu(place: .feed(nil)) }
        }
    }

    /// Whether the mini sidebar's icon is where I am: its own place, or one that hangs under it in the full sidebar.
    private func railOn(_ p: Place) -> Bool {
        guard let now = chosen.wrappedValue else { return false }
        if now == p { return true }
        switch now {
        case .kind, .view, .library: return p == .home
        case .shelf: return p == .books
        case .feed, .feedSource, .feeds: return p == .feed(nil)
        default: return false
        }
    }

    /// The Library's kinds; Emails once there are any.
    private var kinds: [(String, String, String)] {
        let have = model.counts?.o("library")?.raw ?? [:]
        return Place.kinds.filter { $0.0 != "email" || have["email"] != nil }
    }

    private func row(_ p: Place, _ title: String, _ icon: String) -> some View {
        Label(title, systemImage: icon)
            .badge(model.count(p) ?? 0)
            .tag(p)
    }

    /// A place that shows only while it's pinned (Preferences › General has the list); a right-click unpins it.
    private func pinned(_ key: String) -> some View {
        let p = Side.pinnable.first { $0.0 == key } ?? (key, key.capitalized, Place.today, "pin")
        return row(p.2, p.1, p.3)
            .contextMenu {
                Button("Unpin from the Sidebar") {
                    Task { await Side.shared.setPins(Side.shared.pins(model.today?.o("settings")).filter { $0 != key }) }
                }
            }
    }

    private func bottom(_ title: String, _ icon: String, _ key: String?, _ mini: Bool, on: Bool = false, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            HStack {
                Label(title, systemImage: icon)
                if !mini, let key { Spacer(); Text(key).font(.caption).foregroundStyle(.tertiary) }
            }
            .padding(.horizontal, mini ? 1 : 8).padding(.vertical, 5)       // mini: the whole width for the name
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(on ? Color.secondary.opacity(0.15) : .clear, in: RoundedRectangle(cornerRadius: 6))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(key.map { title + " (" + $0 + ")" } ?? title)
    }
}

/// The button at the top left: the sidebar shown or hidden.
struct SidebarButton: View {
    var body: some View {
        Button { Side.shared.toggle() } label: { Label("Sidebar", systemImage: "sidebar.left") }
            .help(Side.shared.hidden ? "Show the sidebar (⌘\\)" : "Hide the sidebar (⌘\\)")
    }
}

/// View › Show or Hide the Sidebar (⌘\\), and its size.
struct SidebarMenu: View {
    var body: some View {
        Button(Side.shared.hidden ? "Show Sidebar" : "Hide Sidebar") { Side.shared.toggle() }
            .keyboardShortcut("\\", modifiers: .command)
        Picker("Sidebar", selection: Binding(get: { Side.shared.size }, set: { Side.shared.size = $0; Side.shared.hidden = false })) {
            Text("Full").tag("full")
            Text("Mini").tag("mini")
        }
    }
}
