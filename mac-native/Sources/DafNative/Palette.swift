import AppKit
import SwiftUI

/// ⌘K, as the page's: go anywhere in Daf, do something (add, log paper, feedback, undo), or search
/// everything: articles and the words inside them, books, highlights and the vault (/api/search).
/// ↑ and ↓ choose, Return goes, Esc closes.
struct PaletteSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openWindow) private var openWindow
    @State private var q = ""
    @State private var found: J?
    @State private var index = 0
    @FocusState private var focused: Bool

    struct Row: Identifiable {
        let id: Int
        let label: String
        let sub: String
        var snip: String?
        var serif = false
        let go: () -> Void
    }

    private static let places: [(String, Place)] = [
        ("Today", .today), ("Daily Review", .review), ("Home", .home), ("Inbox", .library("inbox")), ("Later", .library("later")),
        ("Shortlist", .shortlist), ("Archive", .library("archive")), ("All Feeds", .feed(nil)), ("Books", .books), ("Manga", .manga),
        ("Highlights", .highlights), ("Stats", .stats), ("Torah", .torah), ("Recovery", .recovery), ("Podcasts", .podcasts),
        ("Paper Pages", .paper), ("Sources", .sources),
    ] + Place.kinds.map { ($0.1, .kind($0.0)) }
    private static let settings: [(String, String)] = [
        ("Settings", "general"), ("Reading Settings", "reading"), ("Goals", "goals"), ("Account", "account"),
        ("Phone, Podcasts and Hardcover", "connections"), ("Newsletters and the Morning Email", "connections"),
        ("AI Settings", "ai"), ("Library Tags", "tags"), ("Import from Another App", "import"),
    ]

    private var rows: [Row] {
        let term = q.trimmingCharacters(in: .whitespaces)
        let has: (String) -> Bool = { term.isEmpty || $0.localizedCaseInsensitiveContains(term) }
        var out: [Row] = []
        func add(_ label: String, _ sub: String, snip: String? = nil, serif: Bool = false, _ go: @escaping () -> Void) {
            out.append(Row(id: out.count, label: label, sub: sub, snip: snip, serif: serif, go: go))
        }
        for (label, p) in Self.places where has(label) { add(label, "Go to") { model.place = p } }
        for (label, tab) in Self.settings where has(label) {
            add(label, "Go to") { UserDefaults.standard.set(tab, forKey: "prefsTab"); model.showSettings = true }
        }
        let acts: [(String, () -> Void)] = [
            ("Add a Link, a Book or a PDF", { model.sheet = .addLink }), ("Log Paper Minutes", { model.sheet = .paper }),
            ("Send Feedback", { model.sheet = .feedback }), ("Keyboard Shortcuts", { model.sheet = .shortcuts }),
            ("Undo", { model.undoLast() }), ("Sync Now", { Task { await model.syncNow() } }),
        ]
        for (label, run) in acts where has(label) || (label == "Send Feedback" && term.range(of: "bug|idea|report|problem", options: [.regularExpression, .caseInsensitive]) != nil) {
            add(label, "Do", run)
        }
        guard let f = found, term.count >= 2 else { return out }
        for d in f.a("docs") {
            let item = Item(d)
            add(item.title, (d.s("where_") == "feed" ? "Feed" : "Library") + (d.s("source").map { " · " + $0 } ?? "")) {
                openWindow(id: "route", value: model.route(for: item) ?? "#read/" + API.enc(item.id))
            }
        }
        for d in f.a("text") {
            add(d.s("title") ?? "", "In the text · " + (d.s("where_") == "feed" ? "Feed" : "Library") + (d.s("source").map { " · " + $0 } ?? ""), snip: d.s("snip")) {
                openWindow(id: "route", value: "#read/" + API.enc(d.s("id") ?? "") + "/q:" + API.enc(term))
            }
        }
        for b in f.a("books") {
            add(PaperPages.short(b.s("title")), "Book" + (b.s("author").map { " · " + $0 } ?? "")) { if let id = b.s("id") { model.showBook(id) } }
        }
        for h in f.a("highlights") {
            let book = h.s("book_id") ?? ""
            add(h.s("text") ?? "", "Highlight · " + PaperPages.short(h.s("title")), serif: true) {
                if book.hasPrefix("cal:") { model.showBook(book) }
                else { openWindow(id: "route", value: "#read/" + API.enc(book) + "/hl:" + API.enc(h.s("id") ?? "")) }
            }
        }
        for v in f.a("vault") {
            add(v.s("title") ?? "", "Vault · " + (v.s("folder") ?? "/") + (v.s("snippet").map { " · " + $0 } ?? "")) {
                if let o = v.s("open"), let u = URL(string: o) { NSWorkspace.shared.open(u) }
            }
        }
        return out
    }

    var body: some View {
        let list = rows
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                TextField("Search articles, books, highlights and the vault, or go somewhere", text: $q)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .focused($focused)
                    .onSubmit { go(list) }
                    .onKeyPress(.downArrow) { index = min(index + 1, max(0, list.count - 1)); return .handled }
                    .onKeyPress(.upArrow) { index = max(index - 1, 0); return .handled }
            }
            .padding(14)
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(list) { r in
                            Button { index = r.id; go(list) } label: { row(r, on: r.id == index) }
                                .buttonStyle(.plain)
                                .id(r.id)
                        }
                        if list.isEmpty {
                            Text("Nothing matches.").foregroundStyle(.secondary).padding(30)
                        }
                    }
                    .padding(6)
                }
                .onChange(of: index) { _, i in proxy.scrollTo(i) }
            }
        }
        .frame(width: 640, height: 480)
        .onAppear { focused = true }
        .onChange(of: q) { _, _ in index = 0 }
        .task(id: q) {
            let term = q.trimmingCharacters(in: .whitespaces)
            guard term.count >= 2 else { found = nil; return }
            try? await Task.sleep(nanoseconds: 220_000_000)
            if Task.isCancelled { return }
            let r = try? await API.shared.json("/api/search?q=" + API.enc(term))
            if !Task.isCancelled, q.trimmingCharacters(in: .whitespaces) == term { found = r }
        }
    }

    private func row(_ r: Row, on: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(r.label).font(r.serif ? .system(.body, design: .serif) : .body).lineLimit(2)
            if let s = r.snip { Text(Self.marked(s)).font(.callout).foregroundStyle(.secondary).lineLimit(2) }
            Text(r.sub).font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 7).fill(on ? Color.daf.opacity(0.2) : .clear))
        .contentShape(Rectangle())
    }

    /// The words found in a snippet, between \u{2} and \u{3}, in bold.
    static func marked(_ s: String) -> AttributedString {
        var out = AttributedString()
        var bold = false
        var run = ""
        func flush() {
            var a = AttributedString(run)
            if bold { a.inlinePresentationIntent = .stronglyEmphasized }
            out += a
            run = ""
        }
        for ch in s {
            if ch == "\u{2}" { flush(); bold = true } else if ch == "\u{3}" { flush(); bold = false } else { run.append(ch) }
        }
        flush()
        return out
    }

    private func go(_ list: [Row]) {
        guard list.indices.contains(index) else { return }
        let r = list[index]
        dismiss()
        DispatchQueue.main.async { r.go() }
    }
}

/// Help › Keyboard Shortcuts: what each key does where, in this app.
struct ShortcutsSheet: View {
    @Environment(\.dismiss) private var dismiss

    private static let groups: [(String, [(String, String)])] = [
        ("Everywhere", [("⌘K", "Search everything, or go somewhere"), ("⌘1 to ⌘8", "Today, Review, Inbox, Feed, Highlights, Books, Manga, Stats"),
                        ("⌘L", "Add a link, a book or a PDF"), ("⌘V", "Add the link or the files copied (nothing to paste into)"),
                        ("⇧⌘P", "Log paper minutes"), ("⌘R", "Refresh"), ("⌘Z", "Undo")]),
        ("Library and Feed lists", [("J or ↓", "Next item"), ("K or ↑", "Previous item"), ("Return", "Open it in a window of its own"),
                                    ("E", "Done (archive, or seen in the Feed)"), ("L", "Later"), ("S", "Save to the Library (Feed)"), ("F", "Shortlist"),
                                    ("T", "Tags"), ("D", "Delete"), ("Z", "Undo"), ("⌥⌘K", "Mark all seen"), ("⇧⌘R", "Check for new posts")]),
        ("Articles", [("J, K", "Next and previous paragraph"), ("H", "Highlight the paragraph or the selection"), ("N", "Highlight with a note"),
                      ("P", "Listen, or pause"), ("⇧L", "Read aloud from here"), ("E", "Done"), ("L", "Later"), ("S", "Save to the Library"),
                      ("F", "Shortlist"), ("T", "Tags"), ("D", "Delete"), ("Z", "Undo"), ("O", "Open the original"), ("⇧J, ⇧K", "Next and previous in the list"),
                      ("⇧N", "The article's note"), ("⇧R", "Reset reading progress"), ("⇧C", "Copy the link"), ("⇧M", "Edit the title and author"),
                      ("⌥⌘I", "Inspector"), ("⌥⌘A", "Ask"), ("⌥ while selecting", "Select without highlighting")]),
        ("Books", [("→, ←, Space", "Next and previous page"), ("H", "Highlight the selection"), ("B", "Bookmark the page"), ("P", "Read aloud"),
                   ("L", "Read aloud from a paragraph"), ("⌘F", "Search in the book"), ("⌥⌘T", "The sidebar")]),
        ("Review", [("K or →", "Keep"), ("L or ←", "Less often"), ("N", "Note"), ("F", "Favorite"), ("O", "Open at its spot"),
                    ("Space", "Show a flashcard's answer"), ("1 2 3 4", "Again, hard, good, easy")]),
        ("Manga", [("← →", "Page to the left or right"), ("Space, ↓", "Next page"), ("↑", "Previous page"), ("Home, End", "First and last page"),
                   ("[ ]", "Previous and next volume"), ("M", "Show or hide the bars"), ("T", "Every page"), ("S", "Settings"), ("R", "Reading mode"),
                   ("D", "Page layout"), ("C", "Scale"), ("B", "Crop borders"), ("A", "Auto scroll"), ("F", "Full screen"), ("Esc", "Close")]),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                ForEach(Self.groups, id: \.0) { g in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(g.0).font(.headline)
                        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                            ForEach(g.1, id: \.0) { k in
                                GridRow {
                                    Text(k.0).font(.callout.monospaced()).foregroundStyle(.secondary).gridColumnAlignment(.trailing)
                                    Text(k.1).font(.callout)
                                }
                            }
                        }
                    }
                }
            }
            .padding(24)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(width: 560, height: 600)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
    }
}
