import Foundation

/// A JSON object from Daf, read leniently: Daf's numbers come as ints or floats, its flags as
/// bools or 0/1, and a field it doesn't send is just nil.
struct J: Hashable {
    let raw: [String: Any]

    init(_ raw: [String: Any]) { self.raw = raw }
    init?(_ any: Any?) {
        guard let d = any as? [String: Any] else { return nil }
        raw = d
    }

    func s(_ k: String) -> String? {
        if let v = raw[k] as? String { return v.isEmpty ? nil : v }
        if let v = raw[k] as? NSNumber { return v.stringValue }
        return nil
    }
    func d(_ k: String) -> Double? { (raw[k] as? NSNumber)?.doubleValue ?? (raw[k] as? String).flatMap(Double.init) }
    func i(_ k: String) -> Int? { d(k).map { Int($0) } }
    func b(_ k: String) -> Bool { (raw[k] as? Bool) ?? ((raw[k] as? NSNumber)?.boolValue ?? false) }
    func o(_ k: String) -> J? { J(raw[k]) }
    func a(_ k: String) -> [J] { (raw[k] as? [Any] ?? []).compactMap { J($0) } }
    func list(_ k: String) -> [Any] { raw[k] as? [Any] ?? [] }
    /// A list of words, sent as a list or as JSON in a string (a doc's tags).
    func strings(_ k: String) -> [String] {
        if let a = raw[k] as? [Any] { return a.compactMap { $0 as? String } }
        if let s = raw[k] as? String, let d = s.data(using: .utf8), let a = try? JSONSerialization.jsonObject(with: d) as? [Any] { return a.compactMap { $0 as? String } }
        return []
    }

    static func == (l: J, r: J) -> Bool { NSDictionary(dictionary: l.raw).isEqual(to: r.raw) }
    func hash(into h: inout Hasher) { h.combine(s("id") ?? "") }
}

struct APIError: LocalizedError {
    let status: Int
    let message: String
    var errorDescription: String? { message }
}

/// Daf's API with the sign-in cookie, the same calls the page makes. The cookie lives in the
/// app's own cookie store (URLSession keeps it across launches).
@MainActor
final class API {
    static let shared = API()
    static let baseKey = "base"   // the web-view Daf kept it as "baseURL": Migration carries it over
    static let defaultBase = "https://daf.tiresia.xyz"

    var base: URL {
        let s = UserDefaults.standard.string(forKey: Self.baseKey) ?? Self.defaultBase
        return URL(string: s.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "/"))) ?? URL(string: Self.defaultBase)!
    }

    let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.httpCookieStorage = .shared
        c.httpShouldSetCookies = true
        c.requestCachePolicy = .useProtocolCachePolicy       // pictures by their headers; Daf's answers ask afresh (send)
        c.urlCache = URLCache(memoryCapacity: 48 << 20, diskCapacity: 600 << 20, directory: Store.folder("Pictures"))
        c.timeoutIntervalForRequest = 30
        c.httpAdditionalHeaders = ["User-Agent": "Daf/\(Version.short) (macOS native)"]
        return URLSession(configuration: c)
    }()

    /// A path on Daf ("/api/today"), or an address that's already whole.
    func url(_ path: String) -> URL {
        if path.hasPrefix("http://") || path.hasPrefix("https://") { return URL(string: path)! }
        return URL(string: base.absoluteString + (path.hasPrefix("/") ? path : "/" + path))!
    }

    var cookie: HTTPCookie? {
        HTTPCookieStorage.shared.cookies(for: base)?.first { $0.name == "daf" }
    }

    /// For the self-test: a cookie made on the server, put in the store as a sign-in would.
    func setCookie(_ value: String) {
        let props: [HTTPCookiePropertyKey: Any] = [.name: "daf", .value: value, .domain: base.host ?? "", .path: "/",
                                                   .expires: Date().addingTimeInterval(30 * 86400)]
        if let c = HTTPCookie(properties: props) { HTTPCookieStorage.shared.setCookie(c) }
    }

    func signOut() {
        for c in HTTPCookieStorage.shared.cookies(for: base) ?? [] { HTTPCookieStorage.shared.deleteCookie(c) }
    }

    func signIn(user: String, password: String) async throws {
        _ = try await send("POST", "/api/login", ["user": user, "password": password])
    }

    func get(_ path: String) async throws -> Any {
        try await send("GET", path, nil)
    }

    func json(_ path: String) async throws -> J {
        guard let j = J(try await get(path)) else { throw APIError(status: 0, message: "Daf's answer wasn't what the app expected.") }
        return j
    }

    /// A call to Daf. An answer is kept on this Mac (Cache); with no connection the kept one comes
    /// back instead, and a change waits in the Outbox (with its X-Daf-Op, so it's done once).
    @discardableResult
    func send(_ method: String, _ path: String, _ body: [String: Any]?, op: String? = nil) async throws -> Any {
        var r = URLRequest(url: url(path))
        r.httpMethod = method
        r.cachePolicy = .reloadIgnoringLocalCacheData
        var bodyData: Data?
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            bodyData = try JSONSerialization.data(withJSONObject: body)
            r.httpBody = bodyData
        }
        let write = method != "GET"
        let opID = op ?? (write ? Outbox.newID() : nil)
        if let opID { r.setValue(opID, forHTTPHeaderField: "X-Daf-Op") }
        do {
            if Connection.shared.forced { throw URLError(.notConnectedToInternet) }
            let (data, response) = try await session.data(for: r)
            Connection.shared.reached()
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let parsed = (try? JSONSerialization.jsonObject(with: data)) ?? [:]
            guard (200..<300).contains(status) else {
                let detail = (parsed as? [String: Any])?["detail"] as? String
                if status == 401 { NotificationCenter.default.post(name: .dafSignedOut, object: nil) }
                throw APIError(status: status, message: detail ?? "Daf answered \(status).")
            }
            if !write && path.hasPrefix("/api/") && path != "/api/health" { Cache.put(path, data) }
            return parsed
        } catch where Connection.isOffline(error) {
            Connection.shared.lost()
            if !write, let d = Cache.get(path), let parsed = try? JSONSerialization.jsonObject(with: d) { return parsed }
            if write, op == nil, let opID, Outbox.canWait(method, path) {
                Outbox.shared.add(.init(id: opID, method: method, path: path, body: bodyData))
                return ["queued": true]
            }
            throw error
        }
    }

    /// An answer fetched now and kept under another path (an article kept for later under the
    /// path the reader asks for).
    func keep(_ path: String, as key: String) async {
        var r = URLRequest(url: url(path))
        r.cachePolicy = .reloadIgnoringLocalCacheData
        guard !Connection.shared.forced, let (data, response) = try? await session.data(for: r),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return }
        Cache.put(key, data)
    }

    func data(_ path: String) async throws -> Data {
        if Connection.shared.forced { throw URLError(.notConnectedToInternet) }
        let (data, response) = try await session.data(from: url(path))
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw APIError(status: status, message: "Daf answered \(status).") }
        return data
    }

    /// A file as the body, not JSON (a photo of a page).
    func upload(_ path: String, _ data: Data, type: String) async throws -> Any {
        if Connection.shared.forced { throw URLError(.notConnectedToInternet) }
        var r = URLRequest(url: url(path))
        r.httpMethod = "POST"
        r.setValue(type, forHTTPHeaderField: "Content-Type")
        r.httpBody = data
        r.timeoutInterval = 120
        let (body, response) = try await session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let parsed = (try? JSONSerialization.jsonObject(with: body)) ?? [:]
        guard (200..<300).contains(status) else {
            throw APIError(status: status, message: ((parsed as? [String: Any])?["detail"] as? String) ?? "Daf answered \(status).")
        }
        return parsed
    }

    /// A POST whose answer is bytes, not JSON (a paragraph's speech).
    func post(_ path: String, _ body: [String: Any]) async throws -> Data {
        if Connection.shared.forced { throw URLError(.notConnectedToInternet) }
        var r = URLRequest(url: url(path))
        r.httpMethod = "POST"
        r.cachePolicy = .reloadIgnoringLocalCacheData
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw APIError(status: status, message: "Daf answered \(status).") }
        return data
    }

    /// A picture: from the network, or the copy kept on this Mac when there's no connection.
    func picture(_ u: URL) async -> Data? {
        if !Connection.shared.forced, let (d, r) = try? await session.data(from: u), ((r as? HTTPURLResponse)?.statusCode ?? 200) < 400 { return d }
        let kept = URLRequest(url: u, cachePolicy: .returnCacheDataDontLoad)
        return session.configuration.urlCache?.cachedResponse(for: kept)?.data
    }

    /// A call with a device's token instead of the sign-in (the new-post alerts, as the phone asks).
    func device(_ path: String, token: String) async throws -> J {
        var r = URLRequest(url: url(path))
        r.cachePolicy = .reloadIgnoringLocalCacheData
        r.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard status == 200, let j = J(try? JSONSerialization.jsonObject(with: data)) else { throw APIError(status: status, message: "Daf answered \(status).") }
        return j
    }

    nonisolated static func enc(_ s: String) -> String {
        s.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_.!~*'()"))) ?? s
    }
}

extension Notification.Name {
    static let dafSignedOut = Notification.Name("dafSignedOut")
}

/// "1 highlight", "3 highlights".
func plural(_ n: Int, _ one: String, _ many: String? = nil) -> String { "\(n) " + (n == 1 ? one : many ?? one + "s") }

enum Version {
    static var short: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1" }
}
