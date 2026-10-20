import AppKit
import SafariServices
import WebKit

/// Daf in Safari (the web extension in DafSafari.appex): the app makes the extension's token,
/// a device of its own called "safari" so the one in Zen stays as it is, with the sign-in the
/// window already has, and leaves it with Daf's address in the app group, where the extension's
/// native half hands it over (mac/DafSafari). Nothing to paste.
@MainActor
enum SafariExtension {
    static let identifier = (Bundle.main.bundleIdentifier ?? "xyz.tiresia.daf") + ".safari"

    /// The app group both share ("<team>.xyz.tiresia.daf"); none in an ad hoc build.
    static var shared: UserDefaults? {
        guard let g = Bundle.main.object(forInfoDictionaryKey: "DafAppGroup") as? String, !g.isEmpty else { return nil }
        return UserDefaults(suiteName: g)
    }

    /// Daf → Safari Extension…: a token if there isn't one yet, then Safari's settings, where the
    /// extension is switched on.
    static func setUp() {
        Task { @MainActor in
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
    }

    /// daf://connect-safari, from the extension when it has no token or Daf stopped knowing it.
    static func handle(_ url: URL) {
        let stale = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "stale" }?.value
        Task { @MainActor in _ = await connect(again: stale != nil) }
    }

    /// Makes the token and leaves it for the extension. Nil when it worked, otherwise what to say.
    static func connect(again: Bool) async -> String? {
        guard let shared else { return "This build of Daf isn't signed for Safari. Build it with your Apple Development identity." }
        if !again, let t = shared.string(forKey: "safari.token"), !t.isEmpty, shared.string(forKey: "safari.url") == Server.base.absoluteString {
            return nil
        }
        let cookies = await WKWebsiteDataStore.default().httpCookieStore.allCookies()
            .filter { c in Server.base.host.map { $0 == c.domain || $0.hasSuffix("." + c.domain.trimmingCharacters(in: CharacterSet(charactersIn: "."))) } ?? false }
        guard !cookies.isEmpty else { return "Sign in to Daf in its window first, then try again." }
        var req = URLRequest(url: Server.url("/api/devices"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        HTTPCookie.requestHeaderFields(with: cookies).forEach { req.setValue($1, forHTTPHeaderField: $0) }
        req.httpBody = Data(#"{"name":"safari"}"#.utf8)
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if status == 401 { return "Sign in to Daf in its window first, then try again." }
            guard status == 200, let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let token = body["token"] as? String, !token.isEmpty else { return "Daf answered \(status)." }
            shared.set(token, forKey: "safari.token")
            shared.set(Server.base.absoluteString, forKey: "safari.url")
            shared.set(Date().timeIntervalSince1970, forKey: "safari.made")
            return nil
        } catch {
            return "Daf didn't answer: \(error.localizedDescription)"
        }
    }
}
