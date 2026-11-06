import SwiftUI

/// The Podcasts page, as the page has it (web/podcasts.js, podcasts.py, absapi.py): what I'm listening
/// to, the shows I follow and their episodes, my recordings and audiobooks from Audiobookshelf (each its
/// own category, never mixed with AntennaPod's shows), and my clips. The search in the toolbar looks
/// through my shows and episodes (titles, show notes, and what was said where there's a transcript),
/// Audiobookshelf, and Apple's podcast directory for shows to follow and episodes to play; on a show's
/// page it looks through that show's episodes.
///
/// A row's round button plays it in the player without leaving the list; the row opens the episode's
/// page (its transcript, chapters and clips). Recordings and audiobooks play from their row.
struct PodcastsView: View {
    @Environment(AppModel.self) private var model
    /// The words searched, kept for each place while Daf is open, as the page keeps them.
    @State private var queries: [String: String] = [:]

    private var key: String {
        switch model.podNav {
        case .cat: return "podcasts"
        case .show(let f): return "podshow:" + f
        case .abs(let i): return "podabs:" + i
        }
    }

    var body: some View {
        let q = Binding(get: { queries[key] ?? "" }, set: { queries[key] = $0 })
        let words = q.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines)
        Group {
            switch model.podNav {
            case .show(let feed): ShowPage(feed: feed, q: words).id(feed)
            case .abs(let item): ABSShowPage(item: item, q: words).id(item)
            case .cat(let c):
                if words.isEmpty { PodcastCategories(cat: c) } else { PodcastSearch(q: words) }
            }
        }
        .searchable(text: q, placement: .toolbar, prompt: prompt)
    }

    private var prompt: String {
        switch model.podNav {
        case .cat: return "Search podcasts"
        case .show: return "Search this show"
        case .abs: return "Search these"
        }
    }
}

/// The categories: Listening, Shows, Episodes, Recordings, Audiobooks, Clips.
struct PodcastCategories: View {
    @Environment(AppModel.self) private var model
    let cat: String
    static let cats = [("", "Listening"), ("shows", "Shows"), ("episodes", "Episodes"), ("recordings", "Recordings"), ("audiobooks", "Audiobooks"), ("clips", "Clips")]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Picker("", selection: Binding(get: { cat }, set: { model.podNav = .cat($0) })) {
                    ForEach(Self.cats, id: \.0) { Text($0.1).tag($0.0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: 600)
                switch cat {
                case "shows": ShowsCat()
                case "episodes": EpisodesCat()
                case "recordings": RecordingsCat()
                case "audiobooks": AudiobooksCat()
                case "clips": ClipsCat()
                default: ListeningCat()
                }
            }
            .padding(28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle("Podcasts")
    }
}

/// Answers kept while Daf is open: a category draws at once from the last one, then the fresh one.
@MainActor
enum PodCache {
    static var kept: [String: J] = [:]

    static func get(_ path: String) async throws -> J {
        let d = try await API.shared.json(path)
        kept[path] = d
        return d
    }
}

// MARK: the categories

/// Listening: what I'm in the middle of, here and in Audiobookshelf, the last played first; then the
/// newest episodes of the shows I follow, not yet played.
struct ListeningCat: View {
    @Environment(AppModel.self) private var model
    @State private var l = PodCache.kept["/api/podcasts/listening"]
    @State private var x = PodCache.kept["/api/abs"]
    @State private var ov = PodCache.kept["/api/podcasts"]
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            if let l, let ov {
                if !ov.b("device") && ov.a("subs").isEmpty {
                    Section2("AntennaPod") { Button("Podcasts in Settings…") { model.openSettings(tab: "connections", at: "podcasts") } }
                }
                let going = (l.a("going").map { (t: $0.d("last") ?? 0, e: $0, abs: false) } + (x?.a("going") ?? []).map { (t: $0.d("last") ?? 0, e: $0, abs: true) })
                    .sorted { $0.t > $1.t }
                Section2("Continue") {
                    if going.isEmpty { Text("Nothing started.").foregroundStyle(.secondary) }
                    Capped(items: going.map(\.e), n: 10) { e in
                        if going.first(where: { $0.e == e })?.abs == true { ABSRow(e: e) } else { EpisodeRow(e: e) }
                    }
                }
                if !l.a("new").isEmpty {
                    Section2("New", trailing: AnyView(Button("All Episodes") { model.podNav = .cat("episodes") }.buttonStyle(.link))) {
                        Capped(items: l.a("new"), n: 10) { EpisodeRow(e: $0) }
                    }
                }
                Text("AntennaPod synced " + TodayView.ago(ov.d("last_sync")) + (x?.s("error").map { " · Audiobookshelf: " + $0 } ?? ""))
                    .font(.caption).foregroundStyle(.secondary)
            } else if let error {
                Text(error).foregroundStyle(.secondary)
            } else { Pod.loading }
        }
        .task {
            do {
                async let a = PodCache.get("/api/podcasts/listening")
                async let b = PodCache.get("/api/abs")
                async let c = PodCache.get("/api/podcasts")
                (l, x, ov) = try await (a, b, c)
            } catch { if l == nil { self.error = error.localizedDescription } }
        }
    }
}

/// Shows: the ones I follow, by their newest episode, by name, or by how many I haven't played.
struct ShowsCat: View {
    @Environment(AppModel.self) private var model
    @AppStorage("pod.showsSort") private var sort = "recent"
    @State private var d = PodCache.kept["/api/podcasts/shows"]

    var body: some View {
        let list = (d?.a("shows") ?? []).sorted(by: order)
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Seg(value: $sort, options: Pod.showSorts)
                Spacer()
                if d != nil { Text("\(list.count) shows").font(.caption).foregroundStyle(.secondary) }
            }
            if d == nil { Pod.loading }
            else if list.isEmpty { Pod.empty("No shows yet") }
            else {
                Tiles {
                    ForEach(list, id: \.self) { s in
                        Tile(art: s.s("image"), title: s.s("title") ?? "", sub: [s.i("unplayed").flatMap { $0 > 0 ? "\($0) unplayed" : nil }, s.d("newest").map(Pod.date)].compactMap { $0 }.joined(separator: " · ")) {
                            if let f = s.s("feed") { model.podNav = .show(f) }
                        }
                    }
                }
            }
        }
        .task { d = (try? await PodCache.get("/api/podcasts/shows")) ?? d }
    }

    private func order(_ a: J, _ b: J) -> Bool {
        switch sort {
        case "az": return (a.s("title") ?? "").localizedStandardCompare(b.s("title") ?? "") == .orderedAscending
        case "unplayed": return (a.i("unplayed") ?? 0) > (b.i("unplayed") ?? 0)
        default: return (a.d("newest") ?? 0) > (b.d("newest") ?? 0)
        }
    }
}

/// Episodes of every show I follow: All, Unplayed, In progress, Played, Transcribed, Clipped; by date or length.
struct EpisodesCat: View {
    @AppStorage("pod.epFilter") private var filter = "unplayed"
    @AppStorage("pod.epSort") private var sort = "newest"
    @State private var eps: [J] = []
    @State private var total: Int?
    @State private var more = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Seg(value: $filter, options: Pod.epFilters)
                Spacer()
                Seg(value: $sort, options: Pod.epSorts)
            }
            if let total {
                Text("\(total) " + (total == 1 ? "episode" : "episodes")).font(.caption).foregroundStyle(.secondary)
                if eps.isEmpty { Pod.empty("None") }
                Rows(items: eps) { EpisodeRow(e: $0) }
                if eps.count < total {
                    Button("More") { Task { await load(from: eps.count) } }.disabled(more)
                }
            } else { Pod.loading }
        }
        .task(id: filter + "|" + sort) { await load(from: 0) }
    }

    private func load(from offset: Int) async {
        more = true
        defer { more = false }
        guard let d = try? await API.shared.json("/api/podcasts/episodes?filter=\(filter)&sort=\(sort)&limit=60&offset=\(offset)") else { return }
        eps = offset == 0 ? d.a("episodes") : eps + d.a("episodes")
        total = d.i("total") ?? eps.count
    }
}

/// Recordings: Audiobookshelf's podcast libraries, added by hand: their sets, by when I last listened, by name, or unplayed.
struct RecordingsCat: View {
    @Environment(AppModel.self) private var model
    @AppStorage("pod.recSort") private var sort = "recent"
    @State private var x = PodCache.kept["/api/abs"]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Seg(value: $sort, options: Pod.showSorts)
            if let x {
                let libs = x.a("recordings")
                if let e = x.s("error") { Text("Audiobookshelf: " + e).foregroundStyle(.secondary) }
                else if libs.isEmpty { Pod.empty("No podcast library in Audiobookshelf") }
                ForEach(libs, id: \.self) { lib in
                    if libs.count > 1 { Heading(lib.s("name") ?? "") }
                    Tiles {
                        ForEach(lib.a("shows").sorted(by: order), id: \.self) { s in
                            let n = s.i("count") ?? 0, played = s.i("played") ?? 0
                            Tile(art: Pod.absArt(s.s("item")), title: s.s("title") ?? "",
                                 sub: [s.s("author"), "\(n) " + (n == 1 ? "episode" : "episodes"), played > 0 ? "\(played) played" : nil].compactMap { $0 }.joined(separator: " · ")) {
                                if let i = s.s("item") { model.podNav = .abs(i) }
                            }
                        }
                    }
                }
            } else { Pod.loading }
        }
        .task { x = (try? await PodCache.get("/api/abs")) ?? x }
    }

    private func order(_ a: J, _ b: J) -> Bool {
        switch sort {
        case "az": return (a.s("title") ?? "").localizedStandardCompare(b.s("title") ?? "") == .orderedAscending
        case "unplayed": return (a.i("count") ?? 0) - (a.i("played") ?? 0) > (b.i("count") ?? 0) - (b.i("played") ?? 0)
        default: return (a.d("last") ?? a.d("added") ?? 0) > (b.d("last") ?? b.d("added") ?? 0)
        }
    }
}

/// Audiobooks: Audiobookshelf's, with where I am; one with its book in Daf opens the book's page (Listen, Read).
struct AudiobooksCat: View {
    @Environment(AppModel.self) private var model
    @AppStorage("pod.bookSort") private var sort = "recent"
    @State private var x = PodCache.kept["/api/abs"]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Seg(value: $sort, options: Array(Pod.showSorts.prefix(2)))
            if let x {
                let list = x.a("audiobooks").sorted { a, b in
                    sort == "az" ? (a.s("title") ?? "").localizedStandardCompare(b.s("title") ?? "") == .orderedAscending : (a.d("last") ?? 0) > (b.d("last") ?? 0)
                }
                if let e = x.s("error") { Text("Audiobookshelf: " + e).foregroundStyle(.secondary) }
                else if list.isEmpty { Pod.empty("No audiobooks in Audiobookshelf") }
                Tiles(min: 140) {
                    ForEach(list, id: \.self) { b in book(b) }
                }
            } else { Pod.loading }
        }
        .task { x = (try? await PodCache.get("/api/abs")) ?? x }
    }

    private func book(_ b: J) -> some View {
        let item = b.s("item") ?? "", at = b.d("at") ?? 0, dur = b.d("duration") ?? 0
        let left = b.b("done") ? "Finished" : at > 30 ? Player.hm(dur - at) + " left" : Player.hm(dur)
        return VStack(alignment: .leading, spacing: 6) {
            Tile(art: Pod.absArt(item), title: b.s("title") ?? "", sub: [b.s("author"), left].compactMap { $0 }.joined(separator: " · "),
                 progress: (b.d("pct") ?? 0) / 100) {
                if let book = b.s("book") { model.goTo("#book/" + API.enc(book)) } else { Task { await Player.shared.playABS(item) } }
            }
            HStack(spacing: 6) {
                PlayButton(on: Player.shared.is(Player.absKey(item)) && Player.shared.playing, label: "Listen") { Task { await Player.shared.playABS(item) } }
                if let book = b.s("book"), b.b("readable") {
                    Button("Read") { model.openRoute = "#ebook/" + API.enc(book) }.controlSize(.small)
                }
            }
        }
    }
}

/// Clips: highlights on episodes (and the older clip-only ones), each opening its episode 30 seconds before.
struct ClipsCat: View {
    @Environment(AppModel.self) private var model
    @State private var p = PodCache.kept["/api/podcasts"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let p {
                let clips = p.a("clips")
                if clips.isEmpty { Pod.empty("No clips yet") }
                else {
                    HStack(alignment: .firstTextBaseline) {
                        Heading("Clips")
                        Text("\(clips.count)").font(.caption).foregroundStyle(.tertiary)
                    }
                    ForEach(clips, id: \.self) { c in clip(c) }
                }
            } else { Pod.loading }
        }
        .task { p = (try? await PodCache.get("/api/podcasts")) ?? p }
    }

    private func clip(_ c: J) -> some View {
        let pos = c.s("pos").flatMap { $0.data(using: .utf8) }.flatMap { J(try? JSONSerialization.jsonObject(with: $0)) }?.d("t")
        let text = c.s("text") ?? ""
        return VStack(alignment: .leading, spacing: 4) {
            Text(text)
                .font(.system(.body, design: .serif))
                .environment(\.layoutDirection, Pod.rtl(text) ? .rightToLeft : .leftToRight)
                .textSelection(.enabled)
            HStack(spacing: 4) {
                if let doc = c.s("doc") {
                    Button(c.s("title") ?? "") {
                        model.openRoute = "#read/" + API.enc(doc) + (pos.map { "/t:\(max(0, Int($0) - 30))" } ?? "")
                    }
                    .buttonStyle(.link)
                } else {
                    Text(c.s("title") ?? "")
                }
                Text([c.s("author"), pos.map { Player.clock($0) }, c.d("created").map(Pod.date)].compactMap { $0 }.map { " · " + $0 }.joined())
                    .foregroundStyle(.secondary)
            }
            .font(.caption)
            .lineLimit(1)
        }
        .padding(.leading, 12)
        .overlay(alignment: .leading) { Rectangle().fill(Theme.shared.accent.opacity(0.5)).frame(width: 3) }
    }
}

// MARK: the search

/// Mine first (shows, episodes, Audiobookshelf), then the directory's shows and episodes as they come.
struct PodcastSearch: View {
    @Environment(AppModel.self) private var model
    let q: String
    @State private var mine: J?
    @State private var abs: J?
    @State private var shows: [J]?
    @State private var eps: [J] = []
    @State private var following: Set<String> = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let mine {
                    if !mine.a("shows").isEmpty {
                        Section2("Your shows") {
                            CappedTiles(items: mine.a("shows"), n: 12) { s in
                                Tile(art: s.s("image"), title: s.s("title") ?? "", sub: s.i("unplayed").flatMap { $0 > 0 ? "\($0) unplayed" : nil } ?? "") {
                                    if let f = s.s("feed") { model.podNav = .show(f) }
                                }
                            }
                        }
                    }
                    if !mine.a("episodes").isEmpty {
                        Section2("Your episodes", trailing: AnyView(Text("\(mine.a("episodes").count)").font(.caption).foregroundStyle(.tertiary))) {
                            Capped(items: mine.a("episodes"), n: 8) { EpisodeRow(e: $0) }
                        }
                    }
                    let recs = abs?.a("recordings") ?? [], recEps = abs?.a("episodes") ?? [], books = abs?.a("audiobooks") ?? []
                    if !recs.isEmpty || !recEps.isEmpty {
                        Section2("Recordings") {
                            if !recs.isEmpty {
                                CappedTiles(items: recs, n: 12) { s in
                                    Tile(art: Pod.absArt(s.s("item")), title: s.s("title") ?? "", sub: s.s("author") ?? "") { if let i = s.s("item") { model.podNav = .abs(i) } }
                                }
                            }
                            if !recEps.isEmpty { Capped(items: recEps, n: 8) { ABSRow(e: $0) } }
                        }
                    }
                    if !books.isEmpty {
                        Section2("Audiobooks") {
                            Rows(items: books) { b in ABSRow(e: J(b.raw.merging(["kind": "audiobook", "show": b.raw["author"] ?? ""]) { a, _ in a })) }
                        }
                    }
                    if let shows {
                        if !shows.isEmpty {
                            Section2("Shows in the directory") {
                                CappedTiles(items: shows, n: 12) { s in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Tile(art: s.s("image"), title: s.s("title") ?? "", sub: [s.s("author"), s.i("count").map { "\($0) episodes" }].compactMap { $0 }.joined(separator: " · ")) {
                                            if let f = s.s("feed") { model.podNav = .show(f) }
                                        }
                                        if let f = s.s("feed") { FollowButton(feed: f, on: following.contains(f), small: true) }
                                    }
                                }
                            }
                        }
                        if !eps.isEmpty {
                            Section2("Episodes in the directory") { Capped(items: eps, n: 8) { EpisodeRow(e: $0, found: true) } }
                        }
                        if shows.isEmpty, eps.isEmpty, mine.a("shows").isEmpty, mine.a("episodes").isEmpty, recs.isEmpty, recEps.isEmpty, books.isEmpty {
                            Pod.empty("Nothing matches")
                        }
                    } else { Section2("Directory") { Pod.loading } }
                } else { Pod.loading }
            }
            .padding(28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle("Podcasts")
        .task(id: q) {
            try? await Task.sleep(nanoseconds: 350_000_000)          // a moment after the words stop changing
            guard !Task.isCancelled else { return }
            mine = nil; abs = nil; shows = nil; eps = []
            async let m = API.shared.json("/api/podcasts/search?q=" + API.enc(q))
            async let a = API.shared.json("/api/abs/search?q=" + API.enc(q))
            mine = (try? await m) ?? J(["shows": [], "episodes": []])
            abs = try? await a
            guard !Task.isCancelled else { return }
            let subs = (PodCache.kept["/api/podcasts/shows"]?.a("shows") ?? []) + (mine?.a("shows") ?? [])
            following = Set(subs.compactMap { $0.s("feed") })
            async let ds = API.shared.json("/api/podcasts/directory?kind=shows&q=" + API.enc(q))
            async let de = API.shared.json("/api/podcasts/directory?kind=episodes&q=" + API.enc(q))
            let (s, e) = (try? await ds, try? await de)
            guard !Task.isCancelled else { return }
            shows = s?.a("results") ?? []
            eps = e?.a("results") ?? []
        }
    }
}

// MARK: a show

/// A show: what its feed says of it, Follow, and its episodes filtered and sorted; the search filters them.
struct ShowPage: View {
    @Environment(AppModel.self) private var model
    let feed: String
    let q: String
    @AppStorage("pod.feedFilter") private var filter = ""
    @AppStorage("pod.feedSort") private var sort = "newest"
    @State private var x: J?
    @State private var error: String?
    @State private var shown = 80
    @State private var whole = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Pod.back(model)
                if let x {
                    HStack(alignment: .top, spacing: 18) {
                        PlayerArt(src: x.s("image"), size: 140, corner: 12)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(x.s("title") ?? "Podcast").font(.title2.bold())
                            if let a = x.s("author") { Text(a).foregroundStyle(.secondary) }
                            let n = x.i("count") ?? 0
                            Text(["\(n) " + (n == 1 ? "episode" : "episodes"), x.d("updated").map { "updated " + Pod.date($0) }].compactMap { $0 }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary)
                            HStack {
                                FollowButton(feed: feed, on: x.b("following"))
                                if let l = x.s("link"), l.hasPrefix("http"), let u = URL(string: l) { Link(destination: u) { Label("Website", systemImage: "arrow.up.right.square") } }
                            }
                            if let d = x.s("description") { About(text: d) }
                        }
                    }
                    HStack {
                        Seg(value: $filter, options: Pod.epFilters)
                        Spacer()
                        Seg(value: $sort, options: Pod.epSorts)
                    }
                    let eps = episodes(x)
                    if eps.isEmpty {
                        Pod.empty(!q.isEmpty ? "Nothing matches" : x.s("error").map { x.a("episodes").isEmpty ? "The feed didn't come: " + $0 : "None" } ?? "None")
                    }
                    Rows(items: Array(eps.prefix(shown))) { EpisodeRow(e: $0, show: false, art: false) }
                    if eps.count > shown { Button("More") { shown += 120 } }
                } else if let error {
                    Text(error).foregroundStyle(.secondary)
                } else { Pod.loading }
            }
            .padding(28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(x?.s("title") ?? "Podcasts")
        .task {
            // what Daf knows of it at once (a show I follow has its episodes already), then the feed's latest
            async let known = API.shared.json("/api/podcasts/show?known=1&feed=" + API.enc(feed))
            async let fresh = API.shared.json("/api/podcasts/show?feed=" + API.enc(feed))
            if let k = try? await known, !k.a("episodes").isEmpty, x == nil { x = k }
            do { x = try await fresh } catch { if x == nil { self.error = error.localizedDescription } }
        }
    }

    private func episodes(_ x: J) -> [J] {
        var eps = x.a("episodes").filter { e in
            switch filter {
            case "unplayed": return e.raw["at"] == nil || e.raw["at"] is NSNull
            case "progress": return e.b("started")
            case "played": return e.b("done")
            case "transcribed": return e.b("transcript")
            case "clipped": return (e.i("clips") ?? 0) > 0
            default: return true
            }
        }
        if !q.isEmpty { eps = eps.filter { Find.match(q, $0.s("title"), $0.s("notes")) } }
        return eps.sorted { a, b in
            switch sort {
            case "oldest": return (a.d("published") ?? 0) < (b.d("published") ?? 0)
            case "longest": return (a.d("duration") ?? 0) > (b.d("duration") ?? 0)
            default: return (a.d("published") ?? 0) > (b.d("published") ?? 0)
            }
        }
    }
}

/// One of Audiobookshelf's recordings: its episodes, filtered and sorted, each played from its row.
struct ABSShowPage: View {
    @Environment(AppModel.self) private var model
    let item: String
    let q: String
    @AppStorage("pod.absFilter") private var filter = ""
    @AppStorage("pod.absSort") private var sort = "oldest"
    @State private var x: J?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Pod.back(model)
                if let x {
                    let all = x.a("episodes"), played = all.filter { $0.b("done") }.count
                    HStack(alignment: .top, spacing: 18) {
                        PlayerArt(src: Pod.absArt(item), size: 140, corner: 12)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(x.s("title") ?? "").font(.title2.bold())
                            if let a = x.s("author") { Text(a).foregroundStyle(.secondary) }
                            Text(["\(all.count) " + (all.count == 1 ? "episode" : "episodes"), played > 0 ? "\(played) played" : nil, x.strings("genres").isEmpty ? nil : x.strings("genres").joined(separator: ", ")].compactMap { $0 }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary)
                            if let d = x.s("description") { About(text: d) }
                        }
                    }
                    HStack {
                        Seg(value: $filter, options: Array(Pod.epFilters.prefix(4)))
                        Spacer()
                        Seg(value: $sort, options: Pod.epSorts)
                    }
                    let eps = episodes(all)
                    if eps.isEmpty { Pod.empty(q.isEmpty ? "None" : "Nothing matches") }
                    Rows(items: eps) { e in ABSRow(e: J(e.raw.merging(["item": item]) { a, _ in a }), show: false, art: false) }
                } else if let error {
                    Text(error).foregroundStyle(.secondary)
                } else { Pod.loading }
            }
            .padding(28)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(x?.s("title") ?? "Podcasts")
        .task {
            do { x = try await API.shared.json("/api/abs/show/" + API.enc(item)) } catch { self.error = error.localizedDescription }
        }
        .onReceive(NotificationCenter.default.publisher(for: Player.absPlace).debounce(for: .seconds(2), scheduler: RunLoop.main)) { _ in
            Task { if let n = try? await API.shared.json("/api/abs/show/" + API.enc(item)) { x = n } }
        }
    }

    private func episodes(_ all: [J]) -> [J] {
        var eps = all.filter { e in
            let started = (e.d("at") ?? 0) > 15
            switch filter {
            case "unplayed": return !e.b("done") && !started
            case "progress": return !e.b("done") && started
            case "played": return e.b("done")
            default: return true
            }
        }
        if !q.isEmpty { eps = eps.filter { Find.match(q, $0.s("title"), $0.s("description")) } }
        // recordings often have no date: then by their number, then by title as a person would order them
        func old(_ a: J, _ b: J) -> Bool {
            let pa = a.d("published") ?? 0, pb = b.d("published") ?? 0
            if pa != pb { return pa < pb }
            let na = Double(a.s("number") ?? "") ?? 0, nb = Double(b.s("number") ?? "") ?? 0
            if na != nb { return na < nb }
            return (a.s("title") ?? "").localizedStandardCompare(b.s("title") ?? "") == .orderedAscending
        }
        switch sort {
        case "newest": return eps.sorted { old($1, $0) }
        case "longest": return eps.sorted { ($0.d("duration") ?? 0) > ($1.d("duration") ?? 0) }
        default: return eps.sorted(by: old)
        }
    }
}

// MARK: rows and tiles

/// An AntennaPod episode: the row opens its page (made the first time), the round button plays it here.
struct EpisodeRow: View {
    @Environment(AppModel.self) private var model
    let e: J
    var show = true
    var art = true
    /// One from the directory: what it said of it goes along, until its feed is read.
    var found = false
    @State private var doc: String?

    var body: some View {
        let title = e.s("title") ?? "Episode"
        HStack(alignment: .center, spacing: 12) {
            Button { Task { await open() } } label: {
                HStack(alignment: .top, spacing: 12) {
                    if art { PlayerArt(src: e.s("image"), size: 46) }
                    VStack(alignment: .leading, spacing: 3) {
                        Text(title)
                            .fontWeight(.medium)
                            .lineLimit(2)
                            .multilineTextAlignment(Pod.rtl(title) ? .trailing : .leading)
                            .frame(maxWidth: .infinity, alignment: Pod.rtl(title) ? .trailing : .leading)
                        HStack(spacing: 6) {
                            Text([show ? e.s("show") : nil, e.d("published").map(Pod.date), Pod.len(e.d("duration"))].compactMap { $0 }.joined(separator: " · "))
                            if e.b("transcript") { PodBadge("Transcript") }
                            if let c = e.i("clips"), c > 0 { PodBadge(c == 1 ? "1 clip" : "\(c) clips") }
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        if let s = e.s("snip") { Text(Pod.marked(s)).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                        PodProgress(at: e.d("at"), dur: e.d("duration"), done: e.b("done"))
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .opacity(e.b("done") ? 0.7 : 1)
            PlayButton(on: playingThis) { Task { if let d = await Player.shared.playEpisode(audio: e.s("audio") ?? "", found: found ? e : nil) { doc = d } } }
        }
        .padding(.vertical, 7)
    }

    private var playingThis: Bool {
        let p = Player.shared
        guard p.playing, let c = p.cur else { return false }
        if let d = doc ?? e.s("doc"), c.id == "ep:" + d { return true }
        return c.audio != nil && c.audio == e.s("audio")
    }

    private func open() async {
        if let d = doc ?? e.s("doc") { model.openRoute = "#read/" + API.enc(d); return }
        guard let audio = e.s("audio") else { return }
        do {
            var body: [String: Any] = ["audio": audio]
            if found { body["found"] = e.raw }
            let o = J(try await API.shared.send("POST", "/api/podcasts/open", body))
            if let id = o?.s("id") { doc = id; model.openRoute = "#read/" + API.enc(id) }
        } catch { model.error = error.localizedDescription }
    }
}

/// A recording's or an audiobook's row (Audiobookshelf): all of it plays.
struct ABSRow: View {
    let e: J
    var show = true
    var art = true

    var body: some View {
        let item = e.s("item") ?? "", ep = e.s("kind") == "audiobook" ? nil : e.s("id")
        let id = Player.absKey(item, ep)
        HStack(alignment: .center, spacing: 12) {
            Button { Task { await Player.shared.playABS(item, episode: ep) } } label: {
                HStack(alignment: .top, spacing: 12) {
                    if art { PlayerArt(src: Pod.absArt(item), size: 46) }
                    VStack(alignment: .leading, spacing: 3) {
                        Text(e.s("title") ?? "").fontWeight(.medium).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                        HStack(spacing: 6) {
                            Text([show ? e.s("show") : nil, e.d("published").map(Pod.date), Pod.len(e.d("duration"))].compactMap { $0 }.joined(separator: " · "))
                            if e.s("kind") == "audiobook" { PodBadge("Audiobook") }
                        }
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        PodProgress(at: e.d("at"), dur: e.d("duration"), done: e.b("done"))
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .opacity(e.b("done") ? 0.7 : 1)
            PlayButton(on: Player.shared.is(id) && Player.shared.playing) { Task { await Player.shared.playABS(item, episode: ep) } }
        }
        .padding(.vertical, 7)
    }
}

/// The round button that plays a row in the player, or pauses it when it's the one playing.
struct PlayButton: View {
    let on: Bool
    var label: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            if let label {
                Label(on ? "Pause" : label, systemImage: on ? "pause.fill" : "play.fill")
            } else {
                Image(systemName: on ? "pause.circle.fill" : "play.circle.fill").font(.system(size: 26)).foregroundStyle(Theme.shared.accent)
            }
        }
        .buttonStyle(.borderless)
        .controlSize(.small)
        .help(on ? "Pause" : label ?? "Play")
    }
}

/// How far: a line and the time left, or Played.
struct PodProgress: View {
    let at: Double?
    let dur: Double?
    let done: Bool

    var body: some View {
        if done || ((at ?? 0) > 15 && (dur ?? 0) > 0) {
            HStack(spacing: 8) {
                ProgressView(value: done ? 1 : min(1, (at ?? 0) / max(1, dur ?? 1))).frame(width: 90).controlSize(.mini)
                Text(done ? "Played" : (Pod.len(max(0, (dur ?? 0) - (at ?? 0))) ?? "") + " left").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}

struct PodBadge: View {
    let text: String
    init(_ t: String) { text = t }
    var body: some View {
        Text(text).font(.caption2.weight(.medium)).foregroundStyle(Theme.shared.accent)
            .padding(.horizontal, 5).padding(.vertical, 1)
            .background(Theme.shared.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
    }
}

/// A picture, its title and a line under it; the whole of it a button.
struct Tile: View {
    let art: String?
    let title: String
    let sub: String
    var progress: Double = 0
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 5) {
                PlayerArt(src: art, size: 130, corner: 10)
                    .overlay(alignment: .bottom) {
                        if progress > 0 { ProgressView(value: min(1, progress)).controlSize(.mini).padding(.horizontal, 8).padding(.bottom, 6) }
                    }
                Text(title).font(.callout).lineLimit(2).multilineTextAlignment(.leading)
                if !sub.isEmpty { Text(sub).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
            }
            .frame(width: 130, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct Tiles<Content: View>: View {
    var min: CGFloat = 130
    @ViewBuilder let content: Content
    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: min, maximum: min + 30), alignment: .top)], alignment: .leading, spacing: 18) { content }
    }
}

/// Rows with a line between them.
struct Rows<Row: View>: View {
    let items: [J]
    @ViewBuilder let row: (J) -> Row
    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.offset) { k, e in
                if k > 0 { Divider() }
                row(e)
            }
        }
    }
}

/// The first n, and More for the rest.
struct Capped<Row: View>: View {
    let items: [J]
    let n: Int
    @ViewBuilder let row: (J) -> Row
    @State private var all = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Rows(items: all ? items : Array(items.prefix(n)), row: row)
            if !all, items.count > n { Button("More") { all = true } }
        }
    }
}

struct CappedTiles<T: View>: View {
    let items: [J]
    let n: Int
    @ViewBuilder let tile: (J) -> T
    @State private var all = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Tiles { ForEach(all ? items : Array(items.prefix(n)), id: \.self) { tile($0) } }
            if !all, items.count > n { Button("More") { all = true } }
        }
    }
}

/// A heading, something beside it, and what's under it.
struct Section2<Content: View>: View {
    let title: String
    var trailing: AnyView?
    @ViewBuilder let content: Content
    init(_ title: String, trailing: AnyView? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.trailing = trailing
        self.content = content()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Heading(title)
                Spacer()
                if let trailing { trailing }
            }
            content
        }
    }
}

/// A segmented choice, kept as the page keeps it.
struct Seg: View {
    @Binding var value: String
    let options: [(String, String)]
    var body: some View {
        Picker("", selection: $value) { ForEach(options, id: \.0) { Text($0.1).tag($0.0) } }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
            .controlSize(.small)
    }
}

/// Follow and Following: into the subscriptions AntennaPod syncs (it picks a change up at its next sync).
struct FollowButton: View {
    let feed: String
    @State var on: Bool
    var small = false

    init(feed: String, on: Bool, small: Bool = false) {
        self.feed = feed
        _on = State(initialValue: on)
        self.small = small
    }

    var body: some View {
        Group {
            if on { Button("Following") { Task { await follow(false) } } }
            else { Button("Follow") { Task { await follow(true) } }.buttonStyle(.borderedProminent) }
        }
        .controlSize(small ? .small : .regular)
    }

    private func follow(_ v: Bool) async {
        do {
            _ = try await API.shared.send("POST", "/api/podcasts/follow", ["feed": feed, "follow": v])
            on = v
            PodCache.kept["/api/podcasts/shows"] = nil
            AppModel.shared.say(v ? "Following. AntennaPod gets it at its next sync." : "Not following. AntennaPod drops it at its next sync.")
        } catch { AppModel.shared.error = error.localizedDescription }
    }
}

/// What a show is about: a few lines, and More for the rest.
struct About: View {
    let text: String
    @State private var open = false
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(text).font(.callout).foregroundStyle(.secondary).lineLimit(open ? nil : 4).textSelection(.enabled)
            if text.count > 240 { Button(open ? "Less" : "More") { open.toggle() }.buttonStyle(.link).font(.caption) }
        }
        .padding(.top, 4)
    }
}

@MainActor
enum Pod {
    static let epFilters = [("", "All"), ("unplayed", "Unplayed"), ("progress", "In Progress"), ("played", "Played"), ("transcribed", "Transcribed"), ("clipped", "Clipped")]
    static let epSorts = [("newest", "Newest"), ("oldest", "Oldest"), ("longest", "Longest")]
    static let showSorts = [("recent", "Recent"), ("az", "A–Z"), ("unplayed", "Unplayed")]

    static func absArt(_ item: String?) -> String? { item.map { "/api/abs/cover/" + API.enc($0) } }

    /// "58 min", "1 h 5 min".
    static func len(_ s: Double?) -> String? {
        guard let s, s > 0 else { return nil }
        let m = Int((s / 60).rounded())
        return m >= 60 ? "\(m / 60) h" + (m % 60 > 0 ? " \(m % 60) min" : "") : "\(max(1, m)) min"
    }

    static func date(_ t: Double) -> String {
        let d = Date(timeIntervalSince1970: t)
        return Calendar.current.isDate(d, equalTo: Date(), toGranularity: .year) ? d.formatted(.dateTime.month().day()) : d.formatted(.dateTime.month().day().year())
    }

    static func rtl(_ s: String) -> Bool { s.range(of: "[\u{0590}-\u{05FF}]", options: .regularExpression) != nil }

    /// A transcript's words with the ones searched for marked (the server sends them between \u{2} and \u{3}).
    static func marked(_ s: String) -> AttributedString {
        var out = AttributedString(), run = "", on = false
        func flush() {
            var a = AttributedString(run)
            if on { a.font = .caption.weight(.bold); a.foregroundColor = .primary }
            out += a
            run = ""
        }
        for ch in s {
            if ch == "\u{2}" || ch == "\u{3}" { flush(); on = ch == "\u{2}" } else { run.append(ch) }
        }
        flush()
        return out
    }

    static var loading: some View { ProgressView().frame(maxWidth: .infinity).padding(40) }

    static func empty(_ t: String) -> some View {
        Text(t).font(.headline).foregroundStyle(.secondary).frame(maxWidth: .infinity).padding(40)
    }

    /// Back from a show to the Podcasts page.
    static func back(_ model: AppModel) -> some View {
        Button { model.podNav = .cat(model.podCat) } label: { Label("Podcasts", systemImage: "chevron.left") }
            .buttonStyle(.link)
    }
}

/// Matching on the page, as find.js does: every word somewhere in the texts, whatever its case, accents or Hebrew points.
enum Find {
    static func fold(_ s: String) -> String { s.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil) }

    static func match(_ q: String, _ texts: String?...) -> Bool {
        let words = fold(q).split(whereSeparator: \.isWhitespace)
        guard !words.isEmpty else { return true }
        let hay = fold(texts.compactMap { $0 }.joined(separator: " "))
        return words.allSatisfy { hay.contains($0) }
    }
}
