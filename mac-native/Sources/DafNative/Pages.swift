import Charts
import SwiftUI

/// A book's page: where I am, Read (the book in a window of its own, as Apple Books does), the
/// nightstand, my reading of it, its highlights.
struct BookPage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    let id: String
    @State private var b: J?
    @State private var note = ""
    @State private var swapOut: [J]?

    var body: some View {
        ScrollView {
            if let b {
                VStack(alignment: .leading, spacing: 24) {
                    HStack(alignment: .top, spacing: 20) {
                        AsyncImage(url: b.b("has_cover") ? API.shared.url("/api/cover/" + API.enc(id)) : nil) { p in
                            if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { RoundedRectangle(cornerRadius: 4).fill(.quaternary) }
                        }
                        .frame(width: 120, height: 180)
                        .shadow(radius: 4, y: 2)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(b.b("private") ? "Private reading" : (b.s("title") ?? "")).font(.system(.title, design: .serif).weight(.semibold))
                            if let a = b.s("author") { Text(a).font(.title3).foregroundStyle(.secondary) }
                            if let p = b.s("progress_note") {
                                ProgressView(value: min(100, b.d("progress") ?? 0), total: 100).frame(maxWidth: 280)
                                Text(p).font(.callout).foregroundStyle(.secondary)
                            }
                            if let a = b.s("audio_note") { Label(a, systemImage: "headphones").font(.callout).foregroundStyle(.secondary) }
                            let k = [b.i("minutes_kindle").flatMap { $0 > 0 ? "\($0 / 60) h \($0 % 60)′ on the Kindle" : nil },
                                     b.d("last_read").map { "last opened " + Date(timeIntervalSince1970: $0).formatted(date: .abbreviated, time: .omitted) }].compactMap { $0 }
                            if !k.isEmpty { Text(k.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary) }
                            HStack {
                                if b.b("readable") {
                                    Button { openWindow(id: "route", value: "#ebook/" + API.enc(id)) } label: { Label("Read", systemImage: "book") }
                                        .buttonStyle(.borderedProminent)
                                }
                                Button(b.b("on_nightstand") ? "Off the Nightstand" : "On the Nightstand") { Task { await nightstand(!b.b("on_nightstand")) } }
                                ShelvesMenu(book: id)
                            }
                            .padding(.top, 6)
                        }
                    }
                    if let st = b.o("stats"), (st.i("minutes") ?? 0) > 0 { stats(st) }
                    if !b.b("private") {
                        Panel("A note on this book") {
                            TextField("A thought, a quote, where you were…", text: $note, axis: .vertical).textFieldStyle(.roundedBorder)
                            HStack { Spacer(); Button("Save the Note") { Task { await saveNote() } }.disabled(note.trimmingCharacters(in: .whitespaces).isEmpty) }
                            ForEach(b.a("notes"), id: \.self) { n in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(n.s("text") ?? "").font(.callout)
                                    Text([n.d("at").map { Date(timeIntervalSince1970: $0).formatted(date: .abbreviated, time: .shortened) }, n.b("voice") ? "a voice note" : nil].compactMap { $0 }.joined(separator: " · "))
                                        .font(.caption2).foregroundStyle(.tertiary)
                                }
                            }
                        }
                    }
                    if !b.a("bookmarks").isEmpty {
                        Panel("Audiobook bookmarks") {
                            ForEach(b.a("bookmarks"), id: \.self) { m in
                                Text([m.s("time") ?? m.s("title"), m.s("text") ?? m.s("note")].compactMap { $0 }.joined(separator: " · ")).font(.callout)
                            }
                        }
                    }
                    if !b.b("private") && !b.a("highlights").isEmpty {
                        Panel("In the daily review") {
                            Picker("", selection: Binding(get: { b.s("review_freq") ?? "normal" }, set: { f in Task { await freq(f) } })) {
                                Text("More").tag("more"); Text("As Usual").tag("normal"); Text("Less").tag("less"); Text("Never").tag("never")
                            }
                            .pickerStyle(.segmented).labelsHidden().frame(maxWidth: 360)
                            Text(["more": "This book comes up more often.", "less": "This book comes up less often.",
                                  "never": "This book stays out of the daily review. Its highlights are still here.", "normal": "Like any other book."][b.s("review_freq") ?? "normal"] ?? "")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !b.b("private") { HardcoverSection(bookID: id, title: b.s("title") ?? "") }
                    let hls = b.a("highlights")
                    if !hls.isEmpty {
                        HStack {
                            Text(plural(hls.count, "highlight")).font(.headline)
                            Spacer()
                            if !b.b("private") { Button("Review These") { model.startReview(themed: "n=30&book=" + API.enc(id)) } }
                            Button("Export…") { Task { await export() } }.help("The highlights as Markdown")
                        }
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(hls, id: \.self) { h in
                                HighlightCard(h: h, edit: {}, open: { if let o = h.s("open") { openWindow(id: "route", value: o) } })
                            }
                        }
                    }
                }
                .padding(28)
                .frame(maxWidth: 780, alignment: .leading)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .task(id: id) { b = try? await API.shared.json("/api/books/" + API.enc(id)) }
        .confirmationDialog("Which one steps off?", isPresented: Binding(get: { swapOut != nil }, set: { if !$0 { swapOut = nil } })) {
            ForEach(swapOut ?? [], id: \.self) { x in
                Button(PaperPages.short(x.s("title"))) { Task { await swap(x.s("id")) } }
            }
            Button("Cancel", role: .cancel) { swapOut = nil }
        } message: { Text("The nightstand holds three. The one you take off stays in your library and your vault.") }
    }

    private func stats(_ st: J) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Grid(horizontalSpacing: 12, verticalSpacing: 12) {
                GridRow {
                    Number(value: "\(Int(Double(st.i("minutes") ?? 0) / 60)) h \((st.i("minutes") ?? 0) % 60)′", label: "Read so far")
                    Number(value: "\(st.i("sittings") ?? 0)", label: "Sittings, over " + plural(st.i("days") ?? 0, "day"))
                    Number(value: st.i("pages_per_hour").map { "\($0)" } ?? "—", label: "Pages an hour")
                    Number(value: st.s("finish").map(StatsView.day) ?? "—", label: "Done by, at this pace")
                }
            }
            let days = st.list("last30").enumerated().map { ($0.offset, ($0.element as? NSNumber)?.doubleValue ?? 0) }
            if days.contains(where: { $0.1 > 0 }) {
                Chart(days, id: \.0) { d in
                    BarMark(x: .value("Day", d.0), y: .value("Minutes", d.1)).foregroundStyle(Color.daf.opacity(0.7))
                }
                .chartXAxis(.hidden)
                .frame(height: 90)
            }
        }
    }

    private func saveNote() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/notes", ["text": note.trimmingCharacters(in: .whitespacesAndNewlines), "book_id": id]))
            model.say(["written", "unchanged"].contains(r?.s("vault") ?? "") ? "Saved to the vault note" : "Saved in Daf")
            note = ""
            b = try? await API.shared.json("/api/books/" + API.enc(id))
        } catch { model.error = error.localizedDescription }
    }

    private func freq(_ f: String) async {
        do {
            try await API.shared.send("PUT", "/api/books/\(API.enc(id))/review", ["freq": f])
            model.say(["more": "More often in the daily review", "normal": "As usual in the daily review", "less": "Less often in the daily review", "never": "Out of the daily review"][f] ?? "")
            b = try? await API.shared.json("/api/books/" + API.enc(id))
        } catch { model.error = error.localizedDescription }
    }

    private func export() async {
        guard let data = try? await API.shared.data("/api/highlights/export?fmt=md&book=" + API.enc(id)) else { model.error = "The export didn't come."; return }
        let p = NSSavePanel()
        p.nameFieldStringValue = PaperPages.short(b?.s("title")) + " highlights.md"
        if p.runModal() == .OK, let u = p.url { try? data.write(to: u) }
    }

    private func nightstand(_ on: Bool) async {
        do {
            let t = try await API.shared.json("/api/today")
            var ids = t.a("nightstand").compactMap { $0.s("id") }.filter { $0 != id }
            if on && ids.count >= 3 { swapOut = t.a("nightstand"); return }
            if on { ids.append(id) }
            try await API.shared.send("PUT", "/api/nightstand", ["ids": ids])
            b = try? await API.shared.json("/api/books/" + API.enc(id))
            model.say(on ? "On the nightstand" : "Off the nightstand")
        } catch { model.error = error.localizedDescription }
    }

    /// The nightstand holds three: a fourth asks which one steps off.
    private func swap(_ out: String?) async {
        guard let out, let stand = swapOut else { return }
        swapOut = nil
        do {
            try await API.shared.send("PUT", "/api/nightstand", ["ids": stand.compactMap { $0.s("id") }.map { $0 == out ? id : $0 }])
            b = try? await API.shared.json("/api/books/" + API.enc(id))
            model.say("Swapped")
        } catch { model.error = error.localizedDescription }
    }
}

/// Podcasts: what I've listened to lately, and what I follow (AntennaPod and Audiobookshelf send it).
struct PodcastsView: View {
    @State private var p: J?

    var body: some View {
        ScrollView {
            if let p {
                VStack(alignment: .leading, spacing: 14) {
                    Heading("Listened to lately")
                    VStack(spacing: 0) {
                        ForEach(Array(episodes(p).enumerated()), id: \.offset) { k, e in
                            if k > 0 { Divider() }
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(e.title).lineLimit(1)
                                    Text(e.author).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text("\(e.seconds / 60)′").monospacedDigit().foregroundStyle(.secondary)
                                Text(Date(timeIntervalSince1970: e.last), format: .dateTime.month().day()).foregroundStyle(.tertiary).frame(width: 60, alignment: .trailing)
                            }
                            .padding(.vertical, 7)
                        }
                    }
                    Heading("Following (\(p.a("subs").count))").padding(.top, 10)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), alignment: .leading)], alignment: .leading, spacing: 8) {
                        ForEach(p.a("subs"), id: \.self) { s in Text(s.s("title") ?? s.s("url") ?? "").lineLimit(1) }
                    }
                }
                .padding(28)
                .frame(maxWidth: 900, alignment: .leading)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .navigationTitle("Podcasts")
        .task { p = try? await API.shared.json("/api/podcasts") }
    }

    /// One row an episode: its sessions added up, the latest day, and nothing under a minute.
    private func episodes(_ p: J) -> [(title: String, author: String, seconds: Int, last: Double)] {
        var out: [(title: String, author: String, seconds: Int, last: Double)] = []
        var at: [String: Int] = [:]
        for e in p.a("recent") {
            let t = e.s("title") ?? "", a = e.s("author") ?? "", key = t + "\u{1}" + a
            let secs = e.i("seconds") ?? 0, start = e.d("start") ?? 0
            if let k = at[key] { out[k].seconds += secs; out[k].last = max(out[k].last, start) }
            else { at[key] = out.count; out.append((t, a, secs, start)) }
        }
        return out.filter { $0.seconds >= 60 }
    }
}

/// Sources: whether each place Daf reads from is answering, and Sync Now.
struct SourcesView: View {
    @Environment(AppModel.self) private var model
    @State private var s: J?
    @State private var syncing = false

    var body: some View {
        List {
            if let s {
                ForEach(s.a("checks"), id: \.self) { c in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: c.b("ok") ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                            .foregroundStyle(c.b("ok") ? .green : .orange)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(c.s("name") ?? "").font(.headline)
                            Text(c.s("detail") ?? "").font(.callout).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let last = c.d("last"), last > 0 {
                            Text(Date(timeIntervalSince1970: last), style: .relative).font(.caption).foregroundStyle(.tertiary)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .navigationTitle("Sources")
        .toolbar {
            ToolbarItem {
                Button { Task { await sync() } } label: { Label(syncing ? "Syncing…" : "Sync Now", systemImage: "arrow.triangle.2.circlepath") }
                    .disabled(syncing)
            }
        }
        .task { s = try? await API.shared.json("/api/sources") }
    }

    private func sync() async {
        syncing = true
        defer { syncing = false }
        do {
            try await API.shared.send("POST", "/api/sync", [:])
            s = try? await API.shared.json("/api/sources")
            model.say("Synced")
            model.reload()
        } catch { model.error = error.localizedDescription }
    }
}

/// Torah: this week's parasha and haftarah, the readings to open, Ruach, and earlier weeks.
struct TorahList: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let t = model.torah {
                    if let p = t.o("parasha") {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(p.s("he") ?? "").font(.system(.largeTitle, design: .serif)).frame(maxWidth: .infinity, alignment: .trailing)
                            Text("Parashat \(p.s("name") ?? "")").font(.title3.weight(.semibold))
                            Text(p.s("ref") ?? "").foregroundStyle(.secondary)
                            if let h = t.o("haftarah")?.s("name") { Text("Haftarah: \(h)").font(.callout).foregroundStyle(.secondary) }
                        }
                    }
                    rows("This week", t.a("week"))
                    rows("Ruach", t.a("ruach"))
                    rows("Earlier", t.a("earlier"))
                }
            }
            .padding(20)
        }
        .navigationTitle("Torah")
    }

    @ViewBuilder
    private func rows(_ title: String, _ list: [J]) -> some View {
        if !list.isEmpty {
            Heading(title)
            SelectableRows(items: list.map(Item.init))
        }
    }
}

/// Rows that open in the detail column when clicked, for pages that aren't one list.
struct SelectableRows: View {
    @Environment(AppModel.self) private var model
    let items: [Item]

    var body: some View {
        VStack(spacing: 2) {
            ForEach(items) { item in
                Button { model.selection = item.id } label: {
                    ItemRow(item: item)
                        .padding(.horizontal, 8)
                        .background(RoundedRectangle(cornerRadius: 8).fill(model.selection == item.id ? Color.daf.opacity(0.18) : .clear))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }
}
