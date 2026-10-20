import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// Paper pages: a photo of a page I marked in a paper book. Daf reads its lines (on the server),
/// the marked ones chosen; I pick the book and the lines, and each run of lines next to each other
/// becomes one highlight in that book's note. As the page's #paper.
enum PaperPages {
    static func reading(_ p: J) -> Bool { p.s("status") == "new" || ["queued", "running"].contains(p.o("job")?.s("status") ?? "") }

    static func short(_ t: String?) -> String { String((t ?? "").split(separator: ":").first ?? "") }

    /// Runs of chosen lines next to each other: each is one highlight.
    static func runs(_ chosen: Set<Int>) -> Int {
        var n = 0, last = Int.min
        for i in chosen.sorted() { if i != last + 1 { n += 1 }; last = i }
        return n
    }

    static func status(_ p: J) -> String {
        if reading(p) { return "Reading the page…" }
        if p.s("status") == "error" { return "Couldn't read it" }
        let n = runs(Set((p.list("chosen")).compactMap { ($0 as? NSNumber)?.intValue }))
        return n == 0 ? "No lines chosen" : plural(n, "passage")
    }

    /// A page as a row of the list.
    static func item(_ p: J) -> Item {
        var raw = p.raw
        raw["type"] = "paper"
        raw["kind"] = "paper"
        raw["title"] = p.o("book").map { short($0.s("title")) } ?? "Which book?"
        raw["source"] = (p.i("page").map { "p. \($0) · " } ?? "") + status(p)
        raw["thumb"] = "/api/paper/pages/\(API.enc(p.s("id") ?? ""))/photo"
        return Item(J(raw))
    }

    /// A photo as Daf takes it: a JPEG no bigger than it needs to be (an iPhone's HEIC included).
    static func jpeg(_ data: Data) -> Data? {
        guard let img = NSImage(data: data), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return nil }
        let longest = max(cg.width, cg.height), scale = min(1, 3200 / Double(max(1, longest)))
        let w = Int(Double(cg.width) * scale), h = Int(Double(cg.height) * scale)
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                         isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        NSGraphicsContext.current?.imageInterpolation = .high
        NSImage(cgImage: cg, size: NSSize(width: w, height: h)).draw(in: NSRect(x: 0, y: 0, width: w, height: h))
        NSGraphicsContext.restoreGraphicsState()
        return rep.representation(using: .jpeg, properties: [.compressionFactor: 0.85])
    }

    /// Photos sent to Daf to be read; the first one opened.
    @MainActor
    static func add(_ photos: [Data]) async {
        let m = AppModel.shared
        var first: String?
        for (k, d) in photos.enumerated() {
            guard let jpg = jpeg(d) else { m.say("That isn't a photo Daf can read"); continue }
            if photos.count > 1 { m.say("Sending \(k + 1) of \(photos.count)…") }
            do {
                let r = J(try await API.shared.upload("/api/paper/pages", jpg, type: "image/jpeg"))
                if first == nil { first = r?.s("id") }
            } catch { m.error = "Daf didn't take the photo: " + error.localizedDescription }
        }
        guard let first else { return }
        if m.place != .paper { m.place = .paper }
        await m.load()
        m.selection = first
        m.say(photos.count > 1 ? "Reading \(photos.count) pages" : "Reading the page")
    }

    /// File › Add a Photo of a Page…
    @MainActor
    static func choose() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.image]
        panel.allowsMultipleSelection = true
        panel.message = "Photos of pages you marked"
        guard panel.runModal() == .OK else { return }
        let photos = panel.urls.compactMap { try? Data(contentsOf: $0) }
        Task { await add(photos) }
    }

    /// Photos from Continuity Camera (File › Import from iPhone), a drop, or the share menu.
    @MainActor
    static func take(_ providers: [NSItemProvider]) -> Bool {
        let images = providers.filter { $0.hasItemConformingToTypeIdentifier(UTType.image.identifier) }
        guard !images.isEmpty else { return false }
        Task {
            var photos: [Data] = []
            for p in images {
                if let d = await withCheckedContinuation({ (c: CheckedContinuation<Data?, Never>) in
                    p.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { d, _ in c.resume(returning: d) }
                }) { photos.append(d) }
            }
            await add(photos)
        }
        return true
    }
}

/// One page: its photo beside its lines, the book, the page number, Save.
struct PaperPageView: View {
    @Environment(AppModel.self) private var model
    let id: String
    @State private var p: J?
    @State private var chosen: Set<Int> = []
    @State private var book: J?
    @State private var newTitle: String?
    @State private var page = ""
    @State private var query = ""
    @State private var found: [J] = []
    @State private var busy = false
    @State private var confirmDelete = false

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            AsyncImage(url: API.shared.url("/api/paper/pages/\(API.enc(id))/photo")) { ph in
                if let i = ph.image { i.resizable().aspectRatio(contentMode: .fit) } else { Color.secondary.opacity(0.08) }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(20)
            .onTapGesture(count: 2) { NSWorkspace.shared.open(API.shared.url("/api/paper/pages/\(API.enc(id))/photo")) }
            Divider()
            ScrollView { form.padding(20) }
                .frame(width: 400)
        }
        .navigationTitle(p.map { ($0.i("page").map { "Page \($0)" } ?? "A page") + ($0.o("book").map { " · " + PaperPages.short($0.s("title")) } ?? "") } ?? "Paper page")
        .task(id: id) { await load(); await poll() }
        .confirmationDialog("Delete this page and its highlights?", isPresented: $confirmDelete) {
            Button("Delete", role: .destructive) { Task { await delete() } }
        }
    }

    @ViewBuilder private var form: some View {
        if let p {
            if PaperPages.reading(p) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Reading the page…").font(.headline) }
                    Text("Daf reads the lines and the marks on them. About fifteen seconds.").foregroundStyle(.secondary)
                }
            } else if p.s("status") == "error" {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Couldn't read it").font(.headline)
                    Text(p.s("error") ?? "").foregroundStyle(.secondary)
                    Button("Try Again") { Task { await reread() } }
                }
            } else {
                VStack(alignment: .leading, spacing: 16) {
                    bookBox
                    LabeledContent("Page") { TextField("", text: $page).frame(width: 90).textFieldStyle(.roundedBorder) }
                    Text("Tick the lines to keep. Lines next to each other become one highlight.").font(.caption).foregroundStyle(.secondary)
                    lines(p)
                    HStack {
                        Text(chosen.isEmpty ? "Nothing chosen" : plural(PaperPages.runs(chosen), "highlight") + " from " + plural(chosen.count, "line"))
                            .font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Read Again") { Task { await reread() } }
                        Button("Delete", role: .destructive) { confirmDelete = true }
                        Button("Save") { Task { await save() } }
                            .buttonStyle(.borderedProminent)
                            .disabled(busy || (book == nil && newTitle == nil))
                    }
                }
            }
        } else {
            ProgressView()
        }
    }

    @ViewBuilder private var bookBox: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Book").font(.caption).foregroundStyle(.secondary)
            if book != nil || newTitle != nil {
                HStack {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(book?.s("title") ?? newTitle ?? "").font(.headline).lineLimit(2)
                        Text(book?.s("author") ?? (newTitle != nil ? "A new paper book; Daf makes its note" : "")).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Change") { book = nil; newTitle = nil; Task { await search("") } }
                }
            } else {
                TextField("Search your books", text: $query)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: query) { _, q in Task { await search(q) } }
                ForEach(found, id: \.self) { b in
                    Button { book = b } label: {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(PaperPages.short(b.s("title"))).lineLimit(1)
                            Text(b.s("author") ?? "").font(.caption).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                }
                if query.trimmingCharacters(in: .whitespaces).count > 2 {
                    Button("A new paper book: “\(query.trimmingCharacters(in: .whitespaces))”") { newTitle = query.trimmingCharacters(in: .whitespaces) }
                        .buttonStyle(.link)
                }
            }
        }
    }

    private func lines(_ p: J) -> some View {
        let he = p.s("lang") == "he"
        var margin: [Int: [String]] = [:]
        for m in p.a("margin") { if let l = m.i("line"), let t = m.s("text") { margin[l, default: []].append(t) } }
        return VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(p.a("lines").enumerated()), id: \.offset) { i, l in
                Toggle(isOn: Binding(get: { chosen.contains(i) }, set: { if $0 { chosen.insert(i) } else { chosen.remove(i) } })) {
                    VStack(alignment: he ? .trailing : .leading, spacing: 2) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text(l.s("text") ?? "").font(.system(.body, design: .serif))
                            if l.b("marked") { Image(systemName: "pencil").foregroundStyle(.secondary).help("Marked on the page") }
                        }
                        ForEach(margin[i] ?? [], id: \.self) { t in Text("In the margin: " + t).font(.caption).italic().foregroundStyle(.secondary) }
                    }
                    .frame(maxWidth: .infinity, alignment: he ? .trailing : .leading)
                    .environment(\.layoutDirection, he ? .rightToLeft : .leftToRight)
                }
                .toggleStyle(.checkbox)
            }
        }
    }

    // MARK: Daf

    private func load() async {
        guard let j = try? await API.shared.json("/api/paper/pages/" + API.enc(id)) else { return }
        p = j
        chosen = Set(j.list("chosen").compactMap { ($0 as? NSNumber)?.intValue })
        book = j.o("book")
        page = j.i("page").map(String.init) ?? ""
        if book == nil { await search("") }
    }

    /// While Daf reads the page: ask again every four seconds.
    private func poll() async {
        while let p, PaperPages.reading(p), !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            await load()
        }
        model.reload()
    }

    private func search(_ q: String) async {
        found = Array(((try? await API.shared.json("/api/booksearch?q=" + API.enc(q)))?.a("books") ?? []).prefix(q.isEmpty ? 5 : 8))
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["chosen": chosen.sorted(), "page": page.trimmingCharacters(in: .whitespaces)]
        if let b = book?.s("id") { body["book_id"] = b } else if let t = newTitle { body["new_title"] = t }
        do {
            let r = J(try await API.shared.send("POST", "/api/paper/pages/" + API.enc(id), body))
            let n = r?.i("highlights") ?? 0
            model.say(n == 0 ? "Saved, with no highlights" : plural(n, "highlight") + " in " + PaperPages.short(book?.s("title") ?? newTitle))
            await load()
            model.reload()
        } catch { model.error = error.localizedDescription }
    }

    private func reread() async {
        try? await API.shared.send("POST", "/api/paper/pages/\(API.enc(id))/read", [:])
        await load()
        await poll()
    }

    private func delete() async {
        do {
            try await API.shared.send("DELETE", "/api/paper/pages/" + API.enc(id), nil)
            model.say("Deleted")
            model.selection = nil
            model.reload()
        } catch { model.error = error.localizedDescription }
    }
}
