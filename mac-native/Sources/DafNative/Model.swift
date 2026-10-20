import Foundation
import Observation

/// A place in the sidebar.
enum Place: Hashable {
    case today
    case review
    case library(String)              // inbox, later, archive
    case shortlist
    case feed(String?)                // nil: everything unseen; else a category
    case feedSource(String)           // one feed ("feed/12")
    case books
    case manga
    case torah
    case podcasts
    case highlights
    case stats
    case sources
    case search

    /// A page of its own across the window (sidebar and page), rather than a list and what's open.
    var isPage: Bool { self == .review || self == .stats || self == .podcasts || self == .sources }

    var title: String {
        switch self {
        case .today: return "Today"
        case .review: return "Review"
        case .shortlist: return "Shortlist"
        case .highlights: return "Highlights"
        case .stats: return "Stats"
        case .manga: return "Manga"
        case .torah: return "Torah"
        case .podcasts: return "Podcasts"
        case .sources: return "Sources"
        case .library(let tab): return ["inbox": "Inbox", "later": "Later", "archive": "Archive"][tab] ?? tab.capitalized
        case .feed(let cat): return cat ?? "All Feeds"
        case .feedSource: return "Feed"
        case .books: return "Books"
        case .search: return "Search"
        }
    }
}

/// Something that can be opened: an article, a PDF, a video, a book.
struct Item: Identifiable, Hashable {
    let id: String
    let j: J
    var type: String { j.s("type") ?? (id.hasPrefix("cal:") ? "book" : "doc") }
    var kind: String { j.s("kind") ?? (type == "book" ? "book" : "article") }
    var title: String { j.s("title") ?? j.s("url") ?? "Untitled" }
    var source: String? { j.s("source") ?? j.s("author") }
    var mins: Int? { j.i("mins") }
    var progress: Double { j.d("progress") ?? 0 }
    var thumb: String? {
        if type == "book" { return j.b("has_cover") ? "/api/cover/" + API.enc(id) : nil }
        return j.s("thumb")
    }
    var whereIn: String? { j.s("where_") }
    var status: String? { j.s("status") }
    var isBook: Bool { type == "book" || kind == "book" }
    var isSeries: Bool { type == "series" }
    var isDoc: Bool { !isBook && !isSeries }

    init(_ j: J) {
        self.j = j
        id = j.s("id") ?? UUID().uuidString
    }
}

@MainActor
@Observable
final class AppModel {
    var place: Place? = .today
    var items: [Item] = []
    var selection: Item.ID?
    var counts: J?
    var today: J?
    var home: J?
    var torah: J?
    var loading = false
    var error: String?
    var needsSignIn = false
    var query = ""
    /// The Library's kind: "" for everything, else article, video, tweet, pdf, email.
    var kind = ""
    /// A short word at the bottom of the window ("Saved to the Library"), with Undo when it can be undone.
    var toast: String?
    var toastUndo = false
    @ObservationIgnored private var toastTask: Task<Void, Never>?
    @ObservationIgnored private var pendingUndo: (id: UUID, run: () async -> Void)?
    /// The window's, so Edit › Undo (⌘Z) undoes what the toast offers.
    @ObservationIgnored weak var undoManager: UndoManager?

    func say(_ s: String, undo name: String? = nil, _ action: (() async -> Void)? = nil) {
        toast = s
        toastUndo = action != nil
        if let action {
            let id = UUID()
            pendingUndo = (id, action)
            undoManager?.removeAllActions(withTarget: self)
            undoManager?.registerUndo(withTarget: self) { m in MainActor.assumeIsolated { if m.pendingUndo?.id == id { m.undoLast() } } }
            if let name { undoManager?.setActionName(name) }
        }
        toastTask?.cancel()
        let wait: UInt64 = action != nil ? 6_000_000_000 : 2_600_000_000
        toastTask = Task { try? await Task.sleep(nanoseconds: wait); if !Task.isCancelled { toast = nil; toastUndo = false } }
    }

    func undoLast() {
        guard let p = pendingUndo else { return }
        pendingUndo = nil
        undoManager?.removeAllActions(withTarget: self)
        toast = nil
        toastUndo = false
        Task { await p.run() }
    }

    /// Article › Tags…: the inspector's tag field takes the keys.
    var focusTags = 0
    /// The Feed's folders and feeds with their counts (/api/feed/sources).
    var sources: J?
    /// A feed to unfollow, once that's confirmed.
    var confirmUnfollow: String?
    var showInspector = false
    /// The article open in the reader, kept so the inspector and the toolbar can act on it.
    var reader: ReaderModel?
    let highlights = HighlightsModel()
    var review = ReviewModel()
    var sheet: Sheet?
    /// A route to open in a window of its own ("#ebook/…", "#mread/…"), from code (menus, the self-test).
    var openRoute: String?
    /// Settings, opened from code (the self-test; ⌘, opens it by hand).
    var showSettings = false

    enum Sheet: Identifiable, Hashable {
        case addLink, paper, follow, renameFeed(String)
        var id: String {
            switch self {
            case .addLink: return "addLink"
            case .paper: return "paper"
            case .follow: return "follow"
            case .renameFeed(let f): return "rename " + f
            }
        }
    }

    /// The list's title: a feed by its name.
    func title(_ p: Place?) -> String {
        if case .feedSource(let id)? = p { return feed(id)?.s("title") ?? "Feed" }
        return p?.title ?? "Daf"
    }

    var selected: Item? { items.first { $0.id == selection } ?? continueItems.first { $0.id == selection } }
    var continueItems: [Item] { (home?.a("continue") ?? []).map(Item.init) }

    private var loadTask: Task<Void, Never>?

    init() {
        NotificationCenter.default.addObserver(forName: .dafSignedOut, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.needsSignIn = true }
        }
        needsSignIn = API.shared.cookie == nil
        startClock()
    }

    func reload() {
        loadTask?.cancel()
        loadTask = Task { await load() }
    }

    func load() async {
        guard let place else { return }
        loading = true
        error = nil
        defer { loading = false }
        do {
            async let c = API.shared.json("/api/docs/counts")
            async let t = API.shared.json("/api/today")
            switch place {
            case .today:
                async let h = API.shared.json("/api/home")
                home = try await h
                items = []
            case .library(let tab):
                let j = try await API.shared.json("/api/docs?where=library&tab=\(tab)&limit=200" + (kind.isEmpty ? "" : "&kind=\(kind)"))
                items = j.a("items").map(Item.init)
            case .shortlist:
                let j = try await API.shared.json("/api/docs?where=library&tab=inbox&kind=starred&limit=200")
                items = j.a("items").map(Item.init)
            case .review, .highlights, .stats, .podcasts, .sources:
                items = []
            case .manga:
                let j = try await API.shared.json("/api/manga")
                var seen = Set<String>(), out: [Item] = []
                for s in j.a("continue") + j.a("series") {
                    guard let id = s.s("id"), seen.insert(id).inserted else { continue }
                    var raw = s.raw
                    raw["type"] = "series"
                    raw["kind"] = "series"
                    raw["title"] = s.s("name")
                    raw["source"] = "\(s.i("count") ?? 0) volumes" + ((s.i("read") ?? 0) > 0 ? " · \(s.i("read")!) read" : "")
                    raw["thumb"] = s.s("cover").map { "/api/manga/thumb/b/" + API.enc($0) }
                    out.append(Item(J(raw)))
                }
                items = out
            case .torah:
                let t = try await API.shared.json("/api/torah")
                torah = t
                items = (t.a("week") + t.a("ruach") + t.a("earlier")).map(Item.init)
            case .feed(let cat):
                if sources == nil { await loadSources() }
                let j = try await API.shared.json("/api/docs?where=feed&tab=unseen&limit=200" + (cat.map { "&cat=" + API.enc($0) } ?? ""))
                items = j.a("items").map(Item.init)
            case .feedSource(let f):
                let j = try await API.shared.json("/api/docs?where=feed&tab=unseen&limit=200&feed=" + API.enc(f))
                items = j.a("items").map(Item.init)
            case .books:
                let j = try await API.shared.json("/api/books")
                var seen = Set<String>(), out: [Item] = []
                for key in ["nightstand", "suggested", "others"] {
                    for b in j.a(key) where b.b("readable") || key != "others" {
                        guard let id = b.s("id"), seen.insert(id).inserted else { continue }
                        var raw = b.raw
                        raw["type"] = "book"
                        raw["kind"] = "book"
                        raw["source"] = b.s("author") ?? b.s("progress_note")
                        out.append(Item(J(raw)))
                    }
                }
                items = out
            case .search:
                let q = query.trimmingCharacters(in: .whitespaces)
                guard q.count >= 2 else { items = []; break }
                let j = try await API.shared.json("/api/search?q=" + API.enc(q))
                items = j.a("docs").map(Item.init) + j.a("books").map { b in
                    var raw = b.raw
                    raw["type"] = "book"
                    raw["kind"] = "book"
                    return Item(J(raw))
                }
            }
            counts = try await c
            today = try await t
            needsSignIn = false
        } catch is CancellationError {
        } catch let e as APIError where e.status == 401 {
            needsSignIn = true
        } catch {
            if (error as? URLError)?.code != .cancelled { self.error = error.localizedDescription }
        }
    }

    // MARK: acting on an item

    /// Done in the Library (archive), seen in the Feed.
    func done(_ item: Item) async { await setStatus(item, item.whereIn == "feed" ? (item.status == "seen" ? "unseen" : "seen") : (item.status == "archive" ? "inbox" : "archive")) }
    func later(_ item: Item) async { await setStatus(item, item.status == "later" ? "inbox" : "later") }

    @discardableResult
    func setStatus(_ item: Item, _ status: String) async -> Bool {
        do {
            try await API.shared.send("POST", "/api/docs/\(API.enc(item.id))/status", ["status": status])
            if let i = items.firstIndex(where: { $0.id == item.id }) {
                let next = items.indices.contains(i + 1) ? items[i + 1].id : (i > 0 ? items[i - 1].id : nil)
                items.remove(at: i)
                if selection == item.id { selection = next }
            }
            counts = try? await API.shared.json("/api/docs/counts")
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    /// Delete, with Undo putting it back where it was.
    func delete(_ item: Item) async {
        let was = item.status ?? (item.whereIn == "feed" ? "unseen" : "inbox")
        guard await setStatus(item, "deleted") else { return }
        if reader?.id == item.id { reader?.stop() }
        say("Deleted", undo: "Delete") { [weak self] in
            guard let self else { return }
            do {
                try await API.shared.send("POST", "/api/docs/\(API.enc(item.id))/status", ["status": was])
                self.say("Back in \(["later": "Later", "archive": "the Archive", "unseen": "the Feed", "seen": "the Feed"][was] ?? "the Inbox")")
                await self.load()
                self.selection = item.id
            } catch { self.error = error.localizedDescription }
        }
    }

    func saveToLibrary(_ item: Item) async {
        do {
            try await API.shared.send("POST", "/api/docs/\(API.enc(item.id))/save", [:])
            counts = try? await API.shared.json("/api/docs/counts")
        } catch { self.error = error.localizedDescription }
    }

    // MARK: counts for the sidebar

    func count(_ p: Place) -> Int? {
        guard let counts else { return nil }
        switch p {
        case .shortlist: return counts.i("starred").flatMap { $0 > 0 ? $0 : nil }
        case .review:
            guard let r = today?.o("review"), let total = r.i("total") else { return nil }
            let left = total - (r.i("done") ?? 0)
            return left > 0 ? left : nil
        case .library(let tab):
            if tab == "inbox" { return counts.o("library")?.raw.values.compactMap { ($0 as? NSNumber)?.intValue }.reduce(0, +) }
            return nil
        case .feed(let cat):
            if let cat { return counts.o("feed")?.i(cat) }
            return counts.i("feed_total")
        case .feedSource(let id):
            return feed(id)?.i("count")
        default: return nil
        }
    }

    var feedCategories: [String] { (counts?.o("feed")?.raw.keys.map { $0 } ?? []).sorted() }
}
