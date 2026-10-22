import Foundation
import Observation

/// A place in the sidebar.
enum Place: Hashable {
    case today
    case home                         // the Library's home: its shelves
    case review
    case library(String)              // inbox, later, archive
    case shortlist
    case feed(String?)                // nil: everything unseen; else a category
    case feedSource(String)           // one feed ("feed/12")
    case view(String)                 // a saved view, by its id
    case shelf(String)                // a shelf of books
    case paper                        // photos of paper pages
    case recovery
    case books
    case manga
    case torah
    case podcasts
    case highlights
    case stats
    case sources
    case search

    /// A page of its own across the window (sidebar and page), rather than a list and what's open.
    var isPage: Bool { self == .today || self == .review || self == .stats || self == .podcasts || self == .sources || self == .home || self == .recovery }

    var title: String {
        switch self {
        case .today: return "Today"
        case .home: return "Home"
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
        case .view: return "View"
        case .shelf: return "Shelf"
        case .paper: return "Paper Pages"
        case .recovery: return "Recovery"
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
    var title: String { j.b("private") ? "Private reading" : (j.s("title") ?? j.s("url") ?? "Untitled") }
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
    var isPaper: Bool { type == "paper" }
    var isDoc: Bool { !isBook && !isSeries && !isPaper }

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
    /// The one item open; several chosen at once are `chosen`, and then nothing is open.
    var selection: Item.ID? {
        didSet {
            if let s = selection { if multi != [s] { multi = [s] } } else if multi.count == 1 { multi = [] }
        }
    }
    var multi: Set<Item.ID> = [] {
        didSet {
            let one = multi.count == 1 ? multi.first : nil
            if selection != one { selection = one }
        }
    }
    var chosen: [Item] { items.filter { multi.contains($0.id) } }
    /// The list as shown: a Library tag picked in the filters keeps only what has it.
    var shown: [Item] {
        let list = tag.map { t in items.filter { $0.j.strings("tags").contains(t) } } ?? items
        let q = booksQuery.trimmingCharacters(in: .whitespaces).lowercased()
        guard place == .books, !q.isEmpty else { return list }
        return list.filter { $0.title.lowercased().contains(q) || ($0.j.s("author") ?? "").lowercased().contains(q) }
    }
    /// Books by section, in the page's order: the nightstand, Want to Read, opened lately, the library.
    var bookSections: [(String, [Item])] {
        var out: [(String, [Item])] = []
        for item in shown {
            let s = item.j.s("section") ?? "Books"
            if out.last?.0 == s { out[out.count - 1].1.append(item) } else { out.append((s, [item])) }
        }
        return out
    }
    var booksQuery = ""

    // the list's order and filters, as the page has them
    var sortLibrary = UserDefaults.standard.string(forKey: "sort.library") ?? "new" { didSet { UserDefaults.standard.set(sortLibrary, forKey: "sort.library") } }
    var sortFeed = UserDefaults.standard.string(forKey: "sort.feed") ?? "new" { didSet { UserDefaults.standard.set(sortFeed, forKey: "sort.feed") } }
    var listFilter = ListFilter()
    var tag: String?
    var feedTab = "unseen"
    static let sorts = [("new", "Newest"), ("old", "Oldest"), ("published", "Published"), ("short", "Shortest"), ("long", "Longest"), ("progress", "Started First")]
    /// Saved views and shelves, for the sidebar.
    var views: [J] = []
    var shelves: [J] = []
    var counts: J?
    var today: J?
    var home: J?
    var torah: J?
    var loading = false
    var error: String? { didSet { if let error { recentErrors = Array((recentErrors + [error]).suffix(20)) } } }
    /// What went wrong lately, for Send Feedback.
    @ObservationIgnored var recentErrors: [String] = []
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
    /// Article › Ask…: the inspector's question field takes the keys.
    var focusAsk = 0
    /// A themed review to start (the query /api/review/themed takes), when Review opens.
    var reviewTheme: String?

    /// Review some highlights by theme: Review These, Review More, a tag, favorites, a colour, a book.
    func startReview(themed q: String) {
        reviewTheme = q
        if place != .review { place = .review }
    }

    /// N: the inspector's note takes the keys.
    var focusNote = 0
    /// Article › Edit the Title and Author…
    var editMeta = false
    @ObservationIgnored private var keptBooks = false
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
    /// For Add to Daf: a link dropped or pasted, books and PDFs dropped or pasted.
    @ObservationIgnored var addURL: String?
    @ObservationIgnored var addFiles: [URL] = []
    /// Settings, opened from code (the self-test; ⌘, opens it by hand).
    var showSettings = false

    enum Sheet: Identifiable, Hashable {
        case addLink, paper, follow, renameFeed(String), saveView, newShelf(String?), renameShelf(String), feedback, palette, shortcuts
        var id: String {
            switch self {
            case .addLink: return "addLink"
            case .palette: return "palette"
            case .shortcuts: return "shortcuts"
            case .feedback: return "feedback"
            case .paper: return "paper"
            case .follow: return "follow"
            case .renameFeed(let f): return "rename " + f
            case .saveView: return "saveView"
            case .newShelf(let b): return "newShelf " + (b ?? "")
            case .renameShelf(let s): return "renameShelf " + s
            }
        }
    }

    /// The list's title: a feed by its name.
    func title(_ p: Place?) -> String {
        switch p {
        case .feedSource(let id)?: return feed(id)?.s("title") ?? "Feed"
        case .view(let id)?: return view(id)?.s("name") ?? "View"
        case .shelf(let id)?: return shelves.first { $0.s("id") == id }?.s("name") ?? "Shelf"
        default: return p?.title ?? "Daf"
        }
    }

    var selected: Item? { items.first { $0.id == selection } ?? continueItems.first { $0.id == selection } }

    /// The vault's essays on this week's parasha (Reference/torah/<parasha>/), as the reader opens
    /// them: Daf makes each readable when it's first opened, and its highlights go into the same note.
    static func essays(_ t: J) -> [J] {
        t.a("essays").map { e in
            var raw: [String: Any] = ["id": e.s("id") ?? "", "type": "doc", "kind": "article", "title": e.s("title") ?? "", "vault_essay": e.s("path") ?? "",
                                      "source": e.s("author") ?? e.s("series") ?? "Your vault"]
            if let w = e.i("words") { raw["mins"] = max(1, Int((Double(w) / 238).rounded())) }
            if let p = e.d("progress") { raw["progress"] = p }
            if let h = e.i("highlights"), h > 0 { raw["highlights"] = h }
            return J(raw)
        }
    }

    /// A book's page, on Books (from Today, Recovery, a notice).
    func showBook(_ id: String) {
        place = .books
        Task {
            _ = await until(6) { self.items.contains { $0.id == id } }
            selection = id
        }
    }

    private func until(_ timeout: Double, _ cond: () -> Bool) async -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            if cond() { return true }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        return cond()
    }
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
                items = try await docs("library", tab: tab, arg: kind, sort: sortLibrary, filter: listFilter.dict)
                if tab != "archive" { keepForLater(items) }
            case .shortlist:
                items = try await docs("library", tab: "inbox", arg: "starred", sort: sortLibrary, filter: listFilter.dict)
            case .view(let id):
                if views.isEmpty { await loadViews() }
                guard let v = view(id) else { items = []; break }
                let w = v.s("where") == "feed" ? "feed" : "library"
                items = try await docs(w, tab: v.s("tab") ?? (w == "feed" ? "unseen" : "inbox"), arg: v.s("arg") ?? "", sort: viewSort, filter: viewFilter.dict)
            case .paper:
                items = try await API.shared.json("/api/paper/pages").a("pages").map(PaperPages.item)
            case .shelf(let id):
                let j = try await API.shared.json("/api/shelves/" + API.enc(id))
                items = j.a("books").map { b in
                    var raw = b.raw
                    raw["type"] = "book"
                    raw["kind"] = "book"
                    raw["source"] = b.s("author") ?? b.s("progress_note")
                    return Item(J(raw))
                }
            case .home:
                home = try await API.shared.json("/api/home")
                items = []
            case .recovery:
                items = []
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
                    raw["source"] = plural(s.i("count") ?? 0, "volume") + ((s.i("read") ?? 0) > 0 ? " · \(s.i("read")!) read" : "")
                    raw["thumb"] = s.s("cover").map { "/api/manga/thumb/b/" + API.enc($0) }
                    out.append(Item(J(raw)))
                }
                items = out
            case .torah:
                let t = try await API.shared.json("/api/torah")
                torah = t
                items = (t.a("week") + t.a("ruach") + Self.essays(t) + t.a("earlier")).map(Item.init)
            case .feed(let cat):
                if sources == nil { await loadSources() }
                items = try await docs("feed", tab: feedTab, arg: cat, sort: sortFeed, filter: listFilter.dict)
            case .feedSource(let f):
                items = try await docs("feed", tab: feedTab, arg: f, sort: sortFeed, filter: listFilter.dict)
            case .books:
                // Each book once, in the first section it's in. Hardcover's Want to Read: the ones Daf has.
                async let hc = try? API.shared.json("/api/hardcover/shelf?status=1")
                async let lib = try? API.shared.json("/api/ebooks")
                let j = try await API.shared.json("/api/books")
                var seen = Set<String>(), out: [Item] = []
                func add(_ b: J, _ section: String, id: String? = nil) {
                    guard let id = id ?? b.s("id"), seen.insert(id).inserted else { return }
                    var raw = b.raw
                    raw["id"] = id
                    raw["type"] = "book"
                    raw["kind"] = "book"
                    raw["source"] = b.s("author") ?? b.s("progress_note")
                    raw["section"] = section
                    out.append(Item(J(raw)))
                }
                let stand = j.a("nightstand")
                for b in stand.isEmpty ? j.a("suggested") : stand { add(b, stand.isEmpty ? "Suggested for the nightstand" : "Nightstand") }
                for b in await hc?.a("books") ?? [] { if let d = b.s("daf_id") { add(b, "Want to Read", id: d) } }
                for b in j.a("others") { add(b, "Opened lately") }
                for b in await lib?.a("books") ?? [] { add(b, "Your library") }
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
            Theme.shared.adopt(today?.o("settings")?.o("appearance"))
            needsSignIn = false
            if !keptBooks { keptBooks = true; keepNightstand() }
        } catch is CancellationError {
        } catch let e as APIError where e.status == 401 {
            needsSignIn = true
        } catch {
            if (error as? URLError)?.code != .cancelled { self.error = error.localizedDescription }
        }
    }

    /// A list from Daf as the page asks for it: the Library by kind ("starred" for the Shortlist), the
    /// Feed by folder or by feed, in an order, with the filters.
    private func docs(_ w: String, tab: String, arg: String?, sort: String, filter: [String: Any]) async throws -> [Item] {
        var q = "/api/docs?where=\(w)&tab=\(API.enc(tab))&sort=\(API.enc(sort))&limit=200"
        if let arg, !arg.isEmpty {
            q += w == "feed" ? (arg.hasPrefix("feed/") ? "&feed=" : "&cat=") + API.enc(arg) : "&kind=" + API.enc(arg)
        }
        for (k, v) in filter.sorted(by: { $0.key < $1.key }) { q += "&\(k)=" + API.enc((v as? Bool).map { $0 ? "1" : "0" } ?? "\(v)") }
        return try await API.shared.json(q).a("items").map(Item.init)
    }

    /// A new place: nothing chosen, a saved view's tag (or none), the list again.
    func placeChanged() {
        multi = []
        if case .view? = place { viewAsSaved(load: false) } else { tag = nil }
        reload()
    }

    // a saved view's order and filters, as changed here before Update the View
    var viewSort = "new"
    var viewFilter = ListFilter()

    /// The view open, as it was saved.
    func viewAsSaved(load: Bool = true) {
        guard case .view(let id)? = place, let v = view(id) else { return }
        viewSort = v.s("sort") ?? "new"
        viewFilter = ListFilter(v.o("filter")?.raw ?? [:])
        tag = v.s("tag").flatMap { $0.isEmpty ? nil : $0 }
        if load { reload() }
    }

    var viewChanged: Bool {
        guard case .view(let id)? = place, let v = view(id) else { return false }
        return viewSort != (v.s("sort") ?? "new") || viewFilter != ListFilter(v.o("filter")?.raw ?? [:]) || (tag ?? "") != (v.s("tag") ?? "")
    }

    /// Update the View: its order, filters and tag, as they are now, for every device.
    func updateView() async {
        guard case .view(let id)? = place else { return }
        let list: [[String: Any]] = views.map { v in
            guard v.s("id") == id else { return v.raw }
            var raw = v.raw
            raw["sort"] = viewSort
            raw["filter"] = viewFilter.dict
            raw["tag"] = tag ?? ""
            return raw
        }
        if await saveViews(list) { say("The view is updated") }
    }

    // MARK: saved views and shelves

    func view(_ id: String) -> J? { views.first { $0.s("id") == id } }

    func loadViews() async { if let v = try? await API.shared.json("/api/views") { views = v.a("views") } }
    func loadShelves() async { if let s = try? await API.shared.json("/api/shelves") { shelves = s.a("shelves") } }

    /// The list as it is now, as a view (nil where there's no list to keep: Today, Books, …).
    func currentView(named name: String) -> [String: Any]? {
        var v: [String: Any] = ["name": name, "tag": tag ?? "", "filter": listFilter.dict]
        switch place {
        case .library(let tab)?: v["where"] = "library"; v["arg"] = kind; v["tab"] = tab; v["sort"] = sortLibrary
        case .shortlist?: v["where"] = "library"; v["arg"] = "starred"; v["tab"] = "inbox"; v["sort"] = sortLibrary
        case .feed(let cat)?: v["where"] = "feed"; v["arg"] = cat ?? ""; v["tab"] = feedTab; v["sort"] = sortFeed
        case .feedSource(let f)?: v["where"] = "feed"; v["arg"] = f; v["tab"] = feedTab; v["sort"] = sortFeed
        default: return nil
        }
        return v
    }

    func saveViews(_ list: [[String: Any]]) async -> Bool {
        do {
            let r = J(try await API.shared.send("PUT", "/api/views", ["views": list]))
            views = r?.a("views") ?? views
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func saveCurrentView(named name: String) async -> Bool {
        guard let v = currentView(named: name) else { return false }
        let before = Set(views.compactMap { $0.s("id") })
        guard await saveViews(views.map(\.raw) + [v]) else { return false }
        if let new = views.first(where: { !before.contains($0.s("id") ?? "") })?.s("id") { place = .view(new) }
        say("Saved in the sidebar")
        return true
    }

    func removeView(_ id: String) async {
        guard await saveViews(views.filter { $0.s("id") != id }.map(\.raw)) else { return }
        if place == .view(id) { place = .library("inbox") }
        say("View removed")
    }

    @discardableResult
    func newShelf(_ name: String, with book: String? = nil) async -> Bool {
        var body: [String: Any] = ["name": name]
        if let book { body["book"] = book }
        do {
            let r = J(try await API.shared.send("POST", "/api/shelves", body))
            shelves = r?.a("shelves") ?? shelves
            say(book == nil ? "Shelf made" : "On the new shelf")
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    @discardableResult
    func renameShelf(_ id: String, to name: String) async -> Bool {
        do {
            let r = J(try await API.shared.send("PUT", "/api/shelves/" + API.enc(id), ["name": name]))
            shelves = r?.a("shelves") ?? shelves
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    func deleteShelf(_ id: String) async {
        do {
            let r = J(try await API.shared.send("DELETE", "/api/shelves/" + API.enc(id), nil))
            shelves = r?.a("shelves") ?? shelves
            if place == .shelf(id) { place = .books }
            say("Shelf deleted")
        } catch { self.error = error.localizedDescription }
    }

    /// A book on a shelf, or off it.
    func shelve(_ book: String, on shelf: String, _ on: Bool) async -> Bool {
        do {
            try await API.shared.send(on ? "PUT" : "DELETE", "/api/shelves/\(API.enc(shelf))/books/\(API.enc(book))", nil)
            await loadShelves()
            if place == .shelf(shelf) { await load() }
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    // MARK: several at once

    /// Several chosen, all moved at once (/api/docs/bulk), with Undo putting each back where it was.
    func bulk(_ chosen: [Item], _ status: String) async {
        let docs = chosen.filter(\.isDoc)
        guard !docs.isEmpty else { return }
        let back = Dictionary(grouping: docs, by: { $0.status ?? ($0.whereIn == "feed" ? "unseen" : "inbox") }).mapValues { $0.map(\.id) }
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/bulk", ["ids": docs.map(\.id), "status": status]))
            let done = Set((r?.list("done") ?? []).compactMap { $0 as? String })
            let failed = (r?.list("failed") ?? []).count
            items.removeAll { done.contains($0.id) && $0.status != status }
            multi = []
            counts = try? await API.shared.json("/api/docs/counts")
            let verb = ["archive": "archived", "later": "moved to Later", "inbox": "back in the Inbox", "seen": "marked seen",
                        "unseen": "marked unseen", "deleted": "deleted"][status] ?? status
            let action = ["archive": "Archive", "later": "Read Later", "inbox": "Back to Inbox", "seen": "Mark Seen", "unseen": "Mark Unseen", "deleted": "Delete"][status]
            say("\(done.count) \(verb)" + (failed > 0 ? "; \(failed) didn't move" : ""), undo: action) { [weak self] in
                guard let self else { return }
                for (st, ids) in back { _ = try? await API.shared.send("POST", "/api/docs/bulk", ["ids": ids, "status": st]) }
                self.say("Put back")
                await self.load()
            }
        } catch { self.error = error.localizedDescription }
    }

    /// Articles to the Kindle: one book of them, by way of the folder it shares (/api/kindle/send).
    func sendToKindle(_ ids: [String]) async {
        guard !ids.isEmpty else { return }
        do {
            let r = J(try await API.shared.send("POST", "/api/kindle/send", ["ids": ids]))
            let n = r?.i("count") ?? 0, skipped = (r?.list("skipped") ?? []).count
            say((n <= 1 ? "Sent to the Kindle" : "\(n) sent to the Kindle, as one book") + (skipped > 0 ? "; \(skipped) had no text to send" : ""))
        } catch { self.error = error.localizedDescription }
    }

    // MARK: acting on an item

    /// Done in the Library (archive), seen in the Feed.
    func done(_ item: Item) async {
        let to = item.whereIn == "feed" ? (item.status == "seen" ? "unseen" : "seen") : (item.status == "archive" ? "inbox" : "archive")
        await move(item, to: to, saying: ["seen": "Marked seen", "unseen": "Back in Unseen", "archive": "Archived", "inbox": "Back in the Inbox"][to] ?? "Done")
    }
    func later(_ item: Item) async {
        let to = item.status == "later" ? "inbox" : "later"
        await move(item, to: to, saying: to == "later" ? "Later" : "Back in the Inbox")
    }

    /// A status change with Undo putting it back, as every change on the page has.
    func move(_ item: Item, to status: String, saying: String) async {
        let was = item.status ?? (item.whereIn == "feed" ? "unseen" : "inbox")
        guard await setStatus(item, status) else { return }
        say(saying, undo: saying) { [weak self] in
            guard let self else { return }
            _ = try? await API.shared.send("POST", "/api/docs/\(API.enc(item.id))/status", ["status": was])
            await self.load()
            self.selection = item.id
        }
    }

    /// The Shortlist (a star), on or off (/api/docs/{id}/star).
    func star(_ item: Item) async {
        let on = !item.j.b("starred")
        do {
            try await API.shared.send("PUT", "/api/docs/\(API.enc(item.id))/star", ["starred": on])
            if let k = items.firstIndex(where: { $0.id == item.id }) {
                var raw = items[k].j.raw
                raw["starred"] = on
                items[k] = Item(J(raw))
            }
            counts = try? await API.shared.json("/api/docs/counts")
            say(on ? "On the Shortlist" : "Off the Shortlist")
        } catch { self.error = error.localizedDescription }
    }

    /// The next (1) or previous (-1) in the list, opened.
    func step(_ d: Int) {
        let list = shown
        guard !list.isEmpty else { return }
        let k = list.firstIndex { $0.id == selection } ?? (d > 0 ? -1 : list.count)
        let n = k + d
        guard list.indices.contains(n) else { say(d > 0 ? "That's the last one" : "That's the first one"); return }
        selection = list[n].id
    }

    /// Sync Now: Daf reads every source again (/api/sync).
    func syncNow() async {
        do {
            try await API.shared.send("POST", "/api/sync", [:])
            say("Synced")
            await load()
        } catch { self.error = error.localizedDescription }
    }

    @discardableResult
    func setStatus(_ item: Item, _ status: String) async -> Bool {
        do {
            try await API.shared.send("POST", "/api/docs/\(API.enc(item.id))/status", ["status": status])
            if let i = items.firstIndex(where: { $0.id == item.id }) {
                let next = items.indices.contains(i + 1) ? items[i + 1].id : (i > 0 ? items[i - 1].id : nil)
                items.remove(at: i)
                // as Mail does: the next one opens (Settings › Reading turns it off)
                if selection == item.id { selection = (UserDefaults.standard.object(forKey: "autoAdvance") as? Bool ?? true) ? next : nil }
            }
            counts = try? await API.shared.json("/api/docs/counts")
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    /// Where an item opens in a window of its own (a double-click, Open in a New Window).
    func route(for item: Item) -> String? {
        let id = API.enc(item.id)
        if item.isSeries || item.isPaper { return nil }
        if item.isBook { return item.j.b("readable") ? "#ebook/" + id : nil }
        switch item.kind {
        case "pdf": return "#pdf/" + id
        case "video", "podcast": return "#read/" + id
        case "manga": return "#mread/" + id
        default: return "#read/" + id
        }
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
