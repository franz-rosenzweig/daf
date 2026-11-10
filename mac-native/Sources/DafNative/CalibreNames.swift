import AppKit
import SwiftUI

/// ⋯ › Tags, Authors and Series (bookedit.js items()): every name a field has across the library, with
/// how many books have it, the ones that look alike, and renaming, combining and deleting them. Calibre
/// does the change itself (rename_items, remove_items in calibrewrite.py).
@MainActor
@Observable
final class CalibreNames {
    struct Field: Hashable { let key: String; let label: String }
    struct Item: Hashable, Identifiable { let name: String; let count: Int; var id: String { name } }

    /// The one showing (the self-test reaches it here).
    static weak var open: CalibreNames?

    var field = "tags"
    var fields: [Field] = []
    var items: [Item] = []
    var alike: [[String]] = []
    var q = ""
    var chosen: Set<String> = []
    /// The name being renamed in its row.
    var editing: String?
    var loaded = false
    var failed: String?
    var busy = false
    @ObservationIgnored private var seq = 0

    var label: String { fields.first { $0.key == field }?.label ?? field }

    func count(_ name: String) -> Int { items.first { $0.name == name }?.count ?? 0 }

    /// Most used first.
    func byUse(_ names: [String]) -> [String] { names.sorted { count($0) > count($1) } }

    var shown: [Item] {
        let s = q.trimmingCharacters(in: .whitespaces).lowercased()
        return s.isEmpty ? items : items.filter { $0.name.lowercased().contains(s) }
    }

    var shownAlike: [[String]] {
        let s = q.trimmingCharacters(in: .whitespaces).lowercased()
        return alike.filter { g in s.isEmpty || g.contains { $0.lowercased().contains(s) } }.map(byUse)
    }

    func load(_ f: String? = nil) async {
        Self.open = self
        if let f, f != field { field = f; q = ""; chosen = []; editing = nil }
        seq += 1
        let n = seq
        do {
            let j = try await API.shared.json("/api/catalog/items?field=" + API.enc(field))
            guard n == seq else { return }
            fields = j.a("fields").map { Field(key: $0.s("key") ?? "", label: $0.s("label") ?? "") }
            items = j.a("items").map { Item(name: $0.s("name") ?? "", count: $0.i("count") ?? 0) }
            alike = j.list("alike").compactMap { $0 as? [String] }
            chosen = chosen.filter { c in items.contains { $0.name == c } }
            failed = nil
            loaded = true
        } catch {
            if n == seq { failed = error.localizedDescription }
        }
    }

    /// Would `to` combine names into one the library already has?
    func combines(_ names: [String], into to: String) -> Bool {
        let t = to.trimmingCharacters(in: .whitespaces)
        return items.contains { $0.name == t } && names.contains { $0 != t }
    }

    /// Each name becomes `to` on every book; onto a name that's there already, they're combined.
    @discardableResult
    func rename(_ names: [String], to: String) async -> Bool {
        let t = to.trimmingCharacters(in: .whitespaces)
        let from = names.filter { $0 != t }
        editing = nil
        guard !t.isEmpty, !from.isEmpty else { return false }
        let into = items.contains { $0.name == t }
        busy = true
        defer { busy = false }
        do {
            try await API.shared.send("POST", "/api/catalog/items/rename", ["field": field, "from": from, "to": t], slow: true)
            AppModel.shared.say(into ? "Combined" : "Renamed")
            chosen = []
            await load()
            Catalog.shared.changed()
            return true
        } catch {
            AppModel.shared.error = error.localizedDescription
            return false
        }
    }

    /// The names off every book that has them (an author can only be renamed).
    @discardableResult
    func delete(_ names: [String]) async -> Bool {
        guard field != "authors", !names.isEmpty else { return false }
        busy = true
        defer { busy = false }
        do {
            try await API.shared.send("POST", "/api/catalog/items/delete", ["field": field, "names": names], slow: true)
            AppModel.shared.say("Deleted")
            chosen = []
            await load()
            Catalog.shared.changed()
            return true
        } catch {
            AppModel.shared.error = error.localizedDescription
            return false
        }
    }

    /// The search All Books uses for a name: field:"=name".
    func search(_ name: String) -> String { field + ":\"=" + name.replacingOccurrences(of: "\"", with: "") + "\"" }
}

struct NamesSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var model
    @State private var names = CalibreNames()
    @State private var typed = ""
    @State private var combining: (names: [String], to: String)?
    @State private var combineTo = ""
    @State private var askingCombine = false
    @State private var deleting: [String]?
    @FocusState private var renaming: Bool

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text("Tags, Authors and Series").font(.headline)
                Spacer()
                if names.busy { ProgressView().controlSize(.small) }
                Button("Close") { dismiss() }.keyboardShortcut(names.editing == nil ? .cancelAction : nil)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            VStack(spacing: 10) {
                if names.fields.count > 1 {
                    Picker("Field", selection: Binding(get: { names.field }, set: { f in Task { await names.load(f) } })) {
                        ForEach(names.fields, id: \.key) { Text($0.label).tag($0.key) }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }
                TextField("Find a Name", text: $names.q)
                    .textFieldStyle(.roundedBorder)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            content
            if !names.chosen.isEmpty {
                Divider()
                HStack(spacing: 10) {
                    Text("\(names.chosen.count) chosen").bold()
                    Spacer()
                    Button("Clear") { names.chosen = [] }
                    if names.chosen.count > 1 {
                        Button("Combine…") {
                            combineTo = names.byUse(Array(names.chosen)).first ?? ""
                            askingCombine = true
                        }
                    }
                    if names.field != "authors" {
                        Button("Delete…", role: .destructive) { deleting = Array(names.chosen).sorted() }
                    }
                }
                .padding(.horizontal, 16).padding(.vertical, 9)
            }
        }
        .frame(width: 620, height: 640)
        .disabled(names.busy)
        .task { await names.load() }
        .alert("Combine \(names.chosen.count) Names", isPresented: $askingCombine) {
            TextField("Into", text: $combineTo)
            Button("Combine") {
                let chosen = Array(names.chosen), to = combineTo
                Task { await names.rename(chosen, to: to) }
            }
            Button("Cancel", role: .cancel) {}
        } message: { Text(names.byUse(Array(names.chosen)).map { "“\($0)”" }.joined(separator: ", ")) }
        .confirmationDialog(combineQuestion, isPresented: Binding(get: { combining != nil }, set: { if !$0 { combining = nil } })) {
            Button("Combine") {
                if let c = combining { Task { await names.rename(c.names, to: c.to) } }
                combining = nil
            }
            Button("Cancel", role: .cancel) { names.editing = nil }
        }
        .confirmationDialog(deleteQuestion, isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
            Button("Delete", role: .destructive) {
                if let d = deleting { Task { await names.delete(d) } }
                deleting = nil
            }
        }
    }

    private var combineQuestion: String {
        guard let c = combining else { return "" }
        return "Combine " + c.names.filter { $0 != c.to }.map { "“\($0)”" }.joined(separator: ", ") + " into “\(c.to)”?"
    }

    private var deleteQuestion: String {
        guard let d = deleting else { return "" }
        return "Delete " + (d.count == 1 ? "“\(d[0])”" : "\(d.count) names") + " from every book that has " + (d.count == 1 ? "it?" : "them?")
    }

    @ViewBuilder private var content: some View {
        if let f = names.failed, !names.loaded {
            ContentUnavailableView("It didn't load", systemImage: "exclamationmark.triangle", description: Text(f))
        } else if !names.loaded {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(selection: $names.chosen) {
                let groups = names.shownAlike
                if !groups.isEmpty {
                    Section("Look Alike") {
                        ForEach(groups, id: \.self) { g in AlikeRow(names: names, group: g) { to in ask(g, into: to) } }
                    }
                }
                Section(plural(names.shown.count, names.label.lowercased(), names.label.lowercased())) {
                    ForEach(names.shown) { x in row(x).tag(x.name) }
                }
            }
            .contextMenu(forSelectionType: String.self) { sel in
                if sel.count == 1, let n = sel.first {
                    Button("Rename") { names.editing = n }
                    Button("Show the \(plural(names.count(n), "Book"))") { show(n) }
                }
                if sel.count > 1 {
                    Button("Combine…") { names.chosen = sel; combineTo = names.byUse(Array(sel)).first ?? ""; askingCombine = true }
                }
                if !sel.isEmpty && names.field != "authors" {
                    Divider()
                    Button("Delete…", role: .destructive) { deleting = Array(sel).sorted() }
                }
            } primaryAction: { sel in
                if sel.count == 1 { names.editing = sel.first }
            }
            .overlay { if names.shown.isEmpty && names.shownAlike.isEmpty { Text("Nothing matches.").foregroundStyle(.secondary) } }
        }
    }

    private func row(_ x: CalibreNames.Item) -> some View {
        HStack(spacing: 8) {
            if names.editing == x.name {
                TextField("Name", text: $typed)
                    .textFieldStyle(.roundedBorder)
                    .focused($renaming)
                    .onAppear { typed = x.name; DispatchQueue.main.async { renaming = true } }
                    .onSubmit { commit(x.name) }
                    .onExitCommand { names.editing = nil }
                    .onChange(of: renaming) { _, on in if !on && names.editing == x.name && combining == nil { names.editing = nil } }
            } else {
                Text(x.name).lineLimit(1)
            }
            Spacer()
            Button(String(x.count)) { show(x.name) }
                .buttonStyle(.link)
                .monospacedDigit()
                .help("Show in All Books")
        }
    }

    /// Enter in a renamed row: onto a name that's there already, asked first.
    private func commit(_ from: String) {
        let to = typed.trimmingCharacters(in: .whitespaces)
        guard !to.isEmpty, to != from else { names.editing = nil; return }
        if names.combines([from], into: to) { combining = ([from], to) }
        else { Task { await names.rename([from], to: to) } }
    }

    private func ask(_ group: [String], into to: String) { combining = (group, to) }

    /// The books with this name, in All Books.
    private func show(_ name: String) {
        let q = names.search(name)
        dismiss()
        Catalog.shared.setQ(q)
        if model.place != .catalog { model.place = .catalog }
    }
}

/// One group of names that are probably the same: each with its count, the one to keep, Combine.
private struct AlikeRow: View {
    let names: CalibreNames
    let group: [String]
    let combine: (String) -> Void
    @State private var into = ""

    var body: some View {
        HStack(spacing: 10) {
            Text(group.map { "\($0) (\(names.count($0)))" }.joined(separator: " · "))
                .lineLimit(2)
            Spacer()
            Picker("Into", selection: $into) {
                ForEach(group, id: \.self) { Text($0).tag($0) }
            }
            .labelsHidden()
            .frame(maxWidth: 170)
            Button("Combine") { combine(into.isEmpty ? group[0] : into) }
        }
        .selectionDisabled()
        .onAppear { if into.isEmpty { into = group.first ?? "" } }
    }
}

// MARK: - Find details for many books

/// Find details for many (bookedit.js fill()): what each chosen book is missing, from Hardcover and
/// Calibre's quicker sources, only answers that are surely the same book; each line can be left out.
@MainActor
@Observable
final class BookFill {
    static let fields = [("publisher", "Publisher"), ("published", "Published"), ("comments", "Description"), ("tags", "Tags"), ("series", "Series"),
                         ("languages", "Languages"), ("identifiers", "Identifiers"), ("#pages", "Pages"), ("cover", "Cover")]

    struct Res: Identifiable {
        let id: Int
        let title: String
        let authors: [String]
        var fill: [String: Any]
        let from: [String: String]
        let found: Bool
        var on = true
        var off: Set<String> = []
        /// The lines, in the sheet's order (series_index goes with series, the cover on its own).
        var lines: [String] { BookFill.fields.map(\.0).filter { $0 != "cover" && fill[$0] != nil } }
        var sources: String { Array(Set(from.values)).sorted().joined(separator: ", ") }
    }

    enum Step: Equatable { case pick, looking(Int, Int), results, saving(Int, Int) }

    static weak var open: BookFill?

    let ids: [Int]
    let titles: [String]
    var want: Set<String> = Set(BookFill.fields.map(\.0))
    var step = Step.pick
    var results: [Res] = []
    var failed: String?
    @ObservationIgnored private var seq = 0

    init(_ ids: [Int]) {
        let books = Catalog.shared.books
        self.ids = ids
        titles = ids.map { id in books.first { $0.i("calibre_id") == id }?.s("title") ?? "#\(id)" }
    }

    var some: [Res] { results.filter { !$0.fill.isEmpty } }
    var none: [Res] { results.filter { $0.fill.isEmpty } }
    /// What Save sends: the books ticked, each without the lines taken out (series takes its number with it).
    var chosen: [[String: Any]] {
        some.filter(\.on).compactMap { r in
            var f = r.fill
            for k in r.off {
                f[k] = nil
                if k == "series" { f["series_index"] = nil }
            }
            return f.isEmpty ? nil : ["id": r.id, "fill": f]
        }
    }

    func look() async {
        let fields = Self.fields.map(\.0).filter(want.contains)
        guard !fields.isEmpty else { return }
        seq += 1
        let n = seq
        step = .looking(0, ids.count)
        failed = nil
        do {
            let job = J(try await API.shared.send("POST", "/api/catalog/fill", ["ids": ids, "fields": fields]))?.s("job") ?? ""
            while true {
                try await Task.sleep(for: .seconds(1.5))
                guard n == seq else { return }
                let j = try await API.shared.json("/api/catalog/jobs/" + job)
                if j.s("state") == "running" { step = .looking(j.i("done") ?? 0, j.i("total") ?? ids.count); continue }
                if j.s("state") == "failed" { throw APIError(status: 0, message: j.s("error") ?? "Nothing came back") }
                results = j.a("books").map { b in
                    Res(id: b.i("id") ?? 0, title: b.s("title") ?? "", authors: b.strings("authors"), fill: b.o("fill")?.raw ?? [:],
                        from: (b.o("from")?.raw ?? [:]).compactMapValues { $0 as? String }, found: b.b("found"))
                }
                step = .results
                return
            }
        } catch {
            guard n == seq else { return }
            failed = error.localizedDescription
            step = .results
        }
    }

    /// Writes the ticked ones; true once it's done (a book that couldn't be is said).
    func save() async -> Bool {
        let books = chosen
        guard !books.isEmpty else { return false }
        step = .saving(0, books.count)
        do {
            let job = J(try await API.shared.send("POST", "/api/catalog/fill/apply", ["books": books]))?.s("job") ?? ""
            while true {
                try await Task.sleep(for: .seconds(1.5))
                let j = try await API.shared.json("/api/catalog/jobs/" + job)
                let total = j.i("total") ?? books.count
                step = .saving(j.i("done") ?? 0, total)
                if j.s("state") == "running" { continue }
                let bad = j.a("failed").count
                AppModel.shared.say(plural(total - bad, "book") + " filled in" + (bad > 0 ? "; \(bad) couldn't be" : ""))
                break
            }
        } catch {
            AppModel.shared.error = error.localizedDescription
        }
        Catalog.shared.reload()
        for b in books { if let id = b["id"] as? Int { NotificationCenter.default.post(name: .dafBookEdited, object: "cal:\(id)") } }
        return true
    }

    static func label(_ k: String) -> String { fields.first { $0.0 == k }?.1 ?? k }

    /// One line's value as the sheet shows it.
    static func show(_ k: String, _ v: Any?, index: Any? = nil) -> String {
        switch v {
        case let s as String where k == "comments": return s.count > 140 ? String(s.prefix(140)) + "…" : s
        case let a as [Any]: return a.map { "\($0)" }.joined(separator: ", ")
        case let d as [String: Any]: return d.sorted { $0.key < $1.key }.map { "\($0.key): \($0.value)" }.joined(separator: ", ")
        case let n as NSNumber: return Catalog.num(n)
        case let x?:
            let s = "\(x)"
            if k == "series", let i = index as? NSNumber { return s + " #" + Catalog.num(i) }
            return s
        default: return ""
        }
    }
}

struct FillSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var f: BookFill

    init(ids: [Int]) { _f = State(initialValue: BookFill(ids)) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text(title).font(.headline)
                Spacer()
                switch f.step {
                case .pick:
                    Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                    Button("Look Up") { Task { await f.look() } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(f.want.isEmpty)
                case .looking:
                    Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                case .results:
                    Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                    if !f.some.isEmpty {
                        Button("Save") { Task { if await f.save() { dismiss() } } }
                            .keyboardShortcut(.defaultAction)
                            .disabled(f.chosen.isEmpty)
                    }
                case .saving:
                    EmptyView()
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            Divider()
            Group {
                switch f.step {
                case .pick: pick
                case .looking(let done, let total), .saving(let done, let total):
                    VStack(spacing: 10) {
                        ProgressView(value: Double(done), total: Double(max(1, total))).frame(width: 300)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .results: results
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(width: 640, height: 620)
        .onAppear { BookFill.open = f }
    }

    private var title: String {
        switch f.step {
        case .pick: return "Find Details for " + plural(f.ids.count, "Book")
        case .looking(let done, let total): return "Looking up \(min(done + 1, total)) of \(total)…"
        case .results: return f.failed == nil ? "\(f.some.count) of \(f.results.count) with something to fill in" : "Find Details"
        case .saving(let done, let total): return "Saving \(done) of \(total)…"
        }
    }

    private var pick: some View {
        Form {
            Section("Fill In") {
                ForEach(BookFill.fields, id: \.0) { k, l in
                    Toggle(l, isOn: Binding(get: { f.want.contains(k) }, set: { if $0 { f.want.insert(k) } else { f.want.remove(k) } }))
                }
            }
            Section(plural(f.ids.count, "Book")) {
                ForEach(Array(f.titles.enumerated()), id: \.offset) { _, t in Text(t).foregroundStyle(.secondary).lineLimit(1) }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder private var results: some View {
        if let e = f.failed {
            ContentUnavailableView("Nothing came back", systemImage: "exclamationmark.triangle", description: Text(e))
        } else {
            List {
                ForEach($f.results) { $r in
                    if !r.fill.isEmpty { FillRow(r: $r) }
                }
                if !f.none.isEmpty {
                    Section("Nothing to Fill In") {
                        ForEach(f.none) { r in
                            HStack {
                                Text(r.title).bold().lineLimit(1)
                                Spacer()
                                Text(r.found ? "Nothing missing that was found" : "No answer surely the same book").foregroundStyle(.secondary)
                            }
                            .font(.callout)
                        }
                    }
                }
            }
        }
    }
}

/// One book with something to fill in: ticked as a whole, and each line on its own.
private struct FillRow: View {
    @Binding var r: BookFill.Res

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Toggle("", isOn: $r.on).labelsHidden().toggleStyle(.checkbox)
            FoundCover(url: r.fill["cover"] as? String).frame(width: 44, height: 66)
            VStack(alignment: .leading, spacing: 4) {
                Text(r.title).bold().lineLimit(2)
                Text(r.authors.joined(separator: " & ")).font(.callout).foregroundStyle(.secondary).lineLimit(1)
                ForEach(r.lines + (r.fill["cover"] != nil ? ["cover"] : []), id: \.self) { k in line(k) }
                Text(r.sources).font(.caption).foregroundStyle(.tertiary)
            }
            .disabled(!r.on)
            .opacity(r.on ? 1 : 0.5)
        }
        .padding(.vertical, 6)
    }

    private func line(_ k: String) -> some View {
        let on = !r.off.contains(k)
        return Toggle(isOn: Binding(get: { on }, set: { if $0 { r.off.remove(k) } else { r.off.insert(k) } })) {
            (Text(BookFill.label(k)).foregroundStyle(.secondary) + Text(k == "cover" ? "" : "  " + BookFill.show(k, r.fill[k], index: r.fill["series_index"])))
                .strikethrough(!on)
                .lineLimit(k == "comments" ? 3 : 2)
        }
        .toggleStyle(.checkbox)
        .font(.callout)
    }
}
