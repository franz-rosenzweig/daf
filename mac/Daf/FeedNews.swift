import AppKit
import UserNotifications

/// New posts from the feeds set to notify (the Feed's sources sheet → a feed → "Notify me of new
/// posts"), as macOS notifications. The menu bar's five-minute look (Today.refresh) asks
/// /api/phone/feed-news with this Mac's token; clicking a notification opens the post in Daf.
/// The cursor is Daf's own order of arrival, so nothing rings twice and the backlog never does.
@MainActor
final class FeedNews: NSObject, UNUserNotificationCenterDelegate {
    static let shared = FeedNews()
    private static let onKey = "feedNews.on", cursorKey = "feedNews.cursor"

    var on: Bool { UserDefaults.standard.bool(forKey: Self.onKey) }

    /// The page asks (dafShell.alerts): permission once, then the five-minute look includes this.
    func start() async -> Bool {
        UserDefaults.standard.set(true, forKey: Self.onKey)
        UNUserNotificationCenter.current().delegate = self
        let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])) ?? false
        await check()
        return granted
    }

    func install() {
        if on { UNUserNotificationCenter.current().delegate = self }
    }

    func check() async {
        guard on else { return }
        let d = UserDefaults.standard
        let cursor = d.object(forKey: Self.cursorKey) as? Int ?? -1
        guard let r = try? await Client.feedNews(cursor: cursor) else { return }
        if r.feeds == 0 {                       // nothing set to notify any more
            d.set(false, forKey: Self.onKey)
            d.removeObject(forKey: Self.cursorKey)
            return
        }
        if cursor >= 0 {
            for item in r.items {
                let c = UNMutableNotificationContent()
                c.title = item.title
                c.subtitle = item.source
                c.userInfo = ["route": item.route]
                c.threadIdentifier = "feed"
                try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: item.id, content: c, trigger: nil))
            }
        }
        d.set(r.cursor, forKey: Self.cursorKey)
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                            withCompletionHandler done: @escaping () -> Void) {
        let route = response.notification.request.content.userInfo["route"] as? String
        Task { @MainActor in
            if let route { DafWindowController.show(route); NSApp.bringForward() }
            done()
        }
    }

    /// Shown while Daf is in front, too.
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                            withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .sound])
    }
}
