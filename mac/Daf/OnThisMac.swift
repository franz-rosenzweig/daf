import Foundation

/// What's kept on this Mac by hand, beside what the plan names, for `dafShell.offline` (docs/SHELL.md
/// §2, the same calls and answers as Android's): articles from the reader's ⋯ menu, books from the
/// book's menu, manga volumes from the series page's download buttons. The files sit in LocalCopy's
/// data, by the addresses the readers ask for, so the copy answers them with Daf out of reach;
/// kept.json says what's what.
@MainActor
enum OnThisMac {
    struct State: Codable {
        var docs: [String] = []                // articles kept by hand
        var planDocs: [String] = []            // the articles the plan named last
        var planBooks: [String] = []           // the books it named (being read)
        var books: [String: Book] = [:]
        var manga: [String: Manga] = [:]
    }
    struct Book: Codable {
        var title = "", isPrivate = false, format = "", size = 0, kept = false
    }
    struct Manga: Codable {
        var title = "", series = "", seriesId = "", state = "", error: String?
        var done = 0, total = 0, bytes = 0, size = 1800
    }

    private static var file: URL { LocalCopy.root.appendingPathComponent("kept.json") }
    static var state: State = (try? JSONDecoder().decode(State.self, from: Data(contentsOf: file))) ?? State()

    static func save() {
        if let d = try? JSONEncoder().encode(state) { try? LocalCopy.write(d, to: file) }
    }

    /// An id as the page puts it in a path (encodeURIComponent).
    static func enc(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_.!~*'()"))) ?? id
    }

    private static func exists(_ key: String) -> Bool { FileManager.default.fileExists(atPath: LocalCopy.dataFile(key).path) }

    private static func size(_ key: String) -> Int {
        ((try? FileManager.default.attributesOfItem(atPath: LocalCopy.dataFile(key).path))?[.size] as? NSNumber)?.intValue ?? 0
    }

    // MARK: the page's calls

    static func answer(_ args: [String: Any]) async throws -> Any {
        let op = (args["op"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "list"
        let id = args["id"] as? String ?? "", on = (args["on"] as? Bool) ?? true
        switch op {
        case "has":
            return ["has": exists(bookPath(id) + "/file")]
        case "keep":
            guard !id.isEmpty else { throw ShellError("Which book?") }
            try await keepBook(id, on)
        case "doc":
            guard !id.isEmpty else { throw ShellError("Which article?") }
            try await keepDoc(id, on)
        case "manga":
            guard !id.isEmpty else { throw ShellError("Which volume?") }
            if on { keepManga(id, size: max(600, min(2400, (args["size"] as? NSNumber)?.intValue ?? 1800))) } else { removeManga(id) }
        case "sync":
            let said = await LocalCopy.refreshNow()
            var l = list()
            l["said"] = said
            return l
        default:
            break
        }
        return list()
    }

    /// What's on this Mac: {app, data, docs: [{id, pinned}], books: [{id, title, size, kept}],
    /// manga: [{id, title, series, state, done, total, bytes, error}], bytes, synced}.
    static func list() -> [String: Any] {
        let at = (UserDefaults.standard.object(forKey: "localCopy.at") as? Date).map { Int($0.timeIntervalSince1970 * 1000) } ?? 0
        var bytes = 0
        let books: [[String: Any]] = state.books.compactMap { id, b in
            guard exists(bookPath(id) + "/file") else { return nil }
            bytes += b.size
            return ["id": id, "title": b.isPrivate ? "Private reading" : b.title, "size": b.size, "kept": b.kept]
        }
        let manga: [[String: Any]] = state.manga.map { id, m in
            bytes += m.bytes
            var x: [String: Any] = ["id": id, "title": m.title, "series": m.series, "state": m.state, "done": m.done, "total": m.total, "bytes": m.bytes]
            if let e = m.error { x["error"] = e }
            return x
        }
        let docs: [[String: Any]] = state.docs.map { ["id": $0, "pinned": true] }
            + state.planDocs.filter { !state.docs.contains($0) }.map { ["id": $0, "pinned": false] }
        return ["app": ["ready": LocalCopy.ready, "version": UserDefaults.standard.string(forKey: "localCopy.version") ?? "", "at": at],
                "data": at, "docs": docs, "books": books, "manga": manga, "bytes": bytes, "reading": true, "wifi": false, "synced": at]
    }

    // MARK: articles

    static func keepDoc(_ id: String, _ on: Bool) async throws {
        let path = LocalCopy.docPath(id)
        if on {
            do { try await LocalCopy.keepDoc(path, pictures: true) } catch is LocalCopy.Gone {
                throw ShellError("Daf doesn't have this article any more.")
            } catch {
                throw ShellError("Daf didn't answer: \(error.localizedDescription)")
            }
            if !state.docs.contains(id) { state.docs.append(id) }
        } else {
            state.docs.removeAll { $0 == id }
            if !state.planDocs.contains(id) { LocalCopy.remove(path); LocalCopy.remove(path + "/pdf") }   // nothing else wants it: now
        }
        save()
    }

    // MARK: books

    static func bookPath(_ id: String) -> String { "/api/ebooks/" + enc(id) }

    static func bookKeys(_ id: String) -> [String] {
        [bookPath(id), bookPath(id) + "/file", "/api/cover/" + enc(id)]
    }

    /// The plan's books and the ones kept by hand.
    static func booksToKeep(_ plan: [String]) -> [String] {
        var out = plan
        for (id, b) in state.books where b.kept && !out.contains(id) { out.append(id) }
        return out
    }

    /// A book's details and its file (again only when its format or size changed) and its cover.
    static func fetchBook(_ id: String) async throws {
        let path = bookPath(id)
        let info = try await LocalCopy.fetch(Server.url(path), auth: true)
        LocalCopy.store(info.data, type: info.type, key: path)
        let d = (try? JSONSerialization.jsonObject(with: info.data) as? [String: Any]) ?? [:]
        var b = state.books[id] ?? Book()
        let format = d["format"] as? String ?? "", want = (d["size"] as? NSNumber)?.intValue ?? -1
        if !(exists(path + "/file") && format == b.format && size(path + "/file") == want) {
            let file = try await LocalCopy.fetch(Server.url(path + "/file"), auth: true)
            LocalCopy.store(file.data, type: file.type, key: path + "/file")
        }
        if !exists("/api/cover/" + enc(id)) { await LocalCopy.keep("/api/cover/" + enc(id), Server.url("/api/cover/" + enc(id)), limit: 4 << 20) }
        b.title = d["title"] as? String ?? b.title
        b.isPrivate = d["private"] as? Bool ?? false
        b.format = format
        b.size = size(path + "/file")
        state.books[id] = b
    }

    static func keepBook(_ id: String, _ on: Bool) async throws {
        if on {
            do { try await fetchBook(id) } catch is LocalCopy.Gone {
                throw ShellError("Daf has no file for this book.")
            } catch {
                throw ShellError("Daf didn't answer: \(error.localizedDescription)")
            }
            state.books[id]?.kept = true
        } else {
            state.books[id]?.kept = false
            if !state.planBooks.contains(id) {                          // not being read either: it goes now
                for k in bookKeys(id) { LocalCopy.remove(k) }
                state.books[id] = nil
            }
        }
        save()
    }

    /// Books whose file went (let go after three weeks) leave the list; a kept one stays, to come again.
    static func forgetMissing() {
        for (id, b) in state.books where !b.kept && !exists(bookPath(id) + "/file") { state.books[id] = nil }
    }

    // MARK: manga

    private static var downloading: Task<Void, Never>?

    static func mangaPath(_ id: String) -> String { "/api/manga/books/" + enc(id) }

    /// The keys a downloaded volume keeps: itself, its pages, its series, the reader's settings.
    static func mangaKeys() -> [String] {
        var out: [String] = []
        for (id, m) in state.manga {
            out.append(mangaPath(id))
            if m.total > 0 { out += (1...m.total).map { mangaPath(id) + "/pages/\($0)" } }
            if !m.seriesId.isEmpty { out.append("/api/manga/series/" + enc(m.seriesId)) }
        }
        if !out.isEmpty { out.append("/api/manga/prefs") }
        return out
    }

    /// Downloads a volume's pages at the size this screen's reader asks for, one volume at a time;
    /// what's already here stays, so pressing again carries on.
    static func keepManga(_ id: String, size: Int) {
        var m = state.manga[id] ?? Manga()
        m.state = "waiting"
        m.size = size
        m.error = nil
        state.manga[id] = m
        save()
        let before = downloading
        downloading = Task { @MainActor in
            await before?.value
            await download(id)
        }
    }

    private static func update(_ id: String, _ change: (inout Manga) -> Void) {
        guard var m = state.manga[id] else { return }
        change(&m)
        state.manga[id] = m
        save()
    }

    private static func download(_ id: String) async {
        guard let size = state.manga[id]?.size else { return }            // removed while it waited
        let path = mangaPath(id)
        do {
            let got = try await LocalCopy.fetch(Server.url(path), auth: true)
            LocalCopy.store(got.data, type: got.type, key: path)
            let d = (try? JSONSerialization.jsonObject(with: got.data) as? [String: Any]) ?? [:]
            let total = (d["pages"] as? [Any])?.count ?? 0
            let series = d["series"] as? [String: Any] ?? [:]
            update(id) {
                $0.state = "loading"; $0.total = total
                $0.title = d["name"] as? String ?? ""; $0.series = series["name"] as? String ?? ""; $0.seriesId = series["id"] as? String ?? ""
            }
            // the series page and the reader's settings, so the volume can be reached and read offline
            if let sid = series["id"] as? String { await LocalCopy.keep("/api/manga/series/" + enc(sid), Server.url("/api/manga/series/" + enc(sid))) }
            await LocalCopy.keep("/api/manga/prefs", Server.url("/api/manga/prefs"))
            var bytes = 0
            for n in stride(from: 1, through: total, by: 1) {
                guard state.manga[id] != nil else { return }                // removed while it loaded
                let page = path + "/pages/\(n)"
                if !exists(page) {
                    let g = try await LocalCopy.fetch(Server.url(page + "?size=\(size)"), auth: true)
                    LocalCopy.store(g.data, type: g.type, key: page)
                }
                bytes += Self.size(page)
                if n % 5 == 0 || n == total { update(id) { $0.done = n; $0.bytes = bytes } }
            }
            update(id) { $0.state = "done" }
        } catch is LocalCopy.Gone {
            update(id) { $0.state = "failed"; $0.error = "Komga doesn't have it any more" }
        } catch {
            update(id) { $0.state = "failed"; $0.error = error.localizedDescription }
        }
    }

    static func removeManga(_ id: String) {
        guard let m = state.manga.removeValue(forKey: id) else { return }
        LocalCopy.remove(mangaPath(id))
        for n in stride(from: 1, through: m.total, by: 1) { LocalCopy.remove(mangaPath(id) + "/pages/\(n)") }
        save()
    }

    // MARK: Settings

    /// "54 MB on this Mac, updated today at 10:42."
    static func summary() -> String {
        let fm = FileManager.default
        var bytes = 0
        for dir in [LocalCopy.appDir, LocalCopy.dataDir] {
            guard let all = fm.enumerator(at: dir, includingPropertiesForKeys: [.fileSizeKey]) else { continue }
            for case let f as URL in all { bytes += (try? f.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0 }
        }
        let mb = String(format: "%.0f MB", Double(bytes) / 1_048_576)
        guard let at = UserDefaults.standard.object(forKey: "localCopy.at") as? Date else { return "\(mb) on this Mac, not updated yet." }
        let f = DateFormatter()
        f.doesRelativeDateFormatting = true
        f.dateStyle = .medium
        f.timeStyle = .short
        return "\(mb) on this Mac, updated \(f.string(from: at).lowercased())."
    }
}
