import AppKit
import SafariServices
import Security
import UserNotifications
import WebKit

/// daf:// links, as the web-view Daf answered them: Save to Daf in the share menu hands a link over
/// as daf://save?url=…&title=…&text=…; the Safari extension asks for its token with
/// daf://connect-safari; daf://go/review and the like open a place, for Shortcuts.
@MainActor
enum Links {
    /// What was saved, for the self-test.
    static var saved: [String] = []

    static func handle(_ url: URL) {
        guard let scheme = url.scheme, scheme == "daf" || scheme == "daf-selftest" else { return }
        let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let value = { (k: String) in q.first { $0.name == k }?.value.flatMap { $0.isEmpty ? nil : $0 } }
        switch url.host {
        case "save":
            guard let link = value("url") ?? value("text").flatMap(firstLink) else { return AppModel.shared.say("There was no link to save") }
            Task { await save(link, title: value("title")) }
        case "connect-safari":
            Task { _ = await Safari.connect(again: value("stale") != nil) }
        case "go":
            go(url.pathComponents.dropFirst().first ?? "today")
        default: break
        }
    }

    static func save(_ link: String, title: String?) async {
        var body: [String: Any] = ["url": link]
        if let title { body["title"] = title }
        do {
            try await API.shared.send("POST", "/api/add/link", body)
            saved.append(link)
            AppModel.shared.say("Saved to the Library")
            if case .library = AppModel.shared.place { AppModel.shared.reload() }
        } catch {
            AppModel.shared.error = "Daf didn't save the link: " + error.localizedDescription
        }
    }

    static func go(_ route: String) {
        let m = AppModel.shared
        let places: [String: Place] = ["today": .today, "review": .review, "inbox": .library("inbox"), "library": .library("inbox"),
                                       "later": .library("later"), "archive": .library("archive"), "shortlist": .shortlist, "feed": .feed(nil),
                                       "books": .books, "manga": .manga, "torah": .torah, "podcasts": .podcasts, "highlights": .highlights,
                                       "stats": .stats, "sources": .sources, "paper": .paper, "recovery": .recovery]
        if let p = places[route] { m.place = p } else { m.openRoute = "#" + route }
        NSApp.activate()
    }

    /// The first http(s) address in a piece of text.
    static func firstLink(_ s: String) -> String? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let r = t.range(of: #"https?://\S+"#, options: .regularExpression) else { return nil }
        return String(t[r])
    }
}

/// This Mac's device token (Authorization: Bearer), for what Daf asks a device for rather than a
/// signed-in window: the new-post alerts. The web-view Daf kept it in the login keychain under the
/// same name, so it carries over; a new one is made with the sign-in when there's none. The test
/// build is given its own and never touches the keychain.
@MainActor
enum DeviceToken {
    private static let service = "xyz.tiresia.daf", account = "device token"
    private static var testing: Bool { UserDefaults.standard.string(forKey: "SelfTestOut") != nil }
    private static var cached: String?

    static var value: String? {
        if let cached { return cached }
        if testing {
            cached = UserDefaults.standard.string(forKey: "SelfTestToken").map { $0.hasPrefix("t:") ? String($0.dropFirst(2)) : $0 }
            return cached
        }
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                kSecAttrAccount as String: account, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var out: CFTypeRef?
        if SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data { cached = String(data: d, encoding: .utf8) }
        return cached
    }

    /// The token, made now with the sign-in if there isn't one.
    static func ensure() async -> String? {
        if let v = value, !v.isEmpty { return v }
        guard !testing, let r = J(try? await API.shared.send("POST", "/api/devices", ["name": "mac"])), let t = r.s("token") else { return nil }
        let base: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
        SecItemDelete(base as CFDictionary)
        var add = base
        add[kSecValueData as String] = Data(t.utf8)
        add[kSecAttrLabel as String] = "Daf device token"
        SecItemAdd(add as CFDictionary, nil)
        cached = t
        return t
    }

    /// Daf stopped knowing it (a 401): the next ask makes another.
    static func forget() {
        cached = nil
        guard !testing else { return }
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account] as CFDictionary)
    }
}

/// Daf in Safari (the web extension in DafSafari.appex): the app makes its token, a device of its
/// own called "safari", with my sign-in, and leaves it with Daf's address in the app group, where
/// the extension's native half (mac/DafSafari) hands it over. Nothing to paste.
@MainActor
enum Safari {
    static var identifier: String { (Bundle.main.bundleIdentifier ?? "xyz.tiresia.daf") + ".safari" }

    static var group: UserDefaults? {
        guard let g = Bundle.main.object(forInfoDictionaryKey: "DafAppGroup") as? String, !g.isEmpty else { return nil }
        return UserDefaults(suiteName: g)
    }

    /// Settings → Daf for Safari: a token if there isn't one, then Safari's settings, where it's switched on.
    static func setUp() async {
        if let problem = await connect(again: false) {
            let a = NSAlert()
            a.messageText = "Daf for Safari"
            a.informativeText = problem
            a.runModal()
            return
        }
        do { try await SFSafariApplication.showPreferencesForExtension(withIdentifier: identifier) }
        catch { NSWorkspace.shared.open(URL(fileURLWithPath: "/Applications/Safari.app")) }
    }

    /// Nil when it worked, otherwise what to say.
    static func connect(again: Bool) async -> String? {
        guard let shared = group else { return "This build of Daf isn't signed for Safari. Build it with your Apple Development identity." }
        if !again, let t = shared.string(forKey: "safari.token"), !t.isEmpty, shared.string(forKey: "safari.url") == API.shared.base.absoluteString { return nil }
        do {
            let r = J(try await API.shared.send("POST", "/api/devices", ["name": "safari"]))
            guard let token = r?.s("token") else { return "Daf didn't give a token." }
            shared.set(token, forKey: "safari.token")
            shared.set(API.shared.base.absoluteString, forKey: "safari.url")
            shared.set(Date().timeIntervalSince1970, forKey: "safari.made")
            return nil
        } catch let e as APIError where e.status == 401 {
            return "Sign in to Daf first, then try again."
        } catch { return "Daf didn't answer: \(error.localizedDescription)" }
    }
}

/// New posts in the feeds set to tell me about (a feed's right-click → Tell Me About New Posts), as
/// Mac notifications, as the web-view Daf and the phone have them: every five minutes, Daf's own
/// order of arrival as the cursor, so nothing rings twice and the backlog never does. A click opens
/// the post.
@MainActor
final class FeedNews: NSObject, UNUserNotificationCenterDelegate {
    static let shared = FeedNews()
    private static let onKey = "feedNews.on", cursorKey = "feedNews.cursor"
    /// For the self-test: the last answer.
    var last: J?

    var on: Bool { UserDefaults.standard.bool(forKey: Self.onKey) }

    func install() {
        if on, Bundle.main.bundleIdentifier != nil { UNUserNotificationCenter.current().delegate = self }
    }

    /// Turned on (a feed's switch, or Settings): permission once, then the five-minute look includes this.
    @discardableResult
    func enable() async -> Bool {
        UserDefaults.standard.set(true, forKey: Self.onKey)
        UNUserNotificationCenter.current().delegate = self
        let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])) ?? false
        await check()
        return granted
    }

    func disable() {
        UserDefaults.standard.set(false, forKey: Self.onKey)
        UserDefaults.standard.removeObject(forKey: Self.cursorKey)
    }

    func check(force: Bool = false) async {
        guard on || force, let token = await DeviceToken.ensure() else { return }
        let d = UserDefaults.standard
        let cursor = d.object(forKey: Self.cursorKey) as? Int ?? -1
        let r: J
        do { r = try await API.shared.device("/api/phone/feed-news?cursor=\(cursor)", token: token) }
        catch let e as APIError where e.status == 401 { DeviceToken.forget(); return }
        catch { return }
        last = r
        if r.i("feeds") == 0 && !force { disable(); return }          // nothing set to tell me about any more
        if cursor >= 0 && !force {
            for item in r.a("items") {
                let c = UNMutableNotificationContent()
                c.title = item.s("title") ?? "A new post"
                c.subtitle = item.s("source") ?? ""
                c.userInfo = ["route": item.s("route") ?? ""]
                c.threadIdentifier = "feed"
                try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: item.s("id") ?? UUID().uuidString, content: c, trigger: nil))
            }
        }
        if let n = r.i("cursor") { d.set(n, forKey: Self.cursorKey) }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler done: @escaping () -> Void) {
        let route = response.notification.request.content.userInfo["route"] as? String
        Task { @MainActor in
            if let route, !route.isEmpty { AppModel.shared.openRoute = route; NSApp.activate() }
            done()
        }
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound])
    }
}

/// The first time this app runs as Daf, where the web-view Daf was: its address, its menu bar
/// choice and its sign-in (the window's cookie, from WebKit's store) carry over.
@MainActor
enum Migration {
    static func run() async {
        guard Bundle.main.bundleIdentifier == "xyz.tiresia.daf" else { return }
        let d = UserDefaults.standard
        if d.string(forKey: API.baseKey) == nil, let old = d.string(forKey: "baseURL") { d.set(old, forKey: API.baseKey) }
        if !d.bool(forKey: "migrated.native") {            // once: the web-view Daf's menu bar choice (shown unless turned off)
            d.set(true, forKey: "migrated.native")
            d.set(d.object(forKey: "menuBarShown") as? Bool ?? true, forKey: "menuBar")
        }
        if !d.bool(forKey: "migrated.copy") {              // once: the web-view Daf's offline copy of the page, unused now
            d.set(true, forKey: "migrated.copy")
            for name in ["app", "data", "kept.json", "localStorage.json"] { try? FileManager.default.removeItem(at: Store.dir.appendingPathComponent(name)) }
        }
        guard API.shared.cookie == nil, let host = API.shared.base.host else { return }
        let old = await WKWebsiteDataStore.default().httpCookieStore.allCookies()
        if let c = old.first(where: { $0.name == "daf" && (host == $0.domain || host.hasSuffix("." + $0.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")))) }) {
            HTTPCookieStorage.shared.setCookie(c)
            AppModel.shared.needsSignIn = false
            AppModel.shared.reload()
        }
    }
}
