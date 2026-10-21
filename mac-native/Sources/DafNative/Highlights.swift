import SwiftUI

/// Every highlight, by book or article: the list in the middle (search, a source, a colour, a tag,
/// favorites only, private books too; newest, by book or oldest first), the one chosen on the right
/// with its highlights, their notes, tags and colours. Export what the filters show, or review it.
@MainActor
@Observable
final class HighlightsModel {
    var groups: [J] = []
    var count = 0
    var query = ""
    var source = ""
    var favorites = false
    var color = ""
    var tag = ""
    var sort = "recent"            // recent, book (in reading order), oldest
    var showPrivate = false
    var tags: [String] = []
    var groupID: String?
    var loading = false

    var group: J? { groups.first { Self.key($0) == groupID } }
    static func key(_ g: J) -> String { g.s("book_id") ?? g.s("title") ?? "" }

    func load() async {
        loading = true
        defer { loading = false }
        guard let r = try? await API.shared.json("/api/highlights?" + filter + "&sort=" + sort) else { return }
        tags = r.strings("tags")
        groups = r.a("groups")
        count = r.i("count") ?? 0
        if group == nil { groupID = groups.first.map(Self.key) }
    }

    /// The filters as the page's (and its export's and Review These') query.
    var filter: String {
        var q: [String] = []
        if !query.isEmpty { q.append("q=" + API.enc(query)) }
        if showPrivate { q.append("private=1") }
        if !source.isEmpty { q.append("source=" + source) }
        if !color.isEmpty { q.append("color=" + color) }
        if !tag.isEmpty { q.append("tag=" + API.enc(tag)) }
        if favorites { q.append("fav=1") }
        return q.joined(separator: "&")
    }

    var filtered: Bool { !source.isEmpty || favorites || !color.isEmpty || !tag.isEmpty || showPrivate }

    /// Export: Markdown by book, CSV or JSON (what the filters show), or every flashcard for Anki.
    func export(_ fmt: String) async {
        let path = fmt == "anki" ? "/api/cards/export" : "/api/highlights/export?fmt=\(fmt)" + (filter.isEmpty ? "" : "&" + filter)
        guard let data = try? await API.shared.data(path) else { AppModel.shared.error = "The export didn't come."; return }
        let p = NSSavePanel()
        p.nameFieldStringValue = fmt == "anki" ? "Daf flashcards.txt" : "Daf highlights." + (fmt == "md" ? "md" : fmt)
        if p.runModal() == .OK, let u = p.url { try? data.write(to: u) }
    }

    func update(_ id: String, _ change: (inout [String: Any]) -> Void) {
        for (gi, g) in groups.enumerated() {
            var items = g.a("items")
            guard let k = items.firstIndex(where: { $0.s("id") == id }) else { continue }
            var raw = items[k].raw
            change(&raw)
            items[k] = J(raw)
            var graw = g.raw
            graw["items"] = items.map(\.raw)
            groups[gi] = J(graw)
        }
    }

    func remove(_ id: String) {
        for (gi, g) in groups.enumerated() {
            var graw = g.raw
            graw["items"] = g.a("items").filter { $0.s("id") != id }.map(\.raw)
            groups[gi] = J(graw)
        }
    }
}

/// The middle column: books and articles with highlights.
struct HighlightGroups: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var hl = model.highlights
        List(selection: $hl.groupID) {
            ForEach(hl.groups, id: \.self) { g in
                HStack(spacing: 10) {
                    Thumb(path: g.b("has_cover") ? "/api/cover/" + API.enc(g.s("book_id") ?? "") : nil, book: true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(g.s("title") ?? "").font(.system(.body, design: .serif).weight(.semibold)).lineLimit(2)
                        Text([g.s("author"), plural(g.a("items").count, "highlight"), (g.i("notes") ?? 0) > 0 ? plural(g.i("notes")!, "note") : nil].compactMap { $0 }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                .padding(.vertical, 3)
                .tag(HighlightsModel.key(g))
            }
        }
        .listStyle(.inset)
        .navigationTitle("Highlights")
        .navigationSubtitle("\(hl.count)")
        .searchable(text: $hl.query, placement: .toolbar, prompt: "Highlights, notes, tags")
        .onSubmit(of: .search) { Task { await hl.load() } }
        .toolbar {
            ToolbarItem {
                Menu {
                    Picker("From", selection: $hl.source) {
                        Text("Everywhere").tag("")
                        Text("Kindle").tag("kindle")
                        Text("Made in Daf").tag("daf")
                        Text("Articles").tag("articles")
                        Text("Audiobooks").tag("audio")
                        Text("Paper").tag("paper")
                        Text("Readwise").tag("readwise")
                    }
                    Picker("Color", selection: $hl.color) {
                        Text("Any Color").tag("")
                        ForEach(["yellow", "green", "blue", "pink", "purple"], id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    if !hl.tags.isEmpty {
                        Picker("Tag", selection: $hl.tag) {
                            Text("Any Tag").tag("")
                            ForEach(hl.tags, id: \.self) { Text("#" + $0).tag($0) }
                        }
                    }
                    Toggle("Favorites Only", isOn: $hl.favorites)
                    Toggle("Show Private Books", isOn: $hl.showPrivate)
                    Divider()
                    Picker("Order", selection: $hl.sort) {
                        Text("Newest").tag("recent")
                        Text("By Book").tag("book")
                        Text("Oldest").tag("oldest")
                    }
                    .pickerStyle(.inline)
                } label: { Label("Filter", systemImage: hl.filtered ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle") }
            }
            ToolbarItem {
                Button { // Private books stay out of every review.
                    let q = hl.filter.split(separator: "&").filter { $0 != "private=1" }
                    model.startReview(themed: (["n=30"] + q).joined(separator: "&"))
                } label: {
                    Label("Review These", systemImage: "rectangle.stack")
                }
                .help("A review of what the filters show")
            }
            ToolbarItem {
                Menu {
                    Button("Markdown, by Book…") { Task { await hl.export("md") } }
                    Button("CSV…") { Task { await hl.export("csv") } }
                    Button("JSON…") { Task { await hl.export("json") } }
                    Divider()
                    Button("Flashcards for Anki…") { Task { await hl.export("anki") } }
                } label: { Label("Export", systemImage: "square.and.arrow.up") }
            }
        }
        .onChange(of: hl.source) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.favorites) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.color) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.tag) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.sort) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.showPrivate) { _, _ in Task { await hl.load() } }
        .task { await hl.load() }
    }
}

/// The right side: one book's highlights.
struct HighlightGroupView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    let group: J
    @State private var editing: J?
    @State private var sheet: HLSheet?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(group.s("title") ?? "").font(.system(.title, design: .serif).weight(.semibold))
                    if let a = group.s("author") { Text(a).foregroundStyle(.secondary) }
                }
                .padding(.bottom, 8)
                ForEach(group.a("items"), id: \.self) { h in
                    HighlightCard(h: h, edit: { editing = h }, open: { if let o = h.s("open") { openWindow(id: "route", value: o) } },
                                  tool: { sheet = $0 }, title: group.s("title") ?? "", author: group.s("author"))
                }
            }
            .frame(maxWidth: 720, alignment: .leading)
            .padding(28)
            .frame(maxWidth: .infinity)
        }
        .sheet(item: Binding(get: { editing.map(Editing.init) }, set: { editing = $0?.h })) { e in
            NoteSheet(h: e.h)
        }
        .sheet(item: $sheet) { s in
            HLSheetView(sheet: s) { hid, fields in model.highlights.update(hid) { raw in for (k, v) in fields { raw[k] = v } } }
        }
    }

    struct Editing: Identifiable { let h: J; var id: String { h.s("id") ?? "" } }
}

struct HighlightCard: View {
    @Environment(AppModel.self) private var model
    let h: J
    let edit: () -> Void
    let open: () -> Void
    var tool: (HLSheet) -> Void = { _ in }
    var title = ""
    var author: String? = nil

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 2).fill(Color(ReaderModel.colour(h.s("color")).withAlphaComponent(1))).frame(width: 4)
            VStack(alignment: .leading, spacing: 8) {
                Text(h.s("text") ?? "").font(.system(size: 17, design: .serif)).lineSpacing(4).textSelection(.enabled)
                if let n = h.s("user_note") ?? h.s("note") {
                    Text(n).font(.callout).foregroundStyle(.secondary)
                }
                let tags = h.strings("tags")
                HStack(spacing: 8) {
                    if !tags.isEmpty { Text(tags.map { "#" + $0 }.joined(separator: " ")).font(.caption).foregroundStyle(.tint) }
                    Text([h.s("chapter"), h.s("page").map { "p. " + $0 }, h.s("source")].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.tertiary)
                    Spacer()
                    if h.b("fav") { Image(systemName: "star.fill").foregroundStyle(.yellow).font(.caption) }
                }
            }
        }
        .padding(14)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
        .contextMenu {
            Button("Open at Its Spot", action: open)
            Button("Edit the Note…", action: edit)
            Button(h.b("fav") ? "Not a Favorite" : "Favorite") { Task { await fav() } }
            Menu("Color") {
                ForEach(["yellow", "green", "blue", "pink", "purple"], id: \.self) { c in
                    Button(c.capitalized) { Task { await color(c) } }
                }
            }
            Button("Tags…") { tool(.tags(h)) }
            Button(h.i("cards").map { $0 > 0 ? "Flashcards (\($0))…" : "Make a Flashcard…" } ?? "Make a Flashcard…") { tool(.cards(h)) }
            Button("Copy") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(h.s("text") ?? "", forType: .string) }
            Button("Share as Image…") { tool(.share(h, title: title, author: author)) }
            Button(h.s("r_status") == "never" ? "Back into Review" : "Never Show in Review") {
                let never = h.s("r_status") != "never"
                Task { if await HLTools.review(id, never: never) { model.highlights.update(id) { $0["r_status"] = never ? "never" : "kept" } } }
            }
            Divider()
            Button("Delete the Highlight", role: .destructive) { Task { await delete() } }
        }
        .onTapGesture(count: 2, perform: open)
    }

    private var id: String { h.s("id") ?? "" }

    private func fav() async {
        let on = !h.b("fav")
        do { try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/fav", ["fav": on]); model.highlights.update(id) { $0["fav"] = on } }
        catch { model.error = error.localizedDescription }
    }
    private func color(_ c: String) async {
        do { try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/color", ["color": c]); model.highlights.update(id) { $0["color"] = c } }
        catch { model.error = error.localizedDescription }
    }
    private func delete() async {
        let hid = id, m = model
        do {
            try await API.shared.send("DELETE", "/api/highlights/\(API.enc(hid))", nil)
            m.highlights.remove(hid)
            m.say("Highlight deleted", undo: "Delete the Highlight") {
                _ = try? await API.shared.send("POST", "/api/highlights/\(API.enc(hid))/restore", [:])
                await m.highlights.load()
            }
        } catch { model.error = error.localizedDescription }
    }
}

struct NoteSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let h: J
    /// The reader's own copy to update too, when it's written there.
    var saved: ((String) -> Void)? = nil
    @State private var text = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(h.s("text") ?? "").font(.system(.body, design: .serif)).lineLimit(5).foregroundStyle(.secondary)
            TextEditor(text: $text).font(.body).frame(minHeight: 120)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Save") { Task { await save() } }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 460)
        .onAppear { text = h.s("user_note") ?? "" }
    }

    private func save() async {
        let id = h.s("id") ?? ""
        do {
            try await API.shared.send("PUT", "/api/highlights/\(API.enc(id))/note", ["note": text])
            model.highlights.update(id) { $0["user_note"] = text }
            saved?(text)
            model.say("Note saved")
            dismiss()
        } catch { model.error = error.localizedDescription }
    }
}
