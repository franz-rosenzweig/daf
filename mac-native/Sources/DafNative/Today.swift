import SwiftUI

/// Today, as the page's (/api/today): the day and Year 30, the notices (Shabbat, a book the Kindle
/// finished, one read off the nightstand), the ring with the other goals and the minutes by source,
/// the sittings, the day's review, on this day, the nightstand, the week, Year 30's grid, and how
/// fresh the sources are. A goal met or a milestone reached gets its moment, once.
struct TodayView: View {
    @Environment(AppModel.self) private var model
    @State private var finishing: J?
    @AppStorage("celebrated") private var celebrated = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let t = model.today {
                    hello(t)
                    notices(t)
                    GoalCard(today: t)
                    sittings(t)
                    review(t)
                    onThisDay(t)
                    nightstand(t)
                    if !t.a("week").isEmpty {
                        Heading("This week")
                        Week(days: t.a("week"))
                    }
                    if let y = t.o("year30") { YearCard(year: y, goal: t.d("goal") ?? 60) }
                }
                if !model.continueItems.isEmpty {
                    Heading("Keep reading")
                    VStack(spacing: 2) {
                        ForEach(model.continueItems) { item in
                            Button { model.selection = item.id } label: {
                                ItemRow(item: item)
                                    .padding(.horizontal, 8)
                                    .background(RoundedRectangle(cornerRadius: 8).fill(model.selection == item.id ? Color.accentColor.opacity(0.18) : .clear))
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                if let t = model.today { Text(Self.fresh(t)).font(.caption).foregroundStyle(.tertiary) }
            }
            .padding(20)
        }
        .navigationTitle("Today")
        .toolbar {
            ToolbarItem {
                Button { model.sheet = .paper } label: { Label("Log Paper", systemImage: "book.pages") }
                    .help("Minutes read on paper")
            }
            ToolbarItem {
                Button { model.reload() } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                    .keyboardShortcut("r", modifiers: .command)
            }
        }
        .sheet(item: Binding(get: { finishing.map { Finishing(j: $0) } }, set: { finishing = $0?.j })) { f in
            FinishSheet(bookID: f.j.s("id") ?? "", title: f.j.s("title") ?? "") { model.reload() }.environment(model)
        }
        .onChange(of: model.today) { _, t in if let t { celebrate(t) } }
        .onAppear { if let t = model.today { celebrate(t) } }
    }

    private struct Finishing: Identifiable { let j: J; var id: String { j.s("id") ?? "" } }

    // MARK: the parts

    private func hello(_ t: J) -> some View {
        let dayN = t.o("year30")?.i("today_index").map { $0 + 1 }
        let any = t.o("streak")?.i("any") ?? 0, atGoal = t.o("streak")?.i("goal") ?? 0, goal = t.d("goal") ?? 60
        let streak: String? = any > 1 ? (atGoal > 1 ? "\(atGoal) days in a row " + Self.atWord(goal) : "\(any) days in a row reading") : nil
        return VStack(alignment: .leading, spacing: 3) {
            Text(Self.longDate(t.s("date"))).font(.system(.title2, design: .serif).weight(.semibold))
            Text([dayN.map { "Year 30, day \($0)" }, streak].compactMap { $0 }.joined(separator: " · "))
                .font(.subheadline).foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func notices(_ t: J) -> some View {
        if t.b("shabbat") {
            Notice(icon: "moon.stars") {
                let friday = Calendar.current.component(.weekday, from: Date()) == 6
                Text((friday ? "Shabbat is coming. This week's parasha is on the Torah shelf. " : "Shabbat. ") + "Paper counts: log it here after havdalah, or send Ezer \u{201C}shabbat 60\u{201D}.")
            } actions: {
                if Calendar.current.component(.weekday, from: Date()) == 6 { Button("The Torah Shelf") { model.place = .torah } }
                Button("Log Paper") { model.sheet = .paper }
            }
        }
        ForEach(t.a("hc_finished"), id: \.self) { b in
            Notice(icon: "books.vertical") {
                Text("You reached the end of **\(PaperPages.short(b.s("title")))** on the Kindle. Mark it read on Hardcover?")
            } actions: {
                Button("Mark It Read") { finishing = b }.buttonStyle(.borderedProminent)
                Button("Not Yet") { Task { await notYet(b.s("id")) } }
            }
        }
        if let o = t.o("offstand") {
            Notice(icon: "books.vertical") {
                Text("You've been reading **\(PaperPages.short(o.s("title")))**, and it isn't on the nightstand.")
            } actions: {
                Button("Swap It In") { model.place = .books; Task { try? await Task.sleep(nanoseconds: 300_000_000); model.selection = o.s("id") } }
                Button("Just Browsing") { Task { await justBrowsing(t, o.s("id")) } }
            }
        }
    }

    @ViewBuilder
    private func sittings(_ t: J) -> some View {
        let list = t.a("sessions").filter { ($0.d("minutes") ?? 0) >= 0.5 }
        Heading("Sittings")
        if list.isEmpty {
            Text("Nothing yet today. Kindle reading arrives when the Kindle sleeps or closes a book; audiobooks every five minutes.")
                .font(.callout).foregroundStyle(.secondary)
        } else {
            VStack(spacing: 0) {
                ForEach(Array(list.enumerated()), id: \.offset) { k, s in
                    if k > 0 { Divider() }
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(s.b("private") ? "Private reading" : PaperPages.short(s.s("title"))).lineLimit(1)
                                if !s.b("counted") { Text("not counted").font(.caption2).padding(.horizontal, 5).padding(.vertical, 1).background(.quaternary, in: Capsule()) }
                            }
                            Text([s.s("start"), s.s("label"), s.s("note")].compactMap { $0 }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer()
                        Text("\(max(1, Int((s.d("minutes") ?? 0).rounded()))) min").monospacedDigit().foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 7)
                }
            }
        }
    }

    @ViewBuilder
    private func review(_ t: J) -> some View {
        if let rv = t.o("review"), let total = rv.i("total"), total > 0 {
            let left = total - (rv.i("done") ?? 0), cards = t.i("cards_due") ?? 0
            let done = left <= 0 && cards == 0, days = rv.o("streak")?.i("days") ?? 0
            let f = rv.o("first"), books = rv.list("books").compactMap { $0 as? String }.map { PaperPages.short($0) }
            HStack(alignment: .top, spacing: 14) {
                if done {
                    Image(systemName: "checkmark.circle.fill").font(.system(size: 34)).foregroundStyle(Color.accentColor).frame(width: 40)
                } else if let f, let b = f.s("book_id"), b.hasPrefix("cal:") {
                    Thumb(path: "/api/cover/" + API.enc(b), book: true)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Daily Review").font(.headline)
                    Text(done
                         ? "Done for today" + (days > 1 ? " · \(days) days in a row" : "")
                         : plural(total, "highlight") + (books.first.map { " from " + $0 + (books.count > 1 ? " and more" : "") } ?? "") + (cards > 0 ? " · " + plural(cards, "flashcard") : ""))
                        .font(.callout).foregroundStyle(.secondary)
                    if let f, !done, let q = f.s("text") {
                        Text("\u{201C}" + q + "\u{201D}").font(.system(.callout, design: .serif)).lineLimit(3)
                    }
                    if done {
                        Button("Review More") { model.startReview(themed: "n=10") }
                    } else {
                        let go: String = (rv.i("done") ?? 0) > 0 ? "Continue · \(left) left" : "Review"
                        Button(go) { model.place = .review }.buttonStyle(.borderedProminent)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(14)
            .background(.background.secondary, in: RoundedRectangle(cornerRadius: 12))
        }
    }

    @ViewBuilder
    private func onThisDay(_ t: J) -> some View {
        let list = t.a("on_this_day")
        if !list.isEmpty {
            HStack { Heading("On this day"); Spacer(); Button("Stats") { model.place = .stats }.buttonStyle(.link).font(.caption) }
            ForEach(list, id: \.self) { x in
                VStack(alignment: .leading, spacing: 4) {
                    Text("\u{201C}" + (x.s("text") ?? "") + "\u{201D}").font(.system(.body, design: .serif))
                    Text(PaperPages.short(x.s("title")) + (x.i("year").map { " · \($0)" } ?? "")).font(.caption).foregroundStyle(.secondary)
                }
                .contentShape(Rectangle())
                .onTapGesture { if let o = x.s("open") { model.openRoute = o } }
                .help(x.s("open") == nil ? String() : "Open at this spot")
            }
        }
    }

    @ViewBuilder
    private func nightstand(_ t: J) -> some View {
        let own = t.a("nightstand"), list = own.isEmpty ? t.a("nightstand_suggested") : own
        if !list.isEmpty {
            HStack {
                Heading("Nightstand")
                Spacer()
                if own.isEmpty {
                    Button("Use These Three") { Task { await useThese(list) } }.help("Suggested from what you read lately")
                } else {
                    Button("Change") { model.place = .books }.buttonStyle(.link).font(.caption)
                }
            }
            if own.isEmpty { Text("Suggested from what you read lately. Choose your three on Books.").font(.caption).foregroundStyle(.secondary) }
            VStack(spacing: 2) {
                ForEach(list, id: \.self) { b in
                    Button { model.selection = b.s("id") } label: {
                        HStack(spacing: 12) {
                            Thumb(path: b.b("has_cover") ? "/api/cover/" + API.enc(b.s("id") ?? "") : nil, book: true)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(PaperPages.short(b.s("title"))).font(.system(.callout, design: .serif).weight(.semibold)).lineLimit(2)
                                Text(b.s("author") ?? "").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                if let p = b.d("progress") {
                                    HStack(spacing: 6) {
                                        ProgressView(value: min(100, p), total: 100).frame(width: 70)
                                        Text("\(Int(p.rounded()))%" + (b.s("progress_note").map { " · " + $0 } ?? "")).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                                    }
                                }
                                if let a = b.s("audio_note") { Text("Audiobook · " + a).font(.caption2).foregroundStyle(.secondary) }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(6)
                        .background(RoundedRectangle(cornerRadius: 8).fill(model.selection == b.s("id") ? Color.accentColor.opacity(0.18) : .clear))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: doing

    private func notYet(_ id: String?) async {
        guard let id else { return }
        do {
            try await API.shared.send("POST", "/api/hardcover/book/\(API.enc(id))/notyet", [:])
            model.reload()
        } catch { model.error = error.localizedDescription }
    }

    private func justBrowsing(_ t: J, _ id: String?) async {
        guard let id else { return }
        do {
            try await API.shared.send("PUT", "/api/nightstand", ["ids": t.a("nightstand").compactMap { $0.s("id") }, "not_nightstand": id])
            model.reload()
        } catch { model.error = error.localizedDescription }
    }

    private func useThese(_ list: [J]) async {
        do {
            try await API.shared.send("PUT", "/api/nightstand", ["ids": list.compactMap { $0.s("id") }])
            model.say("On the nightstand")
            model.reload()
        } catch { model.error = error.localizedDescription }
    }

    /// Goals met and milestones reached, each said once. The first time this Mac sees them, it
    /// remembers what's already met without a party.
    private func celebrate(_ t: J) {
        guard t.s("date") == t.s("today") else { return }
        let first = UserDefaults.standard.string(forKey: "celebrated") == nil
        var done = celebrated.split(separator: "\n").map(String.init)
        var fresh: [(key: String, text: String, big: Bool)] = []
        for g in t.a("goals") where g.b("met") && g.b("on") {
            guard let k = g.s("key"), !done.contains(k) else { continue }
            let words = g.s("text") ?? ""
            let text = g.s("kind") == "streak" ? "\(g.i("target") ?? 0) days in a row at the goal." : Self.metWord(g) + " " + words.prefix(1).uppercased() + words.dropFirst() + "."
            fresh.append((k, text, false))
        }
        for m in t.a("milestones_new") {
            guard let id = m.s("id"), !done.contains("ms:" + id) else { continue }
            fresh.append(("ms:" + id, (m.s("label") ?? "") + ".", true))
        }
        guard !fresh.isEmpty else { return }
        done += fresh.map(\.key)
        celebrated = done.suffix(200).joined(separator: "\n")
        if first { return }
        model.say((fresh.first { $0.big } ?? fresh[0]).text)
    }

    // MARK: words

    static func atWord(_ goal: Double) -> String { goal == 60 ? "at the hour" : "at your goal" }

    static func metWord(_ g: J) -> String {
        let p = g.s("period")
        if g.s("kind") == "minutes" && p == "day" && g.d("target") == 60 { return "That's the hour." }
        return ["day": "That's today's goal.", "week": "That's this week's goal.", "month": "That's this month's goal."][p ?? ""] ?? "Goal met."
    }

    static func longDate(_ iso: String?) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let iso, let d = f.date(from: String(iso.prefix(10))) else { return "Today" }
        f.dateFormat = "EEEE, MMMM d"
        return f.string(from: d)
    }

    static func ago(_ ts: Double?) -> String {
        guard let ts, ts > 0 else { return "never" }
        let d = Date().timeIntervalSince1970 - ts
        if d < 3600 { return "\(max(1, Int((d / 60).rounded()))) min ago" }
        if d < 172_800 { return "\(Int((d / 3600).rounded())) h ago" }
        return "\(Int((d / 86400).rounded())) days ago"
    }

    static func fresh(_ t: J) -> String {
        let f = t.o("fresh"), kin = f?.o("kindle")?.o("last")
        let plugin = kin?.d("plugin")
        return "Kindle: newest page " + ago(plugin ?? kin?.d("koinsight")) + (plugin != nil ? " (Daf plugin)" : " (KoInsight)")
            + " · Audiobookshelf checked " + ago(f?.o("audiobookshelf")?.d("checked")) + " · updates every five minutes"
    }
}

/// A line across Today with something to do about it.
struct Notice<Words: View, Actions: View>: View {
    let icon: String
    @ViewBuilder let words: Words
    @ViewBuilder let actions: Actions
    init(icon: String, @ViewBuilder words: () -> Words, @ViewBuilder actions: () -> Actions) {
        self.icon = icon; self.words = words(); self.actions = actions()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Image(systemName: icon).foregroundStyle(Color.accentColor)
                words.font(.callout).fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) { actions }.controlSize(.small).padding(.leading, 26)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }
}

/// The ring and what it follows (minutes, or another goal), the other goals as chips, and the
/// minutes by source, with the ones that don't count marked.
struct GoalCard: View {
    @Environment(AppModel.self) private var model
    let today: J

    private static let sources = ["kindle", "ebook", "manga", "audio", "article", "paper", "video", "podcast"]
    private static let icons = ["minutes": "clock", "pages": "doc.text", "books": "books.vertical", "days": "calendar",
                                "streak": "flame", "highlights": "highlighter", "reviews": "rectangle.stack"]

    var body: some View {
        let m = today.o("main")
        let minutesMain = m == nil || (m?.s("kind") == "minutes" && m?.s("period") == "day")
        let counted = today.d("counted") ?? 0, goal = today.d("goal") ?? 60
        let done = minutesMain ? counted : m?.d("done") ?? 0
        let target = max(1, minutesMain ? goal : m?.d("target") ?? 1)
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 18) {
                Button { goals() } label: {
                    ZStack {
                        Circle().stroke(.quaternary, lineWidth: 10)
                        Circle().trim(from: 0, to: min(1, done / target))
                            .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                            .rotationEffect(.degrees(-90))
                        Text("\(Int(done))").font(.system(.title, design: .rounded).weight(.semibold)).monospacedDigit()
                    }
                    .frame(width: 84, height: 84)
                }
                .buttonStyle(.plain)
                .help("Goals")
                VStack(alignment: .leading, spacing: 3) {
                    if minutesMain {
                        Text("of \(Int(goal.rounded())) minutes").font(.title3.weight(.semibold))
                        Text(counted >= goal ? (goal == 60 ? "That's the hour." : "That's today's goal.") : "\(Int((goal - counted).rounded(.up))) to go")
                            .font(.callout).foregroundStyle(.secondary)
                    } else if let m {
                        Text("of \(m.i("target") ?? 0) " + (m.s("unit") ?? "")).font(.title3.weight(.semibold))
                        Text((m.s("period_label") ?? "") + " · " + (m.b("met") ? TodayView.metWord(m) : "\((m.i("target") ?? 0) - (m.i("done") ?? 0)) to go"))
                            .font(.callout).foregroundStyle(.secondary)
                        Text("\(Int(counted.rounded())) minutes today").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            let others = today.a("goals").filter { !$0.b("main") }
            if !others.isEmpty {
                GoalChips(goals: others, icons: Self.icons) { goals() }
            }
            let count = today.o("settings")?.o("count"), mins = today.o("minutes"), labels = today.o("labels")
            let rows = Self.sources.filter { count?.b($0) == true || (mins?.d($0) ?? 0) > 0 }
            if !rows.isEmpty {
                Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 4) {
                    ForEach(rows, id: \.self) { k in
                        let on = count?.b(k) == true
                        GridRow {
                            Text((labels?.s(k) ?? k.capitalized) + (on ? "" : " · not counted"))
                            Text("\(Int((mins?.d(k) ?? 0).rounded())) min").monospacedDigit().gridColumnAlignment(.trailing)
                        }
                        .foregroundStyle(on ? HierarchicalShapeStyle.primary : .tertiary)
                    }
                }
                .font(.callout)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 12))
    }

    private func goals() {
        UserDefaults.standard.set("goals", forKey: "prefsTab")
        model.showSettings = true
    }
}

/// The other goals, each a chip, filled when it's met.
struct GoalChips: View {
    let goals: [J]
    let icons: [String: String]
    let tap: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(goals, id: \.self) { g in
                Button(action: tap) {
                    Label(g.s("text") ?? "", systemImage: g.b("met") ? "checkmark.circle.fill" : icons[g.s("kind") ?? ""] ?? "target")
                        .font(.caption)
                        .padding(.horizontal, 9).padding(.vertical, 4)
                        .background(g.b("met") ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.1), in: Capsule())
                }
                .buttonStyle(.plain)
                .help(g.s("label") ?? "")
            }
        }
    }
}

/// Year 30: the numbers and every day as a square, a week to a column, shaded by that day's goal.
struct YearCard: View {
    let year: J
    let goal: Double
    @State private var hover: Int?

    var body: some View {
        let targets = year.list("targets").compactMap { ($0 as? NSNumber)?.doubleValue }
        let days = year.list("days").compactMap { ($0 as? NSNumber)?.doubleValue }
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Heading("Year 30")
                Spacer()
                Text("October 9, 2026 to October 8, 2027").font(.caption).foregroundStyle(.tertiary)
            }
            HStack(spacing: 18) {
                stat(String(format: "%.1f h", year.d("total_hours") ?? 0), "of \(Int((targets.reduce(0, +) / 60).rounded()))")
                stat("\(year.i("days_read") ?? 0)", "days read")
                stat("\(year.i("days_goal") ?? 0)", "days " + TodayView.atWord(goal))
                stat("\((year.i("today_index") ?? -1) + 1)", "days in")
            }
            grid(days, targets)
            HStack(spacing: 4) {
                if let h = hover, h < days.count {
                    Text(day(h) + ": \(Int(days[h].rounded())) min").monospacedDigit()
                } else {
                    Text("none")
                    ForEach(0..<5) { k in RoundedRectangle(cornerRadius: 2).fill(Self.shade(k)).frame(width: 9, height: 9) }
                    Text(goal == 60 ? "an hour or more" : "the day's goal or more")
                }
            }
            .font(.caption2).foregroundStyle(.secondary)
        }
    }

    private func stat(_ v: String, _ l: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(v).font(.system(.headline, design: .rounded)).monospacedDigit()
            Text(l).font(.caption2).foregroundStyle(.secondary)
        }
    }

    /// Fits the column: a square's side is the width over the weeks.
    private func grid(_ days: [Double], _ targets: [Double]) -> some View {
        let lead = ((year.i("weekday") ?? 0) + 1) % 7         // Monday = 0; weeks start on Sunday
        let weeks = (lead + days.count + 6) / 7
        let today = year.i("today_index")
        return GeometryReader { geo in
            let step = geo.size.width / CGFloat(max(1, weeks)), side = step * 0.8
            Canvas { ctx, _ in
                for (i, m) in days.enumerated() {
                    let c = i + lead, x = CGFloat(c / 7) * step, y = CGFloat(c % 7) * step
                    let r = CGRect(x: x, y: y, width: side, height: side)
                    let path = Path(roundedRect: r, cornerRadius: side * 0.22)
                    let future = today.map { i > $0 } ?? false
                    ctx.fill(path, with: .color(Self.shade(Self.level(m, i < targets.count ? targets[i] : goal)).opacity(future ? 0.55 : 1)))
                    if i == today { ctx.stroke(path, with: .color(.primary), lineWidth: 1.2) }
                }
            }
            .onContinuousHover { phase in
                if case .active(let p) = phase {
                    let c = Int(p.x / step) * 7 + Int(p.y / step) - lead
                    hover = c >= 0 && c < days.count && Int(p.y / step) < 7 ? c : nil
                } else { hover = nil }
            }
            .frame(height: step * 7)
        }
        .aspectRatio(CGFloat(max(1, weeks)) / 7, contentMode: .fit)
    }

    private func day(_ i: Int) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        guard let s = year.s("start"), let d0 = f.date(from: s), let d = Calendar.current.date(byAdding: .day, value: i, to: d0) else { return "" }
        f.dateFormat = "EEE, MMM d"
        return f.string(from: d)
    }

    /// As the page shades it: against that day's goal (an hour: 60, 30, 15 and 1 minutes).
    static func level(_ m: Double, _ t: Double) -> Int { m >= t ? 4 : m >= t / 2 ? 3 : m >= t / 4 ? 2 : m >= 1 ? 1 : 0 }
    static func shade(_ k: Int) -> Color { k == 0 ? Color.secondary.opacity(0.14) : Color.accentColor.opacity([0, 0.3, 0.5, 0.75, 1][k]) }
}
