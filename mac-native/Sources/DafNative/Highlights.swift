import SwiftUI

/// Every highlight, by book or article: the list in the middle (search, a source, favorites only),
/// the one chosen on the right with its highlights, their notes, tags and colours.
@MainActor
@Observable
final class HighlightsModel {
    var groups: [J] = []
    var count = 0
    var query = ""
    var source = ""
    var favorites = false
    var groupID: String?
    var loading = false

    var group: J? { groups.first { Self.key($0) == groupID } }
    static func key(_ g: J) -> String { g.s("book_id") ?? g.s("title") ?? "" }

    func load() async {
        loading = true
        defer { loading = false }
        var q = ["sort=recent"]
        if !query.isEmpty { q.append("q=" + API.enc(query)) }
        if !source.isEmpty { q.append("source=" + source) }
        if favorites { q.append("fav=1") }
        guard let r = try? await API.shared.json("/api/highlights?" + q.joined(separator: "&")) else { return }
        groups = r.a("groups")
        count = r.i("count") ?? 0
        if group == nil { groupID = groups.first.map(Self.key) }
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
                        Text([g.s("author"), "\(g.a("items").count) highlights", (g.i("notes") ?? 0) > 0 ? "\(g.i("notes")!) notes" : nil].compactMap { $0 }.joined(separator: " · "))
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
                    Toggle("Favorites Only", isOn: $hl.favorites)
                } label: { Label("Filter", systemImage: "line.3.horizontal.decrease.circle") }
            }
        }
        .onChange(of: hl.source) { _, _ in Task { await hl.load() } }
        .onChange(of: hl.favorites) { _, _ in Task { await hl.load() } }
        .task { await hl.load() }
    }
}

/// The right side: one book's highlights.
struct HighlightGroupView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openWindow) private var openWindow
    let group: J
    @State private var editing: J?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(group.s("title") ?? "").font(.system(.title, design: .serif).weight(.semibold))
                    if let a = group.s("author") { Text(a).foregroundStyle(.secondary) }
                }
                .padding(.bottom, 8)
                ForEach(group.a("items"), id: \.self) { h in
                    HighlightCard(h: h, edit: { editing = h }, open: { if let o = h.s("open") { openWindow(id: "route", value: o) } })
                }
            }
            .frame(maxWidth: 720, alignment: .leading)
            .padding(28)
            .frame(maxWidth: .infinity)
        }
        .sheet(item: Binding(get: { editing.map(Editing.init) }, set: { editing = $0?.h })) { e in
            NoteSheet(h: e.h)
        }
    }

    struct Editing: Identifiable { let h: J; var id: String { h.s("id") ?? "" } }
}

struct HighlightCard: View {
    @Environment(AppModel.self) private var model
    let h: J
    let edit: () -> Void
    let open: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 2).fill(Color(ReaderModel.colour(h.s("color")).withAlphaComponent(1))).frame(width: 4)
            VStack(alignment: .leading, spacing: 8) {
                Text(h.s("text") ?? "").font(.system(size: 17, design: .serif)).lineSpacing(4).textSelection(.enabled)
                if let n = h.s("user_note") ?? h.s("note") {
                    Text(n).font(.callout).foregroundStyle(.secondary)
                }
                let tags = (h.list("tags") as? [String]) ?? []
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
            Button("Copy") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(h.s("text") ?? "", forType: .string) }
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
        do { try await API.shared.send("DELETE", "/api/highlights/\(API.enc(id))", nil); model.highlights.remove(id); model.say("Highlight deleted") }
        catch { model.error = error.localizedDescription }
    }
}

struct NoteSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let h: J
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
            model.say("Note saved")
            dismiss()
        } catch { model.error = error.localizedDescription }
    }
}
