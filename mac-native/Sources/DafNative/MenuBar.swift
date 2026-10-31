import SwiftUI

/// Today's minutes in the menu bar ("38′", "60′ ✓" once the goal's met), with the ring, the review
/// and the quick things. Off unless turned on in Settings (the web-view app shows its own).
struct MenuBarLabel: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        let main = model.today?.o("main")
        let done = Int(main?.d("done") ?? model.today?.d("counted") ?? 0)
        if main?.b("met") == true { Text("\(done)′ ✓") } else { Text(model.today == nil ? "Daf" : "\(done)′") }
    }
}

struct MenuBarPanel: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let t = model.today { Ring(today: t) }
            Divider()
            Button { show(.today) } label: { Label("Open Daf", systemImage: "book") }
            Button { show(.review) } label: { Label("Review", systemImage: "rectangle.stack") }
            Button { show(nil); model.sheet = .addLink } label: { Label("Add to Daf…", systemImage: "plus") }
            Button { show(nil); model.sheet = .paper } label: { Label("Log Paper Minutes…", systemImage: "book.closed") }
        }
        .buttonStyle(.plain)
        .padding(16)
        .frame(width: 300)
        .task { await model.refreshToday() }
    }

    private func show(_ place: Place?) {
        if let place { model.place = place }
        openWindow(id: "main")
        NSApp.activate()
    }
}

/// Today's minutes in the menu bar: on for Daf itself, as the web-view Daf had them; off for the test build.
enum MenuBarSetting {
    static var byDefault: Bool { Bundle.main.bundleIdentifier == "xyz.tiresia.daf" }
    static var on: Bool { UserDefaults.standard.object(forKey: "menuBar") as? Bool ?? byDefault }
}

extension AppModel {
    /// Today's numbers, for the menu bar: every five minutes while the app runs.
    func refreshToday() async {
        if let t = try? await API.shared.json("/api/today") { today = t }
    }

    func startClock() {
        Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                Task {
                    await self.refreshToday()
                    await FeedNews.shared.check()
                    await Outbox.shared.flush()
                }
            }
        }
    }
}

/// Settings: the address and sign-in, the menu bar; Daf's own reading preferences.
struct PrefsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @AppStorage("menuBar") private var menuBar = MenuBarSetting.byDefault
    @State private var address = API.shared.base.absoluteString
    @State private var s: J?
    @State private var voices: [String] = []
    @AppStorage("prefsTab") private var tab = "general"
    @AppStorage("keepOffline") private var keepOffline = true
    @AppStorage("autoAdvance") private var autoAdvance = true
    @State private var alerts = FeedNews.shared.on

    var body: some View {
        TabView(selection: $tab) {
            Form {
                Section("Daf") {
                    TextField("Address", text: $address).onSubmit { UserDefaults.standard.set(address, forKey: API.baseKey); model.reload() }
                    LabeledContent("Signed in", value: API.shared.cookie == nil ? "No" : "Yes")
                    Button("Sign Out") { API.shared.signOut(); model.needsSignIn = true }
                }
                Section("Sidebar") {
                    Picker("On this Mac", selection: Binding(get: { Side.shared.mode }, set: { Side.shared.mode = $0 })) {
                        ForEach(Side.modes, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .pickerStyle(.segmented)
                }
                .id("sidebar")
                Section("Pinned in the sidebar") {
                    let pins = Side.shared.pins(model.today?.o("settings"))
                    ForEach(Side.pinnable, id: \.0) { p in
                        Toggle(p.1, isOn: Binding(get: { pins.contains(p.0) }, set: { on in
                            Task { await Side.shared.setPins(on ? pins + [p.0] : pins.filter { $0 != p.0 }) }
                        }))
                    }
                }
                Section {
                    Toggle("Show today's minutes in the menu bar", isOn: $menuBar)
                    Toggle("Tell me about new posts in the feeds I choose", isOn: Binding(get: { alerts }, set: { on in
                        alerts = on
                        if on { Task { await FeedNews.shared.enable() } } else { FeedNews.shared.disable() }
                    }))
                } footer: { Text("Choose the feeds by right-clicking one in the sidebar: Tell Me About New Posts.").foregroundStyle(.secondary) }
                Section("With no connection") {
                    Toggle("Keep the Inbox, Later and the nightstand's books on this Mac", isOn: $keepOffline)
                    if !Outbox.shared.ops.isEmpty {
                        LabeledContent("Waiting to go to Daf", value: plural(Outbox.shared.ops.count, "change"))
                    }
                }
                Section("Daf for Safari") {
                    Button("Set Up Daf for Safari…") { Task { await Safari.setUp() } }
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("General", systemImage: "gearshape") }
            .tag("general")

            Form {
                if let s {
                    Section("Review") {
                        Stepper("Highlights a day: \(s.i("review_size") ?? 5)", value: binding("review_size", s.i("review_size") ?? 5), in: 1...20)
                        Stepper("New flashcards a day: \(s.i("cards_per_day") ?? 5)", value: binding("cards_per_day", s.i("cards_per_day") ?? 5), in: 0...30)
                    }
                    Section {
                        Picker("The Feed lets go after", selection: binding("feed_expire_days", s.i("feed_expire_days") ?? 30)) {
                            ForEach(Self.windows(s.i("feed_expire_days") ?? 30), id: \.0) { w in Text(w.1).tag(w.0) }
                        }
                    } header: { Text("The Feed") } footer: {
                        Text("Unseen items older than this move to Seen, so the Feed never becomes a pile. A longer time brings back the unread ones FreshRSS still has.").foregroundStyle(.secondary)
                    }
                    Section {
                        Toggle("After Archive or Later, open the next one", isOn: $autoAdvance)
                    } header: { Text("Articles") } footer: {
                        Text("Off, archiving the open article or moving it to Later goes back to the list. On this Mac.").foregroundStyle(.secondary)
                    }
                    Section {
                        Picker("Home time zone", selection: Binding(get: { s.s("home_tz") ?? TimeZone.current.identifier }, set: { z in put(["home_tz": z]); model.say("Days now follow " + z); model.reload() })) {
                            ForEach(Self.zones(s.s("home_tz")), id: \.self) { Text($0).tag($0) }
                        }
                    } header: { Text("Days") } footer: {
                        Text("Decides when a day starts and ends. Switch it when you travel.").foregroundStyle(.secondary)
                    }
                    Section("Read aloud") {
                        if !voices.isEmpty {
                            Picker("Voice", selection: Binding(get: { s.s("tts_voice") ?? "af_heart" }, set: { put(["tts_voice": $0]) })) {
                                ForEach(voices, id: \.self) { v in Text(Self.voiceName(v)).tag(v) }
                            }
                        }
                        LabeledContent("Speed") {
                            Slider(value: Binding(get: { s.d("tts_speed") ?? 1 }, set: { v in put(["tts_speed": (v * 20).rounded() / 20]) }), in: 0.5...2, step: 0.05)
                                .frame(width: 200)
                            Text(String(format: "%.2f×", s.d("tts_speed") ?? 1)).monospacedDigit().frame(width: 50)
                        }
                    }
                    Section {
                        Button("Everything Else in Daf's Preferences…") { openWindow(id: "route", value: "#prefs") }
                    }
                } else {
                    ProgressView()
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("Reading", systemImage: "book") }
            .tag("reading")

            GoalsPrefs()
                .tabItem { Label("Goals", systemImage: "target") }
                .tag("goals")
            AppearancePrefs()
                .tabItem { Label("Appearance", systemImage: "paintpalette") }
                .tag("appearance")
            AccountPrefs()
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
                .tag("account")
            ConnectionsPrefs()
                .tabItem { Label("Connections", systemImage: "point.3.connected.trianglepath.dotted") }
                .tag("connections")
            AIPrefs()
                .tabItem { Label("AI", systemImage: "sparkles") }
                .tag("ai")
            TagsPrefs()
                .tabItem { Label("Tags", systemImage: "tag") }
                .tag("tags")
            ImportPrefs()
                .tabItem { Label("Import", systemImage: "square.and.arrow.down") }
                .tag("import")
            .task {
                s = try? await API.shared.json("/api/settings")
                let all = (try? await API.shared.json("/api/voices"))?.strings("voices") ?? []
                voices = all.filter { $0.range(of: "^[ab][fm]_[a-z]+$", options: .regularExpression) != nil }
                    .sorted { (Self.kinds.firstIndex(of: String($0.prefix(2))) ?? 9, $0) < (Self.kinds.firstIndex(of: String($1.prefix(2))) ?? 9, $1) }
            }
        }
        .frame(width: 600, height: 640)
    }

    /// How long the Feed keeps what's unseen, as the page offers it (and whatever's set now).
    static func windows(_ now: Int) -> [(Int, String)] {
        let w = [(7, "a week"), (14, "2 weeks"), (21, "3 weeks"), (30, "a month"), (60, "2 months"), (90, "3 months"), (180, "6 months"), (365, "a year"), (3650, "never")]
        return w.contains { $0.0 == now } ? w : (w + [(now, "\(now) days")]).sorted { $0.0 < $1.0 }
    }

    static func zones(_ now: String?) -> [String] {
        var z = ["America/Phoenix", "Asia/Jerusalem"]
        for x in [now, TimeZone.current.identifier].compactMap({ $0 }) where !z.contains(x) { z.append(x) }
        return z
    }

    /// Kokoro's voices as the page names them: "Heart · American woman".
    static let kinds = ["af", "am", "bf", "bm"]
    static func voiceName(_ id: String) -> String {
        let kind = ["af": "American woman", "am": "American man", "bf": "British woman", "bm": "British man"][String(id.prefix(2))]
        let name = id.split(separator: "_").last.map { $0.prefix(1).uppercased() + $0.dropFirst() } ?? id
        return kind.map { name + " · " + $0 } ?? name
    }

    private func binding(_ key: String, _ value: Int) -> Binding<Int> {
        Binding(get: { s?.i(key) ?? value }, set: { put([key: $0]) })
    }

    private func put(_ change: [String: Any]) {
        guard var raw = s?.raw else { return }
        for (k, v) in change { raw[k] = v }
        s = J(raw)
        Task {
            do { try await API.shared.send("PUT", "/api/settings", change) } catch { model.error = error.localizedDescription }
        }
    }
}
