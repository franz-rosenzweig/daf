import AppKit
import SwiftUI
import WebKit

// Settings › Connections › Instagram and AniList, as the page has them (web/social.js, web/anilist.js).

/// The Instagram sign-in Daf fetches reels with: whether it's there and when it was renewed, Sign In
/// (Instagram's own page, in a window here), the switch that lets the browser extension keep it
/// fresh, the reels waiting for it, and Forget It.
struct InstagramSection: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?
    @State private var signingIn = false

    private static let by = ["web": "the web page", "browser": "the browser extension", "safari": "Safari"]

    var body: some View {
        Section {
            Text("Share a reel to Daf (or save its link) and Daf keeps the video, its caption and a transcript you can highlight. To fetch it, Daf uses your own Instagram sign-in, kept on your server and nowhere else.")
                .font(.callout).foregroundStyle(.secondary)
            if let s {
                LabeledContent {
                    HStack {
                        if s.b("signed_in") { Button("Forget It") { Task { await forget() } } }
                        Button(s.b("signed_in") ? "Sign In Again…" : "Sign In to Instagram…") { signingIn = true }
                    }
                } label: {
                    Text("Sign-in")
                    Text(state(s)).foregroundStyle(s.d("expired") != nil ? .red : .secondary)
                }
                Toggle(isOn: Binding(get: { s.b("from_browser") }, set: { on in Task { await fromBrowser(on) } })) {
                    Text("Keep Daf signed in from my browser")
                    Text("When you're on instagram.com in a browser with the Daf extension, it sends Instagram's sign-in to Daf whenever it has changed, so Daf's never runs out. Only instagram.com's cookies, only to your Daf.")
                }
                if let n = s.i("waiting"), n > 0 {
                    let ok = s.b("signed_in") && s.d("expired") == nil
                    LabeledContent("Waiting", value: (n == 1 ? "1 reel is" : "\(n) reels are") + " waiting for a sign-in. "
                                   + (ok ? (n == 1 ? "It's on its way." : "They're on their way.") : (n == 1 ? "It comes in by itself" : "They come in by themselves") + " once Daf has one."))
                }
            } else { ProgressView().controlSize(.small) }
        } header: { Text("Instagram") }
        .id("instagram")
        .task { s = try? await API.shared.json("/api/instagram") }
        .sheet(isPresented: $signingIn) {
            InstagramSignIn { ok in
                signingIn = false
                Task {
                    s = try? await API.shared.json("/api/instagram")
                    if ok { model.say("Signed in to Instagram") }
                }
            }
        }
    }

    private func state(_ s: J) -> String {
        if let t = s.d("expired") { return "Instagram turned the sign-in away " + TodayView.ago(t) + ". Sign in again to renew it." }
        if s.b("signed_in") {
            let by = s.s("by").map { Self.by[$0] ?? ($0.hasPrefix("android") ? "the Android app" : $0.hasPrefix("mac") ? "the Mac app" : $0) }
            return "Signed in. Renewed " + TodayView.ago(s.d("updated")) + (by.map { " by " + $0 } ?? "") + "."
        }
        return "Not signed in yet. Reels need it: Instagram shows almost nothing to a visitor."
    }

    private func fromBrowser(_ on: Bool) async {
        do {
            s = J(try await API.shared.send("PUT", "/api/instagram", ["from_browser": on]))
            model.say(on ? "The extension keeps Daf signed in to Instagram" : "The extension won't send Instagram's sign-in")
        } catch { model.error = error.localizedDescription }
    }

    private func forget() async {
        do {
            s = J(try await API.shared.send("DELETE", "/api/instagram/cookies", nil))
            model.say("Daf forgot the Instagram sign-in")
        } catch { model.error = error.localizedDescription }
    }
}

/// Instagram's own sign-in page in a window that keeps nothing on this Mac. Once Instagram has
/// signed you in (its sessionid cookie), its cookies go to Daf (/api/instagram/cookies) with this
/// Mac's device token, and the window closes. The cookies are never written anywhere else, or logged.
struct InstagramSignIn: View {
    let done: (Bool) -> Void
    @State private var status = "Sign in as you would on instagram.com. Daf takes the sign-in once you're in."
    @State private var sent = false

    var body: some View {
        VStack(spacing: 0) {
            InstagramWeb { cookies in
                guard !sent else { return }
                sent = true
                status = "Signed in. Sending it to Daf…"
                Task {
                    do {
                        try await Self.send(cookies)
                        done(true)
                    } catch {
                        sent = false
                        status = error.localizedDescription
                    }
                }
            }
            Divider()
            HStack {
                Text(status).font(.callout).foregroundStyle(.secondary).lineLimit(2)
                Spacer()
                Button("Cancel") { done(false) }.keyboardShortcut(.cancelAction)
            }
            .padding(12)
        }
        .frame(width: 460, height: 700)
    }

    /// Instagram's cookies to Daf, as an app's sign-in sends them: with the device token (so Daf
    /// says the Mac app renewed it), else the sign-in.
    static func send(_ cookies: [HTTPCookie]) async throws {
        let list: [[String: Any]] = cookies.map { c in
            ["name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
             "expires": Int(c.expiresDate?.timeIntervalSince1970 ?? 0), "secure": c.isSecure]
        }
        guard let token = await DeviceToken.ensure() else {
            try await API.shared.send("POST", "/api/instagram/cookies", ["cookies": list])
            return
        }
        var r = URLRequest(url: API.shared.url("/api/instagram/cookies"))
        r.httpMethod = "POST"
        r.httpShouldHandleCookies = false
        r.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try JSONSerialization.data(withJSONObject: ["cookies": list])
        let (data, response) = try await API.shared.session.data(for: r)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
            throw APIError(status: status, message: detail ?? "Daf answered \(status).")
        }
    }
}

/// instagram.com/accounts/login in a web view with a store of its own that isn't kept; it calls
/// back once the store holds a signed-in session.
struct InstagramWeb: NSViewRepresentable {
    let signedIn: ([HTTPCookie]) -> Void

    init(_ signedIn: @escaping ([HTTPCookie]) -> Void) { self.signedIn = signedIn }

    func makeCoordinator() -> Watcher { Watcher(signedIn) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        let web = WKWebView(frame: .zero, configuration: config)
        config.websiteDataStore.httpCookieStore.add(context.coordinator)
        context.coordinator.store = config.websiteDataStore.httpCookieStore
        web.load(URLRequest(url: URL(string: "https://www.instagram.com/accounts/login/")!))
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {}

    static func dismantleNSView(_ web: WKWebView, coordinator: Watcher) {
        coordinator.store?.remove(coordinator)
        web.stopLoading()
    }

    final class Watcher: NSObject, WKHTTPCookieStoreObserver {
        let signedIn: ([HTTPCookie]) -> Void
        weak var store: WKHTTPCookieStore?

        init(_ signedIn: @escaping ([HTTPCookie]) -> Void) { self.signedIn = signedIn }

        func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
            cookieStore.getAllCookies { all in
                let ig = all.filter { $0.domain.hasSuffix("instagram.com") }
                guard ig.contains(where: { $0.name == "sessionid" && !$0.value.isEmpty }) else { return }
                DispatchQueue.main.async { self.signedIn(ig) }
            }
        }
    }
}

/// AniList: the sign-in Daf's manga tracker sets your progress on AniList with, every hour.
/// Connect opens AniList in the browser, which comes back to Daf's own page.
struct AniListSection: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?
    @State private var clientID = ""

    var body: some View {
        Section {
            Text("Every hour Daf's manga tracker works out how far you've read each series (on the Kindle, in Daf, in Komga) and sets it on AniList, turning volumes into chapters. It never lowers what AniList has.")
                .font(.callout).foregroundStyle(.secondary)
            if let s {
                LabeledContent {
                    if s.s("client_id") != nil {
                        HStack {
                            if s.b("connected") && !s.b("expired") { Button("Forget It") { Task { await forget() } } }
                            if let u = s.s("authorize").flatMap(URL.init(string:)) {
                                Button(s.b("connected") ? "Connect Again…" : "Connect AniList…") { NSWorkspace.shared.open(u) }
                            }
                        }
                    }
                } label: {
                    Text("Sign-in")
                    Text(state(s)).foregroundStyle(s.b("expired") ? .red : .secondary)
                }
                if let lr = s.o("last_run"), lr.s("summary") != nil || failed(s) {
                    LabeledContent {
                        EmptyView()
                    } label: {
                        Text("Last update")
                        Text(TodayView.ago(lr.d("at")) + ": " + (failed(s) ? lr.s("error") ?? "" : lr.s("summary") ?? ""))
                            .foregroundStyle(failed(s) ? .red : .secondary)
                    }
                }
                DisclosureGroup("The AniList client (once)") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("1. On AniList, open Settings → Developer and press Create New Client.")
                        HStack(alignment: .firstTextBaseline) {
                            Text("2. Name it Daf, and for the Redirect URL paste \(s.s("redirect") ?? "") exactly as it is. If Connect doesn't bring you back to Daf, this is usually why.")
                            Button("Copy") {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(s.s("redirect") ?? "", forType: .string)
                            }
                        }
                        Text("3. Save, then paste its Client ID (a number) here. Daf doesn't need the secret.")
                        HStack {
                            TextField("Client ID", text: $clientID).frame(width: 140)
                            Button("Save") { Task { await save() } }
                            Spacer()
                            Link("AniList's developer settings", destination: URL(string: "https://anilist.co/settings/developer")!)
                        }
                    }
                    .font(.callout)
                    .textSelection(.enabled)
                }
            } else { ProgressView().controlSize(.small) }
        } header: { Text("AniList") }
        .id("anilist")
        .task { await load() }
    }

    private func failed(_ s: J) -> Bool { s.o("last_run")?.s("error") != nil && s.b("connected") && !s.b("expired") }

    private func state(_ s: J) -> String {
        let day = { (t: Double?) in t.map { Date(timeIntervalSince1970: $0).formatted(date: .long, time: .omitted) } ?? "" }
        if s.b("expired") { return "The AniList sign-in ran out on " + day(s.d("expires_at")) + ". Connect again to renew it." }
        if s.b("connected") {
            let soon = (s.d("expires_at") ?? .infinity) - Date().timeIntervalSince1970 < 21 * 86400
            return "Connected as " + (s.o("user")?.s("name") ?? "") + ", until " + day(s.d("expires_at")) + "." + (soon ? " Renew it soon." : "")
        }
        return "Not connected yet."
    }

    private func load() async {
        s = try? await API.shared.json("/api/anilist")
        clientID = s?.s("client_id") ?? ""
    }

    private func save() async {
        do {
            s = J(try await API.shared.send("PUT", "/api/anilist", ["client_id": clientID.trimmingCharacters(in: .whitespaces)]))
            model.say("Saved. Now Connect AniList.")
        } catch { model.error = error.localizedDescription }
    }

    private func forget() async {
        do {
            try await API.shared.send("DELETE", "/api/anilist", nil)
            model.say("Daf forgot the AniList sign-in")
            await load()
        } catch { model.error = error.localizedDescription }
    }
}
