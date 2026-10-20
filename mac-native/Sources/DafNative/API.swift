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
    static let baseKey = "base"
    static let defaultBase = "https://daf.tiresia.xyz"

    var base: URL {
        let s = UserDefaults.standard.string(forKey: Self.baseKey) ?? Self.defaultBase
        return URL(string: s.trimmingCharacters(in: .whitespaces).trimmingCharacters(in: CharacterSet(charactersIn: "/"))) ?? URL(string: Self.defaultBase)!
    }

    let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.httpCookieStorage = .shared
        c.httpShouldSetCookies = true
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
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

    @discardableResult
    func send(_ method: String, _ path: String, _ body: [String: Any]?) async throws -> Any {
        var r = URLRequest(url: url(path))
        r.httpMethod = method
        if let body {
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, response) = try await session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let parsed = (try? JSONSerialization.jsonObject(with: data)) ?? [:]
        guard (200..<300).contains(status) else {
            let detail = (parsed as? [String: Any])?["detail"] as? String
            if status == 401 { NotificationCenter.default.post(name: .dafSignedOut, object: nil) }
            throw APIError(status: status, message: detail ?? "Daf answered \(status).")
        }
        return parsed
    }

    func data(_ path: String) async throws -> Data {
        let (data, response) = try await session.data(from: url(path))
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw APIError(status: status, message: "Daf answered \(status).") }
        return data
    }

    nonisolated static func enc(_ s: String) -> String {
        s.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-_.!~*'()"))) ?? s
    }
}

extension Notification.Name {
    static let dafSignedOut = Notification.Name("dafSignedOut")
}

enum Version {
    static var short: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1" }
}
