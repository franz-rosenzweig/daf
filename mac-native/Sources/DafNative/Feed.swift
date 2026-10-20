import SwiftUI

/// The Feed's sources, as the page's source picker has them (/api/feed/sources): folders, their
/// feeds and what's unseen in each; renaming, moving and unfollowing a feed, its two switches,
/// marking a folder or a feed seen (with Undo), following a new site.
extension AppModel {
    var feedFolders: [J] { sources?.a("folders") ?? [] }

    /// The folders for the sidebar: FreshRSS's, else the ones the counts know.
    var folderNames: [String] {
        let named = feedFolders.compactMap { $0.s("name") }
        return named.isEmpty ? feedCategories : named
    }

    func feeds(in folder: String) -> [J] {
        (feedFolders.first { ($0.s("name") ?? "") == folder })?.a("feeds") ?? []
    }

    func feed(_ id: String) -> J? {
        for f in feedFolders { if let x = f.a("feeds").first(where: { $0.s("id") == id }) { return x } }
        return nil
    }

    func loadSources() async {
        if let s = try? await API.shared.json("/api/feed/sources") { sources = s }
    }

    /// After a change to the Feed: the counts, the sources and the list beside them.
    func feedChanged() async {
        counts = try? await API.shared.json("/api/docs/counts")
        await loadSources()
        switch place {
        case .feed, .feedSource: await load()
        default: break
        }
    }

    /// Everything unseen in a folder or a feed (or the whole Feed), marked seen, with Undo.
    func markSeen(_ p: Place) async {
        var body: [String: Any] = [:]
        switch p {
        case .feedSource(let id): body["feed"] = id
        case .feed(let cat): body["cat"] = cat ?? ""
        default: return
        }
        do {
            let r = J(try await API.shared.send("POST", "/api/feed/seen", body))
            let ids = (r?.list("ids") ?? []).compactMap { $0 as? String }
            await feedChanged()
            guard !ids.isEmpty else { say("Nothing to mark"); return }
            say("\(ids.count) marked seen", undo: "Mark All Seen") { [weak self] in
                guard let self else { return }
                do {
                    try await API.shared.send("POST", "/api/docs/bulk", ["ids": ids, "status": "unseen"])
                    self.say("Back in Unseen")
                    await self.feedChanged()
                } catch { self.error = error.localizedDescription }
            }
        } catch { self.error = error.localizedDescription }
    }

    /// Asks FreshRSS for what's new now, as pulling the list down does on the phone.
    func refreshFeed() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/feed/refresh", [:]))
            if r?.b("busy") == true { say("Daf is already syncing; try again in a moment") }
            else { let n = r?.i("new") ?? 0; say(n > 0 ? "\(n) new" : "Nothing new") }
        } catch { self.error = error.localizedDescription }
        await feedChanged()
    }

    /// A feed renamed or moved, or one of its switches: {"title"}, {"folder"}, {"full"}, {"notify"}.
    @discardableResult
    func editFeed(_ id: String, _ change: [String: Any]) async -> Bool {
        var body = change
        body["feed"] = id
        do {
            try await API.shared.send("PUT", "/api/feed/sources", body)
            await feedChanged()
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }

    func unfollow(_ id: String) async {
        let name = feed(id)?.s("title") ?? "the feed"
        do {
            try await API.shared.send("DELETE", "/api/feed/sources?feed=" + API.enc(id), nil)
            if place == .feedSource(id) { place = .feed(nil) }
            say("No longer following \(name)")
            await feedChanged()
        } catch { self.error = error.localizedDescription }
    }

    /// The list's Refresh: the Feed asks FreshRSS first; anywhere else it's the list again.
    func refresh() {
        switch place {
        case .feed, .feedSource: Task { await refreshFeed() }
        default: reload()
        }
    }
}

// MARK: the sidebar's Feed section

struct FeedSection: View {
    @Environment(AppModel.self) private var model
    @AppStorage("openFolders") private var open = ""

    var body: some View {
        Section("Feed") {
            Label("All Feeds", systemImage: "dot.radiowaves.up.forward")
                .badge(model.count(.feed(nil)) ?? 0)
                .tag(Place.feed(nil))
                .contextMenu { ScopeMenu(place: .feed(nil)) }
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

struct FeedRow: View {
    @Environment(AppModel.self) private var model
    let feed: J

    var body: some View {
        let id = feed.s("id") ?? ""
        Label {
            Text(feed.s("title") ?? id)
        } icon: {
            FeedIcon(hash: feed.s("icon"))
        }
        .badge(feed.i("count") ?? 0)
        .tag(Place.feedSource(id))
        .contextMenu { FeedMenu(feed: feed) }
    }
}

/// The feed's own little picture, from FreshRSS by way of Daf.
struct FeedIcon: View {
    let hash: String?
    var body: some View {
        if let hash {
            AsyncImage(url: API.shared.url("/api/feed/icon/" + hash)) { p in
                if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { Image(systemName: "dot.radiowaves.up.forward") }
            }
            .frame(width: 16, height: 16)
            .clipShape(RoundedRectangle(cornerRadius: 3))
        } else {
            Image(systemName: "dot.radiowaves.up.forward")
        }
    }
}

/// What a folder or the whole Feed can do.
struct ScopeMenu: View {
    @Environment(AppModel.self) private var model
    let place: Place
    var body: some View {
        Button("Mark All Seen") { Task { await model.markSeen(place) } }
        Divider()
        Button("Follow a Site…") { model.sheet = .follow }
    }
}

/// What a feed can do: the same as its row in the page's source picker.
struct FeedMenu: View {
    @Environment(AppModel.self) private var model
    let feed: J

    var body: some View {
        let id = feed.s("id") ?? ""
        Button("Mark All Seen") { Task { await model.markSeen(.feedSource(id)) } }
        Divider()
        Button("Rename…") { model.sheet = .renameFeed(id) }
        Menu("Move To") {
            ForEach(model.folderNames.filter { !$0.isEmpty }, id: \.self) { f in
                Button { Task { await model.editFeed(id, ["folder": f]) } } label: {
                    if f == feed.s("folder") { Label(f, systemImage: "checkmark") } else { Text(f) }
                }
            }
            Divider()
            Button("No Folder") { Task { await model.editFeed(id, ["folder": ""]) } }
        }
        Toggle("Always Load the Full Article", isOn: Binding(get: { feed.b("full") }, set: { on in Task { await model.editFeed(id, ["full": on]) } }))
        Toggle("Tell Me About New Posts", isOn: Binding(get: { feed.b("notify") }, set: { on in Task { await model.editFeed(id, ["notify": on]) } }))
        Divider()
        if let site = feed.s("site"), let url = URL(string: site) { Link("Open the Site", destination: url) }
        if let u = feed.s("url") {
            Button("Copy the Feed's Address") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string) }
        }
        Divider()
        Button("Unfollow…", role: .destructive) { model.confirmUnfollow = id }
    }
}

// MARK: sheets

/// File › Follow a Site…: a site or a feed, followed in FreshRSS in one of the folders (/api/add/feed).
struct FollowSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var url = ""
    @State private var folder = ""
    @State private var newFolder = ""
    @State private var busy = false

    var body: some View {
        Form {
            Section {
                TextField("Site or feed", text: $url, prompt: Text("https://…"))
                    .onAppear {
                        if let s = NSPasteboard.general.string(forType: .string), s.hasPrefix("http") { url = s }
                        if case .feed(let cat?) = model.place { folder = cat }
                    }
                Picker("Folder", selection: $folder) {
                    Text("No folder").tag("")
                    ForEach(model.folderNames.filter { !$0.isEmpty }, id: \.self) { Text($0).tag($0) }
                    Divider()
                    Text("A new folder…").tag("\u{1}new")
                }
                if folder == "\u{1}new" { TextField("New folder", text: $newFolder) }
            } header: { Text("Follow a site") } footer: {
                Text("Its new posts come into the Feed.").foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 440)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Follow") { Task { await follow() } }.disabled(busy || !url.lowercased().hasPrefix("http"))
            }
        }
    }

    private func follow() async {
        busy = true
        defer { busy = false }
        let f = folder == "\u{1}new" ? newFolder.trimmingCharacters(in: .whitespaces) : folder
        do {
            let r = J(try await API.shared.send("POST", "/api/add/feed", ["url": url.trimmingCharacters(in: .whitespaces), "folder": f]))
            model.say("Following \(r?.s("name") ?? "it")")
            dismiss()
            await model.feedChanged()
        } catch { model.error = error.localizedDescription }
    }
}

struct RenameFeedSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let id: String
    @State private var title = ""

    var body: some View {
        Form {
            Section("Rename the feed") {
                TextField("Name", text: $title)
            }
        }
        .formStyle(.grouped)
        .frame(width: 400)
        .onAppear { title = model.feed(id)?.s("title") ?? "" }
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button("Rename") { Task { if await model.editFeed(id, ["title": title]) { dismiss() } } }
                    .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}
