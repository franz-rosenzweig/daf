import AppKit
import SwiftUI
import UniformTypeIdentifiers

extension Notification.Name {
    /// A Calibre book changed in Daf (its Daf id, "cal:12" as the object): its page shows it again.
    static let dafBookEdited = Notification.Name("dafBookEdited")
}

/// Editing Calibre books (bookedit.js; calibrewrite.py does the writing, through Calibre itself): one
/// book's details, cover and files, or the same change to several at once. Only what changed is sent.
@MainActor
@Observable
final class BookEdit {
    struct Custom: Hashable {
        let key: String
        let label: String
        let dtype: String
        let multi: Bool
        let options: [String]
    }

    struct Values: Equatable {
        var title = "", authors = "", series = "", seriesIndex = "", publisher = "", published = "", languages = "", identifiers = "", comments = ""
        var tags: [String] = []
        var rating: Double?
        var custom: [String: String] = [:]
    }

    enum Step: Equatable { case form, finding, found, compare(Int) }

    /// The sheet open now, for the self-test.
    static weak var open: BookEdit?

    let ids: [Int]
    var one: Int? { ids.count == 1 ? ids[0] : nil }
    var bulk: Bool { ids.count > 1 }
    private(set) var d: J?
    private(set) var loadFailed: String?
    var v = Values()
    private(set) var orig = Values()
    private(set) var custom: [Custom] = []
    private(set) var choices: [String: [String]] = [:]
    private(set) var files: [J] = []
    private(set) var convertTo: [String] = []
    private(set) var hasCover = false
    /// Up by one with each new cover, so the picture is fetched again.
    private(set) var coverV = 0
    /// What's under way with the files ("Converting to EPUB…").
    var working: String?
    /// What went wrong, in Daf's words.
    var problem: String?
    private(set) var busy = false
    /// Words typed into a tag field and not yet a tag: they become tags at Save.
    var typed: [String: String] = [:]
    // several books
    var addTags: [String] = []
    var removeTags: [String] = []
    private(set) var theirTags: [String] = []
    var number = false
    var numberFrom = "1"
    var noRating = false
    /// "Last, First" names turned around (when Authors is left empty).
    var flip = false
    // Find details
    var step: Step = .form
    var findTitle = ""
    var findAuthor = ""
    private(set) var results: [J] = []
    private(set) var findErrors: [String] = []
    private(set) var findFailed: String?
    var take: Set<String> = []
    var takeCover = false
    @ObservationIgnored private var findSeq = 0

    init(_ ids: [Int]) { self.ids = ids }

    private func get(_ path: String) async throws -> J {
        guard let j = J(try JSONSerialization.jsonObject(with: try await API.shared.data(path))) else {
            throw APIError(status: 0, message: "Daf's answer wasn't what the app expected.")
        }
        return j
    }

    func load() async {
        Self.open = self
        guard let first = ids.first else { return }
        do {
            let j = try await get("/api/catalog/book/\(first)")
            custom = j.a("custom").map { Custom(key: $0.s("key") ?? "", label: $0.s("label") ?? "", dtype: $0.s("dtype") ?? "text", multi: $0.b("multi"), options: $0.strings("enum")) }
                .filter { $0.key != "#isbn" && !(bulk && $0.dtype == "comments") }
            choices = (j.o("choices")?.raw ?? [:]).compactMapValues { ($0 as? [Any])?.compactMap { $0 as? String } }
            files = j.a("files")
            convertTo = j.strings("convert_to")
            hasCover = j.b("cover")
            if bulk {
                let books = Catalog.shared.books.filter { ids.contains($0.i("calibre_id") ?? -1) }
                theirTags = Set(books.flatMap { $0.strings("tags") }).sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
                v = Values()
                for c in custom { v.custom[c.key] = "" }
            } else {
                v = Self.values(j, custom)
            }
            orig = v
            d = j
        } catch { loadFailed = error.localizedDescription }
    }

    static func num(_ d: Double) -> String { Catalog.num(NSNumber(value: d)) }

    static func values(_ j: J, _ custom: [Custom]) -> Values {
        var v = Values()
        v.title = j.s("title") ?? ""
        v.authors = j.strings("authors").joined(separator: " & ")
        v.series = j.s("series") ?? ""
        v.seriesIndex = j.s("series") == nil ? "" : j.d("series_index").map(num) ?? ""
        v.tags = j.strings("tags")
        v.rating = j.d("rating")
        v.publisher = j.s("publisher") ?? ""
        v.published = j.s("published") ?? ""
        v.languages = j.strings("languages").joined(separator: ", ")
        let ids = j.o("identifiers")?.raw ?? [:]
        v.identifiers = ids.keys.sorted().map { k in "\(k): " + ((ids[k] as? String) ?? Catalog.num(ids[k] as Any)) }.joined(separator: "\n")
        v.comments = j.s("comments") ?? ""
        for c in custom { v.custom[c.key] = text(j.raw[c.key], c) }
        return v
    }

    static func text(_ x: Any?, _ c: Custom) -> String {
        guard let x, !(x is NSNull) else { return "" }
        if let a = x as? [Any] { return a.map { ($0 as? String) ?? Catalog.num($0) }.joined(separator: ", ") }
        if let s = x as? String { return s }
        if let n = x as? NSNumber { return c.dtype == "bool" ? (n.boolValue ? "true" : "false") : Catalog.num(n) }
        return "\(x)"
    }

    static func split(_ s: String, _ by: String) -> [String] {
        s.components(separatedBy: by).map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    /// "type: value" a line → {type: value}.
    static func idents(_ s: String) -> [(String, String)] {
        s.split(separator: "\n").compactMap { l in
            guard let i = l.firstIndex(of: ":") else { return nil }
            let k = l[..<i].trimmingCharacters(in: .whitespaces), v = l[l.index(after: i)...].trimmingCharacters(in: .whitespaces)
            return k.isEmpty || v.isEmpty || k.contains(" ") ? nil : (k, v)
        }
    }

    static func add(_ text: String, to list: inout [String]) {
        for t in split(text, ",") where !list.contains(where: { $0.lowercased() == t.lowercased() }) { list.append(t) }
    }

    private func addTyped() {
        for (k, t) in typed where !t.trimmingCharacters(in: .whitespaces).isEmpty {
            switch k {
            case "add": Self.add(t, to: &addTags)
            case "remove": Self.add(t, to: &removeTags)
            default: Self.add(t, to: &v.tags)
            }
        }
        typed = [:]
    }

    var dirty: Bool {
        let typing = typed.values.contains { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        return v != orig || typing || !addTags.isEmpty || !removeTags.isEmpty || number || noRating || flip
    }

    /// A custom column's words → what Calibre takes.
    func value(_ s: String, _ c: Custom) -> Any {
        if s == "\u{0}" { return NSNull() }
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return NSNull() }
        switch c.dtype {
        case "bool": return t == "true"
        case "int", "float", "rating":
            guard let d = Double(t) else { return t }
            return c.dtype == "int" && d == d.rounded() ? Int(d) as Any : d as Any
        default: return c.multi ? Self.split(t, ",") : t
        }
    }

    /// One book: only what changed.
    func fields() -> [String: Any] {
        var f: [String: Any] = [:]
        let a = v, o = orig
        if a.title != o.title { f["title"] = a.title }
        if a.authors != o.authors { f["authors"] = Self.split(a.authors, "&") }
        if a.series != o.series { f["series"] = a.series }
        if a.seriesIndex != o.seriesIndex, let n = Double(a.seriesIndex.trimmingCharacters(in: .whitespaces)) { f["series_index"] = n }
        if a.tags != o.tags { f["tags"] = a.tags }
        if a.rating != o.rating { f["rating"] = a.rating.map { $0 as Any } ?? NSNull() }
        if a.publisher != o.publisher { f["publisher"] = a.publisher }
        if a.published != o.published { f["published"] = a.published.isEmpty ? NSNull() : a.published as Any }
        if a.languages != o.languages { f["languages"] = Self.split(a.languages, ",") }
        if a.identifiers != o.identifiers { f["identifiers"] = Dictionary(Self.idents(a.identifiers), uniquingKeysWith: { _, b in b }) }
        if a.comments != o.comments { f["comments"] = a.comments }
        for c in custom where a.custom[c.key] != o.custom[c.key] { f[c.key] = value(a.custom[c.key] ?? "", c) }
        return f
    }

    /// Several books: what was filled in; the rest stays as each book has it.
    func bulkFields() -> [String: Any] {
        var f: [String: Any] = [:]
        func t(_ s: String) -> String { s.trimmingCharacters(in: .whitespaces) }
        if !t(v.authors).isEmpty { f["authors"] = Self.split(v.authors, "&") } else if flip { f["authors_flip"] = true }
        if !t(v.series).isEmpty { f["series"] = t(v.series) }
        if !t(v.publisher).isEmpty { f["publisher"] = t(v.publisher) }
        if !t(v.published).isEmpty { f["published"] = v.published }
        if !t(v.languages).isEmpty { f["languages"] = Self.split(v.languages, ",") }
        if noRating { f["rating"] = NSNull() } else if let r = v.rating { f["rating"] = r }
        if number { f["series_number"] = Double(t(numberFrom)) ?? 1 }
        for c in custom { if let s = v.custom[c.key], !s.isEmpty { f[c.key] = value(s, c) } }
        return f
    }

    /// In the table's order, for numbering a series.
    var inOrder: [Int] {
        let order = Catalog.shared.books.compactMap { $0.i("calibre_id") }.filter { ids.contains($0) }
        return order.count == ids.count ? order : ids
    }

    func save() async -> Bool {
        addTyped()
        busy = true
        defer { busy = false }
        do {
            if let one {
                let f = fields()
                if f.isEmpty { return true }
                try await API.shared.send("PUT", "/api/catalog/book/\(one)", ["fields": f])
                AppModel.shared.say("Saved in Calibre")
            } else {
                let f = bulkFields()
                if f.isEmpty && addTags.isEmpty && removeTags.isEmpty { return true }
                try await API.shared.send("POST", "/api/catalog/bulk", ["ids": inOrder, "fields": f, "add_tags": addTags, "remove_tags": removeTags])
                AppModel.shared.say("\(ids.count) books changed in Calibre")
            }
            after()
            return true
        } catch {
            problem = error.localizedDescription
            return false
        }
    }

    /// After a change: All Books, the book's page and Books show it.
    private func after() {
        Catalog.shared.reload()
        for id in ids { NotificationCenter.default.post(name: .dafBookEdited, object: "cal:\(id)") }
        if AppModel.shared.place == .books { AppModel.shared.reload() }
    }

    // MARK: tidying: copies of one book merged, books removed, Calibre's trash

    /// "Remove “Title” from Calibre?" or "Remove 3 books from Calibre?"
    static func removeQuestion(_ books: [J]) -> String {
        "Remove " + (books.count == 1 ? "“\(books[0].s("title") ?? "the book")”" : "\(books.count) books") + " from Calibre?"
    }

    /// The highlights Daf has from them, if any.
    static func removeNote(_ books: [J]) -> String {
        let hl = books.reduce(0) { $0 + ($1.i("highlights") ?? 0) }
        guard hl > 0 else { return "" }
        return (books.count == 1 ? "It has " : "They have ") + plural(hl, "highlight") + " in Daf."
    }

    /// Into Calibre's trash (it keeps them for 14 days).
    static func remove(_ books: [J]) async throws {
        let ids = books.compactMap { $0.i("calibre_id") }
        guard !ids.isEmpty else { return }
        try await API.shared.send("POST", "/api/catalog/remove", ["ids": ids], slow: true)
        AppModel.shared.say(ids.count == 1 ? "Removed" : "\(ids.count) books removed")
        Catalog.shared.reload()
    }

    /// Several copies of one book into `keep`: its missing files, tags and fields from the others, theirs to the trash.
    static func merge(keep: Int, ids: [Int]) async throws {
        try await API.shared.send("POST", "/api/catalog/merge", ["keep": keep, "ids": ids], slow: true)
        AppModel.shared.say("Merged into one")
        Catalog.shared.reload()
        NotificationCenter.default.post(name: .dafBookEdited, object: "cal:\(keep)")
    }

    /// The copy to keep: the one with a cover, then the most files, then the first added.
    static func best(_ books: [J]) -> J? {
        books.min { a, b in
            if a.b("cover") != b.b("cover") { return a.b("cover") }
            let fa = a.strings("formats").count, fb = b.strings("formats").count
            if fa != fb { return fa > fb }
            return (a.s("added") ?? "") < (b.s("added") ?? "")
        }
    }

    static func trash(private priv: Bool) async throws -> [J] {
        guard let j = J(try JSONSerialization.jsonObject(with: try await API.shared.data("/api/catalog/trash" + (priv ? "?private=1" : "")))) else { return [] }
        return j.a("books")
    }

    static func putBack(_ id: Int) async throws {
        try await API.shared.send("POST", "/api/catalog/trash/restore", ["ids": [id]], slow: true)
        AppModel.shared.say("Back in Calibre")
        Catalog.shared.reload()
    }

    // MARK: the cover and the files

    func setCover(_ data: Data? = nil, url: String? = nil) async {
        guard let one else { return }
        do {
            if let url { try await API.shared.send("PUT", "/api/catalog/book/\(one)/cover", ["url": url]) }
            else if let data { _ = try await API.shared.upload("/api/catalog/book/\(one)/cover", data, type: "application/octet-stream", method: "PUT") }
            else { return }
            hasCover = true
            coverV += 1
            Self.freshCover("cal:\(one)")
            AppModel.shared.say("New cover")
            after()
        } catch { problem = error.localizedDescription }
    }

    /// The cover's plain address is kept on the Mac: forgotten now, so every picture of it is fetched again.
    static func freshCover(_ did: String) {
        let r = URLRequest(url: API.shared.url("/api/cover/" + API.enc(did)))
        URLCache.shared.removeCachedResponse(for: r)
        API.shared.session.configuration.urlCache?.removeCachedResponse(for: r)
    }

    private func refreshFiles() async {
        guard let one, let j = try? await get("/api/catalog/book/\(one)") else { return }
        files = j.a("files")
        Catalog.shared.reload()
    }

    func download(_ fmt: String, name: String) {
        guard let one else { return }
        let p = NSSavePanel()
        p.nameFieldStringValue = name + "." + fmt.lowercased()
        guard p.runModal() == .OK, let url = p.url else { return }
        Task {
            do { try await API.shared.data("/api/catalog/book/\(one)/files/" + API.enc(fmt)).write(to: url) }
            catch { problem = error.localizedDescription }
        }
    }

    func convert(_ from: String, to: String) async {
        guard let one else { return }
        working = "Converting to \(to)…"
        do {
            let job = J(try await API.shared.send("POST", "/api/catalog/book/\(one)/convert", ["from": from, "to": to]))?.s("job") ?? ""
            while true {
                try await Task.sleep(for: .seconds(2))
                let j = try await get("/api/catalog/jobs/" + job)
                if j.s("state") == "done" { AppModel.shared.say("Converted to \(to)"); break }
                if j.s("state") == "failed" { problem = j.s("error") ?? "Calibre couldn't convert it"; break }
            }
        } catch { problem = error.localizedDescription }
        working = nil
        await refreshFiles()
    }

    func remove(_ fmt: String) async {
        guard let one else { return }
        do {
            try await API.shared.send("DELETE", "/api/catalog/book/\(one)/files/" + API.enc(fmt), nil)
            AppModel.shared.say(fmt + " removed")
        } catch { problem = error.localizedDescription }
        await refreshFiles()
    }

    func addFile(_ url: URL) async {
        guard let one else { return }
        working = "Adding \(url.lastPathComponent)…"
        do {
            let data = try Data(contentsOf: url)
            let r = J(try await API.shared.upload("/api/catalog/book/\(one)/files?name=" + API.enc(url.lastPathComponent), data,
                                                  type: "application/octet-stream", timeout: 900))
            AppModel.shared.say((r?.s("format") ?? "The file") + " added")
        } catch { problem = error.localizedDescription }
        working = nil
        await refreshFiles()
    }

    static let bookTypes: [UTType] = ["epub", "kepub", "azw3", "azw", "mobi", "kfx", "pdf", "fb2", "cbz", "cbr", "cb7", "txt", "rtf", "docx",
                                      "html", "htmlz", "djvu", "lit", "odt"].compactMap { UTType(filenameExtension: $0) }

    // MARK: Find details: Hardcover and Calibre's own sources (calibrefind.py)

    /// The book's own title and author (and its identifiers) at first; `again`, what's typed at the top.
    func find(again: Bool = false) async {
        guard let one else { return }
        if !again {
            findTitle = v.title
            findAuthor = Self.split(v.authors, "&").first ?? ""
        }
        findSeq += 1
        let n = findSeq
        step = .finding
        results = []
        findErrors = []
        findFailed = nil
        do {
            let a = findAuthor.trimmingCharacters(in: .whitespaces)
            let body: [String: Any] = again ? ["title": findTitle.trimmingCharacters(in: .whitespaces), "authors": a.isEmpty ? [] : [a]] : [:]
            let job = J(try await API.shared.send("POST", "/api/catalog/book/\(one)/find", body))?.s("job") ?? ""
            while true {
                try await Task.sleep(for: .seconds(1.5))
                guard n == findSeq, step == .finding else { return }
                let j = try await get("/api/catalog/jobs/" + job)
                if j.s("state") == "running" { continue }
                if j.s("state") == "failed" { throw APIError(status: 0, message: j.s("error") ?? "Nothing came back") }
                results = j.a("results")
                findErrors = j.strings("errors")
                step = .found
                return
            }
        } catch {
            guard n == findSeq else { return }
            findFailed = error.localizedDescription
            step = .found
        }
    }

    static let compared = [("title", "Title"), ("authors", "Authors"), ("series", "Series"), ("tags", "Tags"), ("publisher", "Publisher"),
                           ("published", "Published"), ("languages", "Languages"), ("identifiers", "Identifiers"), ("comments", "Description"),
                           ("#pages", "Pages")]
    var comparedFields: [(String, String)] { Self.compared.filter { $0.0 != "#pages" || v.custom["#pages"] != nil } }

    func found(_ x: J, _ k: String) -> String {
        switch k {
        case "authors": return x.strings("authors").joined(separator: " & ")
        case "series":
            guard let s = x.s("series") else { return "" }
            return s + (x.d("series_index").map { " #" + Self.num($0) } ?? "")
        case "tags": return x.strings("tags").joined(separator: ", ")
        case "languages": return x.strings("languages").joined(separator: ", ")
        case "identifiers":
            let i = x.o("identifiers")?.raw ?? [:]
            return i.keys.sorted().map { k in "\(k): " + ((i[k] as? String) ?? Catalog.num(i[k] as Any)) }.joined(separator: "\n")
        case "#pages": return x.i("pages").map(String.init) ?? ""
        case "published": return String((x.s("published") ?? "").prefix(10))
        default: return x.s(k) ?? ""
        }
    }

    func now(_ k: String) -> String {
        switch k {
        case "title": return v.title
        case "authors": return v.authors
        case "series": return v.series.isEmpty ? "" : v.series + (v.seriesIndex.isEmpty ? "" : " #" + v.seriesIndex)
        case "tags": return v.tags.joined(separator: ", ")
        case "publisher": return v.publisher
        case "published": return v.published
        case "languages": return v.languages
        case "identifiers": return v.identifiers
        case "comments": return v.comments
        default: return v.custom[k] ?? ""
        }
    }

    func same(_ x: J, _ k: String) -> Bool {
        now(k).trimmingCharacters(in: .whitespacesAndNewlines) == found(x, k).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// One answer beside what the book has now: what it's missing is ticked to take.
    func compare(_ i: Int) {
        guard results.indices.contains(i) else { return }
        let x = results[i]
        take = []
        let kinds = Set(Self.idents(v.identifiers).map(\.0))
        for (k, _) in comparedFields where !found(x, k).isEmpty && !same(x, k) {
            let tick = k == "identifiers" ? (x.o("identifiers")?.raw.keys ?? [:].keys).contains { !kinds.contains($0) } : now(k).isEmpty
            if tick { take.insert(k) }
        }
        takeCover = !hasCover && x.s("cover") != nil
        step = .compare(i)
    }

    /// Use These: the ticked ones into the form (nothing's saved till Save); a ticked cover at once.
    func use(_ i: Int) async {
        guard results.indices.contains(i) else { return }
        let x = results[i]
        if take.contains("title"), let t = x.s("title") { v.title = t }
        if take.contains("authors") { v.authors = found(x, "authors") }
        if take.contains("series") { v.series = x.s("series") ?? ""; v.seriesIndex = x.d("series_index").map(Self.num) ?? "" }
        if take.contains("tags") { for t in x.strings("tags") where !v.tags.contains(t) { v.tags.append(t) } }
        if take.contains("publisher") { v.publisher = x.s("publisher") ?? "" }
        if take.contains("published") { v.published = found(x, "published") }
        if take.contains("languages") { v.languages = found(x, "languages") }
        if take.contains("comments") { v.comments = x.s("comments") ?? "" }
        if take.contains("#pages") { v.custom["#pages"] = found(x, "#pages") }
        if take.contains("identifiers") {
            var lines = Self.idents(v.identifiers)
            let have = Set(lines.map(\.0))
            let got = x.o("identifiers")?.raw ?? [:]
            for k in got.keys.sorted() where !have.contains(k) { lines.append((k, (got[k] as? String) ?? Catalog.num(got[k] as Any))) }
            v.identifiers = lines.map { "\($0.0): \($0.1)" }.joined(separator: "\n")
        }
        step = .form
        if takeCover, let c = x.s("cover") { await setCover(url: c) }
    }
}

// MARK: the sheet

struct BookEditSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var e: BookEdit
    @State private var leaving = false
    @State private var linking = false
    @State private var link = ""
    @State private var removing: String?
    @State private var removingBook = false

    init(ids: [Int]) { _e = State(initialValue: BookEdit(ids)) }

    var body: some View {
        VStack(spacing: 0) {
            header.padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            Group {
                if let f = e.loadFailed {
                    ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(f))
                } else if e.d == nil {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    switch e.step {
                    case .form: if e.bulk { BulkForm(e: e) } else { oneForm }
                    case .finding, .found: FindList(e: e)
                    case .compare(let i): CompareView(e: e, i: i)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: e.bulk ? 640 : 920, height: 700)
        .task { await e.load() }
        .interactiveDismissDisabled()
        .confirmationDialog("Leave without saving?", isPresented: $leaving) {
            Button("Leave", role: .destructive) { dismiss() }
        }
        .alert("Daf", isPresented: Binding(get: { e.problem != nil }, set: { if !$0 { e.problem = nil } })) {
            Button("OK") { e.problem = nil }
        } message: { Text(e.problem ?? "") }
        .alert("Cover from a Link", isPresented: $linking) {
            TextField("Address", text: $link)
            Button("Use It") {
                let u = link.trimmingCharacters(in: .whitespaces)
                link = ""
                if !u.isEmpty { Task { await e.setCover(url: u) } }
            }
            Button("Cancel", role: .cancel) { link = "" }
        }
        .confirmationDialog(BookEdit.removeQuestion(e.d.map { [$0] } ?? []), isPresented: $removingBook) {
            Button("Remove", role: .destructive) {
                guard let d = e.d else { return }
                Task {
                    do {
                        try await BookEdit.remove([d])
                        dismiss()
                        if AppModel.shared.place == .books { AppModel.shared.place = .catalog }
                    } catch { e.problem = error.localizedDescription }
                }
            }
        } message: { Text(BookEdit.removeNote(e.d.map { [$0] } ?? [])) }
        .confirmationDialog("Remove the \(removing ?? "") file from Calibre?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } })) {
            Button("Remove", role: .destructive) {
                if let f = removing { Task { await e.remove(f) } }
                removing = nil
            }
        }
    }

    @ViewBuilder private var header: some View {
        HStack(spacing: 10) {
            switch e.step {
            case .form:
                Text(e.bulk ? "\(e.ids.count) Books" : e.v.title.isEmpty ? "Edit Details" : e.v.title).font(.headline).lineLimit(1)
                Spacer()
                if !e.bulk { Button("Find Details…") { Task { await e.find() } }.disabled(e.d == nil) }
                Button("Cancel") { if e.dirty { leaving = true } else { dismiss() } }
                    .keyboardShortcut(.cancelAction)
                Button(e.busy ? "Saving…" : "Save") { Task { if await e.save() { dismiss() } } }
                    .keyboardShortcut(.return, modifiers: .command)
                    .buttonStyle(.borderedProminent)
                    .disabled(e.busy || e.d == nil)
            case .finding, .found:
                Text("Find Details").font(.headline)
                Spacer()
                Button("Back") { e.step = .form }.keyboardShortcut(.cancelAction)
            case .compare(let i):
                Text(e.results.indices.contains(i) ? e.results[i].s("source") ?? "Found" : "Found").font(.headline)
                Spacer()
                Button("Back") { e.step = .found }.keyboardShortcut(.cancelAction)
                Button("Use These") { Task { await e.use(i) } }
                    .keyboardShortcut(.return, modifiers: .command)
                    .buttonStyle(.borderedProminent)
            }
        }
    }

    // MARK: one book

    private var oneForm: some View {
        HStack(alignment: .top, spacing: 0) {
            ScrollView { side.padding(16) }.frame(width: 230)
            Divider()
            ScrollView {
            Form {
                Section {
                    TextField("Title", text: $e.v.title)
                    SuggestField(label: "Authors", text: $e.v.authors, choices: e.choices["authors"] ?? [], sep: "&")
                    LabeledContent("Series") {
                        HStack {
                            SuggestField(label: "Series", text: $e.v.series, choices: e.choices["series"] ?? []).labelsHidden()
                            TextField("Number in the Series", text: $e.v.seriesIndex).labelsHidden().frame(width: 56).textFieldStyle(.roundedBorder)
                        }
                    }
                    LabeledContent("Tags") { TagChips(list: $e.v.tags, typed: typed("tags"), choices: e.choices["tags"] ?? []) }
                    LabeledContent("Rating") { StarsField(value: $e.v.rating) }
                    SuggestField(label: "Publisher", text: $e.v.publisher, choices: e.choices["publisher"] ?? [])
                    LabeledContent("Published") { DayField(text: $e.v.published) }
                    SuggestField(label: "Languages", text: $e.v.languages, choices: e.choices["languages"] ?? [], sep: ",")
                }
                Section {
                    LabeledContent("Identifiers") {
                        TextBox(text: $e.v.identifiers, height: 70).font(.system(.callout, design: .monospaced))
                    }
                    LabeledContent("Description") { TextBox(text: $e.v.comments, height: 170) }
                }
                if !e.custom.isEmpty {
                    Section {
                        ForEach(e.custom, id: \.key) { c in
                            CustomField(c: c, text: customText(c.key), choices: e.choices[c.key] ?? [], bulk: false)
                        }
                    }
                }
            }
            .formStyle(.columns)
            .padding(22)
            }
        }
    }

    private var side: some View {
        VStack(alignment: .leading, spacing: 10) {
            BookCoverImage(did: "cal:\(e.one ?? 0)", has: e.hasCover, v: e.coverV, title: e.v.title).frame(width: 150, height: 225)
            Button("Change Cover…") { chooseCover() }
            Button("Cover from a Link…") { linking = true }
            Text("Files").font(.headline).padding(.top, 10)
            if e.files.isEmpty { Text("No file").foregroundStyle(.secondary) }
            ForEach(Array(e.files.enumerated()), id: \.offset) { _, f in
                let fmt = f.s("format") ?? ""
                HStack(spacing: 6) {
                    Text(fmt).bold()
                    Text(Self.size(f.d("size"))).font(.caption).foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    if f.b("exists") {
                        Button { e.download(fmt, name: f.s("name") ?? e.v.title) } label: { Image(systemName: "arrow.down.circle") }
                            .buttonStyle(.borderless).help("Download")
                    }
                    Menu {
                        ForEach(e.convertTo.filter { $0 != fmt }, id: \.self) { to in
                            Button("Convert to \(to)") { Task { await e.convert(fmt, to: to) } }
                        }
                        Divider()
                        Button("Remove the \(fmt) File…", role: .destructive) { removing = fmt }
                    } label: { Image(systemName: "ellipsis.circle") }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .help("More for \(fmt)")
                }
            }
            if let w = e.working {
                HStack(spacing: 6) { ProgressView().controlSize(.small); Text(w).font(.caption).foregroundStyle(.secondary) }
            }
            Button("Add a File…") { chooseFile() }.disabled(e.working != nil)
            Button("Remove from Calibre…", role: .destructive) { removingBook = true }
                .padding(.top, 18)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    static func size(_ n: Double?) -> String {
        guard let n else { return "" }
        return n >= 1_048_576 ? String(format: "%.1f MB", n / 1_048_576) : "\(max(1, Int((n / 1024).rounded()))) KB"
    }

    private func typed(_ k: String) -> Binding<String> { Binding(get: { e.typed[k] ?? "" }, set: { e.typed[k] = $0 }) }
    private func customText(_ k: String) -> Binding<String> { Binding(get: { e.v.custom[k] ?? "" }, set: { e.v.custom[k] = $0 }) }

    private func chooseCover() {
        let p = NSOpenPanel()
        p.allowedContentTypes = [.jpeg, .png, .webP, .gif]
        guard p.runModal() == .OK, let url = p.url, let data = try? Data(contentsOf: url) else { return }
        Task { await e.setCover(data) }
    }

    private func chooseFile() {
        let p = NSOpenPanel()
        p.allowedContentTypes = BookEdit.bookTypes
        guard p.runModal() == .OK, let url = p.url else { return }
        Task { await e.addFile(url) }
    }
}

/// Several books: what's filled in goes to all of them; what's left empty stays as each one has it.
struct BulkForm: View {
    @Bindable var e: BookEdit

    var body: some View {
        ScrollView {
        Form {
            Section {
                SuggestField(label: "Authors", text: $e.v.authors, choices: e.choices["authors"] ?? [], sep: "&", prompt: "No Change")
                LabeledContent("") {
                    Toggle("Turn “Last, First” names around", isOn: $e.flip).disabled(!e.v.authors.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                SuggestField(label: "Series", text: $e.v.series, choices: e.choices["series"] ?? [], prompt: "No Change")
                LabeledContent("") {
                    HStack(spacing: 6) {
                        Toggle("Number them from", isOn: $e.number)
                        TextField("From", text: $e.numberFrom).labelsHidden().frame(width: 50).textFieldStyle(.roundedBorder).disabled(!e.number)
                        Text("in the table's order")
                    }
                }
                LabeledContent("Add Tags") { TagChips(list: $e.addTags, typed: typed("add"), choices: e.choices["tags"] ?? []) }
                LabeledContent("Remove Tags") { TagChips(list: $e.removeTags, typed: typed("remove"), choices: e.theirTags) }
                LabeledContent("Rating") {
                    HStack(spacing: 14) {
                        StarsField(value: $e.v.rating)
                        Toggle("No Rating", isOn: $e.noRating)
                    }
                }
                SuggestField(label: "Publisher", text: $e.v.publisher, choices: e.choices["publisher"] ?? [], prompt: "No Change")
                LabeledContent("Published") { DayField(text: $e.v.published) }
                SuggestField(label: "Languages", text: $e.v.languages, choices: e.choices["languages"] ?? [], sep: ",", prompt: "No Change")
            }
            if !e.custom.isEmpty {
                Section {
                    ForEach(e.custom, id: \.key) { c in
                        CustomField(c: c, text: Binding(get: { e.v.custom[c.key] ?? "" }, set: { e.v.custom[c.key] = $0 }), choices: e.choices[c.key] ?? [], bulk: true)
                    }
                }
            }
        }
        .formStyle(.columns)
        .padding(22)
        }
        .onChange(of: e.v.rating) { _, r in if r != nil { e.noRating = false } }
        .onChange(of: e.noRating) { _, on in if on { e.v.rating = nil } }
    }

    private func typed(_ k: String) -> Binding<String> { Binding(get: { e.typed[k] ?? "" }, set: { e.typed[k] = $0 }) }
}

/// Find details: the title and author to look for, and what came back.
struct FindList: View {
    @Bindable var e: BookEdit

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                TextField("Title", text: $e.findTitle)
                TextField("Author", text: $e.findAuthor).frame(width: 220)
                Button("Search") { Task { await e.find(again: true) } }
            }
            .textFieldStyle(.roundedBorder)
            .onSubmit { Task { await e.find(again: true) } }
            .padding(12)
            Divider()
            if e.step == .finding {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let f = e.findFailed {
                ContentUnavailableView("Nothing came back", systemImage: "magnifyingglass", description: Text(f))
            } else if e.results.isEmpty {
                ContentUnavailableView("Nothing found", systemImage: "magnifyingglass")
            } else {
                List {
                    ForEach(Array(e.results.enumerated()), id: \.offset) { i, x in
                        Button { e.compare(i) } label: { row(x) }.buttonStyle(.plain)
                    }
                    ForEach(e.findErrors, id: \.self) { Text($0).font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
    }

    private func row(_ x: J) -> some View {
        let year = String((x.s("published") ?? "").prefix(4))
        let series = x.s("series").map { $0 + (x.d("series_index").map { " #" + BookEdit.num($0) } ?? "") }
        let meta = [year, x.s("publisher"), series, x.i("pages").map { "\($0) pages" }].compactMap { $0 }.filter { !$0.isEmpty }
        return HStack(spacing: 12) {
            FoundCover(url: x.s("cover")).frame(width: 44, height: 66)
            VStack(alignment: .leading, spacing: 2) {
                Text(x.s("title") ?? "").bold().lineLimit(2)
                Text(x.strings("authors").joined(separator: ", ")).lineLimit(1)
                Text(meta.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            Text(x.s("source") ?? "").font(.caption).padding(.horizontal, 7).padding(.vertical, 2).background(Capsule().fill(.quaternary))
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }
}

/// One answer beside what the book has now, a field a row, each with a box to take it.
struct CompareView: View {
    @Bindable var e: BookEdit
    let i: Int

    var body: some View {
        let x = e.results.indices.contains(i) ? e.results[i] : J([:])
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let c = x.s("cover") {
                    HStack(alignment: .top, spacing: 28) {
                        VStack(spacing: 6) {
                            BookCoverImage(did: "cal:\(e.one ?? 0)", has: e.hasCover, v: e.coverV, title: e.v.title).frame(width: 100, height: 150)
                            Text("Now").font(.caption).foregroundStyle(.secondary)
                        }
                        VStack(spacing: 6) {
                            FoundCover(url: c).frame(width: 100, height: 150)
                            Toggle("Use This Cover", isOn: $e.takeCover)
                        }
                    }
                }
                Grid(alignment: .topLeading, horizontalSpacing: 14, verticalSpacing: 10) {
                    GridRow {
                        Color.clear.frame(width: 1, height: 1)
                        Color.clear.frame(width: 1, height: 1)
                        Text("Now").font(.caption.bold()).foregroundStyle(.secondary)
                        Text("Found").font(.caption.bold()).foregroundStyle(.secondary)
                    }
                    ForEach(e.comparedFields, id: \.0) { k, label in
                        let got = e.found(x, k), now = e.now(k), same = e.same(x, k)
                        if !got.isEmpty {
                            GridRow {
                                Toggle(label, isOn: Binding(get: { e.take.contains(k) }, set: { if $0 { e.take.insert(k) } else { e.take.remove(k) } }))
                                    .labelsHidden().disabled(same)
                                Text(label).bold()
                                Text(now.isEmpty ? "—" : now).foregroundStyle(.secondary).lineLimit(8).frame(maxWidth: .infinity, alignment: .leading)
                                Text(got).lineLimit(8).frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .opacity(same ? 0.5 : 1)
                        }
                    }
                }
            }
            .padding(20)
        }
    }
}

// MARK: the fields

/// A text field that suggests what Calibre already has (an author, a series, a publisher); with `sep`,
/// a list, and the suggestions are for its last part.
struct SuggestField: View {
    let label: String
    @Binding var text: String
    let choices: [String]
    var sep: String?
    var prompt: String?

    var body: some View {
        TextField(label, text: $text, prompt: prompt.map { Text($0) })
            .textInputSuggestions {
                ForEach(matches, id: \.self) { m in Text(m).textInputCompletion(completion(m)) }
            }
    }

    private var parts: (head: String, last: String) {
        guard let sep, let r = text.range(of: sep, options: .backwards) else { return ("", text) }
        return (String(text[..<r.upperBound]), String(text[r.upperBound...]))
    }

    private var matches: [String] {
        let w = parts.last.trimmingCharacters(in: .whitespaces).lowercased()
        guard !w.isEmpty else { return [] }
        let starts = choices.filter { $0.lowercased().hasPrefix(w) }
        let inside = choices.filter { !$0.lowercased().hasPrefix(w) && $0.lowercased().contains(w) }
        return Array((starts + inside).filter { $0.lowercased() != w }.prefix(8))
    }

    private func completion(_ m: String) -> String {
        let head = parts.head.trimmingCharacters(in: .whitespaces)
        return head.isEmpty ? m : head + " " + m
    }
}

/// Tags as chips: × takes one away; Return or a comma makes what's typed a tag.
struct TagChips: View {
    @Binding var list: [String]
    @Binding var typed: String
    let choices: [String]

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(list, id: \.self) { t in
                HStack(spacing: 4) {
                    Text(t)
                    Button { list.removeAll { $0 == t } } label: { Image(systemName: "xmark").font(.caption2.weight(.bold)) }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Remove \(t)")
                }
                .font(.callout)
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(Capsule().fill(Color.secondary.opacity(0.15)))
            }
            SuggestField(label: "Add", text: $typed, choices: choices.filter { !list.contains($0) })
                .labelsHidden()
                .textFieldStyle(.roundedBorder)
                .frame(width: 160)
                .onSubmit { commit() }
                .onChange(of: typed) { _, t in if t.contains(",") { commit() } }
        }
    }

    private func commit() {
        BookEdit.add(typed, to: &list)
        typed = ""
    }
}

/// Stars, by halves; clicking the one that's on clears it.
struct StarsField: View {
    @Binding var value: Double?

    var body: some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { n in
                let v = value ?? 0, d = Double(n)
                Button { value = value == d ? nil : d } label: {
                    Image(systemName: v >= d ? "star.fill" : v >= d - 0.5 ? "star.leadinghalf.filled" : "star")
                        .foregroundStyle(v >= d - 0.5 ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(n == 1 ? "1 star" : "\(n) stars")
            }
        }
    }
}

/// A day as Calibre keeps it ("YYYY-MM-DD"), or none.
struct DayField: View {
    @Binding var text: String

    static let f: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    var body: some View {
        if text.isEmpty {
            Button("Add a Date") { text = Self.f.string(from: Date()) }
        } else if let d = Self.f.date(from: text) {
            HStack(spacing: 6) {
                DatePicker("Date", selection: Binding(get: { d }, set: { text = Self.f.string(from: $0) }), displayedComponents: .date)
                    .labelsHidden()
                    .datePickerStyle(.field)
                    .environment(\.timeZone, TimeZone(identifier: "UTC")!)
                Button { text = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
                    .accessibilityLabel("No Date")
            }
        } else {
            TextField("Date", text: $text).labelsHidden()
        }
    }
}

/// A Calibre column of my own, by its kind.
struct CustomField: View {
    let c: BookEdit.Custom
    @Binding var text: String
    let choices: [String]
    let bulk: Bool

    var body: some View {
        switch c.dtype {
        case "enumeration":
            Picker(c.label, selection: $text) {
                if bulk { Text("No Change").tag(""); Text("None").tag("\u{0}") } else { Text("None").tag("") }
                ForEach(c.options, id: \.self) { Text($0).tag($0) }
            }
        case "bool":
            Picker(c.label, selection: $text) {
                Text(bulk ? "No Change" : "None").tag("")
                Text("Yes").tag("true")
                Text("No").tag("false")
            }
        case "datetime":
            LabeledContent(c.label) { DayField(text: $text) }
        case "rating":
            LabeledContent(c.label) { StarsField(value: Binding(get: { Double(text) }, set: { text = $0.map(BookEdit.num) ?? "" })) }
        case "comments":
            LabeledContent(c.label) { TextBox(text: $text, height: 70) }
        case "int", "float":
            TextField(c.label, text: $text, prompt: bulk ? Text("No Change") : nil)
        default:
            SuggestField(label: c.label, text: $text, choices: choices, sep: c.multi ? "," : nil, prompt: bulk ? "No Change" : nil)
        }
    }
}

/// The book's cover from Daf, fetched again when `v` changes.
struct BookCoverImage: View {
    let did: String
    let has: Bool
    let v: Int
    let title: String

    var body: some View {
        Group {
            if has {
                AsyncImage(url: API.shared.url("/api/cover/" + API.enc(did) + "?v=\(v)")) { p in
                    if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { RoundedRectangle(cornerRadius: 4).fill(.quaternary) }
                }
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 4).fill(.quaternary)
                    Text(title).font(.system(.callout, design: .serif)).multilineTextAlignment(.center).padding(10).foregroundStyle(.secondary)
                }
            }
        }
        .shadow(radius: 3, y: 1)
    }
}

/// A cover Find details found, through Daf (the Mac never asks Amazon or Google itself).
struct FoundCover: View {
    let url: String?

    var body: some View {
        if let url {
            AsyncImage(url: API.shared.url("/api/catalog/coverproxy?u=" + API.enc(url))) { p in
                if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { RoundedRectangle(cornerRadius: 3).fill(.quaternary) }
            }
        } else {
            RoundedRectangle(cornerRadius: 3).fill(.quaternary)
        }
    }
}

/// Merge: which of the chosen copies stays; the others' files, tags and missing details go into it.
struct MergeSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var model
    let ids: [Int]
    @State private var keep: Int?
    @State private var busy = false

    /// The chosen books as All Books has them.
    var books: [J] { Catalog.shared.books.filter { ids.contains($0.i("calibre_id") ?? -1) } }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text("Merge \(ids.count) Books").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button(busy ? "Merging…" : "Merge") {
                    guard let keep else { return }
                    busy = true
                    Task {
                        do { try await BookEdit.merge(keep: keep, ids: ids); Catalog.shared.chosen = []; dismiss() }
                        catch { model.error = error.localizedDescription }
                        busy = false
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(keep == nil || busy)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            List {
                Picker("Keep", selection: $keep) {
                    ForEach(books, id: \.self) { b in row(b).tag(b.i("calibre_id")) }
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()
            }
        }
        .frame(width: 560, height: min(620, CGFloat(170 + 96 * ids.count)))
        .onAppear { if keep == nil { keep = BookEdit.best(books)?.i("calibre_id") } }
    }

    private func row(_ b: J) -> some View {
        let meta = [b.strings("formats").isEmpty ? "No file" : b.strings("formats").joined(separator: ", "), b.s("added") ?? "",
                    (b.i("highlights") ?? 0) > 0 ? plural(b.i("highlights") ?? 0, "highlight") : ""].filter { !$0.isEmpty }
        return HStack(spacing: 12) {
            if b.b("cover"), let id = b.s("id") {
                AsyncImage(url: API.shared.url("/api/cover/" + API.enc(id) + "?v=" + (b.s("cover_v") ?? "0"))) { p in
                    if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { RoundedRectangle(cornerRadius: 3).fill(.quaternary) }
                }
                .frame(width: 48, height: 72)
            } else {
                RoundedRectangle(cornerRadius: 3).fill(.quaternary).frame(width: 48, height: 72)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(b.s("title") ?? "").bold().lineLimit(2)
                Text(b.strings("authors").joined(separator: " & ")).lineLimit(1)
                Text(meta.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 6)
    }
}

/// Calibre's trash: the books removed lately (Calibre keeps them 14 days), each with Put Back.
struct TrashSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var model
    @State private var books: [J]?
    @State private var failed: String?
    @State private var putting: Set<Int> = []

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Calibre's Trash").font(.headline)
                Spacer()
                Button("Close") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            Group {
                if let failed { ContentUnavailableView("It didn't open", systemImage: "exclamationmark.triangle", description: Text(failed)) }
                else if let books, books.isEmpty { ContentUnavailableView("Nothing in the Trash", systemImage: "trash") }
                else if let books {
                    List(books, id: \.self) { b in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(b.s("title") ?? "").bold()
                                Text([b.s("author"), b.d("removed").map { Date(timeIntervalSince1970: $0).formatted(date: .abbreviated, time: .omitted) }]
                                        .compactMap { $0 }.joined(separator: " · "))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Put Back") {
                                guard let id = b.i("id") else { return }
                                putting.insert(id)
                                Task {
                                    do { try await BookEdit.putBack(id); self.books?.removeAll { $0.i("id") == id } }
                                    catch { model.error = error.localizedDescription }
                                    putting.remove(id)
                                }
                            }
                            .disabled(putting.contains(b.i("id") ?? -1))
                        }
                        .padding(.vertical, 3)
                    }
                } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: 520, height: 480)
        .task {
            do { books = try await BookEdit.trash(private: Catalog.shared.priv) } catch { failed = error.localizedDescription }
        }
    }
}

/// A few lines of text with a field's edge, as Calibre's description box.
struct TextBox: View {
    @Binding var text: String
    let height: CGFloat

    var body: some View {
        TextEditor(text: $text)
            .multilineTextAlignment(.leading)
            .scrollContentBackground(.hidden)
            .padding(4)
            .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 5))
            .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color(nsColor: .separatorColor)))
            .frame(height: height)
    }
}
