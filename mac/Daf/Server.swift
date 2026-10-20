import AppKit
import Security

/// Where Daf is. The window loads the live site (docs/SHELL.md); the base URL is a
/// setting, with the public address as the default and the tailnet one as the other.
enum Server {
    static let baseKey = "baseURL"
    static let defaultBase = "https://daf.tiresia.xyz"

    static var base: URL {
        let s = UserDefaults.standard.string(forKey: baseKey) ?? defaultBase
        return URL(string: s.trimmingCharacters(in: .whitespaces)).flatMap(normal) ?? URL(string: defaultBase)!
    }

    /// An address as Daf keeps it: http or https, a host, a port if any, no path.
    static func normal(_ u: URL) -> URL? {
        guard let scheme = u.scheme?.lowercased(), ["http", "https"].contains(scheme),
              let host = u.host, !host.isEmpty else { return nil }
        var c = URLComponents()
        c.scheme = scheme
        c.host = host
        c.port = u.port
        return c.url
    }

    /// A page of the app ("#today") or a path on the server ("/api/save").
    static func url(_ where_: String) -> URL {
        if where_.hasPrefix("#") { return URL(string: base.absoluteString + "/" + where_)! }
        return URL(string: base.absoluteString + (where_.hasPrefix("/") ? where_ : "/" + where_))!
    }

    /// A page the window may show: the base URL's origin, or the app's own copy (daf-app://app, LocalCopy).
    static func isOurs(_ u: URL) -> Bool {
        if u.scheme?.lowercased() == "daf-app" { return true }
        func port(_ x: URL) -> Int { x.port ?? (x.scheme?.lowercased() == "https" ? 443 : 80) }
        return u.scheme?.lowercased() == base.scheme && u.host?.lowercased() == base.host?.lowercased() && port(u) == port(base)
    }

    static func setBase(_ s: String) -> Bool {
        guard let u = URL(string: s.trimmingCharacters(in: .whitespaces)).flatMap(normal) else { return false }
        guard u != base else { return true }
        UserDefaults.standard.set(u.absoluteString, forKey: baseKey)
        NotificationCenter.default.post(name: .dafBaseChanged, object: nil)
        return true
    }
}

extension Notification.Name {
    /// The base URL changed: windows load again, the menu bar asks again.
    static let dafBaseChanged = Notification.Name("daf.baseChanged")
    /// The device token changed: the menu bar asks again.
    static let dafTokenChanged = Notification.Name("daf.tokenChanged")
}

/// The device token the menu bar and Save to Daf use (`Authorization: Bearer`), never
/// the window's cookie. Kept in the login keychain. The self-test starts from its own
/// (-SelfTestToken) and keeps any new one in memory; it never touches the keychain.
@MainActor
enum Token {
    private static let service = "xyz.tiresia.daf"
    private static let account = "device token"
    private static var cached: String??

    private static var testing: Bool { UserDefaults.standard.string(forKey: "SelfTestOut") != nil }

    static var value: String? {
        if testing {
            if cached == nil {
                // selftest.sh passes "t:<token>": a bare token can start with "-"
                let t = UserDefaults.standard.string(forKey: "SelfTestToken").map { $0.hasPrefix("t:") ? String($0.dropFirst(2)) : $0 }
                cached = .some(t.flatMap { $0.isEmpty ? nil : $0 })
            }
            return cached ?? nil
        }
        if let cached { return cached }
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true,
                                kSecMatchLimit as String: kSecMatchLimitOne]
        var out: CFTypeRef?
        let found = SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess
        let t = found ? (out as? Data).flatMap { String(data: $0, encoding: .utf8) } : nil
        cached = .some(t)
        return t
    }

    /// Saves a new token, or forgets it with nil or "". False if the keychain said no.
    @discardableResult
    static func set(_ token: String?) -> Bool {
        let t = token?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if testing {
            cached = .some(t.isEmpty ? nil : t)
            NotificationCenter.default.post(name: .dafTokenChanged, object: nil)
            return true
        }
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                   kSecAttrAccount as String: account]
        SecItemDelete(base as CFDictionary)
        var ok = true
        if !t.isEmpty {
            var add = base
            add[kSecValueData as String] = Data(t.utf8)
            add[kSecAttrLabel as String] = "Daf device token"
            ok = SecItemAdd(add as CFDictionary, nil) == errSecSuccess
        }
        cached = .some(t.isEmpty || !ok ? nil : t)
        NotificationCenter.default.post(name: .dafTokenChanged, object: nil)
        return ok
    }
}

/// The two endpoints the native parts need (docs/NATIVE.md).
enum Client {
    struct Widget: Codable, Equatable {
        struct Highlight: Codable, Equatable { var text: String; var title: String? }
        /// One of the goals in Preferences → Goals; `main` is the one the ring follows.
        struct Goal: Codable, Equatable {
            var id: String
            var kind: String
            var label: String?
            var unit: String?
            var done: Double
            var target: Double
            var period: String
            var period_label: String?
            var met: Bool?
            var pct: Double?
            var text: String?
            /// Minutes a day: the hour's own goal, shown the way it always was.
            var isDailyMinutes: Bool { kind == "minutes" && period == "day" }
        }
        struct Book: Codable, Equatable { var id: String; var title: String; var progress: Double? }
        var date: String
        var minutes: Double
        var goal: Double
        var year_day: Double?
        var year_hours: Double?
        var highlight: Highlight?
        var nightstand: [Book]?
        var main: Goal?
    }

    enum Failure: LocalizedError {
        case noToken, refused(String), unreachable(String)
        var errorDescription: String? {
            switch self {
            case .noToken: return "No device token yet. Add one in Settings."
            case .refused(let why): return why
            case .unreachable(let why): return "Daf didn't answer: \(why)"
            }
        }
    }

    static func widget() async throws -> Widget {
        let data = try await request("/api/phone/widget")
        return try JSONDecoder().decode(Widget.self, from: data)
    }

    struct FeedNews: Codable {
        struct Item: Codable { var id: String; var title: String; var source: String; var route: String }
        var cursor: Int
        var feeds: Int
        var items: [Item]
    }

    /// New posts in the feeds set to notify (FeedNews.swift).
    static func feedNews(cursor: Int) async throws -> FeedNews {
        let data = try await request("/api/phone/feed-news" + (cursor >= 0 ? "?cursor=\(cursor)" : ""))
        return try JSONDecoder().decode(FeedNews.self, from: data)
    }

    static func save(url: String, title: String? = nil, text: String? = nil) async throws {
        var body: [String: String] = ["url": url]
        if let title, !title.isEmpty { body["title"] = title }
        if let text, !text.isEmpty { body["text"] = text }
        _ = try await request("/api/save", json: body)
    }

    private static func request(_ path: String, json: [String: String]? = nil) async throws -> Data {
        guard let token = await Token.value else { throw Failure.noToken }
        var r = URLRequest(url: Server.url(path), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        r.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        r.setValue(await UserAgent.shell, forHTTPHeaderField: "User-Agent")
        if let json {
            r.httpMethod = "POST"
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = try JSONSerialization.data(withJSONObject: json)
        }
        let data: Data, response: URLResponse
        do { (data, response) = try await URLSession.shared.data(for: r) } catch {
            throw Failure.unreachable(error.localizedDescription)
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw Failure.refused(code == 401 ? "Daf doesn't know this device token. Make a new one and put it in Settings."
                                  : detail ?? "Daf answered \(code)")
        }
        return data
    }
}

@MainActor
enum UserAgent {
    static var version: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    }
    /// What the page looks for (docs/SHELL.md §1).
    static var name: String { "Daf/\(version) (macOS shell)" }
    static var shell: String { "Daf/\(version) (macOS shell) CFNetwork" }
}
