import AppKit
import SwiftUI

/// The sidebar, as the page has it (app.js sideMode): full, mini (its icons) or hidden, kept on this
/// Mac. ⌘\ goes full → mini → hidden; hidden, the button at the top left brings the mini one back
/// for a moment. While an article is open there's no sidebar at all, and ⌘\ brings it for a moment.
@MainActor
@Observable
final class Side {
    static let shared = Side()
    static let modes = [("full", "Full"), ("mini", "Mini"), ("hidden", "Hidden")]

    var mode = UserDefaults.standard.string(forKey: "sideMode") ?? "full" {
        didSet {
            UserDefaults.standard.set(mode, forKey: "sideMode")
            peeking = false
            apply()
        }
    }
    /// Back for a moment over the page, as the mini one.
    var peeking = false { didSet { if peeking != oldValue { apply() } } }
    /// An article open in the window: no sidebar then.
    var reading = false { didSet { if reading != oldValue { peeking = false; apply() } } }
    /// The width the split view was last given, so a width dragged by hand stays.
    @ObservationIgnored private var widthFor = ""

    /// How it shows now.
    var shown: String { peeking ? "mini" : reading ? "hidden" : mode }
    var mini: Bool { shown == "mini" }

    /// ⌘\: full → mini → hidden; while reading, or after a moment, it goes again.
    func cycle() {
        if peeking { peeking = false; return }
        if reading { peeking = true; return }
        mode = mode == "full" ? "mini" : mode == "mini" ? "hidden" : "full"
    }

    /// The button at the top left: a hidden sidebar back for a moment, else ⌘\.
    func button() {
        if peeking { peeking = false } else if shown == "hidden" { peeking = true } else { cycle() }
    }

    /// A place picked while it was there for a moment: it goes again.
    func chose() { if peeking { peeking = false } }

    /// The main window's sidebar as it should be (Focus mode puts it away itself).
    func apply() {
        let want = shown == "hidden" ? "" : mini ? "mini" : "full", changed = want != widthFor
        widthFor = want
        for w in NSApp.windows where Focus.isMain(w) && !Focus.shared.isOn(w) {
            guard let s = Focus.split(w), s.splitViewItems.count > 1 else { continue }
            let item = s.splitViewItems[0], hide = want.isEmpty
            item.minimumThickness = mini ? 54 : 190
            item.maximumThickness = mini ? 64 : 320
            if item.isCollapsed != hide {
                // sized once it's out: sized while it opens, it settled too narrow
                NSAnimationContext.runAnimationGroup { _ in item.animator().isCollapsed = hide } completionHandler: {
                    MainActor.assumeIsolated { Side.shared.fit(changed) }
                }
            } else { fit(changed) }
        }
    }

    /// An open sidebar at its width: as it was dragged, unless it changed size or is out of bounds.
    private func fit(_ changed: Bool) {
        for w in NSApp.windows where Focus.isMain(w) && !Focus.shared.isOn(w) {
            guard let s = Focus.split(w), s.splitViewItems.count > 1, !s.splitViewItems[0].isCollapsed else { continue }
            let item = s.splitViewItems[0], wide = item.viewController.view.frame.width
            if changed || wide < item.minimumThickness - 1 || wide > item.maximumThickness + 1 {
                s.splitView.setPosition(mini ? 58 : 220, ofDividerAt: 0)
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

/// A row's look: its icon and name, or just the icon in the mini sidebar.
struct SideLabelStyle: LabelStyle {
    let mini: Bool
    func makeBody(configuration: Configuration) -> some View {
        if mini { configuration.icon.frame(maxWidth: .infinity) } else { Label(configuration) }
    }
}

struct Sidebar: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openSettings) private var openSettings
    @AppStorage("libOpen") private var libOpen = false
    @AppStorage("catsOpen") private var catsOpen = true

    var body: some View {
        let mini = Side.shared.mini
        List(selection: Binding(get: { model.place }, set: { model.place = $0; Side.shared.chose() })) {
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
            if !pins.isEmpty {
                Section(mini ? "" : "Pinned") {
                    ForEach(pins, id: \.0) { p in row(p.2, p.1, p.3, mini) }
                }
            }
            if model.place == .search {
                Section(mini ? "" : "Search") { row(.search, "“\(model.query)”", "magnifyingglass", mini) }
            }
        }
        .listStyle(.sidebar)
        .labelStyle(SideLabelStyle(mini: mini))
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
                bottom("Stats", "chart.bar", nil, mini, on: model.place == .stats) { model.place = .stats; Side.shared.chose() }
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

/// The button at the top left: full → mini → hidden, or a hidden sidebar back for a moment.
struct SidebarButton: View {
    var body: some View {
        Button { Side.shared.button() } label: { Label("Sidebar", systemImage: "sidebar.left") }
            .help("Sidebar: full, mini or hidden (⌘\\)")
    }
}
