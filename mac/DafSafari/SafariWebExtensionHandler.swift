import AppKit
import SafariServices

/// The Safari extension's native half. The web extension (extension/, built for Safari, with
/// safari.js) asks for Daf's address and its token; the Daf app made the token and left it in the
/// app group (Daf/SafariExtension.swift). With none there yet, or one Daf no longer knows, it asks
/// the app for a new one (daf://connect-safari) and the extension asks again a moment later.
@objc(SafariWebExtensionHandler)
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
    func beginRequest(with context: NSExtensionContext) {
        let item = context.inputItems.first as? NSExtensionItem
        let message = item?.userInfo?[SFExtensionMessageKey] as? [String: Any] ?? [:]
        var answer: [String: Any] = ["error": "unknown request"]
        if message["op"] as? String == "connect" {
            answer = connect(stale: message["stale"] as? String)
        }
        let reply = NSExtensionItem()
        reply.userInfo = [SFExtensionMessageKey: answer]
        context.completeRequest(returningItems: [reply], completionHandler: nil)
    }

    private func connect(stale: String?) -> [String: Any] {
        guard let g = Bundle.main.object(forInfoDictionaryKey: "DafAppGroup") as? String, !g.isEmpty,
              let shared = UserDefaults(suiteName: g) else { return ["error": "This build of Daf isn't signed for Safari."] }
        if let token = shared.string(forKey: "safari.token"), !token.isEmpty, token != stale {
            return ["url": shared.string(forKey: "safari.url") ?? "https://daf.tiresia.xyz", "token": token]
        }
        // the app makes one with its sign-in; once a minute at most
        let now = Date().timeIntervalSince1970
        if now - shared.double(forKey: "safari.asked") > 60 {
            shared.set(now, forKey: "safari.asked")
            var u = URLComponents(string: "daf://connect-safari")!
            if stale != nil { u.queryItems = [URLQueryItem(name: "stale", value: "1")] }
            if let url = u.url { NSWorkspace.shared.open(url) }
        }
        return ["pending": true]
    }
}
