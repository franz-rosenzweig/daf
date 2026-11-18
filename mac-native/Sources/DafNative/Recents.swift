import SwiftUI

/// Recents, as the page has it (web/recents.js, recents.py): everything read, watched, listened to or
/// opened, newest first, a day at a time. A row opens what it was; a private sitting has no link.
/// More asks for the week before.
struct RecentsView: View {
    @State private var days: [J] = []
    @State private var next: String?
    @State private var loaded = false
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                ForEach(days, id: \.self) { d in
                    Panel(Self.dayName(d.s("date") ?? "")) {
                        VStack(spacing: 0) {
                            ForEach(Array(d.a("items").enumerated()), id: \.offset) { i, x in
                                if i > 0 { Divider() }
                                RecentRow(x: x)
                            }
                        }
                        .padding(.horizontal, 14)
                        .background(Theme.shared.card, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
                if loaded && days.isEmpty { Text("Nothing yet").foregroundStyle(.secondary) }
                if next != nil {
                    Button(busy ? "Loading…" : "More") { Task { await more() } }.disabled(busy)
                }
            }
            .padding(28)
            .frame(maxWidth: 820, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .navigationTitle("Recents")
        .task { await load() }
    }

    private func load() async {
        guard let r = try? await API.shared.json("/api/recents?n=7") else { loaded = true; return }
        days = r.a("days")
        next = r.s("next")
        loaded = true
        if days.isEmpty && next != nil { await more() }
    }

    /// The week before; through a quiet stretch it keeps asking until there's something to show or nothing older.
    private func more() async {
        guard !busy, var before = next else { return }
        busy = true
        defer { busy = false }
        for i in 0..<9 {
            guard let r = try? await API.shared.json("/api/recents?n=\(i == 0 ? 7 : 14)&before=" + API.enc(before)) else { return }
            days += r.a("days")
            next = r.s("next")
            guard r.a("days").isEmpty, let older = next else { return }
            before = older
        }
    }

    /// Today, Yesterday, the weekday within the week, then the whole date.
    static func dayName(_ iso: String) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        guard let d = f.date(from: iso) else { return iso }
        let cal = Calendar.current
        let n = cal.dateComponents([.day], from: cal.startOfDay(for: d), to: cal.startOfDay(for: Date())).day ?? 0
        if n == 0 { return "Today" }
        if n == 1 { return "Yesterday" }
        let out = DateFormatter()
        out.locale = Locale(identifier: "en_US")
        out.dateFormat = n < 7 ? "EEEE" : cal.component(.year, from: d) == cal.component(.year, from: Date()) ? "EEEE, MMMM d" : "EEEE, MMMM d, yyyy"
        return out.string(from: d)
    }
}

/// One thing of a day's: its picture or its kind's icon, its name, what it was and for how long, and when.
struct RecentRow: View {
    @Environment(AppModel.self) private var model
    let x: J
    private static let icons = ["Book": "books.vertical", "Kindle": "book.closed", "Article": "doc.text", "Video": "play.rectangle",
                                "Podcast": "headphones", "Audiobook": "headphones", "Manga": "book.pages", "Paper": "doc"]

    var body: some View {
        if let go = x.s("go") {
            Button { open(go) } label: { line.contentShape(Rectangle()) }.buttonStyle(.plain)
        } else {
            line
        }
    }

    private var line: some View {
        let book = x.s("go")?.hasPrefix("book/") == true, kind = x.s("kind") ?? ""
        var meta: [String] = []
        for m in [kind, x.s("author") ?? "", (x.i("minutes") ?? 0) > 0 ? "\(x.i("minutes") ?? 0) min" : ""] where !m.isEmpty && !meta.contains(m) { meta.append(m) }
        return HStack(spacing: 12) {
            Group {
                if let pic = x.s("pic") { Thumb(path: pic, book: book) }
                else { Image(systemName: Self.icons[kind] ?? "doc.text").font(.title3).foregroundStyle(.secondary).frame(height: 40) }
            }
            .frame(width: 54)
            VStack(alignment: .leading, spacing: 2) {
                Text(book ? PaperPages.short(x.s("title")) : (x.s("title") ?? "")).font(.system(.body, design: .serif).weight(.semibold)).lineLimit(2)
                Text(meta.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(x.s("time") ?? "").font(.caption).monospacedDigit().foregroundStyle(.secondary)
        }
        .padding(.vertical, 8)
    }

    /// Where the page's link goes: a book's page on Books, the reader in its own window, Listen, Paper Pages.
    private func open(_ go: String) {
        let cut = go.firstIndex(of: "/")
        let head = cut.map { String(go[..<$0]) } ?? go, rest = cut.map { String(go[go.index(after: $0)...]) }
        switch head {
        case "paper": model.place = .paper
        case "book": if let rest { model.showBook(rest) }
        case "read", "mread": if let rest { model.openRoute = "#" + head + "/" + API.enc(rest) }
        default: model.goTo("#" + go)
        }
    }
}
