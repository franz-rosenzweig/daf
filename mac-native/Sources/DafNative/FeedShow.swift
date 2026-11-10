import SwiftUI

// What shows where in the Feed, as the page has it (web/feeds.js, rss.py Show): where each folder's and
// feed's posts show (Everywhere, Its folder, Hidden), whether it's pinned under Feed in the sidebar
// (settings feed_pins), and how much the Edition takes from it (the Taste page's dial). A folder's
// settings are its feeds' too, unless a feed has its own. Hidden is the Edition's pool: Daf still reads it.

@MainActor
@Observable
final class FeedManage {
    static let shared = FeedManage()
    static let shows = [("all", "Everywhere"), ("folder", "Its folder"), ("hidden", "Hidden")]
    static let editions = [("more", "More"), ("", "Normal"), ("less", "Less"), ("mute", "Off")]

    /// /api/feed/manage: {folders: [{name, show, edition, week, feeds: [...]}], pins, hide_empty}.
    private(set) var data: J?

    var folders: [J] { data?.a("folders") ?? [] }
    var pins: [String] { data?.strings("pins") ?? [] }

    func load() async {
        if let d = try? await API.shared.json("/api/feed/manage") { data = d }
    }

    func folder(_ name: String) -> J? { folders.first { ($0.s("name") ?? "") == name } }

    func feed(_ id: String) -> (J, J)? {
        for f in folders { if let x = f.a("feeds").first(where: { $0.s("id") == id }) { return (x, f) } }
        return nil
    }

    /// A key's name: the folder's, or the feed's title.
    func name(_ key: String) -> String? {
        key.hasPrefix("folder:") ? folder(String(key.dropFirst(7)))?.s("name") : feed(key)?.0.s("title")
    }

    // MARK: the changes, the same from the page, the menus and the sidebar

    func setShow(_ keys: [String], _ show: String?) async {
        await write { try await API.shared.send("PUT", "/api/feed/show", ["keys": keys, "show": show ?? NSNull()]) }
    }

    /// The Edition's dial for a folder ("folder:Name") or a feed (by its title).
    func setEdition(_ key: String, _ adj: String) async {
        let name = key.hasPrefix("folder:") ? key : feed(key)?.0.s("title")
        guard let name else { return }
        await write(counts: false) { try await API.shared.send("PUT", "/api/edition/settings", ["source": ["name": name, "adj": adj]]) }
    }

    func setPin(_ key: String, _ on: Bool) async {
        if data == nil { await load() }
        var list = pins.filter { $0 != key }
        if on { list.append(key) }
        await setPins(list)
    }

    func setPins(_ list: [String]) async {
        await write { try await API.shared.send("PUT", "/api/settings", ["feed_pins": list]) }
    }

    func hideEmpty(_ on: Bool) async {
        await write { try await API.shared.send("PUT", "/api/settings", ["feed_pins_hide_empty": on]) }
    }

    func move(_ feeds: [String], to folder: String) async {
        await write { for id in feeds { try await API.shared.send("PUT", "/api/feed/sources", ["feed": id, "folder": folder]) } }
    }

    func unfollow(_ feeds: [String]) async {
        await write { for id in feeds { try await API.shared.send("DELETE", "/api/feed/sources?feed=" + API.enc(id), nil) } }
    }

    /// After a change: this page, and the sidebar's pins and counts.
    private func write(counts: Bool = true, _ f: () async throws -> Void) async {
        do {
            try await f()
            await load()
            if counts { await AppModel.shared.feedChanged() }
        } catch { AppModel.shared.error = error.localizedDescription }
    }
}

/// The menu on a folder ("folder:Name") or a feed ("feed/12"): right-click in the sidebar or on the
/// Feeds page. Pin, Show, Edition, Mark All Seen, and for a feed renaming, moving and unfollowing.
struct FeedKeyMenu: View {
    @Environment(AppModel.self) private var model
    let key: String

    var body: some View {
        let fm = FeedManage.shared, isFolder = key.hasPrefix("folder:")
        let folder = isFolder ? fm.folder(String(key.dropFirst(7))) : nil, pair = isFolder ? nil : fm.feed(key)
        let show = isFolder ? folder?.s("show") ?? "all" : pair?.0.s("own_show") ?? ""
        let ed = (isFolder ? folder : pair?.0)?.s("edition") ?? ""
        let place: Place = isFolder ? .feed(String(key.dropFirst(7))) : .feedSource(key)
        if !(isFolder && show == "hidden") {
            Button(fm.pins.contains(key) ? "Unpin from the Sidebar" : "Pin to the Sidebar") { Task { await fm.setPin(key, !fm.pins.contains(key)) } }
        }
        Menu("Show") {
            if !isFolder { check("Like Its Folder", show.isEmpty) { await fm.setShow([key], nil) } }
            ForEach(FeedManage.shows, id: \.0) { k, l in check(l, show == k) { await fm.setShow([key], k) } }
        }
        Menu("Edition") {
            if !isFolder { check("Like Its Folder", ed.isEmpty) { await fm.setEdition(key, "") } }
            ForEach(FeedManage.editions.filter { !(isFolder == false && $0.0.isEmpty) }, id: \.0) { k, l in
                check(l, isFolder ? ed == k : !ed.isEmpty && ed == k) { await fm.setEdition(key, k) }
            }
        }
        Divider()
        if show != "hidden" {
            Button("Mark All as Seen") { Task { await model.markSeen(place) } }
            OlderMenu(place: place)
        }
        if let pair {
            let x = pair.0, home = pair.1
            Divider()
            Button("Rename…") { model.sheet = .renameFeed(key) }
            Menu("Move To") {
                ForEach(fm.folders.compactMap { $0.s("name") }.filter { !$0.isEmpty }, id: \.self) { f in
                    check(f, f == home.s("name")) { await fm.move([key], to: f) }
                }
                Divider()
                Button("No Folder") { Task { await fm.move([key], to: "") } }
            }
            Toggle("Always Load the Full Article", isOn: Binding(get: { x.b("full") }, set: { on in Task { await model.editFeed(key, ["full": on]); await fm.load() } }))
            Toggle("Tell Me About New Posts", isOn: Binding(get: { x.b("notify") }, set: { on in
                Task { if await model.editFeed(key, ["notify": on]), on, !FeedNews.shared.on { await FeedNews.shared.enable() }; await fm.load() }
            }))
            if let site = x.s("site"), !site.isEmpty, let url = URL(string: site) { Link("Open the Site", destination: url) }
            if let u = x.s("url") {
                Button("Copy the Feed's Address") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string) }
            }
            Button("Unfollow…", role: .destructive) { model.confirmUnfollow = key }
        }
        Divider()
        Button("Feeds") { model.place = .feeds }
    }

    private func check(_ label: String, _ on: Bool, _ act: @escaping () async -> Void) -> some View {
        Button { Task { await act() } } label: { if on { Label(label, systemImage: "checkmark") } else { Text(label) } }
    }
}

/// Under Feed in the sidebar: the pinned folders and feeds in their order (/api/docs/counts feed_pins),
/// each with what's unseen, and the Feeds page.
struct FeedPins: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let hide = model.counts?.b("feed_pins_hide_empty") == true
        ForEach(model.counts?.a("feed_pins") ?? [], id: \.self) { p in
            let key = p.s("key") ?? "", n = p.i("count") ?? 0
            let place: Place = key.hasPrefix("folder:") ? .feed(String(key.dropFirst(7))) : .feedSource(key)
            if !hide || n > 0 || model.place == place {
                Group {
                    if key.hasPrefix("folder:") {
                        Label(p.s("name") ?? "", systemImage: "folder")
                    } else {
                        Label { Text(p.s("name") ?? key) } icon: { FeedIcon(hash: (p.s("icon") ?? "").isEmpty ? nil : p.s("icon")) }
                    }
                }
                .badge(n)
                .tag(place)
                .contextMenu { FeedKeyMenu(key: key) }
            }
        }
        Label("Feeds", systemImage: "list.bullet.rectangle").tag(Place.feeds)
            .task { if FeedManage.shared.data == nil { await FeedManage.shared.load() } }
    }
}

// MARK: the Feeds page

struct FeedsPage: View {
    @Environment(AppModel.self) private var model
    @State private var fm = FeedManage.shared
    @State private var chip = "all"
    @State private var q = ""
    @State private var sel = Set<String>()
    @State private var unfollowing = false
    @State private var naming = false
    @State private var newFolder = ""
    @AppStorage("feedsOpen") private var openList = ""

    struct Row: Identifiable, Hashable {
        let id: String                  // "folder:Name", "feed/12", or "heading:Hidden"
        let j: J
        let folder: String
        var feeds: [Row]?
        var isFolder: Bool { id.hasPrefix("folder:") }
        var isHeading: Bool { id.hasPrefix("heading:") }
    }

    private static let quiet: Double = 30 * 86_400

    var body: some View {
        VStack(spacing: 0) {
            chips.padding(.horizontal, 16).padding(.vertical, 10)
            Divider()
            table
            if !picked.isEmpty { Divider(); bulk }
        }
        .navigationTitle("Feeds")
        .searchable(text: $q, placement: .toolbar, prompt: "Search")
        .toolbar {
            ToolbarItem { Button("Follow a Site…") { model.sheet = .follow } }
        }
        .task { await fm.load() }
        .confirmationDialog("Unfollow \(plural(pickedFeeds.count, "feed"))?", isPresented: $unfollowing) {
            Button("Unfollow", role: .destructive) { let ids = pickedFeeds; Task { await fm.unfollow(ids); sel = [] } }
        }
        .alert("A New Folder", isPresented: $naming) {
            TextField("Name", text: $newFolder)
            Button("Move") {
                let f = newFolder.trimmingCharacters(in: .whitespaces), ids = pickedFeeds
                newFolder = ""
                if !f.isEmpty { Task { await fm.move(ids, to: f); sel = [] } }
            }
            Button("Cancel", role: .cancel) { newFolder = "" }
        }
    }

    // MARK: what shows

    private var allFeeds: [J] { fm.folders.flatMap { $0.a("feeds") } }

    private func keep(_ f: J, _ x: J) -> Bool {
        let words = q.trimmingCharacters(in: .whitespaces).lowercased()
        if !words.isEmpty, ![x.s("title"), f.s("name"), x.s("site")].contains(where: { ($0 ?? "").lowercased().contains(words) }) { return false }
        switch chip {
        case "everywhere": return x.s("show") == "all"
        case "folder": return x.s("show") == "folder"
        case "hidden": return x.s("show") == "hidden"
        case "quiet": return (x.d("last") ?? 0) < Date().timeIntervalSince1970 - Self.quiet
        case "problems": return x.s("error") != nil
        default: return true
        }
    }

    private var rows: [Row] {
        var out: [Row] = [], heading = false
        for f in fm.folders {
            let name = f.s("name") ?? ""
            let feeds = f.a("feeds").filter { keep(f, $0) }
            guard !feeds.isEmpty else { continue }
            if f.s("show") == "hidden" && !heading {
                heading = true
                out.append(Row(id: "heading:Hidden", j: J(["name": "Hidden"]), folder: ""))
            }
            out.append(Row(id: "folder:" + name, j: f, folder: name, feeds: feeds.map { Row(id: $0.s("id") ?? "", j: $0, folder: name) }))
        }
        return out
    }

    private var filtering: Bool { chip != "all" || !q.trimmingCharacters(in: .whitespaces).isEmpty }

    private var chips: some View {
        let all = allFeeds, now = Date().timeIntervalSince1970
        let n: [String: Int] = [
            "all": all.count, "everywhere": all.filter { $0.s("show") == "all" }.count, "folder": all.filter { $0.s("show") == "folder" }.count,
            "hidden": all.filter { $0.s("show") == "hidden" }.count, "quiet": all.filter { ($0.d("last") ?? 0) < now - Self.quiet }.count,
            "problems": all.filter { $0.s("error") != nil }.count,
        ]
        return HStack(spacing: 6) {
            ForEach([("all", "All"), ("everywhere", "Everywhere"), ("folder", "Its folder"), ("hidden", "Hidden"), ("quiet", "Quiet"), ("problems", "Problems")], id: \.0) { k, l in
                if k != "problems" || (n[k] ?? 0) > 0 {
                    Button { chip = k } label: { Text(l) + Text(" \(n[k] ?? 0)").foregroundStyle(.secondary) }
                        .buttonStyle(.bordered)
                        .tint(chip == k ? (k == "problems" ? .orange : Color.daf) : nil)
                        .controlSize(.small)
                }
            }
            Spacer()
        }
    }

    private var table: some View {
        Table(of: Row.self, selection: $sel) {
            TableColumn("Name") { r in name(r) }.width(min: 220, ideal: 340)
            TableColumn("A week") { r in if !r.isHeading { week(r.j.d("week") ?? 0) } }.width(70)
            TableColumn("Show") { r in if !r.isHeading && !(r.isFolder && r.folder.isEmpty) { showPicker(r) } }.width(min: 230, ideal: 250)
            TableColumn("Sidebar") { r in pin(r) }.width(56)
            TableColumn("Edition") { r in if !r.isHeading && !(r.isFolder && r.folder.isEmpty) { edition(r) } }.width(min: 100, ideal: 120)
            TableColumn("") { r in
                if !r.isHeading && !(r.isFolder && r.folder.isEmpty) {
                    Menu { FeedKeyMenu(key: r.id) } label: { Image(systemName: "ellipsis") }
                        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                }
            }.width(30)
        } rows: {
            ForEach(rows) { r in
                if let feeds = r.feeds {
                    DisclosureTableRow(r, isExpanded: open(r.folder)) { ForEach(feeds) { TableRow($0) } }
                } else {
                    TableRow(r)
                }
            }
        }
        .contextMenu(forSelectionType: String.self) { keys in
            if keys.count == 1, let k = keys.first, !k.hasPrefix("heading:") { FeedKeyMenu(key: k) }
        } primaryAction: { keys in
            guard keys.count == 1, let k = keys.first else { return }
            if k.hasPrefix("folder:") { model.place = .feed(String(k.dropFirst(7))) }
            else if k.hasPrefix("feed/") { model.place = .feedSource(k) }
        }
    }

    // MARK: the cells

    @ViewBuilder private func name(_ r: Row) -> some View {
        if r.isHeading {
            Text("Hidden").font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase)
        } else if r.isFolder {
            HStack(spacing: 6) {
                Image(systemName: "folder").foregroundStyle(.secondary)
                Text(r.folder.isEmpty ? "No folder" : r.folder).fontWeight(.semibold)
                Text("\(r.j.a("feeds").count)").foregroundStyle(.secondary)
            }
        } else {
            HStack(spacing: 6) {
                FeedIcon(hash: (r.j.s("icon") ?? "").isEmpty ? nil : r.j.s("icon"))
                Text(r.j.s("title") ?? r.id).lineLimit(1)
                if let e = r.j.s("error") { Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange).help(e) }
            }
        }
    }

    private func week(_ w: Double) -> some View {
        HStack(spacing: 4) {
            Capsule().fill(Color.daf.opacity(0.5)).frame(width: max(2, min(40, (w.squareRoot() * 7).rounded())), height: 4)
            if w > 0 { Text(w >= 10 ? "\(Int(w.rounded()))" : String(format: "%g", w)).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }
        }
    }

    private func showPicker(_ r: Row) -> some View {
        let cur = r.j.s("show") ?? "all", inherited = !r.isFolder && (r.j.s("own_show") ?? "").isEmpty
        return Picker("Show", selection: Binding(get: { cur }, set: { v in Task { await fm.setShow([r.id], v) } })) {
            ForEach(FeedManage.shows, id: \.0) { Text($0.1).tag($0.0) }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .controlSize(.small)
        .opacity(inherited ? 0.55 : 1)
        .help(inherited ? "Like its folder" : "")
    }

    @ViewBuilder private func pin(_ r: Row) -> some View {
        if !r.isHeading && !(r.isFolder && r.folder.isEmpty) && r.j.s("show") != "hidden" {
            let on = fm.pins.contains(r.id)
            Button { Task { await fm.setPin(r.id, !on) } } label: { Image(systemName: on ? "pin.fill" : "pin") }
                .buttonStyle(.borderless)
                .foregroundStyle(on ? Color.daf : .secondary)
                .help(on ? "Unpin" : "Pin")
        }
    }

    private func edition(_ r: Row) -> some View {
        let cur = r.j.s("edition") ?? ""
        return Picker("Edition", selection: Binding(get: { cur }, set: { v in Task { await fm.setEdition(r.id, v) } })) {
            if !r.isFolder { Text("Like folder").tag("") }
            ForEach(FeedManage.editions.filter { !(r.isFolder == false && $0.0.isEmpty) }, id: \.0) { Text($0.1).tag($0.0) }
        }
        .labelsHidden()
        .controlSize(.small)
    }

    private func open(_ folder: String) -> Binding<Bool> {
        Binding(get: { filtering || openList.split(separator: "\n").contains { $0 == folder } },
                set: { on in
                    var names = openList.split(separator: "\n").map(String.init).filter { $0 != folder }
                    if on { names.append(folder) }
                    openList = names.joined(separator: "\n")
                })
    }

    // MARK: several at once

    private var picked: [String] { sel.filter { !$0.hasPrefix("heading:") && $0 != "folder:" }.sorted() }

    /// A folder picked stands for its feeds where a feed is needed (Move, Unfollow).
    private var pickedFeeds: [String] {
        var out = Set<String>()
        for k in picked {
            if k.hasPrefix("folder:") { fm.folder(String(k.dropFirst(7)))?.a("feeds").compactMap { $0.s("id") }.forEach { out.insert($0) } }
            else { out.insert(k) }
        }
        return out.sorted()
    }

    private var bulk: some View {
        HStack(spacing: 10) {
            Text("\(picked.count) selected").bold()
            Menu("Show…") {
                ForEach(FeedManage.shows, id: \.0) { k, l in Button(l) { let keys = picked; Task { await fm.setShow(keys, k); sel = [] } } }
            }
            .fixedSize()
            Menu("Edition…") {
                ForEach(FeedManage.editions, id: \.0) { k, l in
                    Button(l) { let keys = picked; Task { for key in keys { await fm.setEdition(key, k) }; sel = [] } }
                }
            }
            .fixedSize()
            Menu("Move To…") {
                ForEach(fm.folders.compactMap { $0.s("name") }.filter { !$0.isEmpty }, id: \.self) { f in
                    Button(f) { let ids = pickedFeeds; Task { await fm.move(ids, to: f); sel = [] } }
                }
                Divider()
                Button("A New Folder…") { naming = true }
            }
            .fixedSize()
            Button("Unfollow…") { unfollowing = true }.disabled(pickedFeeds.isEmpty)
            Spacer()
            Button("Clear") { sel = [] }
        }
        .controlSize(.small)
        .padding(.horizontal, 16).padding(.vertical, 8)
    }
}

/// Settings › General: what's pinned under Feed, in order, with Hide Pins with Nothing New.
struct FeedPinsSettings: View {
    @Environment(AppModel.self) private var model
    @State private var fm = FeedManage.shared

    var body: some View {
        Section {
            let pins = fm.pins.filter { fm.name($0) != nil }
            ForEach(Array(pins.enumerated()), id: \.element) { i, k in
                HStack {
                    Text(fm.name(k) ?? k)
                    Spacer()
                    Button { var list = pins; list.swapAt(i, i - 1); Task { await fm.setPins(list) } } label: { Image(systemName: "arrow.up") }
                        .buttonStyle(.borderless).disabled(i == 0).help("Up")
                    Button { Task { await fm.setPin(k, false) } } label: { Image(systemName: "pin.slash") }
                        .buttonStyle(.borderless).help("Unpin")
                }
            }
            Toggle("Hide pins with nothing new", isOn: Binding(get: { fm.data?.b("hide_empty") ?? false }, set: { on in Task { await fm.hideEmpty(on) } }))
        } header: {
            HStack {
                Text("Under Feed")
                Spacer()
                Button("Feeds") { model.place = .feeds; NSApp.activate() }.buttonStyle(.link).font(.caption)
            }
        }
        .task { await fm.load() }
    }
}
