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

    /// What can be pinned under the six places: the key Daf keeps (settings.nav_pins), its name, its place, its icon.
    static let pinnable: [(String, String, Place, String)] = [
        ("podcasts", "Podcasts", .podcasts, "headphones"), ("manga", "Manga", .manga, "book.pages"), ("torah", "Torah", .torah, "scroll"),
        ("recovery", "Recovery", .recovery, "sunrise"), ("shortlist", "Shortlist", .shortlist, "star"),
        ("paper", "Paper Pages", .paper, "camera.viewfinder"), ("sources", "Sources", .sources, "arrow.triangle.2.circlepath"),
    ]
    static let pinnedByDefault = ["podcasts", "manga", "torah", "recovery", "shortlist"]

    /// What's pinned, as Daf keeps it for every device.
    func pins(_ settings: J?) -> [String] {
        (settings?.raw["nav_pins"] as? [Any])?.compactMap { $0 as? String } ?? Self.pinnedByDefault
    }

    func setPins(_ keys: [String]) async {
        let ordered = Self.pinnable.map(\.0).filter(keys.contains)
        do {
            try await API.shared.send("PUT", "/api/settings", ["nav_pins": ordered])
            AppModel.shared.pinned(ordered)
        } catch { AppModel.shared.error = error.localizedDescription }
    }
}

/// A row's look: its icon and name, or in the mini sidebar the icon with its name under it.
struct SideLabelStyle: LabelStyle {
    let mini: Bool
    func makeBody(configuration: Configuration) -> some View {
        if mini {
            VStack(spacing: 2) {
                configuration.icon.font(.title3)
                configuration.title.font(.system(size: 9.5, weight: .medium)).lineLimit(1).minimumScaleFactor(0.75)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 2)
        } else { Label(configuration) }
    }
}

struct Sidebar: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openSettings) private var openSettings
    @AppStorage("libOpen") private var libOpen = false
    @AppStorage("catsOpen") private var catsOpen = true
    @State private var editPins = false

    var body: some View {
        let mini = Side.shared.mini
        List(selection: Binding(get: { model.place }, set: { model.place = $0 })) {
            row(.today, "Today", "sun.max", mini)
            row(.review, "Review", "rectangle.stack", mini)
            if mini {
                row(.home, "Library", "tray.full", mini)
                row(.books, "Books", "books.vertical", mini)
                row(.feed(nil), "Feed", "dot.radiowaves.up.forward", mini)
            } else {
                DisclosureGroup(isExpanded: $libOpen) {
                    ForEach(kinds, id: \.0) { k in row(.kind(k.0), k.1, k.2, mini) }
                    ForEach(model.views, id: \.self) { v in
                        Label(v.s("name") ?? "View", systemImage: "line.3.horizontal.decrease.circle")
                            .tag(Place.view(v.s("id") ?? ""))
                            .contextMenu { Button("Remove the View", role: .destructive) { Task { await model.removeView(v.s("id") ?? "") } } }
                    }
                } label: { row(.home, "Library", "tray.full", mini) }
                BooksRow()
                DisclosureGroup(isExpanded: $catsOpen) {
                    FeedFolders()
                } label: {
                    row(.feed(nil), "Feed", "dot.radiowaves.up.forward", mini)
                        .contextMenu { ScopeMenu(place: .feed(nil)) }
                }
            }
            row(.highlights, "Highlights", "highlighter", mini)
            let pins = Side.pinnable.filter { Side.shared.pins(model.today?.o("settings")).contains($0.0) }
            Section {
                ForEach(pins, id: \.0) { p in row(p.2, p.1, p.3, mini) }
            } header: {
                if !mini {
                    HStack {
                        Text("Pinned")
                        Spacer()
                        Button("Edit") { editPins = true }
                            .buttonStyle(.borderless)
                            .font(.caption)
                            .popover(isPresented: $editPins, arrowEdge: .trailing) { PinsEditor() }
                    }
                }
            }
            if model.place == .search {
                Section(mini ? "" : "Search") { row(.search, "“\(model.query)”", "magnifyingglass", mini) }
            }
        }
        .listStyle(.sidebar)
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
                bottom("Search", "magnifyingglass", "⌘K", mini) { model.sheet = .palette }
                bottom("Stats", "chart.bar", nil, mini, on: model.place == .stats) { model.place = .stats }
                bottom("Preferences", "gearshape", "⌘,", mini) { openSettings() }
            }
            .labelStyle(SideLabelStyle(mini: mini))
            .padding(.horizontal, mini ? 6 : 10)
            .padding(.vertical, 8)
        }
    }

    /// The Library's kinds; Emails once there are any.
    private var kinds: [(String, String, String)] {
        let have = model.counts?.o("library")?.raw ?? [:]
        return Place.kinds.filter { $0.0 != "email" || have["email"] != nil }
    }

    private func row(_ p: Place, _ title: String, _ icon: String, _ mini: Bool) -> some View {
        Label(title, systemImage: icon)
            .badge(mini ? 0 : model.count(p) ?? 0)
            .help(mini ? title : "")
            .tag(p)
    }

    private func bottom(_ title: String, _ icon: String, _ key: String?, _ mini: Bool, on: Bool = false, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            HStack {
                Label(title, systemImage: icon)
                if !mini, let key { Spacer(); Text(key).font(.caption).foregroundStyle(.tertiary) }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(on ? Color.secondary.opacity(0.15) : .clear, in: RoundedRectangle(cornerRadius: 6))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(key.map { title + " (" + $0 + ")" } ?? title)
    }
}

/// Pinned's Edit: which places sit under the six, kept by Daf for every device.
struct PinsEditor: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let on = Set(Side.shared.pins(model.today?.o("settings")))
        VStack(alignment: .leading, spacing: 6) {
            Text("Pinned").font(.headline)
            ForEach(Side.pinnable, id: \.0) { p in
                Toggle(isOn: Binding(get: { on.contains(p.0) }, set: { v in
                    Task { await Side.shared.setPins(v ? Array(on.union([p.0])) : Array(on.subtracting([p.0]))) }
                })) { Label(p.1, systemImage: p.3) }
            }
        }
        .padding(16)
        .frame(width: 220, alignment: .leading)
    }
}

/// The Feed's folders, each opening on its feeds, and the feeds in no folder.
struct FeedFolders: View {
    @Environment(AppModel.self) private var model
    @AppStorage("openFolders") private var open = ""

    var body: some View {
        ForEach(model.folderNames, id: \.self) { name in
            if name.isEmpty {
                ForEach(model.feeds(in: ""), id: \.self) { FeedRow(feed: $0) }
            } else {
                DisclosureGroup(isExpanded: expanded(name)) {
                    ForEach(model.feeds(in: name), id: \.self) { FeedRow(feed: $0) }
                } label: {
                    Label(name, systemImage: "folder")
                        .badge(model.count(.feed(name)) ?? 0)
                        .tag(Place.feed(name))
                        .contextMenu { ScopeMenu(place: .feed(name)) }
                }
            }
        }
    }

    private func expanded(_ name: String) -> Binding<Bool> {
        Binding(get: { open.split(separator: "\n").contains { $0 == name } },
                set: { on in
                    var names = open.split(separator: "\n").map(String.init).filter { $0 != name }
                    if on { names.append(name) }
                    open = names.joined(separator: "\n")
                })
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
