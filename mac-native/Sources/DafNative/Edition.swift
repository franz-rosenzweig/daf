import SwiftUI

// The Edition, as the page has it (web/edition.js, daf/edition.py): a short paper each morning, chosen
// by what you read, watch and listen to, and its Taste page, where you see what it thinks you like and
// turn things up, down or off.

enum Ed {
    static func day(_ s: String) -> Date? {
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = "yyyy-MM-dd"
        return f.date(from: s)
    }
    static func format(_ s: String, _ pattern: String) -> String {
        guard let d = day(s) else { return s }
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.dateFormat = pattern
        return f.string(from: d)
    }
    /// "Monday, 9 November 2026"
    static func long(_ s: String) -> String { format(s, "EEEE, d MMMM yyyy") }
    /// "Mon 9 Nov"
    static func short(_ s: String) -> String { format(s, "EEE d MMM") }
    static func hm(_ m: Int) -> String { m >= 60 ? "\(m / 60) h" + (m % 60 > 0 ? " \(m % 60) m" : "") : "\(m) min" }
    static func length(_ it: J) -> String? {
        guard let m = it.i("minutes"), m > 0 else { return nil }
        return it.s("kind") == "article" ? "\(m) min" : hm(m)
    }
    static func icon(_ kind: String?) -> String {
        switch kind { case "video": return "play.rectangle"; case "podcast": return "mic"; default: return "doc.text" }
    }
    static func hebrew(_ s: String?) -> Bool { s?.range(of: "[\u{0590}-\u{05FF}]", options: .regularExpression) != nil }
}

struct EditionView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    @State private var r: J?
    @State private var day = ""
    @State private var taste = false
    @State private var again = false
    @State private var busy = false
    @State private var votes: [String: Int] = [:]

    private var ed: J? { r?.o("edition") }

    var body: some View {
        Group {
            if taste { TasteView() }
            else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        if let r { paper(r) } else { ProgressView().frame(maxWidth: .infinity).padding(60) }
                    }
                    .padding(28)
                    .frame(maxWidth: 1100, alignment: .leading)
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .navigationTitle(taste ? "Taste" : "Edition")
        .toolbar { tools }
        .task(id: day) { await load() }
        .task(id: r?.b("building") == true) {
            while r?.b("building") == true && !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                if !Task.isCancelled { await load() }
            }
        }
        .confirmationDialog("Make this edition again from what's new now?", isPresented: $again) {
            Button("Make It Again") { Task { await build(again: true) } }
        }
    }

    @ToolbarContentBuilder private var tools: some ToolbarContent {
        if taste {
            ToolbarItem { Button("Edition") { taste = false } }
        } else if let r {
            let days = r.strings("days"), here = r.s("day") ?? ""
            if days.count > 1 || (!days.isEmpty && days.first != here) {
                ToolbarItem {
                    Picker("Past Editions", selection: Binding(get: { here }, set: { day = $0 })) {
                        if !days.contains(here) { Text(Ed.short(here)).tag(here) }
                        ForEach(days, id: \.self) { Text(Ed.short($0)).tag($0) }
                    }
                    .fixedSize()
                }
            }
            ToolbarItem { Button("Taste") { taste = true } }
            if let ed {
                ToolbarItem {
                    Button { Task { await kindle() } } label: { Label(ed.s("kindle") != nil ? "On Kindle" : "Kindle", systemImage: "book.closed") }
                        .labelStyle(.titleAndIcon)
                        .help("Send to the Kindle")
                        .disabled(busy)
                }
                ToolbarItem {
                    Button { again = true } label: { Label("Make It Again", systemImage: "arrow.clockwise") }
                        .help("Make it again")
                        .disabled(busy)
                }
            }
        }
    }

    // MARK: the page

    @ViewBuilder private func paper(_ r: J) -> some View {
        if let ed {
            let items = ed.a("items")
            masthead(ed, items)
            if let lead = items.first {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 28) { leadView(lead); todayList(items).frame(width: 300) }
                        .frame(minWidth: 760)
                    VStack(alignment: .leading, spacing: 20) { leadView(lead); todayList(items) }
                }
                Divider()
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 20, alignment: .top)], alignment: .leading, spacing: 24) {
                ForEach(Array(items.dropFirst().enumerated()), id: \.offset) { k, it in card(it, k + 2) }
            }
            HStack { line; Text("End of the edition").font(.caption).foregroundStyle(.secondary).fixedSize(); line }
                .padding(.top, 8)
        } else if r.b("building") {
            TodayCard { Text(day.isEmpty ? "Making today's edition…" : "Making this edition…").font(.title3) }
        } else {
            TodayCard {
                Text("No edition for " + Ed.long(r.s("day") ?? "")).font(.title3)
                Button("Make It Now") { Task { await build(again: false) } }.buttonStyle(.borderedProminent).disabled(busy)
            }
        }
    }

    private var line: some View { Rectangle().fill(.quaternary).frame(height: 1) }

    private func masthead(_ ed: J, _ items: [J]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text([Ed.long(ed.s("day") ?? ""), ed.s("hebrew"), "No. \(ed.i("number") ?? 0)"].compactMap { $0 }.joined(separator: " · "))
                .font(.system(.title3, design: .serif))
            HStack(spacing: 12) {
                HStack(spacing: 3) {
                    ForEach(Array(items.enumerated()), id: \.offset) { _, it in
                        Capsule().fill(it.b("done") || it.b("opened") ? Color.daf : Color.secondary.opacity(0.2)).frame(width: 22, height: 4)
                    }
                }
                Text("\(ed.i("done") ?? 0) of \(items.count)" + ((ed.i("left") ?? 0) > 0 ? " · " + Ed.hm(ed.i("left") ?? 0) + " left" : ""))
                    .font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    private func leadView(_ it: J) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Button { open(it) } label: {
                VStack(alignment: .leading, spacing: 8) {
                    kicker(it, 1)
                    Text(it.s("title") ?? "").font(.system(size: 30, weight: .semibold, design: .serif))
                        .multilineTextAlignment(Ed.hebrew(it.s("title")) ? .trailing : .leading)
                    if let dek = it.s("summary"), !dek.isEmpty {
                        Text(dek).font(.system(.title3, design: .serif)).foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: Ed.hebrew(it.s("title")) ? .trailing : .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(it.raw["exists"] as? Bool == false)
            meta(it)
            acts(it)
        }
        .opacity(it.b("done") ? 0.6 : 1)
    }

    private func todayList(_ items: [J]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Today").font(.caption.weight(.semibold)).foregroundStyle(.secondary).textCase(.uppercase)
            ForEach(Array(items.enumerated()), id: \.offset) { k, it in
                Button { open(it) } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(k + 1)").font(.callout.weight(.semibold).monospacedDigit()).foregroundStyle(.secondary).frame(width: 18, alignment: .trailing)
                        Image(systemName: Ed.icon(it.s("kind"))).font(.caption).foregroundStyle(.secondary)
                        Text(it.s("title") ?? "").lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .opacity(it.b("done") || it.b("opened") ? 0.5 : 1)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func card(_ it: J, _ n: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { open(it) } label: {
                VStack(alignment: .leading, spacing: 8) {
                    thumb(it)
                    kicker(it, n)
                    Text(it.s("title") ?? "").font(.system(.headline, design: .serif)).lineLimit(4)
                        .frame(maxWidth: .infinity, alignment: Ed.hebrew(it.s("title")) ? .trailing : .leading)
                        .multilineTextAlignment(Ed.hebrew(it.s("title")) ? .trailing : .leading)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(it.raw["exists"] as? Bool == false)
            meta(it)
            acts(it)
        }
        .opacity(it.b("done") ? 0.6 : 1)
    }

    @ViewBuilder private func thumb(_ it: J) -> some View {
        if let t = it.s("thumb"), t.hasPrefix("/api/") {
            Color.clear.frame(height: 130)
                .overlay { Cover(path: t, title: it.s("title") ?? "", book: false) }
                .overlay { if it.s("kind") == "video" { Image(systemName: "play.fill").font(.title2).foregroundStyle(.white).shadow(radius: 3) } }
                .clipShape(RoundedRectangle(cornerRadius: 8))
        } else {
            let letter = String((it.s("publication") ?? it.s("source") ?? "?").trimmingCharacters(in: .whitespaces).prefix(1))
            ZStack {
                (it.s("kind") == "video" ? Color.red : it.s("kind") == "podcast" ? Color.purple : Color.daf).opacity(0.12)
                Text(letter).font(.system(size: 34, weight: .semibold, design: .serif)).foregroundStyle(Color.daf)
            }
            .frame(height: 130)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private func kicker(_ it: J, _ n: Int) -> some View {
        HStack(spacing: 6) {
            Image(systemName: Ed.icon(it.s("kind")))
            Text(it.s("section") ?? "")
            Text("\(n)").fontWeight(.bold)
        }
        .font(.caption.weight(.medium)).foregroundStyle(Color.daf).textCase(.uppercase)
    }

    @ViewBuilder private func meta(_ it: J) -> some View {
        let bits = [it.s("publication") ?? it.s("source"), Ed.length(it)].compactMap { $0 }.filter { !$0.isEmpty }
        if !bits.isEmpty { Text(bits.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary) }
        if let why = it.s("why"), !why.isEmpty {
            Text(why).font(.caption).padding(.horizontal, 8).padding(.vertical, 3)
                .background(Color.secondary.opacity(0.1), in: Capsule())
        }
    }

    private func acts(_ it: J) -> some View {
        let id = it.s("id") ?? "", vote = votes[id] ?? it.i("vote") ?? 0
        return HStack(spacing: 10) {
            if it.b("done") { Label("Read", systemImage: "checkmark").font(.caption).foregroundStyle(.secondary) }
            Spacer(minLength: 0)
            Button { Task { await self.vote(id, vote == 1 ? 0 : 1) } } label: { Image(systemName: vote > 0 ? "hand.thumbsup.fill" : "hand.thumbsup") }
                .help("More like this")
            Button { Task { await self.vote(id, vote == -1 ? 0 : -1) } } label: { Image(systemName: vote < 0 ? "hand.thumbsdown.fill" : "hand.thumbsdown") }
                .help("Less like this")
        }
        .buttonStyle(.borderless)
        .foregroundStyle(.secondary)
    }

    // MARK: doing

    private func open(_ it: J) {
        guard let id = it.s("id"), it.raw["exists"] as? Bool != false else { return }
        openWindow(id: "route", value: "#read/" + API.enc(id))
    }

    private func load() async {
        do {
            let got = try await API.shared.json("/api/edition" + (day.isEmpty ? "" : "?day=" + day))
            r = got
            votes = [:]
        } catch { model.error = error.localizedDescription }
    }

    private func vote(_ id: String, _ v: Int) async {
        votes[id] = v
        do { try await API.shared.send("POST", "/api/edition/vote", ["id": id, "vote": v]) }
        catch { model.error = error.localizedDescription }
    }

    private func build(again: Bool) async {
        busy = true
        defer { busy = false }
        do {
            try await API.shared.send("POST", "/api/edition/build", ["day": r?.s("day") ?? ""])
            if var raw = r?.raw {
                raw["building"] = true
                if again { raw["edition"] = NSNull() }
                r = J(raw)
            }
        } catch { model.error = error.localizedDescription }
    }

    private func kindle() async {
        busy = true
        defer { busy = false }
        do {
            let k = J(try await API.shared.send("POST", "/api/edition/kindle", ["day": r?.s("day") ?? ""]))
            if var raw = r?.raw, var e = ed?.raw {
                e["kindle"] = k?.s("file") ?? true
                raw["edition"] = e
                r = J(raw)
            }
            model.say("On its way to the Kindle")
        } catch { model.error = error.localizedDescription }
    }
}

// MARK: Taste

struct TasteView: View {
    @Environment(AppModel.self) private var model
    @State private var t: J?
    @State private var s: [String: Any] = [:]
    @State private var muting = ""
    @State private var naming = false

    private static let mix: [(String, String, Int, Int, Int, String)] = [
        ("pieces", "Pieces", 3, 20, 1, ""), ("videos", "Videos", 0, 6, 1, "up to "), ("podcasts", "Podcasts", 0, 6, 1, "up to "),
        ("torah", "Torah", 0, 4, 1, "at least "), ("wildcard", "Wildcard", 0, 3, 1, ""), ("longest", "Longest piece", 5, 120, 5, " min"),
        ("halflife", "Habits fade over", 7, 180, 7, " days"), ("hour", "Ready by", 3, 11, 1, ":00"),
    ]
    private static let days = [("sun", "Sun"), ("mon", "Mon"), ("tue", "Tue"), ("wed", "Wed"), ("thu", "Thu"), ("fri", "Fri"), ("sat", "Sat")]
    private static let learned = [("watched", "Watched"), ("opened", "Opened"), ("played", "Played"), ("highlighted", "Highlighted"),
                                  ("saved", "Saved"), ("up", "Thumbs up"), ("down", "Thumbs down")]

    var body: some View {
        ScrollView {
            if let t {
                VStack(alignment: .leading, spacing: 20) {
                    chips(t)
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 20) { topics(t); mixCard.frame(width: 340) }.frame(minWidth: 780)
                        VStack(alignment: .leading, spacing: 20) { topics(t); mixCard }
                    }
                    sources(t)
                }
                .padding(28)
                .frame(maxWidth: 1100, alignment: .leading)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(60)
            }
        }
        .task { await load() }
    }

    // MARK: what it learned

    @ViewBuilder private func chips(_ t: J) -> some View {
        if let rp = t.o("report"), (rp.i("shown") ?? 0) > 0 {
            chipRow("Last 2 weeks", [("Shown", rp.i("shown")), ("Opened", rp.i("opened")), ("Read", rp.i("read")), ("👍", rp.i("up")), ("👎", rp.i("down"))])
        }
        let seen = t.o("seen")
        let learn = Self.learned.compactMap { k, l in (seen?.i(k) ?? 0) > 0 ? (l, seen?.i(k)) : nil }
        if !learn.isEmpty { chipRow(nil, learn) }
        let rising = t.a("rising").compactMap { $0.s("word") }
        if !rising.isEmpty { chipRow("Picking up on", rising.map { ($0, nil) }) }
    }

    private func chipRow(_ head: String?, _ list: [(String, Int?)]) -> some View {
        FlowLayout(spacing: 6) {
            if let head { Text(head).font(.caption.weight(.semibold)).foregroundStyle(.secondary).padding(.vertical, 4).padding(.trailing, 4) }
            ForEach(Array(list.enumerated()), id: \.offset) { _, c in
                HStack(spacing: 4) {
                    Text(c.0).fontWeight(c.1 == nil ? .regular : .semibold)
                    if let n = c.1 { Text("\(n)").foregroundStyle(.secondary) }
                }
                .font(.caption).padding(.horizontal, 9).padding(.vertical, 4)
                .background(Color.secondary.opacity(0.1), in: Capsule())
            }
        }
    }

    // MARK: topics

    private func topics(_ t: J) -> some View {
        let list = t.a("topics"), top = max(0.01, list.compactMap { $0.d("weight") }.max() ?? 0.01)
        return TodayCard("Topics", accessory: {
            Button(naming ? "Naming…" : "Name Them Again") { Task { await nameAgain() } }.buttonStyle(.link).font(.caption).disabled(naming)
        }) {
            if list.isEmpty { Text("None yet.").foregroundStyle(.secondary) }
            ForEach(Array(list.enumerated()), id: \.offset) { _, tp in
                HStack(spacing: 10) {
                    Text(tp.s("name") ?? "").frame(width: 150, alignment: .leading).lineLimit(1)
                    GeometryReader { g in
                        Capsule().fill(Color.secondary.opacity(0.12))
                            .overlay(alignment: .leading) { Capsule().fill(Color.daf).frame(width: g.size.width * (tp.d("weight") ?? 0) / top) }
                    }
                    .frame(height: 6)
                    Text(tp.s("trend") == "up" ? "↑" : tp.s("trend") == "down" ? "↓" : "–")
                        .foregroundStyle(tp.s("trend") == "up" ? .green : tp.s("trend") == "down" ? .orange : .secondary)
                        .help(tp.s("trend") == "up" ? "Rising" : tp.s("trend") == "down" ? "Fading" : "")
                    seg3(tp.s("adj") ?? "") { await adjust("topic", tp.s("name") ?? "", $0) }
                }
            }
        }
    }

    /// Less / More / Mute, the one that's on pressed again to take it back.
    private func seg3(_ adj: String, _ set: @escaping (String) async -> Void) -> some View {
        HStack(spacing: 2) {
            ForEach([("less", "Less"), ("more", "More"), ("mute", "Mute")], id: \.0) { k, l in
                Button(l) { Task { await set(adj == k ? "" : k) } }
                    .buttonStyle(.bordered)
                    .tint(adj == k ? Color.daf : nil)
                    .controlSize(.small)
            }
        }
    }

    // MARK: the mix

    private var mixCard: some View {
        TodayCard("Mix") {
            Toggle("Every morning", isOn: flag("on"))
            HStack {
                Text("Days")
                Spacer()
                HStack(spacing: 2) {
                    ForEach(Self.days, id: \.0) { k, l in
                        let on = (s["days"] as? [String] ?? []).contains(k)
                        Button(l) { toggleDay(k) }.buttonStyle(.bordered).controlSize(.small).tint(on ? Color.daf : nil)
                    }
                }
            }
            ForEach(Self.mix, id: \.0) { m in
                let v = (s[m.0] as? NSNumber)?.intValue ?? m.2
                HStack {
                    Text(m.1)
                    Spacer()
                    Stepper(value: Binding(get: { v }, set: { n in set(m.0, max(m.2, min(m.3, n))) }), in: m.2...m.3, step: m.4) {
                        Text(Self.format(m, v)).monospacedDigit()
                    }
                    .fixedSize()
                }
            }
            Toggle("Kindle", isOn: flag("kindle"))
            Toggle("Chosen by the model", isOn: flag("ai"))
        }
    }

    private static func format(_ m: (String, String, Int, Int, Int, String), _ v: Int) -> String {
        switch m.5 {
        case ":00": return String(format: "%02d:00", v)
        case " min", " days": return "\(v)" + m.5
        default: return m.5 + "\(v)"
        }
    }

    private func flag(_ k: String) -> Binding<Bool> {
        Binding(get: { s[k] as? Bool ?? false }, set: { v in set(k, v) })
    }

    private func toggleDay(_ k: String) {
        var d = s["days"] as? [String] ?? []
        if d.contains(k) { d.removeAll { $0 == k } } else { d.append(k) }
        set("days", Self.days.map(\.0).filter { d.contains($0) })
    }

    private func set(_ k: String, _ v: Any) {
        s[k] = v
        Task {
            do { try await API.shared.send("PUT", "/api/edition/settings", [k: v]) }
            catch { model.error = error.localizedDescription }
        }
    }

    // MARK: sources

    private func sources(_ t: J) -> some View {
        TodayCard("Sources") {
            ForEach(Array(t.a("sources").enumerated()), id: \.offset) { _, x in
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(x.s("name") ?? "").lineLimit(1)
                        if let f = Self.facts(x.o("facts")) { Text(f).font(.caption).foregroundStyle(.secondary) }
                    }
                    Spacer()
                    seg3(x.s("adj") ?? "") { await adjust("source", x.s("name") ?? "", $0) }
                }
            }
            HStack {
                TextField("Source, or folder:Name", text: $muting).textFieldStyle(.roundedBorder).frame(maxWidth: 300)
                    .onSubmit { Task { await muteTyped() } }
                Button("Mute") { Task { await muteTyped() } }.disabled(muting.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            let muted = t.strings("muted")
            if !muted.isEmpty {
                Text("Muted").font(.subheadline.weight(.semibold)).padding(.top, 6)
                ForEach(muted, id: \.self) { m in
                    HStack {
                        Text(m.hasPrefix("folder:") ? String(m.dropFirst(7)) : m)
                        if m.hasPrefix("folder:") { Text("folder").font(.caption).foregroundStyle(.secondary) }
                        Spacer()
                        Button("Unmute") { Task { await adjust("source", m, "") } }.buttonStyle(.link).font(.caption)
                    }
                    .foregroundStyle(.secondary)
                }
            }
        }
    }

    /// The two things most done with a source: "12 watched · 👍 3".
    private static func facts(_ f: J?) -> String? {
        let names = ["watched": "watched", "opened": "opened", "played": "played", "highlighted": "highlighted", "saved": "saved", "up": "👍", "down": "👎"]
        guard let f else { return nil }
        let top = f.raw.compactMap { k, v -> (String, Int)? in
            guard names[k] != nil, let n = (v as? NSNumber)?.intValue else { return nil }
            return (k, n)
        }.sorted { $0.1 > $1.1 }.prefix(2)
        let s = top.map { k, n in k == "up" || k == "down" ? "\(names[k]!) \(n)" : "\(n) \(names[k]!)" }.joined(separator: " · ")
        return s.isEmpty ? nil : s
    }

    // MARK: doing

    private func load() async {
        do {
            let got = try await API.shared.json("/api/edition/taste")
            t = got
            s = got.o("settings")?.raw ?? [:]
        } catch { model.error = error.localizedDescription }
    }

    private func adjust(_ kind: String, _ name: String, _ adj: String) async {
        do {
            try await API.shared.send("PUT", "/api/edition/settings", [kind: ["name": name, "adj": adj]])
            await load()
        } catch { model.error = error.localizedDescription }
    }

    private func muteTyped() async {
        let v = muting.trimmingCharacters(in: .whitespaces)
        guard !v.isEmpty else { return }
        await adjust("source", v, "mute")
        muting = ""
    }

    private func nameAgain() async {
        naming = true
        defer { naming = false }
        do {
            try await API.shared.send("POST", "/api/edition/topics", [:])
            await load()
        } catch { model.error = error.localizedDescription }
    }
}
