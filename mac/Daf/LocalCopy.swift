import AppKit
import CryptoKit
import WebKit

/// Daf with no network on the Mac, the way Moshe works: the app keeps its own copy of Daf's screens
/// (every file of the server's web/, from /api/app-files, its fonts among them) and of the data the
/// server says to keep (/api/offline/plan: today, the review ahead, lists, articles with their
/// pictures and PDFs, the books being read), and what's kept by hand (OnThisMac). When Daf's server
/// can't be reached, the window loads that copy from daf-app://app/ (AppScheme); online it is the
/// live site, as before (YouTube plays only on a real web address). Coming back, what was done
/// offline goes first, then the live site again. What nothing names any more leaves after three
/// weeks without being kept or read.
@MainActor
enum LocalCopy {
    static let scheme = "daf-app"
    static let origin = URL(string: "daf-app://app/")!
    /// The windows are on the copy now (Daf didn't answer).
    static var active = false

    static var root: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(Bundle.main.bundleIdentifier ?? "xyz.tiresia.daf", isDirectory: true)
        try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }
    static var appDir: URL { root.appendingPathComponent("app", isDirectory: true) }
    static var dataDir: URL { root.appendingPathComponent("data", isDirectory: true) }

    static var ready: Bool { FileManager.default.fileExists(atPath: appDir.appendingPathComponent("index.html").path) }

    /// A page of Daf on the copy: daf-app://app/#today.
    static func url(_ route: String?) -> URL {
        guard let route, !route.isEmpty else { return origin }
        return URL(string: origin.absoluteString + (route.hasPrefix("#") ? route : "#" + route)) ?? origin
    }

    // MARK: keeping the copy up to date

    private static var refreshing = false

    /// Daf's screens and data, while Daf answers: at launch, every few hours, and when the network is back.
    static func keepUpToDate() {
        Task { await refreshNow() }
    }

    /// The same, waited for (Settings' Update Now, dafShell.offline sync). Says what it did.
    @discardableResult
    static func refreshNow() async -> String {
        guard !refreshing else { return "It's already updating." }
        refreshing = true
        defer { refreshing = false }
        do {
            try await refreshScreens()
            let said = await keepData()
            UserDefaults.standard.set(Date(), forKey: "localCopy.at")
            return said
        } catch {
            NSLog("Daf: the copy for offline didn't update: \(error.localizedDescription)")
            return "Daf didn't answer: \(error.localizedDescription)"
        }
    }

    /// Fetches the files of web/ that changed (by their SHA-1).
    static func refreshScreens() async throws {
        let list = try await fetch(Server.url("/api/app-files"), auth: false)
        guard let d = try JSONSerialization.jsonObject(with: list.data) as? [String: Any],
              let version = d["version"] as? String, let files = d["files"] as? [[String: Any]] else { throw URLError(.cannotParseResponse) }
        let had = UserDefaults.standard.dictionary(forKey: "localCopy.hashes") as? [String: String] ?? [:]
        if version == UserDefaults.standard.string(forKey: "localCopy.version"), ready { return }
        var now: [String: String] = [:]
        for f in files {
            guard let path = f["path"] as? String, let sha = f["sha1"] as? String else { continue }
            let to = appDir.appendingPathComponent(String(path.drop { $0 == "/" }))
            if had[path] != sha || !FileManager.default.fileExists(atPath: to.path) {
                let body = try await fetch(Server.url(path), auth: false).data
                guard sha1(body) == sha else { throw URLError(.cannotDecodeContentData) }
                try write(body, to: to)
            }
            now[path] = sha
        }
        try? FileManager.default.removeItem(at: root.appendingPathComponent("fonts"))   // Google's, before Daf had its own
        UserDefaults.standard.set(now, forKey: "localCopy.hashes")
        UserDefaults.standard.set(version, forKey: "localCopy.version")
    }

    /// What the server says to keep for offline, by address and query; pictures by their whole URL;
    /// then what's kept by hand (OnThisMac), up to date; then what nothing names any more goes, once
    /// it hasn't been kept or read here for three weeks. Says what it did.
    @discardableResult
    static func keepData() async -> String {
        var urls = ["/api/me", "/api/settings", "/api/today", "/api/review", "/api/home", "/api/books", "/api/highlights", "/api/docs/counts", "/api/stats"]
        var docs: [String] = [], images: [String] = [], ebooks: [String] = []
        let plan = try? await fetch(Server.url("/api/offline/plan"), auth: true)
        if let p = plan, let d = try? JSONSerialization.jsonObject(with: p.data) as? [String: Any] {
            urls = d["urls"] as? [String] ?? urls
            docs = d["docs"] as? [String] ?? []
            images = d["images"] as? [String] ?? []
            ebooks = d["ebooks"] as? [String] ?? []
        }
        var live = Set<String>(), got = 0, failed = 0
        for u in urls {
            live.insert(u)
            if let a = anyKey(u) { live.insert(a) }
            if await keep(u, Server.url(u)) != nil { got += 1 } else { failed += 1 }
        }
        var planDocs: [String] = []
        for id in docs {
            let path = docPath(id)
            guard let b = try? await keepDoc(path, pictures: false) else { failed += 1; continue }
            images += pictures(b)
            live.formUnion(docKeys(path, b))
            planDocs.append(id)
            got += 1
        }
        if plan != nil { OnThisMac.state.planDocs = planDocs }
        // the articles kept by hand, pictures and all; one deleted in Daf goes from here too
        for id in OnThisMac.state.docs {
            let path = docPath(id)
            do {
                let b = try await keepDoc(path, pictures: true)
                if (try? JSONSerialization.jsonObject(with: b) as? [String: Any])?["status"] as? String == "deleted" { throw Gone() }
                live.formUnion(docKeys(path, b))
            } catch is Gone {
                OnThisMac.state.docs.removeAll { $0 == id }
                remove(path)
                remove(path + "/pdf")
            } catch {
                if let b = try? Data(contentsOf: dataFile(path)) { live.formUnion(docKeys(path, b)) }   // no answer now: it stays
            }
        }
        // the books being read (the plan's) and the ones kept by hand
        if plan != nil { OnThisMac.state.planBooks = ebooks }
        for id in OnThisMac.booksToKeep(ebooks) {
            do { try await OnThisMac.fetchBook(id) } catch is Gone { OnThisMac.state.books[id] = nil } catch { }
            live.formUnion(OnThisMac.bookKeys(id))
        }
        for img in images where !img.isEmpty && !img.hasPrefix("data:") { live.insert(absolute(img)) }
        for img in images.prefix(400) where !img.isEmpty && !img.hasPrefix("data:") {
            let abs = absolute(img)
            if !FileManager.default.fileExists(atPath: dataFile(abs).path), let u = URL(string: abs) {
                await keep(abs, u, auth: Server.isOurs(u), limit: 4 << 20)
            }
        }
        live.formUnion(OnThisMac.mangaKeys())
        let gone = prune(live)
        OnThisMac.forgetMissing()
        OnThisMac.save()
        return "\(got) kept" + (failed > 0 ? ", \(failed) didn't come" : "") + (gone > 0 ? ", \(gone) let go" : "")
    }

    static func docPath(_ id: String) -> String { "/api/docs/" + OnThisMac.enc(id) }

    static func absolute(_ src: String) -> String { src.hasPrefix("/") ? Server.url(src).absoluteString : src }

    /// An article, and its PDF when it has one; by hand, its pictures too (the plan's come after,
    /// four hundred at most). Gone when Daf has no such article.
    @discardableResult
    static func keepDoc(_ path: String, pictures withPictures: Bool) async throws -> Data {
        let got = try await fetch(Server.url(path + "?prefetch=1"), auth: true)
        store(got.data, type: got.type, key: path)
        let d = (try? JSONSerialization.jsonObject(with: got.data) as? [String: Any]) ?? [:]
        if d["kind"] as? String == "pdf" || d["has_pdf"] as? Bool == true, !FileManager.default.fileExists(atPath: dataFile(path + "/pdf").path) {
            await keep(path + "/pdf", Server.url(path + "/pdf"))
        }
        if withPictures {
            for img in pictures(got.data) where !img.isEmpty && !img.hasPrefix("data:") {
                let abs = absolute(img)
                if !FileManager.default.fileExists(atPath: dataFile(abs).path), let u = URL(string: abs) { await keep(abs, u, auth: Server.isOurs(u), limit: 4 << 20) }
            }
        }
        return got.data
    }

    /// The keys an article keeps: itself, its PDF, its pictures.
    static func docKeys(_ path: String, _ doc: Data) -> [String] {
        [path, path + "/pdf"] + pictures(doc).filter { !$0.isEmpty && !$0.hasPrefix("data:") }.map(absolute)
    }

    /// Lets go of what nothing names any more (live: the keys that stay), once it hasn't been kept or
    /// read here for three weeks. Returns how many went.
    static func prune(_ live: Set<String>) -> Int {
        let names = Set(live.map(key)), fm = FileManager.default
        let old = Date().addingTimeInterval(-21 * 24 * 3600)
        guard let files = try? fm.contentsOfDirectory(at: dataDir, includingPropertiesForKeys: [.contentModificationDateKey]) else { return 0 }
        var n = 0
        for f in files where f.pathExtension.isEmpty && !names.contains(f.lastPathComponent) {
            let at = (try? f.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
            guard at < old else { continue }
            try? fm.removeItem(at: f)
            try? fm.removeItem(at: f.appendingPathExtension("type"))
            n += 1
        }
        return n
    }

    static func remove(_ key: String) {
        try? FileManager.default.removeItem(at: dataFile(key))
        try? FileManager.default.removeItem(at: dataFile(key).appendingPathExtension("type"))
    }

    /// Read here: it stays three weeks more.
    static func touch(_ file: URL) {
        try? FileManager.default.setAttributes([.modificationDate: Date()], ofItemAtPath: file.path)
    }

    @discardableResult
    static func keep(_ key: String, _ url: URL, auth: Bool = true, limit: Int = 64 << 20) async -> Data? {
        guard let got = try? await fetch(url, auth: auth), got.data.count <= limit else { return nil }
        store(got.data, type: got.type, key: key)
        return got.data
    }

    static func pictures(_ doc: Data) -> [String] {
        guard let d = try? JSONSerialization.jsonObject(with: doc) as? [String: Any] else { return [] }
        var out = (d["blocks"] as? [[String: Any]] ?? []).filter { $0["t"] as? String == "img" }.compactMap { $0["src"] as? String }
        if let t = d["thumb"] as? String, !t.isEmpty { out.append(t) }
        return out
    }

    // MARK: files and fetching

    static func dataFile(_ key: String) -> URL { dataDir.appendingPathComponent(Self.key(key)) }

    /// A list kept in another order or with other filters still answers for the same list: the
    /// Library's and Feed's by where, tab, kind, cat and feed; Highlights whatever its query.
    static func anyKey(_ key: String) -> String? {
        let parts = key.split(separator: "?", maxSplits: 1).map(String.init)
        if parts[0] == "/api/highlights" { return "/api/highlights?_any" }
        guard parts[0] == "/api/docs", parts.count == 2 else { return nil }
        let q = URLComponents(string: "http://x/?" + parts[1])?.queryItems ?? []
        return "/api/docs?_any" + ["where", "tab", "kind", "cat", "feed"].map { k in "&\(k)=" + (q.first { $0.name == k }?.value ?? "") }.joined()
    }

    /// Keeps what came under its key, and its list's any-key too.
    static func store(_ data: Data, type: String, key: String) {
        for k in [key] + (anyKey(key).map { [$0] } ?? []) {
            try? write(data, to: dataFile(k))
            try? write(Data(type.utf8), to: dataFile(k).appendingPathExtension("type"))
        }
    }

    /// What was kept for a request: its own key, the path alone (a doc), or its list's any-key.
    static func kept(_ path: String, _ query: String) -> URL? {
        for k in [path + query, path] + (anyKey(path + query).map { [$0] } ?? []) {
            let f = dataFile(k)
            if FileManager.default.fileExists(atPath: f.path) { return f }
        }
        return nil
    }

    /// A file's name for an address: the same whether its path came percent-encoded (as the page
    /// asks, kk%3A…) or not (as the plan names it), so both find it.
    static func key(_ s: String) -> String {
        let parts = s.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
        let path = parts[0].removingPercentEncoding ?? parts[0]
        return sha1(Data((parts.count == 2 ? path + "?" + parts[1] : path).utf8))
    }

    static func sha1(_ d: Data) -> String { Insecure.SHA1.hash(data: d).map { String(format: "%02x", $0) }.joined() }

    static func write(_ d: Data, to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try d.write(to: url, options: .atomic)
    }

    struct Got { var data: Data; var type: String }

    /// GET with the window's sign-in (its cookies for Daf's address) when auth.
    static func fetch(_ url: URL, auth: Bool, browser: Bool = false) async throws -> Got {
        var r = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        r.httpShouldHandleCookies = false
        r.setValue(browser ? "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
                           : UserAgent.shell, forHTTPHeaderField: "User-Agent")
        if auth { for (k, v) in await cookieHeader() { r.setValue(v, forHTTPHeaderField: k) } }
        let (data, response) = try await URLSession.shared.data(for: r)
        guard let h = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
        if auth && [404, 410].contains(h.statusCode) { throw Gone() }
        guard h.statusCode == 200 else { throw URLError(.badServerResponse) }
        return Got(data: data, type: h.value(forHTTPHeaderField: "Content-Type") ?? "application/octet-stream")
    }

    /// Daf says there's no such thing (any more).
    struct Gone: Error {}

    /// The window's cookies for Daf's address, as a request header.
    static func cookieHeader() async -> [String: String] {
        let all = await WKWebsiteDataStore.default().httpCookieStore.allCookies()
        let host = Server.base.host ?? ""
        let mine = all.filter { c in host == c.domain || host.hasSuffix("." + c.domain.trimmingCharacters(in: CharacterSet(charactersIn: "."))) }
        return HTTPCookie.requestHeaderFields(with: mine)
    }

    // MARK: the page's settings, carried to the copy

    private static var snapshotFile: URL { root.appendingPathComponent("localStorage.json") }

    /// The live page's localStorage (its type, layout and reader settings), but not its outbox,
    /// which goes from where it was made.
    static let snapshotJS = "JSON.stringify(Object.fromEntries(Object.entries(localStorage).filter(([k]) => k !== 'daf.outbox')))"

    static func keepSnapshot(_ json: String) {
        try? write(Data(json.utf8), to: snapshotFile)
    }

    /// Run first in the copy's page: the live page's settings. A snapshot newer than the last one the
    /// copy took replaces what's there (a theme changed online); otherwise only what's missing is added.
    static var seedScript: String {
        let json = (try? String(contentsOf: snapshotFile, encoding: .utf8)) ?? "{}"
        let at = ((try? FileManager.default.attributesOfItem(atPath: snapshotFile.path))?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
        return "if (location.protocol === 'daf-app:') { try { const s = \(json), at = \(Int(at * 1000)), newer = +(localStorage.getItem('daf.shell.seeded') || 0) < at; "
            + "for (const k in s) if (newer || localStorage.getItem(k) === null) localStorage.setItem(k, s[k]); if (newer) localStorage.setItem('daf.shell.seeded', String(at)); } catch (e) {} }"
    }
}

/// daf-app://app/: the copy's files; /api/… through to Daf with the window's sign-in, and from what
/// was kept when Daf doesn't answer; __img/ (an article's pictures) from the copy.
final class AppScheme: NSObject, WKURLSchemeHandler {
    static let shared = AppScheme()
    private var stopped = Set<ObjectIdentifier>()
    private let lock = NSLock()

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return task.didFailWithError(URLError(.badURL)) }
        let path = url.path
        if path.hasPrefix("/api/") { return pass(task, url: url) }
        Task { @MainActor in
            if path.hasPrefix("/__img/") {
                let key = String(path.dropFirst(7))
                let f = LocalCopy.dataDir.appendingPathComponent(key)
                let type = (try? String(contentsOf: f.appendingPathExtension("type"), encoding: .utf8)) ?? "image/jpeg"
                return self.answer(task, url, try? Data(contentsOf: f), type)
            }
            var file = LocalCopy.appDir.appendingPathComponent(String(path.drop { $0 == "/" }))
            var isDir: ObjCBool = false
            if path == "/" || !FileManager.default.fileExists(atPath: file.path, isDirectory: &isDir) || isDir.boolValue {
                file = LocalCopy.appDir.appendingPathComponent("index.html")
            }
            guard let data = try? Data(contentsOf: file) else { return self.fail(task, URLError(.fileDoesNotExist)) }
            self.answer(task, url, data, Self.mime(file.pathExtension))
        }
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {
        lock.lock(); stopped.insert(ObjectIdentifier(task)); lock.unlock()
    }

    private func live(_ task: WKURLSchemeTask) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return !stopped.contains(ObjectIdentifier(task))
    }

    private func answer(_ task: WKURLSchemeTask, _ url: URL, _ data: Data?, _ type: String, status: Int = 200, headers: [String: String] = [:]) {
        guard live(task) else { return }
        guard let data else { return fail(task, URLError(.fileDoesNotExist)) }
        var h = headers
        h["Content-Type"] = type
        h["Content-Length"] = String(data.count)
        h["Cache-Control"] = h["Cache-Control"] ?? "no-cache"
        task.didReceive(HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: h)!)
        task.didReceive(data)
        task.didFinish()
    }

    private func fail(_ task: WKURLSchemeTask, _ e: Error) {
        guard live(task) else { return }
        task.didFailWithError(e)
    }

    /// Daf's API: through to the server with the window's sign-in; a GET that doesn't come is
    /// answered from what was kept, a change that doesn't go fails as a network error does, so the
    /// page's outbox keeps it.
    private func pass(_ task: WKURLSchemeTask, url: URL) {
        let path = url.path, query = url.query.map { "?" + $0 } ?? ""
        let method = task.request.httpMethod ?? "GET"
        let body = task.request.httpBody
        let range = task.request.value(forHTTPHeaderField: "Range")
        let headers = task.request.allHTTPHeaderFields ?? [:]
        Task { @MainActor in
            let found = method == "GET" ? LocalCopy.kept(path, query) : nil
            if LocalCopy.active, let k = found, let d = try? Data(contentsOf: k) {
                // offline: what was kept, with its pictures pointed at their kept copies
                LocalCopy.touch(k)
                let type = (try? String(contentsOf: k.appendingPathExtension("type"), encoding: .utf8)) ?? "application/json"
                return self.answer(task, url, path.hasPrefix("/api/docs/") ? Self.localPictures(d) : d, type, headers: ["X-Daf-Offline": "1"])
            }
            var r = URLRequest(url: Server.url(path + query), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
            r.httpMethod = method
            r.httpBody = body
            r.httpShouldHandleCookies = false
            for (k, v) in headers where !["cookie", "host", "origin", "referer"].contains(k.lowercased()) { r.setValue(v, forHTTPHeaderField: k) }
            if let range { r.setValue(range, forHTTPHeaderField: "Range") }
            r.setValue(UserAgent.shell, forHTTPHeaderField: "User-Agent")
            for (k, v) in await LocalCopy.cookieHeader() { r.setValue(v, forHTTPHeaderField: k) }
            do {
                let (data, response) = try await URLSession.shared.data(for: r)
                guard let h = response as? HTTPURLResponse else { throw URLError(.badServerResponse) }
                if [502, 503, 504].contains(h.statusCode) || (520...530).contains(h.statusCode) { throw URLError(.cannotConnectToHost) }
                // the sign-in the server set (a login) goes where the live site will find it
                let fields = h.allHeaderFields.reduce(into: [String: String]()) { $0["\($1.key)"] = "\($1.value)" }
                for c in HTTPCookie.cookies(withResponseHeaderFields: fields, for: Server.base) {
                    await WKWebsiteDataStore.default().httpCookieStore.setCookie(c)
                }
                if method == "GET" && h.statusCode == 200 && data.count < (16 << 20) && !path.hasSuffix("/file") {
                    LocalCopy.store(data, type: h.value(forHTTPHeaderField: "Content-Type") ?? "application/json", key: path + query)
                }
                var out: [String: String] = [:]
                for k in ["Content-Range", "Accept-Ranges", "Content-Disposition", "ETag", "Last-Modified"] { if let v = h.value(forHTTPHeaderField: k) { out[k] = v } }
                self.answer(task, url, data, h.value(forHTTPHeaderField: "Content-Type") ?? "application/octet-stream", status: h.statusCode, headers: out)
            } catch {
                if let k = found, let d = try? Data(contentsOf: k) {
                    LocalCopy.touch(k)
                    let type = (try? String(contentsOf: k.appendingPathExtension("type"), encoding: .utf8)) ?? "application/json"
                    return self.answer(task, url, path.hasPrefix("/api/docs/") ? Self.localPictures(d) : d, type, headers: ["X-Daf-Offline": "1"])
                }
                self.fail(task, URLError(.notConnectedToInternet))
            }
        }
    }

    /// An article's pictures, where a copy was kept: daf-app://app/__img/<key>.
    @MainActor
    private static func localPictures(_ doc: Data) -> Data {
        guard var d = try? JSONSerialization.jsonObject(with: doc) as? [String: Any], var blocks = d["blocks"] as? [[String: Any]] else { return doc }
        for i in blocks.indices where blocks[i]["t"] as? String == "img" {
            guard let src = blocks[i]["src"] as? String else { continue }
            let abs = src.hasPrefix("/") ? Server.url(src).absoluteString : src
            if FileManager.default.fileExists(atPath: LocalCopy.dataFile(abs).path) { blocks[i]["src"] = "daf-app://app/__img/" + LocalCopy.key(abs) }
        }
        d["blocks"] = blocks
        return (try? JSONSerialization.data(withJSONObject: d)) ?? doc
    }

    static func mime(_ ext: String) -> String {
        switch ext.lowercased() {
        case "html": return "text/html; charset=utf-8"
        case "js", "mjs": return "text/javascript; charset=utf-8"
        case "css": return "text/css; charset=utf-8"
        case "json", "webmanifest": return "application/json"
        case "svg": return "image/svg+xml"
        case "png": return "image/png"
        case "ico": return "image/x-icon"
        case "woff2": return "font/woff2"
        case "wasm": return "application/wasm"
        default: return "application/octet-stream"
        }
    }
}

/// On the copy: every 30 seconds, and whenever the Mac's network changes, ask Daf if it's back;
/// when it is, each window sends what was done offline and goes back to the live site.
@MainActor
final class Reconnect {
    static let shared = Reconnect()
    private var timer: Timer?

    func watch() {
        guard timer == nil else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in Task { @MainActor in await Reconnect.shared.check() } }
        NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in await Reconnect.shared.check() }
        }
    }

    func check() async {
        guard LocalCopy.active else { stop(); return }
        var r = URLRequest(url: Server.url("/api/health"), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 5)
        r.httpMethod = "GET"
        guard let (_, resp) = try? await URLSession.shared.data(for: r), (resp as? HTTPURLResponse)?.statusCode == 200 else { return }
        for c in DafWindowController.all { await c.goLive() }
        stop()
    }

    private func stop() {
        timer?.invalidate()
        timer = nil
    }
}
