import AppKit
import ImageIO
import SwiftUI
import UniformTypeIdentifiers

/// All Books (daf/catalog.py, web/catalog.js): the Calibre library as a spreadsheet. The search is
/// Calibre's, read on the server; Filter writes it (a value's first click puts it in, the second turns
/// it into "not …", the third takes it out). The search, the order, the columns, their widths and Show
/// Private Books are kept on this Mac; a saved view keeps them on the server for every device.
@MainActor
@Observable
final class Catalog {
    static let shared = Catalog()

    struct Col: Hashable {
        let key: String
        let label: String
        let type: String
        var numeric: Bool { ["number", "rating", "percent", "size"].contains(type) }
        /// Numbers and dates sort biggest and newest first on their first click, as on the web.
        var descFirst: Bool { numeric || type == "date" || type == "bool" }
    }

    private(set) var books: [J] = []
    private(set) var columns: [Col] = []
    private(set) var facets: [J]?
    private(set) var views: [J] = []
    private(set) var defaults: [String] = []
    private(set) var total = 0
    /// The search Daf couldn't read, in its words.
    private(set) var searchError: String?
    /// Daf didn't answer.
    private(set) var failed: String?
    private(set) var loaded = false
    /// Up by one with each answer, so the table reads its rows again.
    private(set) var version = 0

    var q = ""
    var sort = "added"
    var desc = true
    var cols: [String]?
    var widths: [String: Double] = [:]
    var priv = false
    var view: String?
    var lastView: String?
    var side = UserDefaults.standard.bool(forKey: "catalogSide") {
        didSet { UserDefaults.standard.set(side, forKey: "catalogSide") }
    }
    var open = Set(UserDefaults.standard.stringArray(forKey: "catalogOpen") ?? ["added", "missing", "status", "tags"]) {
        didSet { UserDefaults.standard.set(Array(open), forKey: "catalogOpen") }
    }
    var all: Set<String> = []
    var fq = ""
    /// The row chosen, and where the table was scrolled, for coming back to it.
    var picked: String?
    @ObservationIgnored var scroll: NSPoint?
    @ObservationIgnored private var seq = 0

    init() {
        guard let d = UserDefaults.standard.dictionary(forKey: "catalog") else { return }
        let k = J(d)
        q = k.s("q") ?? ""
        sort = k.s("sort") ?? "added"
        desc = d["desc"] as? Bool ?? true
        cols = (d["cols"] as? [String]).flatMap { $0.isEmpty ? nil : $0 }
        widths = (d["widths"] as? [String: Any] ?? [:]).compactMapValues { ($0 as? NSNumber)?.doubleValue }
        priv = k.b("priv")
        view = k.s("view")
        lastView = k.s("lastView")
    }

    func keep() {
        var d: [String: Any] = ["q": q, "sort": sort, "desc": desc, "widths": widths, "priv": priv]
        if let cols { d["cols"] = cols }
        if let view { d["view"] = view }
        if let lastView { d["lastView"] = lastView }
        UserDefaults.standard.set(d, forKey: "catalog")
    }

    // MARK: loading

    private var query: String {
        "q=\(API.enc(q))&sort=\(API.enc(sort))&desc=\(desc ? 1 : 0)" + (priv ? "&private=1" : "")
    }

    func load(facets want: Bool = false) async {
        seq += 1
        let n = seq
        let path = "/api/catalog?" + query + (want || facets == nil ? "&facets=1" : "")
        do {
            let data = try await API.shared.data(path)
            guard n == seq, let r = J(try JSONSerialization.jsonObject(with: data)) else { return }
            columns = r.a("columns").map { Col(key: $0.s("key") ?? "", label: $0.s("label") ?? "", type: $0.s("type") ?? "text") }
            books = r.a("books")
            total = r.i("total") ?? books.count
            searchError = r.s("error")
            views = r.a("views")
            defaults = r.strings("default_columns")
            if r.raw["facets"] != nil { facets = r.a("facets") }
            failed = nil
            loaded = true
            version += 1
        } catch {
            if n == seq { failed = error.localizedDescription }
        }
    }

    func reload() { Task { await load(facets: side) } }

    /// The search, the order or the columns changed: a view stays chosen while they're its own.
    func changed(load: Bool = true) {
        view = dirtyView()
        keep()
        if load { reload() }
    }

    private func dirtyView() -> String? {
        guard let v = views.first(where: { $0.s("name") == view }) else { return nil }
        let same = (v.s("q") ?? "") == q && (v.s("sort") ?? "added") == sort && v.b("desc") == desc && v.strings("cols") == (cols ?? [])
        return same ? view : nil
    }

    func setQ(_ s: String) {
        let t = s.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        guard t != q else { return }
        q = t
        changed()
    }

    func sortBy(_ key: String, desc d: Bool) {
        guard key != sort || d != desc else { return }
        sort = key
        desc = d
        changed()
    }

    func showPrivate(_ on: Bool) {
        priv = on
        keep()
        facets = nil
        Task { await load(facets: true) }
    }

    // MARK: columns

    static let widthFor: [String: Double] = [
        "title": 300, "authors": 180, "series": 170, "tags": 200, "rating": 112, "added": 112, "published": 100, "modified": 112,
        "publisher": 160, "languages": 90, "formats": 110, "size": 80, "isbn": 130, "identifiers": 240, "cover": 70, "status": 96,
        "progress": 120, "last_read": 112, "audio": 110, "highlights": 92, "shelves": 160, "calibre_id": 90,
    ]

    /// The columns showing, in their order: the title always among them.
    var shown: [Col] {
        let known = Dictionary(columns.map { ($0.key, $0) }, uniquingKeysWith: { a, _ in a })
        var want = (cols ?? (defaults.isEmpty ? ["title"] : defaults)).filter { known[$0] != nil }
        if !want.contains("title") { want.insert("title", at: 0) }
        return want.compactMap { known[$0] }
    }

    func width(_ c: Col) -> Double {
        widths[c.key] ?? Self.widthFor[c.key] ?? (c.type == "list" ? 160 : c.numeric ? 92 : c.type == "date" ? 112 : 140)
    }

    /// What the table draws from: the columns, their order and widths.
    var layout: String { shown.map { "\($0.key):\(Int(width($0)))" }.joined(separator: ",") }

    func setCols(_ keys: [String]) {
        guard keys != shown.map(\.key) else { return }
        cols = keys
        changed(load: false)
    }

    func toggle(_ key: String) {
        guard key != "title" else { return }
        var on = shown.map(\.key)
        if let i = on.firstIndex(of: key) { on.remove(at: i) } else { on.append(key) }
        setCols(on)
    }

    func resetCols() {
        cols = nil
        widths = [:]
        changed(load: false)
    }

    // MARK: Filter: Calibre's tag browser

    static let added = [("added:thisweek", "This week"), ("added:thismonth", "This month"), ("added:>=30daysago", "Last 30 days"),
                        ("added:thisyear", "This year"), ("added:lastyear", "Last year")]
    static let missing = [("formats:false", "No file"), ("cover:false", "No cover"), ("tags:false", "No tags"),
                          ("rating:false", "No rating"), ("series:false", "No series")]

    static func term(_ key: String, _ v: Any) -> String {
        if key == "rating" { return "rating:" + num(v) }
        let s = (v as? String) ?? num(v)
        return key + ":\"=" + s.replacingOccurrences(of: "\"", with: "") + "\""
    }

    static func num(_ v: Any) -> String {
        guard let n = v as? NSNumber else { return "\(v)" }
        let d = n.doubleValue
        return d == d.rounded() ? String(Int(d)) : String(d)
    }

    private func rx(_ t: String, not neg: Bool) -> NSRegularExpression? {
        try? NSRegularExpression(pattern: "(^|[\\s(])" + (neg ? "not " : "") + NSRegularExpression.escapedPattern(for: t) + "(?=$|[\\s)])",
                                 options: .caseInsensitive)
    }

    private func match(_ t: String, not neg: Bool) -> NSTextCheckingResult? {
        rx(t, not: neg)?.firstMatch(in: q, range: NSRange(q.startIndex..., in: q))
    }

    /// "in", "out" (as "not …") or "".
    func state(_ t: String) -> String { match(t, not: true) != nil ? "out" : match(t, not: false) != nil ? "in" : "" }

    func cycle(_ t: String) {
        var s = q
        func swap(_ m: NSTextCheckingResult, _ with: String) {
            guard let whole = Range(m.range, in: s), let lead = Range(m.range(at: 1), in: s) else { return }
            s.replaceSubrange(whole, with: String(s[lead]) + with)
        }
        if let m = match(t, not: true) { swap(m, "") }
        else if let m = match(t, not: false) { swap(m, "not " + t) }
        else { s = s.isEmpty ? t : s + " " + t }
        setQ(s)
    }

    // MARK: views, kept on the server

    func apply(_ v: J) {
        q = v.s("q") ?? ""
        sort = v.s("sort") ?? "added"
        desc = v.b("desc")
        let c = v.strings("cols")
        cols = c.isEmpty ? nil : c
        widths = (v.raw["widths"] as? [String: Any] ?? [:]).compactMapValues { ($0 as? NSNumber)?.doubleValue }
        view = v.s("name")
        lastView = view
        keep()
        reload()
    }

    func resetAll() {
        q = ""
        sort = "added"
        desc = true
        cols = nil
        widths = [:]
        view = nil
        keep()
        reload()
    }

    func save(as name: String) async throws {
        let others = views.filter { ($0.s("name") ?? "").lowercased() != name.lowercased() }.map(\.raw)
        let mine: [String: Any] = ["name": name, "q": q, "sort": sort, "desc": desc, "cols": cols ?? [],
                                   "widths": widths.mapValues { Int($0.rounded()) }]
        try await putViews(others + [mine])
        view = name
        lastView = name
        keep()
    }

    func delete(view name: String) async throws {
        try await putViews(views.filter { $0.s("name") != name }.map(\.raw))
        if view == name { view = nil; keep() }
    }

    private func putViews(_ vs: [[String: Any]]) async throws {
        views = J(try await API.shared.send("PUT", "/api/catalog/views", ["views": vs]))?.a("views") ?? []
    }

    // MARK: Export as CSV

    var exportPath: String { "/api/catalog/export?" + query + "&cols=" + API.enc(shown.map(\.key).joined(separator: ",")) }

    func export() {
        let p = NSSavePanel()
        p.nameFieldStringValue = "All books.csv"
        p.allowedContentTypes = [.commaSeparatedText]
        guard p.runModal() == .OK, let url = p.url else { return }
        let path = exportPath
        Task {
            do {
                try await API.shared.data(path).write(to: url)
                AppModel.shared.say("Exported")
            } catch { AppModel.shared.error = error.localizedDescription }
        }
    }

    // MARK: what a cell says

    static let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    static func day(_ s: String, monthOnly: Bool) -> String {
        let p = s.split(separator: "-").compactMap { Int($0) }
        guard p.count >= 2, (1...12).contains(p[1]) else { return s }
        return monthOnly || p.count < 3 ? "\(months[p[1] - 1]) \(p[0])" : "\(months[p[1] - 1]) \(p[2]), \(p[0])"
    }

    static let numbers: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 2
        return f
    }()

    /// A cell's words, each part plain or dimmed (a series' number, a rating's empty stars).
    static func text(_ b: J, _ c: Col) -> [(String, Bool)] {
        if c.key == "series" {
            guard let s = b.s("series") else { return [] }
            let i = ((b.d("series_index") ?? 0) * 10).rounded() / 10
            return [(s + " ", false), ("#" + (i == i.rounded() ? String(Int(i)) : String(i)), true)]
        }
        guard let v = b.raw[c.key], !(v is NSNull) else { return [] }
        if let a = v as? [Any] { return a.isEmpty ? [] : [(a.map { ($0 as? String) ?? num($0) }.joined(separator: c.key == "authors" ? " & " : ", "), false)] }
        switch c.type {
        case "rating":
            guard let n = b.d(c.key) else { return [] }
            return stars(n)
        case "date":
            guard let s = b.s(c.key) else { return [] }
            return [(day(s, monthOnly: c.key == "published"), false)]
        case "size":
            guard let n = b.d(c.key) else { return [] }
            return [(String(format: "%.1f MB", n / 1_048_576), false)]
        case "bool":
            return b.b(c.key) ? [("✓", false)] : []
        case "number":
            if let n = v as? NSNumber { return [(numbers.string(from: n) ?? num(n), false)] }
            return [("\(v)", false)]
        default:
            return [((v as? String) ?? num(v), false)]
        }
    }

    static func stars(_ n: Double) -> [(String, Bool)] {
        let full = Int(n), half = n - Double(full) >= 0.5
        let empty = max(0, 5 - full - (half ? 1 : 0))
        return [(String(repeating: "★", count: full) + (half ? "½" : ""), false), (String(repeating: "★", count: empty), true)]
    }
}

// MARK: the page

struct CatalogPage: View {
    @Environment(AppModel.self) private var model
    @State private var cat = Catalog.shared
    @State private var typed = Catalog.shared.q
    @State private var typing: Task<Void, Never>?
    @State private var showCols = false
    @State private var naming = false
    @State private var newName = ""
    @State private var replacing: String?
    @State private var deleting: String?

    var body: some View {
        HStack(spacing: 0) {
            if cat.side {
                CatalogFilter(cat: cat).frame(width: 260)
                Divider()
            }
            VStack(spacing: 0) {
                if let e = cat.searchError ?? (cat.loaded ? cat.failed : nil) {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
                        Text(e)
                        Spacer()
                    }
                    .font(.callout)
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(.red.opacity(0.08))
                    Divider()
                }
                CatalogTable(cat: cat, version: cat.version, layout: cat.layout, sort: cat.sort + (cat.desc ? "↓" : "↑")) { model.open(book: $0) }
                    .overlay {
                        if !cat.loaded {
                            if let f = cat.failed { ContentUnavailableView("It didn't load", systemImage: "exclamationmark.triangle", description: Text(f)) }
                            else { ProgressView() }
                        } else if cat.books.isEmpty && cat.searchError == nil {
                            Text("Nothing matches.").foregroundStyle(.secondary)
                        }
                    }
            }
        }
        .navigationTitle("All Books")
        .navigationSubtitle(cat.loaded ? (cat.books.count == cat.total ? plural(cat.total, "book") : "\(cat.books.count) of \(cat.total)") : "")
        .searchable(text: $typed, placement: .toolbar, prompt: "Search")
        .onSubmit(of: .search) { typing?.cancel(); cat.setQ(typed) }
        .onChange(of: typed) { _, t in
            typing?.cancel()
            typing = Task {
                try? await Task.sleep(for: .milliseconds(250))
                if !Task.isCancelled { cat.setQ(t) }
            }
        }
        .onChange(of: cat.q) { _, q in
            if typed.split(whereSeparator: \.isWhitespace).joined(separator: " ") != q { typed = q }
        }
        .toolbar {
            ToolbarItemGroup {
                Toggle(isOn: Binding(get: { cat.side }, set: { on in cat.side = on; if on && cat.facets == nil { cat.reload() } })) {
                    Label("Filter", systemImage: "line.3.horizontal.decrease")
                }
                .help("Filter")
                Button { showCols.toggle() } label: { Label("Columns", systemImage: "tablecells") }
                    .help("Columns")
                    .popover(isPresented: $showCols, arrowEdge: .bottom) { CatalogColumns(cat: cat) }
                viewsMenu
                Menu {
                    Button("Export as CSV…") { cat.export() }
                    Toggle("Show Private Books", isOn: Binding(get: { cat.priv }, set: { cat.showPrivate($0) }))
                } label: { Label("More", systemImage: "ellipsis.circle") }
                .help("More")
            }
        }
        .task { await cat.load(facets: cat.side) }
        .alert("Save as a View", isPresented: $naming) {
            TextField("Name", text: $newName)
            Button("Save") {
                let n = newName.trimmingCharacters(in: .whitespaces)
                guard !n.isEmpty else { return }
                if cat.views.contains(where: { ($0.s("name") ?? "").lowercased() == n.lowercased() }) { replacing = n } else { save(n) }
            }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Replace the view “\(replacing ?? "")”?", isPresented: Binding(get: { replacing != nil }, set: { if !$0 { replacing = nil } })) {
            Button("Replace") { if let n = replacing { save(n) }; replacing = nil }
        }
        .confirmationDialog("Delete the view “\(deleting ?? "")”?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
            Button("Delete", role: .destructive) {
                if let n = deleting { Task { do { try await cat.delete(view: n) } catch { model.error = error.localizedDescription } } }
                deleting = nil
            }
        }
    }

    private var viewsMenu: some View {
        let names = cat.views.compactMap { $0.s("name") }
        return Menu {
            ForEach(names, id: \.self) { name in
                Toggle(name, isOn: Binding(get: { cat.view == name }, set: { _ in
                    if let v = cat.views.first(where: { $0.s("name") == name }) { cat.apply(v) }
                }))
            }
            if !names.isEmpty { Divider() }
            if cat.view == nil, let last = cat.lastView, names.contains(last) {
                Button("Save into “\(last)”") { save(last) }
            }
            Button("Save as a View…") { newName = cat.view ?? ""; naming = true }
            Button("All Books, Newest First") { cat.resetAll() }
            if !names.isEmpty {
                Divider()
                Menu("Delete a View") {
                    ForEach(names, id: \.self) { name in Button(name + "…") { deleting = name } }
                }
            }
        } label: { Label(cat.view ?? "Views", systemImage: "bookmark") }
        .labelStyle(.titleAndIcon)
        .help("Views")
    }

    private func save(_ name: String) {
        Task {
            do { try await cat.save(as: name); model.say("Saved") }
            catch { model.error = error.localizedDescription }
        }
    }
}

/// Columns: every one there is, those showing first in their order (dragged to move), then the rest.
struct CatalogColumns: View {
    @Bindable var cat: Catalog

    var body: some View {
        let on = cat.shown
        let rest = cat.columns.filter { !on.contains($0) }
        VStack(spacing: 0) {
            List {
                Section {
                    ForEach(on, id: \.key) { c in toggle(c, true).disabled(c.key == "title") }
                        .onMove { from, to in
                            var keys = on.map(\.key)
                            keys.move(fromOffsets: from, toOffset: to)
                            cat.setCols(keys)
                        }
                }
                Section {
                    ForEach(rest, id: \.key) { c in toggle(c, false) }
                }
            }
            .frame(width: 270, height: 440)
            Divider()
            HStack {
                Button("Default Columns") { cat.resetCols() }
                Spacer()
            }
            .padding(10)
        }
    }

    private func toggle(_ c: Catalog.Col, _ on: Bool) -> some View {
        Toggle(c.label, isOn: Binding(get: { on }, set: { _ in cat.toggle(c.key) }))
    }
}

/// Filter: quick ones (Added, Missing), then every value of every field there is to filter by, with
/// how many books have it. A click puts the value into the search; the search is the filter.
struct CatalogFilter: View {
    @Bindable var cat: Catalog

    struct Val {
        let t: String
        let label: String
        var n: Int?
        var rating: Double?
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                TextField("Find a Value", text: $cat.fq).textFieldStyle(.roundedBorder)
                if !cat.q.isEmpty { Button("Clear") { cat.setQ("") } }
            }
            .padding(10)
            Divider()
            List {
                group("added", "Added", Catalog.added.map { Val(t: $0.0, label: $0.1) })
                group("missing", "Missing", Catalog.missing.map { Val(t: $0.0, label: $0.1) })
                ForEach(Array((cat.facets ?? []).enumerated()), id: \.offset) { _, f in
                    let key = f.s("key") ?? ""
                    group(key, f.s("label") ?? key, f.list("values").compactMap { x -> Val? in
                        guard let p = x as? [Any], p.count >= 2 else { return nil }
                        let v = p[0], n = (p[1] as? NSNumber)?.intValue
                        return Val(t: Catalog.term(key, v), label: (v as? String) ?? Catalog.num(v), n: n,
                                   rating: key == "rating" ? (v as? NSNumber)?.doubleValue : nil)
                    })
                }
            }
            .listStyle(.sidebar)
        }
    }

    @ViewBuilder private func group(_ key: String, _ label: String, _ every: [Val]) -> some View {
        let fq = cat.fq.trimmingCharacters(in: .whitespaces).lowercased()
        let items = fq.isEmpty ? every : every.filter { $0.label.lowercased().contains(fq) || label.lowercased().contains(fq) }
        if !items.isEmpty {
            let many = fq.isEmpty && !cat.all.contains(key) && items.count > 30
            DisclosureGroup(isExpanded: Binding(get: { !fq.isEmpty || cat.open.contains(key) },
                                                set: { if $0 { cat.open.insert(key) } else { cat.open.remove(key) } })) {
                ForEach(many ? Array(items.prefix(30)) : items, id: \.t) { v in row(v) }
                if many { Button("Show All \(items.count)") { cat.all.insert(key) }.buttonStyle(.link) }
            } label: {
                HStack {
                    Text(label)
                    Spacer()
                    Text("\(items.count)").foregroundStyle(.secondary).monospacedDigit()
                }
            }
        }
    }

    private func row(_ v: Val) -> some View {
        let st = cat.state(v.t)
        return Button { cat.cycle(v.t) } label: {
            HStack(spacing: 6) {
                Image(systemName: st == "out" ? "minus" : "checkmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(st == "out" ? Color.red : Color.accentColor)
                    .opacity(st.isEmpty ? 0 : 1)
                    .frame(width: 14)
                if let r = v.rating {
                    let s = Catalog.stars(r)
                    HStack(spacing: 0) {
                        Text(s[0].0)
                        Text(s[1].0).foregroundStyle(.tertiary)
                    }
                } else {
                    Text(v.label).strikethrough(st == "out").lineLimit(1)
                }
                Spacer(minLength: 4)
                if let n = v.n { Text("\(n)").foregroundStyle(.secondary).monospacedDigit() }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: the table

/// An NSTableView, so the columns can be dragged into a new order and made wider or narrower, and
/// the order and widths kept (and saved with a view). Right-clicking the column names chooses them.
struct CatalogTable: NSViewRepresentable {
    let cat: Catalog
    let version: Int
    let layout: String
    let sort: String
    let open: (J) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(cat, open) }

    func makeNSView(context: Context) -> NSScrollView {
        let c = context.coordinator
        let t = CatalogTableView()
        t.style = .fullWidth
        t.usesAlternatingRowBackgroundColors = true
        t.columnAutoresizingStyle = .noColumnAutoresizing
        t.allowsColumnReordering = true
        t.allowsColumnResizing = true
        t.allowsColumnSelection = false
        t.allowsMultipleSelection = false
        t.rowHeight = 30
        t.intercellSpacing = NSSize(width: 10, height: 2)
        t.delegate = c
        t.dataSource = c
        t.target = c
        t.doubleAction = #selector(Coordinator.doubleClicked)
        t.onReturn = { [weak c] in c?.openPicked() }
        let header = NSMenu()
        header.delegate = c
        t.headerView?.menu = header
        c.headerMenu = header
        let rowMenu = NSMenu()
        rowMenu.delegate = c
        t.menu = rowMenu
        let s = NSScrollView()
        s.documentView = t
        s.hasVerticalScroller = true
        s.hasHorizontalScroller = true
        s.autohidesScrollers = true
        c.table = t
        NotificationCenter.default.addObserver(c, selector: #selector(Coordinator.moved(_:)), name: NSTableView.columnDidMoveNotification, object: t)
        NotificationCenter.default.addObserver(c, selector: #selector(Coordinator.resized(_:)), name: NSTableView.columnDidResizeNotification, object: t)
        c.sync()
        return s
    }

    func updateNSView(_ s: NSScrollView, context: Context) {
        context.coordinator.open = open
        context.coordinator.sync()
    }

    static func dismantleNSView(_ s: NSScrollView, coordinator: Coordinator) {
        coordinator.cat.scroll = s.contentView.bounds.origin
        NotificationCenter.default.removeObserver(coordinator)
    }

    @MainActor
    final class Coordinator: NSObject, NSTableViewDataSource, NSTableViewDelegate, NSMenuDelegate {
        let cat: Catalog
        var open: (J) -> Void
        weak var table: NSTableView?
        weak var headerMenu: NSMenu?
        private var drawn = -1
        private var syncing = false

        init(_ cat: Catalog, _ open: @escaping (J) -> Void) {
            self.cat = cat
            self.open = open
        }

        /// The table as the catalog has it: its columns, their widths, the order, the rows.
        func sync() {
            guard let t = table else { return }
            syncing = true
            defer { syncing = false }
            let cols = cat.shown
            var reload = cat.version != drawn
            if cols.map(\.key) != t.tableColumns.map(\.identifier.rawValue) {
                for tc in t.tableColumns { t.removeTableColumn(tc) }
                for c in cols { t.addTableColumn(column(c)) }
                reload = true
            } else {
                for (tc, c) in zip(t.tableColumns, cols) where abs(tc.width - cat.width(c)) > 0.5 { tc.width = cat.width(c) }
            }
            if t.sortDescriptors.first?.key != cat.sort || t.sortDescriptors.first?.ascending != !cat.desc {
                t.sortDescriptors = [NSSortDescriptor(key: cat.sort, ascending: !cat.desc)]
            }
            for tc in t.tableColumns {
                let on = tc.identifier.rawValue == cat.sort
                t.setIndicatorImage(on ? NSImage(named: cat.desc ? "NSDescendingSortIndicator" : "NSAscendingSortIndicator") : nil, in: tc)
            }
            t.highlightedTableColumn = nil
            guard reload else { return }
            drawn = cat.version
            t.reloadData()
            if let p = cat.picked, let i = cat.books.firstIndex(where: { $0.s("id") == p }) {
                t.selectRowIndexes([i], byExtendingSelection: false)
            } else { t.deselectAll(nil) }
            // back where it was, once there are rows and the table has its size
            if let o = cat.scroll, !cat.books.isEmpty {
                cat.scroll = nil
                DispatchQueue.main.async { [weak t] in
                    guard let s = t?.enclosingScrollView else { return }
                    s.contentView.scroll(to: o)
                    s.reflectScrolledClipView(s.contentView)
                }
            }
        }

        private func column(_ c: Catalog.Col) -> NSTableColumn {
            let tc = NSTableColumn(identifier: .init(c.key))
            tc.title = c.label
            tc.minWidth = 48
            tc.maxWidth = 900
            tc.width = cat.width(c)
            tc.resizingMask = .userResizingMask
            tc.sortDescriptorPrototype = NSSortDescriptor(key: c.key, ascending: !c.descFirst)
            tc.headerCell.alignment = c.numeric ? .right : .left
            return tc
        }

        func numberOfRows(in tableView: NSTableView) -> Int { cat.books.count }

        func tableView(_ t: NSTableView, viewFor tc: NSTableColumn?, row: Int) -> NSView? {
            guard let tc, row < cat.books.count, let c = cat.columns.first(where: { $0.key == tc.identifier.rawValue }) else { return nil }
            let kind = c.key == "title" ? "title" : c.type == "percent" ? "pct" : "text"
            let cell = (t.makeView(withIdentifier: .init(kind), owner: nil) as? CatalogCell) ?? CatalogCell(kind)
            cell.show(cat.books[row], c)
            return cell
        }

        func tableView(_ t: NSTableView, sortDescriptorsDidChange oldDescriptors: [NSSortDescriptor]) {
            guard !syncing, let s = t.sortDescriptors.first, let k = s.key else { return }
            cat.sortBy(k, desc: !s.ascending)
        }

        func tableViewSelectionDidChange(_ n: Notification) {
            guard !syncing, let t = table, t.selectedRow >= 0, t.selectedRow < cat.books.count else { return }
            cat.picked = cat.books[t.selectedRow].s("id")
        }

        @objc func moved(_ n: Notification) {
            guard !syncing, let t = table else { return }
            cat.setCols(t.tableColumns.map(\.identifier.rawValue))
        }

        @objc func resized(_ n: Notification) {
            guard !syncing, let tc = n.userInfo?["NSTableColumn"] as? NSTableColumn else { return }
            cat.widths[tc.identifier.rawValue] = tc.width.rounded()
            cat.keep()
        }

        @objc func doubleClicked() {
            guard let t = table, t.clickedRow >= 0, t.clickedRow < cat.books.count else { return }
            open(cat.books[t.clickedRow])
        }

        func openPicked() {
            guard let t = table, t.selectedRow >= 0, t.selectedRow < cat.books.count else { return }
            open(cat.books[t.selectedRow])
        }

        @objc private func openClicked() { doubleClicked() }

        @objc private func toggleColumn(_ item: NSMenuItem) {
            if let k = item.representedObject as? String { cat.toggle(k) }
        }

        @objc private func defaultColumns() { cat.resetCols() }

        func menuNeedsUpdate(_ m: NSMenu) {
            m.removeAllItems()
            if m === headerMenu {
                let on = cat.shown.map(\.key)
                for c in cat.shown + cat.columns.filter({ !on.contains($0.key) }) {
                    let i = NSMenuItem(title: c.label, action: c.key == "title" ? nil : #selector(toggleColumn(_:)), keyEquivalent: "")
                    i.target = self
                    i.representedObject = c.key
                    i.state = on.contains(c.key) ? .on : .off
                    m.addItem(i)
                }
                m.addItem(.separator())
                let d = NSMenuItem(title: "Default Columns", action: #selector(defaultColumns), keyEquivalent: "")
                d.target = self
                m.addItem(d)
            } else if let t = table, t.clickedRow >= 0 {
                let o = NSMenuItem(title: "Open", action: #selector(openClicked), keyEquivalent: "")
                o.target = self
                m.addItem(o)
            }
        }
    }
}

final class CatalogTableView: NSTableView {
    var onReturn: (() -> Void)?
    override func keyDown(with e: NSEvent) {
        if e.keyCode == 36 || e.keyCode == 76 { onReturn?() } else { super.keyDown(with: e) }
    }
}

/// A cell: the title with its cover, a bar with its percent, or words.
final class CatalogCell: NSTableCellView {
    private let label = NSTextField(labelWithString: "")
    private var cover: NSImageView?
    private var bar: CatalogBar?
    private var coverID: String?

    init(_ kind: String) {
        super.init(frame: .zero)
        identifier = .init(kind)
        label.lineBreakMode = .byTruncatingTail
        label.maximumNumberOfLines = 1
        label.translatesAutoresizingMaskIntoConstraints = false
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        addSubview(label)
        textField = label
        var lead = leadingAnchor, gap: CGFloat = 2
        if kind == "title" {
            let iv = NSImageView()
            iv.translatesAutoresizingMaskIntoConstraints = false
            iv.imageScaling = .scaleProportionallyUpOrDown
            iv.wantsLayer = true
            iv.layer?.cornerRadius = 2
            iv.layer?.masksToBounds = true
            addSubview(iv)
            cover = iv
            NSLayoutConstraint.activate([
                iv.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 2), iv.centerYAnchor.constraint(equalTo: centerYAnchor),
                iv.widthAnchor.constraint(equalToConstant: 18), iv.heightAnchor.constraint(equalToConstant: 26),
            ])
            lead = iv.trailingAnchor
            gap = 8
        }
        if kind == "pct" {
            let b = CatalogBar()
            b.translatesAutoresizingMaskIntoConstraints = false
            addSubview(b)
            bar = b
            NSLayoutConstraint.activate([
                b.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 2), b.centerYAnchor.constraint(equalTo: centerYAnchor),
                b.heightAnchor.constraint(equalToConstant: 6), b.trailingAnchor.constraint(equalTo: label.leadingAnchor, constant: -6),
                label.widthAnchor.constraint(equalToConstant: 38),
            ])
            label.alignment = .right
            NSLayoutConstraint.activate([label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -2), label.centerYAnchor.constraint(equalTo: centerYAnchor)])
        } else {
            NSLayoutConstraint.activate([
                label.leadingAnchor.constraint(equalTo: lead, constant: gap), label.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -2),
                label.centerYAnchor.constraint(equalTo: centerYAnchor),
            ])
        }
    }

    required init?(coder: NSCoder) { fatalError() }

    func show(_ b: J, _ c: Catalog.Col) {
        toolTip = nil
        let base = NSFont.systemFont(ofSize: NSFont.systemFontSize)
        if let bar {
            let v = b.d(c.key)
            bar.isHidden = v == nil
            bar.value = v ?? 0
            label.font = base.withMonospacedDigits
            label.textColor = .secondaryLabelColor
            label.stringValue = v.map { "\(Int($0.rounded()))%" } ?? ""
            if c.key == "progress" { toolTip = b.s("progress_note") }
            return
        }
        if cover != nil {
            let priv = b.b("private")
            label.font = priv ? NSFontManager.shared.convert(base, toHaveTrait: .italicFontMask) : base
            label.textColor = priv ? .secondaryLabelColor : .labelColor
            label.stringValue = b.s("title") ?? ""
            toolTip = b.s("title")
            showCover(b)
            return
        }
        let para = NSMutableParagraphStyle()
        para.alignment = c.numeric ? .right : .left
        para.lineBreakMode = .byTruncatingTail
        let font = c.numeric ? base.withMonospacedDigits : base
        let out = NSMutableAttributedString()
        for (s, dim) in Catalog.text(b, c) {
            out.append(NSAttributedString(string: s, attributes: [.font: font, .paragraphStyle: para,
                                                                   .foregroundColor: dim ? NSColor.tertiaryLabelColor : NSColor.labelColor]))
        }
        label.attributedStringValue = out
        if c.type == "list" || c.type == "text", out.length > 20 { toolTip = out.string }
    }

    private func showCover(_ b: J) {
        guard let iv = cover, let id = b.s("id") else { return }
        coverID = id
        iv.layer?.backgroundColor = NSColor.quaternaryLabelColor.cgColor
        guard b.b("cover") else { iv.image = nil; return }
        if let img = CatalogCovers.cache.object(forKey: id as NSString) { iv.image = img; return }
        iv.image = nil
        Task { @MainActor [weak self] in
            guard let img = await CatalogCovers.get(id), self?.coverID == id else { return }
            self?.cover?.image = img
        }
    }
}

final class CatalogBar: NSView {
    var value: Double = 0 { didSet { needsDisplay = true } }
    override func draw(_ r: NSRect) {
        let track = bounds.insetBy(dx: 0, dy: max(0, (bounds.height - 6) / 2))
        NSColor.quaternaryLabelColor.setFill()
        NSBezierPath(roundedRect: track, xRadius: track.height / 2, yRadius: track.height / 2).fill()
        guard value > 0 else { return }
        var fill = track
        fill.size.width = max(track.height, track.width * min(1, value / 100))
        Theme.nsAccent.setFill()
        NSBezierPath(roundedRect: fill, xRadius: track.height / 2, yRadius: track.height / 2).fill()
    }
}

/// Covers for the table, made small once (a cover is a whole page's picture).
@MainActor
enum CatalogCovers {
    static let cache = NSCache<NSString, NSImage>()
    private static var loading: [String: Task<NSImage?, Never>] = [:]

    static func get(_ id: String) async -> NSImage? {
        if let i = cache.object(forKey: id as NSString) { return i }
        if let t = loading[id] { return await t.value }
        let t = Task { () -> NSImage? in
            guard let d = try? await API.shared.data("/api/cover/" + API.enc(id)) else { return nil }
            return small(d)
        }
        loading[id] = t
        let img = await t.value
        loading[id] = nil
        if let img { cache.setObject(img, forKey: id as NSString) }
        return img
    }

    nonisolated static func small(_ d: Data) -> NSImage? {
        guard let src = CGImageSourceCreateWithData(d as CFData, nil),
              let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                                                    kCGImageSourceThumbnailMaxPixelSize: 80,
                                                                    kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary)
        else { return nil }
        return NSImage(cgImage: cg, size: NSSize(width: CGFloat(cg.width) / 2, height: CGFloat(cg.height) / 2))
    }
}

private extension NSFont {
    var withMonospacedDigits: NSFont { NSFont.monospacedDigitSystemFont(ofSize: pointSize, weight: .regular) }
}
