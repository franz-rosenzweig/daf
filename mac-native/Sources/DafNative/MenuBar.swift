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
            Button { show(nil); model.sheet = .addLink } label: { Label("Add a Link…", systemImage: "link") }
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

extension AppModel {
    /// Today's numbers, for the menu bar: every five minutes while the app runs.
    func refreshToday() async {
        if let t = try? await API.shared.json("/api/today") { today = t }
    }

    func startClock() {
        Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { guard let self else { return }; Task { await self.refreshToday() } }
        }
    }
}

/// Settings: the address and sign-in, the menu bar; Daf's own reading preferences.
struct PrefsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @AppStorage("menuBar") private var menuBar = false
    @State private var address = API.shared.base.absoluteString
    @State private var s: J?
    @State private var voices: [String] = []
    @AppStorage("prefsTab") private var tab = "general"

    var body: some View {
        TabView(selection: $tab) {
            Form {
                Section("Daf") {
                    TextField("Address", text: $address).onSubmit { UserDefaults.standard.set(address, forKey: API.baseKey); model.reload() }
                    LabeledContent("Signed in", value: API.shared.cookie == nil ? "No" : "Yes")
                    Button("Sign Out") { API.shared.signOut(); model.needsSignIn = true }
                }
                Section {
                    Toggle("Show today's minutes in the menu bar", isOn: $menuBar)
                } footer: { Text("Daf's other Mac app shows them too; turn this on when you use this one instead.").foregroundStyle(.secondary) }
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
                    Section("The Feed") {
                        Stepper("Unseen items go after \(s.i("feed_expire_days") ?? 30) days", value: binding("feed_expire_days", s.i("feed_expire_days") ?? 30), in: 3...3650, step: 1)
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
            .task {
                s = try? await API.shared.json("/api/settings")
                let all = (try? await API.shared.json("/api/voices"))?.strings("voices") ?? []
                voices = all.filter { $0.range(of: "^[ab][fm]_[a-z]+$", options: .regularExpression) != nil }
                    .sorted { (Self.kinds.firstIndex(of: String($0.prefix(2))) ?? 9, $0) < (Self.kinds.firstIndex(of: String($1.prefix(2))) ?? 9, $1) }
            }
        }
        .frame(width: 480, height: 430)
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
