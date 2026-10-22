import SwiftUI

/// Settings › Goals: the goals as the page's Preferences has them (/api/goals): each one on or off,
/// its target and its period, the one the ring follows; a preset to start from; and what counts
/// toward the reading time.
struct GoalsPrefs: View {
    @Environment(AppModel.self) private var model
    @State private var g: J?
    @State private var count: J?

    private static let counts: [(String, String, String)] = [
        ("kindle", "Books on the Kindle", "KOReader's reading time"),
        ("ebook", "Books in Daf", "Time in Daf's book reader"),
        ("manga", "Manga in Daf", "Time in Daf's manga reader"),
        ("audio", "Audiobooks", "Listening time from Audiobookshelf"),
        ("article", "Articles in Daf", "Time with an article open in Daf"),
        ("paper", "Paper books", "Minutes logged here or with Ezer"),
        ("video", "Videos", "Time with a video open in Daf"),
    ]

    var body: some View {
        Form {
            if let g {
                let goals = g.a("goals")
                Section {
                    Picker("The ring follows", selection: Binding(get: { goals.first { $0.b("main") }?.s("id") ?? "minutes" },
                                                                set: { id in Task { await put(["goals": [["id": id, "main": true]]]) } })) {
                        ForEach(goals.filter { $0.b("on") }, id: \.self) { goal in Text(goal.s("label") ?? "").tag(goal.s("id") ?? "") }
                    }
                }
                Section("Goals") {
                    ForEach(goals, id: \.self) { goal in row(goal, kind: g.o("kinds")?.o(goal.s("id") ?? "")) }
                }
                if let presets = g.o("presets"), !presets.raw.isEmpty {
                    Section {
                        HStack {
                            ForEach(presets.raw.keys.sorted(), id: \.self) { k in
                                let p = presets.o(k)
                                Button(p?.s("label") ?? k) { Task { await put(["preset": k]) } }.help(p?.s("text") ?? "")
                            }
                        }
                    } header: { Text("Start from") } footer: {
                        Text("A preset sets the goals afresh; the days already read keep the goals they had.").foregroundStyle(.secondary)
                    }
                }
                if let count {
                    Section("What counts toward the reading time") {
                        ForEach(Self.counts, id: \.0) { k, label, words in
                            Toggle(isOn: Binding(get: { count.b(k) }, set: { on in Task { await setCount(k, on) } })) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(label)
                                    Text(words).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        LabeledContent("Podcasts", value: "Never counted")
                    }
                }
            } else {
                ProgressView()
            }
        }
        .formStyle(.grouped)
        .task { await load() }
    }

    @ViewBuilder
    private func row(_ goal: J, kind: J?) -> some View {
        let id = goal.s("id") ?? ""
        let period = goal.s("period") ?? ""
        let range = (kind?.o("range")?.list(period) ?? []).compactMap { ($0 as? NSNumber)?.intValue }
        let units = (kind?.list("unit") ?? []).compactMap { $0 as? String }
        let target = goal.i("target") ?? 0
        VStack(alignment: .leading, spacing: 6) {
            Toggle(isOn: Binding(get: { goal.b("on") }, set: { on in Task { await put(["goals": [["id": id, "on": on]]]) } })) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(kind?.s("label") ?? id)
                    if goal.b("on") { Text(goal.s("text") ?? "").font(.caption).foregroundStyle(goal.b("met") ? Color.green : .secondary) }
                }
            }
            if goal.b("on") {
                HStack {
                    if range.count == 3 {
                        Stepper(value: Binding(get: { target }, set: { v in Task { await put(["goals": [["id": id, "target": v]]]) } }),
                                in: range[0]...range[1], step: range[2]) {
                            Text("\(target) " + (target == 1 ? units.first ?? "" : units.last ?? "")).monospacedDigit()
                        }
                        .fixedSize()
                    }
                    let periods = kind?.a("periods") ?? []
                    if periods.count > 1 {
                        Picker("", selection: Binding(get: { period }, set: { p in Task { await put(["goals": [["id": id, "period": p]]]) } })) {
                            ForEach(periods, id: \.self) { p in Text(p.s("words") ?? p.s("id") ?? "").tag(p.s("id") ?? "") }
                        }
                        .labelsHidden()
                        .fixedSize()
                    } else if let w = periods.first?.s("words") {
                        Text(w).foregroundStyle(.secondary)
                    }
                    Spacer()
                }
                if id == "books" {
                    Toggle("Manga volumes count as books", isOn: Binding(get: { goal.b("manga") }, set: { on in Task { await put(["goals": [["id": id, "manga": on]]]) } }))
                        .font(.callout)
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func load() async {
        g = try? await API.shared.json("/api/goals")
        count = (try? await API.shared.json("/api/settings"))?.o("count")
    }

    private func put(_ body: [String: Any]) async {
        do {
            g = J(try await API.shared.send("PUT", "/api/goals", body)) ?? g
            if g?.a("goals").isEmpty != false { g = try? await API.shared.json("/api/goals") }
            await model.refreshToday()
        } catch { model.error = error.localizedDescription }
    }

    private func setCount(_ k: String, _ on: Bool) async {
        do {
            try await API.shared.send("PUT", "/api/settings", ["count": [k: on]])
            var raw = count?.raw ?? [:]
            raw[k] = on
            count = J(raw)
            g = try? await API.shared.json("/api/goals")
            await model.refreshToday()
        } catch { model.error = error.localizedDescription }
    }
}
