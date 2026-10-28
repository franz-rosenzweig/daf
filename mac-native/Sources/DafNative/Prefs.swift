import AppKit
import SwiftUI
import UniformTypeIdentifiers

// The rest of Daf's preferences, as the page has them (web/app.js renderPrefs and its cards), each
// a tab in Settings: Account, Connections, AI, Library Tags, Import. And Help › Send Feedback….

/// A token shown once, to copy.
struct TokenBox: View {
    let token: String
    let note: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(note).font(.caption).foregroundStyle(.secondary)
            HStack {
                Text(token).font(.system(.callout, design: .monospaced)).textSelection(.enabled).lineLimit(2)
                Spacer()
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(token, forType: .string)
                }
            }
        }
    }
}

func whenSeen(_ d: J) -> String {
    let made = d.d("created").map { "Connected " + Date(timeIntervalSince1970: $0).formatted(date: .abbreviated, time: .omitted) } ?? "Connected"
    return made + (d.d("last_seen").map { ", last used " + TodayView.ago($0) } ?? ", not used yet")
}

// MARK: Account

/// The username and password, the other browsers, the connected devices and the browser extension's token.
struct AccountPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var user = ""
    @State private var signedAs = ""
    @State private var newPassword = ""
    @State private var current = ""
    @State private var devices: [J] = []
    @State private var browserToken: String?
    @State private var confirmOthers = false
    @State private var disconnect: String?

    private static let labels = ["kindle": "The Kindle (Daf plugin)", "phone": "The phone (Tasker and the widget)", "mac": "Daf for Mac",
                                 "android": "Daf for Android", "safari": "Safari extension (connected by Daf for Mac)", "antennapod": "AntennaPod (podcasts)"]

    var body: some View {
        Form {
            Section {
                TextField("Username", text: $user)
                SecureField("New password", text: $newPassword)
                SecureField("Current password", text: $current)
                HStack { Spacer(); Button("Save") { Task { await save() } }.disabled(current.isEmpty || (user == signedAs && newPassword.isEmpty)) }
            } header: { Text("Signed in as \(signedAs)") } footer: {
                Text("A new password is optional, at least 10 characters, and signs out every other browser. The current password is needed for either change.").foregroundStyle(.secondary)
            }
            Section {
                LabeledContent("Other browsers") { Button("Sign Them Out…") { confirmOthers = true } }
            } footer: { Text("The Kindle, the phone, the apps and AntennaPod use their own tokens and stay connected.").foregroundStyle(.secondary) }
            Section {
                ForEach(devices.filter { $0.s("name") != "browser" }, id: \.self) { d in
                    let name = d.s("name") ?? ""
                    LabeledContent {
                        Button("Disconnect…") { disconnect = name }
                    } label: {
                        Text(Self.label(name))
                        Text(whenSeen(d))
                    }
                }
                let br = devices.first { $0.s("name") == "browser" }
                LabeledContent {
                    HStack {
                        Button(br == nil ? "Make a Token" : "New Token") { Task { await makeBrowserToken() } }
                        if br != nil { Button("Disconnect…") { disconnect = "browser" } }
                    }
                } label: {
                    Text("Browser extension")
                    Text(br.map { whenSeen($0) + ". A new token replaces it." } ?? "Highlight on any web page and keep it in Daf.")
                }
                if let browserToken { TokenBox(token: browserToken, note: "Paste it into the extension's options now; Daf only shows it once.") }
            } header: { Text("Connected devices") } footer: {
                Text("Each has its own token. Disconnecting one stops it until it connects again.").foregroundStyle(.secondary)
            }
            Section { Button("Sign Out") { Task { await signOut() } } }
        }
        .formStyle(.grouped)
        .task { await load() }
        .confirmationDialog("Sign out every other browser?", isPresented: $confirmOthers) {
            Button("Sign Them Out") { Task { await signOutOthers() } }
        }
        .confirmationDialog("Disconnect \(Self.label(disconnect ?? ""))?", isPresented: Binding(get: { disconnect != nil }, set: { if !$0 { disconnect = nil } })) {
            Button("Disconnect", role: .destructive) { if let d = disconnect { Task { await off(d) } } }
        } message: {
            Text(disconnect == "kindle" ? "It stops sending pages and highlights until a new token is made on the server and put on the Kindle." : "It stops until it connects again.")
        }
    }

    static func label(_ name: String) -> String {
        if let l = labels[name] { return l }
        if name.hasPrefix("android-") { return "Daf for Android · " + name.dropFirst(8).uppercased() }
        return name == "browser" ? "the browser extension" : name
    }

    private func load() async {
        signedAs = (try? await API.shared.json("/api/me"))?.s("user") ?? ""
        if user.isEmpty { user = signedAs }
        devices = (try? await API.shared.json("/api/phone"))?.a("devices") ?? []
    }

    private func save() async {
        let u = user.trimmingCharacters(in: .whitespaces).lowercased()
        do {
            let r = J(try await API.shared.send("POST", "/api/account", ["current": current, "user": u != signedAs ? u : "", "password": newPassword]))
            model.say(r?.b("signed_out_others") == true ? "Saved. Other browsers are signed out." : "Saved")
            current = ""
            newPassword = ""
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func signOutOthers() async {
        do { try await API.shared.send("POST", "/api/account/signout-others", [:]); model.say("Every other browser is signed out") }
        catch { model.error = error.localizedDescription }
    }

    private func makeBrowserToken() async {
        do {
            browserToken = J(try await API.shared.send("POST", "/api/devices", ["name": "browser"]))?.s("token")
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func off(_ name: String) async {
        disconnect = nil
        do {
            try await API.shared.send("DELETE", "/api/devices/" + API.enc(name), nil)
            if name == "browser" { browserToken = nil }
            model.say("Disconnected")
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func signOut() async {
        _ = try? await API.shared.send("POST", "/api/logout", [:])
        API.shared.signOut()
        model.needsSignIn = true
    }
}

// MARK: Connections

/// The phone, AntennaPod, Hardcover, newsletters and the morning email.
struct ConnectionsPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var phone: J?
    @State private var phoneToken: String?
    @State private var pod: J?
    @State private var podToken: String?
    @State private var hc: J?
    @State private var settings: J?
    @State private var digest: J?
    @State private var user = ""

    private var base: String { (settings?.s("public_url") ?? API.shared.base.absoluteString).replacingOccurrences(of: "/+$", with: "", options: .regularExpression) }

    var body: some View {
        ScrollViewReader { proxy in
            Form {
                phoneSection
                podSection
                hcSection
                NewslettersSection()
                digestSection
                InstagramSection()
                AniListSection()
            }
            .formStyle(.grouped)
            .task {
                await load()
                // opened at a section (a reel that needs Instagram, the Podcasts page)
                if let at = UserDefaults.standard.string(forKey: "prefsFocus") {
                    UserDefaults.standard.removeObject(forKey: "prefsFocus")
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    withAnimation { proxy.scrollTo(at, anchor: .top) }
                }
            }
        }
    }

    private func load() async {
        async let p = try? API.shared.json("/api/phone")
        async let a = try? API.shared.json("/api/podcasts")
        async let h = try? API.shared.json("/api/hardcover")
        async let s = try? API.shared.json("/api/settings")
        async let d = try? API.shared.json("/api/digest")
        async let me = try? API.shared.json("/api/me")
        phone = await p
        pod = await a
        hc = await h
        settings = await s
        digest = await d
        let who = await me
        user = who?.s("user") ?? ""
    }

    @ViewBuilder private var phoneSection: some View {
        Section("Phone") {
            if let phone {
                let shown = phone.o("nudges")?.i("shown") ?? 0, followed = phone.o("nudges")?.i("followed") ?? 0
                let dev = phone.a("devices").first { $0.s("name") == "phone" }
                LabeledContent("The evening nudge", value: shown > 0 ? "\(shown) shown this week, \(followed) followed by reading within 30 minutes" : "Nothing shown this week yet")
                LabeledContent {
                    Button(dev == nil ? "Make a Token" : "New Token") { Task { await newPhoneToken() } }
                } label: {
                    Text("Phone token")
                    Text(dev.map { whenSeen($0) + ". A new one replaces it." } ?? "For Tasker and the widget.")
                }
                if let phoneToken { TokenBox(token: phoneToken, note: "Copy it now; Daf only shows it once.") }
                DisclosureGroup("Set up the nudge in Tasker") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("1. Profiles → + → Application: tick Instagram, Reddit, X and Discord, then back. Long-press the profile → Add → Time, from 21:00 to 03:00.")
                        Text("2. New task, call it Daf nudge. Add Net → HTTP Request: Method GET, URL \(base)/api/phone/nudge, Headers Authorization:Bearer \(phoneToken ?? "YOUR-TOKEN"), and tick Structure Output.")
                        Text("3. Add Task → If %http_data.show ~ true.")
                        Text("4. Add Alert → Notify: Title %http_data.title, Text %http_data.text. Under Actions, add Net → Browse URL %http_data.url so tapping it opens Daf.")
                        Text("5. Add Task → End If. Daf decides the rest: at most one nudge every 25 minutes, none once the hour is done.")
                    }
                    .font(.callout).textSelection(.enabled)
                }
                let inbox = phone.a("inbox").prefix(5).compactMap { $0.s("title") ?? $0.s("url") }
                if !inbox.isEmpty { LabeledContent("Shared to Daf", value: inbox.joined(separator: " · ")) }
            } else { ProgressView().controlSize(.small) }
        }
    }

    @ViewBuilder private var podSection: some View {
        Section("Podcasts (AntennaPod)") {
            if let pod {
                LabeledContent {
                    Button(pod.o("device") != nil || pod.b("device") ? "New Password" : "Make a Password") { Task { await newPodToken() } }
                } label: {
                    Text("Sync")
                    Text((pod.d("last_sync").map { "Last sync " + TodayView.ago($0) + ", " + plural(pod.a("subs").count, "subscription") + "." } ?? "Not connected yet.")
                         + " Listening shows on Today but never counts toward the hour.")
                }
                if let podToken { TokenBox(token: podToken, note: "The AntennaPod password. Daf only shows it once.") }
                Toggle("Transcribe episodes I play or open", isOn: Binding(get: { settings?.o("podcasts")?.raw["transcribe"] as? Bool != false }, set: { on in
                    guard var raw = settings?.raw else { return }
                    raw["podcasts"] = ["transcribe": on]
                    settings = J(raw)
                    Task {
                        do {
                            try await API.shared.send("PUT", "/api/settings", ["podcasts": ["transcribe": on]])
                            model.say(on ? "Episodes you play get transcripts" : "Transcripts only when you ask")
                        } catch { model.error = error.localizedDescription }
                    }
                }))
                DisclosureGroup("Set up AntennaPod") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("1. AntennaPod → Settings → Synchronization → gpodder.net.")
                        Text("2. Server: \(base) (AntennaPod may insist on https). Username: \(user). Password: the one above.")
                        Text("3. Pick or create the device AntennaPod, and let it sync.")
                        Text("4. To clip: in an episode, Share → with position, send it to Ezer. The minute before that point comes back transcribed, and lands in Highlights and the vault.")
                    }
                    .font(.callout).textSelection(.enabled)
                }
            } else { ProgressView().controlSize(.small) }
        }
        .id("podcasts")
    }

    @ViewBuilder private var hcSection: some View {
        Section("Hardcover") {
            if let hc {
                if !hc.b("connected") {
                    Text("Not connected: Daf needs HARDCOVER_API_KEY in the vault's settings file (see docs/OPERATIONS.md).").foregroundStyle(.secondary)
                } else {
                    let c = hc.o("counts")
                    LabeledContent("@" + (hc.s("user") ?? ""), value: ["Want to read", "Reading", "Read", "Paused", "Did not finish"]
                        .compactMap { k in c?.i(k).flatMap { $0 > 0 ? "\($0) \(k.lowercased())" : nil } }.joined(separator: " · "))
                    Text("\(hc.i("linked") ?? 0) of the books are linked, through the vault notes.").font(.caption).foregroundStyle(.secondary)
                    Toggle(isOn: setting("hc_progress")) {
                        Text("Send progress from Daf's reader")
                        Text("Forward only, never to a book I've finished. The Kindle's progress already goes up through the vault's own Hardcover sync.")
                    }
                    Toggle(isOn: setting("hc_autostart")) {
                        Text("Start books as Reading")
                        Text("A Want to Read book I begin in Daf moves to Reading on Hardcover.")
                    }
                    if let last = hc.o("last") {
                        Text("Last sent " + TodayView.ago(last.d("at")) + ": " + last.a("items").compactMap { $0.s("did") }.joined(separator: ", "))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            } else { ProgressView().controlSize(.small) }
        }
    }

    @ViewBuilder private var digestSection: some View {
        Section("Morning email") {
            if let g = digest {
                if !g.b("configured") {
                    Text("Needs Proton Mail Bridge on the server.").foregroundStyle(.secondary)
                } else {
                    let d = g.o("digest"), last = g.o("last"), new = g.o("now")?.i("new") ?? 0, feed = g.o("now")?.i("feed") ?? 0
                    Toggle(isOn: Binding(get: { d?.b("on") ?? false }, set: { on in Task { await putDigest(["on": on], on ? "The morning email is on, at " + Self.hour(d?.i("hour") ?? 6) : "No morning email") } })) {
                        Text("Send it")
                        Text(last?.b("sent") == true ? "The last one went " + TodayView.ago(last?.d("at")) + " with \(last?.i("new") ?? 0) new."
                             : last?.s("error").map { "The last one didn't go: " + $0 } ?? "Right now it would have \(new) new" + (feed > 0 ? " and \(feed) in the Feed." : "."))
                    }
                    Picker("At", selection: Binding(get: { d?.i("hour") ?? 6 }, set: { h in Task { await putDigest(["hour": h], "At " + Self.hour(h)) } })) {
                        ForEach(4...12, id: \.self) { h in Text(Self.hour(h)).tag(h) }
                    }
                    Toggle(isOn: Binding(get: { d?.b("feed") ?? false }, set: { on in Task { await putDigest(["feed": on], on ? "With the Feed" : "Without the Feed") } })) {
                        Text("The Feed too")
                        Text("How many new posts, by folder.")
                    }
                    HStack {
                        Spacer()
                        Button("See It") { Task { await preview() } }
                        Button("Send One Now") { Task { await sendDigest() } }
                    }
                }
            } else { ProgressView().controlSize(.small) }
        }
    }

    static func hour(_ h: Int) -> String { "\(h % 12 == 0 ? 12 : h % 12):00 " + (h < 12 ? "am" : "pm") }

    private func setting(_ k: String) -> Binding<Bool> {
        Binding(get: { (settings?.raw[k] as? Bool) != false }, set: { on in
            guard var raw = settings?.raw else { return }
            raw[k] = on
            settings = J(raw)
            Task {
                do { try await API.shared.send("PUT", "/api/settings", [k: on]); model.say("Saved") } catch { model.error = error.localizedDescription }
            }
        })
    }

    private func newPhoneToken() async {
        do { phoneToken = J(try await API.shared.send("POST", "/api/phone/token", [:]))?.s("token"); phone = try? await API.shared.json("/api/phone") }
        catch { model.error = error.localizedDescription }
    }

    private func newPodToken() async {
        do { podToken = J(try await API.shared.send("POST", "/api/podcasts/token", [:]))?.s("token"); pod = try? await API.shared.json("/api/podcasts") }
        catch { model.error = error.localizedDescription }
    }

    private func putDigest(_ body: [String: Any], _ said: String) async {
        do {
            if let r = J(try await API.shared.send("PUT", "/api/digest", body)), let d = r.o("digest"), var raw = digest?.raw {
                raw["digest"] = d.raw
                digest = J(raw)
            }
            model.say(said)
        } catch { model.error = error.localizedDescription }
    }

    private func sendDigest() async {
        do { model.say("Sent: " + (J(try await API.shared.send("POST", "/api/digest/send", [:]))?.s("subject") ?? "")) }
        catch { model.error = error.localizedDescription }
    }

    /// The email as it would go, in the browser (a file of its own, since the page needs the sign-in).
    private func preview() async {
        guard let data = try? await API.shared.data("/api/digest/preview") else { model.error = "The preview didn't come."; return }
        let u = FileManager.default.temporaryDirectory.appendingPathComponent("Daf morning email.html")
        try? data.write(to: u)
        NSWorkspace.shared.open(u)
    }
}

/// Newsletters: senders found in the Proton mailbox (read only); the ticked ones come into Library › Emails.
struct NewslettersSection: View {
    @Environment(AppModel.self) private var model
    @State private var r: J?
    @State private var chosen: Set<String> = []
    @State private var find = ""
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        Section {
            if let r {
                if !r.b("configured") {
                    Text("Needs Proton Mail Bridge on the server.").foregroundStyle(.secondary)
                } else {
                    Text("Daf reads the Proton mail through Bridge without marking anything read or moving it. Tick the senders whose emails belong in Daf, and their issues come into Library › Emails" + ((r.i("count") ?? 0) > 0 ? " (\(r.i("count") ?? 0) so far)." : "."))
                        .font(.callout).foregroundStyle(.secondary)
                    TextField("Find a sender", text: $find)
                    let all = r.a("senders").filter { find.isEmpty || ($0.s("name") ?? "").localizedCaseInsensitiveContains(find) || ($0.s("address") ?? "").localizedCaseInsensitiveContains(find) }
                    let likely = all.filter { $0.b("likely") || chosen.contains($0.s("address") ?? "") }
                    let rest = all.filter { !$0.b("likely") && !chosen.contains($0.s("address") ?? "") }
                    ForEach(likely, id: \.self) { row($0) }
                    if !rest.isEmpty {
                        DisclosureGroup("Other mail with an unsubscribe link (\(rest.count))") { ForEach(rest, id: \.self) { row($0) } }
                    }
                    HStack {
                        Text(status).font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Look Again") { Task { await load(fresh: true) } }.disabled(busy)
                        Button("Save") { Task { await save() } }.disabled(busy)
                    }
                }
            } else { ProgressView().controlSize(.small) }
        } header: { Text("Newsletters") }
        .task { await load(fresh: false) }
    }

    private func row(_ s: J) -> some View {
        let a = s.s("address") ?? ""
        return Toggle(isOn: Binding(get: { chosen.contains(a) }, set: { if $0 { chosen.insert(a) } else { chosen.remove(a) } })) {
            Text(s.s("name") ?? a)
            Text(a + " · \(s.i("count") ?? 0) in 45 days" + (s.s("last_subject").map { " · " + $0 } ?? "")).lineLimit(1)
        }
        .toggleStyle(.checkbox)
    }

    private func load(fresh: Bool) async {
        busy = true
        defer { busy = false }
        guard var got = try? await API.shared.json("/api/newsletters") else { return }
        if fresh, let scan = J(try? await API.shared.send("POST", "/api/newsletters/scan", [:])) {
            var raw = got.raw
            for (k, v) in scan.raw { raw[k] = v }
            got = J(raw)
        }
        r = got
        chosen = Set(got.strings("chosen"))
    }

    private func save() async {
        busy = true
        defer { busy = false }
        status = chosen.isEmpty ? "" : "Bringing in the last month…"
        do {
            let a = J(try await API.shared.send("PUT", "/api/newsletters", ["chosen": Array(chosen)]))
            status = a?.s("error") ?? (chosen.isEmpty ? "No newsletters" : "\(a?.i("imported") ?? 0) new in Library › Emails")
        } catch { status = ""; model.error = error.localizedDescription }
    }
}

// MARK: AI

/// What Daf asks the model, and which model: summaries and tags of what I save, the ready
/// questions, and the words Daf uses for each (Daf's own, or mine).
struct AIPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var a: J?
    @State private var questions = ""
    @State private var bookQuestions = ""
    @State private var drafts: [String: String] = [:]

    var body: some View {
        Form {
            if let a, let ai = a.o("ai") {
                Section {
                    Toggle(isOn: Binding(get: { ai.b("auto_summary") }, set: { on in Task { await put(["auto_summary": on], on ? "Summaries on" : "Summaries off: Summarize still works") } })) {
                        Text("Summaries of what I save")
                        Text("Two or three lines on every article in the Library, a few each sync. Off, Summarize still works one at a time.")
                    }
                    Toggle(isOn: Binding(get: { ai.b("auto_tags") }, set: { on in Task { await put(["auto_tags": on], on ? "New saves get tags" : "No tags from the model") } })) {
                        Text("Tags for what I save")
                        Text("Two to four on each new save in the Library, from the tags I already use where one fits. Never on a private one.")
                    }
                    Picker("Model", selection: Binding(get: { ai.s("model") ?? "" }, set: { m in
                        Task { await put(["model": m], "The model is " + Self.short(a.a("models").first { $0.s("id") == m }?.s("label") ?? m)) }
                    })) {
                        ForEach(a.a("models"), id: \.self) { m in Text(m.s("label") ?? "").tag(m.s("id") ?? "") }
                    }
                } footer: {
                    Text("Summaries, Ask, the meaning of a word in its sentence and flashcard suggestions. Private titles never go on their own (summaries skip them); what I ask about myself does.").foregroundStyle(.secondary)
                }
                Section("Ready questions") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("In an article's Ask, one a line")
                        TextEditor(text: $questions).font(.callout).frame(height: 64)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text("In a book's Ask")
                        TextEditor(text: $bookQuestions).font(.callout).frame(height: 64)
                    }
                    HStack { Spacer(); Button("Save") { Task { await put(["questions": lines(questions), "book_questions": lines(bookQuestions)], "Questions saved") } } }
                }
                Section {
                    let labels = a.o("labels"), own = ai.o("prompts")
                    ForEach((a.o("defaults")?.raw.keys.map { $0 } ?? []).sorted { order($0) < order($1) }, id: \.self) { k in
                        let lab = labels?.list(k).compactMap { $0 as? String } ?? []
                        let mine = (own?.s(k) ?? "").isEmpty == false
                        DisclosureGroup {
                            VStack(alignment: .leading, spacing: 6) {
                                Text((lab.count > 1 ? lab[1] + " " : "") + "Daf adds what it's about.").font(.caption).foregroundStyle(.secondary)
                                TextEditor(text: Binding(get: { drafts[k] ?? own?.s(k).flatMap { $0.isEmpty ? nil : $0 } ?? a.o("defaults")?.s(k) ?? "" }, set: { drafts[k] = $0 }))
                                    .font(.callout).frame(height: 90)
                                HStack {
                                    Spacer()
                                    if mine { Button("Daf's Own") { drafts[k] = nil; Task { await put(["prompts": [k: ""]], "Daf's own again") } } }
                                    Button("Save") { if let t = drafts[k] { Task { await put(["prompts": [k: t]], "Saved: " + (lab.first ?? k)) } } }.disabled(drafts[k] == nil)
                                }
                            }
                        } label: {
                            HStack { Text(lab.first ?? k); if mine { Text("mine").font(.caption2).padding(.horizontal, 5).background(.quaternary, in: Capsule()) } }
                        }
                    }
                } header: { Text("What Daf asks for each") } footer: {
                    Text("Each starts as Daf's own. One changed here is kept on the server for every device, and Daf's Own brings the original back.").foregroundStyle(.secondary)
                }
            } else { ProgressView() }
        }
        .formStyle(.grouped)
        .task { await load() }
    }

    private static let keys = ["summary", "ask", "ask_book", "word_en", "word_he", "card", "tags"]
    private func order(_ k: String) -> Int { Self.keys.firstIndex(of: k) ?? 99 }
    static func short(_ label: String) -> String { label.replacingOccurrences(of: " \\(.*", with: "", options: .regularExpression) }
    private func lines(_ s: String) -> [String] { s.split(separator: "\n").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }

    private func show(_ r: J) {
        a = r
        let ai = r.o("ai")
        let q = ai?.strings("questions") ?? [], bq = ai?.strings("book_questions") ?? []
        questions = (q.isEmpty ? r.strings("questions") : q).joined(separator: "\n")
        bookQuestions = (bq.isEmpty ? r.strings("book_questions") : bq).joined(separator: "\n")
    }

    private func load() async { if let r = try? await API.shared.json("/api/ai") { show(r) } }

    private func put(_ body: [String: Any], _ said: String) async {
        do {
            if let r = J(try await API.shared.send("PUT", "/api/ai", body)) { show(r) }
            if let p = body["prompts"] as? [String: String] { for k in p.keys { drafts[k] = nil } }
            model.say(said)
        } catch { model.error = error.localizedDescription }
    }
}

// MARK: Library tags

/// Every tag on saved articles, with how many use it: rename one (a name in use merges them),
/// remove one everywhere, and the tidy-up, where the model proposes merges and only the ticked ones happen.
struct TagsPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var st: J?
    @State private var find = ""
    @State private var picked: Set<Int> = []
    @State private var renaming: String?
    @State private var newName = ""
    @State private var removing: String?

    var body: some View {
        Form {
            if let st {
                let tags = st.a("tags"), once = tags.filter { $0.i("n") == 1 }.count
                let job = st.o("job"), busy = ["queued", "running"].contains(job?.s("status") ?? "")
                let tidy = st.o("tidy").flatMap { $0.a("changes").isEmpty ? nil : $0 }
                Section {
                    LabeledContent {
                        Button(tidy == nil ? "Propose a Tidy-Up" : "Propose Again") { Task { await propose() } }.disabled(busy)
                    } label: {
                        Text("Tidy up")
                        Text(busy ? "The model is looking at the list. This takes a minute or two."
                             : tidy.map { "Proposed " + TodayView.ago($0.d("at")) + ": tick what you want, then Apply." } ?? "The model proposes merges for the whole list. Nothing changes until you tick and apply.")
                    }
                    if job?.s("status") == "failed", !busy { Text("The last try didn't work: " + (job?.s("error") ?? "")).font(.caption).foregroundStyle(.secondary) }
                    if let tidy {
                        ForEach(tidy.a("changes"), id: \.self) { x in
                            let id = x.i("id") ?? -1
                            Toggle(isOn: Binding(get: { picked.contains(id) }, set: { if $0 { picked.insert(id) } else { picked.remove(id) } })) {
                                Text(x.strings("from").joined(separator: ", ") + " → " + (x.s("to").flatMap { $0.isEmpty ? nil : $0 } ?? "removed"))
                                Text(plural(x.i("docs") ?? 0, "article") + (x.s("why").map { " · " + $0 } ?? ""))
                            }
                            .toggleStyle(.checkbox)
                        }
                        HStack {
                            Spacer()
                            Button("Untick All") { picked = [] }
                            Button("Apply the Ticked Ones") { Task { await apply() } }.buttonStyle(.borderedProminent).disabled(picked.isEmpty)
                        }
                    }
                } footer: {
                    Text("\(plural(tags.count, "tag")) on saved articles" + (once > 0 ? ", \(once) of them used once" : "") + ". Renaming one to a name already in use merges the two.").foregroundStyle(.secondary)
                }
                Section {
                    TextField("Find a tag", text: $find)
                    ForEach(tags.filter { find.isEmpty || ($0.s("name") ?? "").localizedCaseInsensitiveContains(find) }, id: \.self) { t in
                        let name = t.s("name") ?? ""
                        LabeledContent {
                            HStack {
                                Text("\(t.i("n") ?? 0)").monospacedDigit().foregroundStyle(.secondary)
                                Button("Rename…") { newName = name; renaming = name }
                                Button("Remove…") { removing = name }
                            }
                        } label: { Text(name) }
                    }
                }
            } else { ProgressView() }
        }
        .formStyle(.grouped)
        .task { await load() }
        .task(id: working) {
            // the tidy-up runs on the server: look again every five seconds until it's done
            while working {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if Task.isCancelled { return }
                await load()
            }
        }
        .alert("Rename \u{201C}\(renaming ?? "")\u{201D}", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("New name", text: $newName)
            Button("Rename") { if let r = renaming { Task { await rename(r, to: newName.trimmingCharacters(in: .whitespaces)) } } }
            Button("Cancel", role: .cancel) { renaming = nil }
        } message: { Text("A name already in use merges them.") }
        .confirmationDialog("Remove the tag \u{201C}\(removing ?? "")\u{201D} from every article?", isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } })) {
            Button("Remove", role: .destructive) { if let r = removing { Task { await rename(r, to: "") } } }
        }
    }

    private var working: Bool { ["queued", "running"].contains(st?.o("job")?.s("status") ?? "") }

    private func load() async {
        guard let r = try? await API.shared.json("/api/doc-tags") else { return }
        let was = st?.o("tidy")?.d("at")
        st = r
        if r.o("tidy")?.d("at") != was { picked = Set(r.o("tidy")?.a("changes").compactMap { $0.i("id") } ?? []) }
    }

    private func propose() async {
        do { try await API.shared.send("POST", "/api/doc-tags/tidy", [:]); await load() } catch { model.error = error.localizedDescription }
    }

    private func apply() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/doc-tags/apply", ["ids": Array(picked)]))
            model.say(plural(r?.i("changed") ?? 0, "article") + " retagged")
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func rename(_ from: String, to: String) async {
        renaming = nil
        removing = nil
        guard to != from else { return }
        do {
            let r = J(try await API.shared.send("POST", "/api/doc-tags/rename", ["from": from, "to": to]))
            let n = plural(r?.i("changed") ?? 0, "article")
            model.say(to.isEmpty ? "Removed from " + n : n + " now say \u{201C}\(to)\u{201D}")
            await load()
        } catch { model.error = error.localizedDescription }
    }
}

// MARK: Import

/// An export file from another app: Daf says which app it's from and what's in it, then brings it
/// in in the background, a few links a second, and this follows along.
struct ImportPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var list: [J] = []
    @State private var reading: String?
    @State private var archived: Set<String> = []
    @State private var noFolders: Set<String> = []
    @State private var dropping = false

    private static let apps = [
        ("Instapaper", "Settings → Export → Download .CSV file. Instapaper's export has no highlights."),
        ("Readwise Reader", "Preferences → Export → Export library (CSV). Readwise highlights are already in Daf from the vault."),
        ("Raindrop.io", "Settings → Backups → Create new, then the CSV. Highlights come along."),
        ("GoodLinks", "Settings → Export → JSON. Highlights come along."),
        ("Wallabag", "Export → JSON. The articles' text and annotations come along."),
        ("Matter, Feedbin and others", "Any CSV or JSON with a column of links (url), with titles, tags and dates when it has them."),
        ("Feed readers (Feedly, Inoreader, NetNewsWire…)", "Export the subscriptions as OPML. They go into FreshRSS, in their folders."),
        ("Browsers and Pinboard", "Bookmarks exported as an HTML file. Folders become tags."),
        ("Pocket (closed July 2025)", "The export it emailed: the zip of CSV files, or the older ril_export.html."),
        ("Omnivore (closed November 2024)", "The export zip. The articles' text and highlights come along, which matters for pages that are gone."),
    ]

    var body: some View {
        Form {
            Section {
                VStack(spacing: 6) {
                    Image(systemName: "square.and.arrow.down.on.square").font(.title)
                    Text("Drop an export file here").font(.headline)
                    Button("Choose a File…") { choose() }
                }
                .frame(maxWidth: .infinity).padding(.vertical, 14)
                .background(RoundedRectangle(cornerRadius: 10).strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [5])).foregroundStyle(dropping ? Color.daf : .secondary.opacity(0.4)))
                .onDrop(of: [.fileURL], isTargeted: $dropping) { providers in
                    guard let p = providers.first else { return false }
                    _ = p.loadObject(ofClass: URL.self) { u, _ in if let u { Task { @MainActor in await upload(u) } } }
                    return true
                }
                if let reading { Text("Reading \(reading)…").font(.callout).foregroundStyle(.secondary) }
            } footer: {
                Text("Bring a library over from another app. Daf shows what's in the file before anything happens. Links go to the Library with when they were saved, whether they were read, stars and tags.").foregroundStyle(.secondary)
            }
            if !list.isEmpty {
                Section("Imports") { ForEach(list, id: \.self) { row($0) } }
            }
            Section {
                DisclosureGroup("Where each app keeps its export") {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Self.apps, id: \.0) { a in Text("**\(a.0)**: \(a.1)").font(.callout) }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .task { await load() }
        .task(id: list.contains { $0.s("state") == "running" }) {
            while list.contains(where: { $0.s("state") == "running" }) {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if Task.isCancelled { return }
                await load()
            }
        }
    }

    @ViewBuilder
    private func row(_ r: J) -> some View {
        let id = r.s("id") ?? "\(r.i("id") ?? 0)", opml = r.s("service") == "opml"
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(r.s("label") ?? "").font(.headline)
                Text([r.s("name"), r.d("created").map { TodayView.ago($0) }].compactMap { $0 }.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
            }
            Text(Self.what(r)).font(.caption).foregroundStyle(.secondary)
            let done = r.i("pos") ?? 0, total = r.i("total") ?? 0
            switch r.s("state") ?? "" {
            case "ready":
                if !opml, let n = r.o("status")?.i("archive"), n > 0 {
                    Toggle("Bring the \(n) read ones too, into the Archive", isOn: Binding(get: { archived.contains(id) }, set: { if $0 { archived.insert(id) } else { archived.remove(id) } }))
                }
                if opml, !r.list("folders").isEmpty {
                    Toggle("Into their folders", isOn: Binding(get: { !noFolders.contains(id) }, set: { if $0 { noFolders.remove(id) } else { noFolders.insert(id) } }))
                }
                HStack { Spacer(); Button("Never Mind") { Task { await act(id, "drop") } }; Button(opml ? "Bring Them In" : "Bring It In") { Task { await act(id, "start") } }.buttonStyle(.borderedProminent) }
            case "running":
                ProgressView(value: Double(done), total: Double(max(1, total)))
                Text("\(done) of \(total)" + (Self.tally(r).isEmpty ? "" : " · " + Self.tally(r))).font(.caption).foregroundStyle(.secondary)
                HStack { Spacer(); Button("Stop") { Task { await act(id, "stop") } } }
            default:
                Text((r.s("state") == "stopped" ? "Stopped at \(done) of \(total). " : "Done. ") + Self.tally(r)).font(.caption).foregroundStyle(.secondary)
                if !r.a("errors").isEmpty {
                    DisclosureGroup("What didn't go") {
                        Text(r.a("errors").map { ($0.s("url") ?? "") + ": " + ($0.s("error") ?? "") }.joined(separator: "\n")).font(.caption).textSelection(.enabled)
                    }
                }
                HStack {
                    Spacer()
                    if r.s("state") == "stopped" { Button("Go On") { Task { await act(id, "start") } } }
                    Button("Clear") { Task { await act(id, "drop") } }
                }
            }
        }
        .padding(.vertical, 4)
    }

    static func what(_ r: J) -> String {
        if r.s("service") == "opml" { return plural(r.i("feeds") ?? 0, "feed") + (r.list("folders").isEmpty ? "" : " in " + plural(r.list("folders").count, "folder")) }
        let st = r.o("status")
        return [plural(r.i("links") ?? 0, "link"), st?.i("archive").flatMap { $0 > 0 ? "\($0) read" : nil }, r.i("starred").flatMap { $0 > 0 ? "\($0) starred" : nil },
                r.i("tagged").flatMap { $0 > 0 ? "\($0) tagged" : nil }, r.i("highlights").flatMap { $0 > 0 ? plural($0, "highlight") : nil },
                r.i("with_text").flatMap { $0 > 0 ? "\($0) with their text" : nil }].compactMap { $0 }.joined(separator: " · ")
    }

    static func tally(_ r: J) -> String {
        let opml = r.s("service") == "opml"
        func n(_ k: String) -> Int { r.i(k) ?? 0 }
        return [n("added") > 0 ? "\(n("added"))" + (opml ? " followed" : " saved") : nil, n("had") > 0 ? "\(n("had"))" + (opml ? " followed already" : " already in Daf") : nil,
                n("skipped") > 0 ? "\(n("skipped")) read ones left out" : nil, n("hl_added") > 0 ? plural(n("hl_added"), "highlight") : nil,
                n("failed") > 0 ? "\(n("failed")) didn't go" : nil].compactMap { $0 }.joined(separator: " · ")
    }

    private func load() async { list = (try? await API.shared.json("/api/imports"))?.a("imports") ?? list }

    private func choose() {
        let p = NSOpenPanel()
        p.allowedContentTypes = ["csv", "json", "html", "htm", "opml", "xml", "zip", "txt"].compactMap { UTType(filenameExtension: $0) }
        if p.runModal() == .OK, let u = p.url { Task { await upload(u) } }
    }

    private func upload(_ u: URL) async {
        reading = u.lastPathComponent
        defer { reading = nil }
        guard let data = try? Data(contentsOf: u) else { model.error = "That file didn't open."; return }
        do {
            _ = try await API.shared.upload("/api/import?name=" + API.enc(u.lastPathComponent), data, type: "application/octet-stream")
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func act(_ id: String, _ go: String) async {
        do {
            switch go {
            case "start":
                try await API.shared.send("POST", "/api/import/\(API.enc(id))/start", ["archived": archived.contains(id), "folders": !noFolders.contains(id)])
                model.say("Bringing it in. It goes on in the background.")
            case "stop": try await API.shared.send("POST", "/api/import/\(API.enc(id))/stop", [:])
            default: try await API.shared.send("DELETE", "/api/import/" + API.enc(id), nil)
            }
        } catch { model.error = error.localizedDescription }
        await load()
    }
}

// MARK: Feedback

/// Help › Send Feedback…: a note about Daf, with where Daf is and what went wrong lately, filed as
/// an issue on Daf's GitHub repo (/api/feedback). With no connection it waits like any other change.
struct FeedbackSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var sent: [J] = []
    @State private var busy = false

    private var context: [String: Any] {
        let w = NSApp.keyWindow ?? NSApp.mainWindow
        let item = model.selected
        return ["route": model.title(model.place),
                "title": item.map { $0.j.b("private") ? "" : $0.title } ?? "",
                "device": "Daf for Mac " + Version.short + " (native), macOS " + ProcessInfo.processInfo.operatingSystemVersionString,
                "app": "native",
                "size": w.map { "\(Int($0.frame.width))×\(Int($0.frame.height))" } ?? "",
                "theme": NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? "dark" : "light",
                "online": !Connection.shared.offline,
                "errors": Array(model.recentErrors.suffix(12)) + Outbox.shared.ops.prefix(5).map { "waiting: " + $0.method + " " + $0.path }]
    }

    var body: some View {
        Form {
            Section {
                TextEditor(text: $text).font(.body).frame(minHeight: 120)
            } header: { Text("Send feedback") } footer: {
                Text("Something broken, something missing, something I'd like different. It goes with where Daf is, this Mac and window, and " +
                     (model.recentErrors.isEmpty ? "that nothing went wrong lately." : "the last \(min(12, model.recentErrors.count)) things that went wrong.") +
                     " A private title is left out. It becomes an issue on Daf's GitHub repo.").foregroundStyle(.secondary)
            }
            if !sent.isEmpty {
                Section("Sent before") {
                    ForEach(sent.prefix(8), id: \.self) { f in
                        LabeledContent {
                            if let i = f.s("issue"), let u = URL(string: i) { Link("#" + (i.split(separator: "/").last.map(String.init) ?? ""), destination: u) }
                            else if f.s("error") != nil { Text("waiting for GitHub").foregroundStyle(.secondary) }
                        } label: {
                            Text(String((f.s("text") ?? "").split(separator: "\n").first ?? "").prefix(120))
                            Text(TodayView.ago(f.d("at")))
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 520, height: 460)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            ToolbarItem(placement: .confirmationAction) {
                Button(busy ? "Sending…" : "Send") { Task { await send() } }
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(busy || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .task { sent = (try? await API.shared.json("/api/feedback"))?.a("feedback") ?? [] }
    }

    private func send() async {
        busy = true
        defer { busy = false }
        do {
            let r = J(try await API.shared.send("POST", "/api/feedback", ["text": text.trimmingCharacters(in: .whitespacesAndNewlines), "ctx": context]))
            model.say(r?.s("issue") != nil ? "Sent, thank you" : r?.b("queued") == true ? "It goes when Daf is back online" : "Kept; it goes to GitHub on the next sync")
            dismiss()
        } catch { model.error = error.localizedDescription }
    }
}
