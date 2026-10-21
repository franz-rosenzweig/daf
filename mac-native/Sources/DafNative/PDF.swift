import AppKit
import PDFKit
import SwiftUI

/// A PDF as printed, in Apple's own PDF view, with highlights as the page's PDF view has them
/// (web/pdfview.js): select and highlight (H, N, or as you select), each kept with its page and
/// boxes (pos.pdf) and, when its words are in the text view too, its place there; highlights made in
/// the text view found on the page by their words. Right-click one for its note, colour, tags and
/// the rest. Time here counts as reading, and the page read is the progress. − and + zoom.
@MainActor
@Observable
final class PDFModel {
    let id: String
    var doc: J?
    var document: PDFDocument?
    var highlights: [J] = []
    var editing: ReaderModel.Editing?
    var sheet: HLSheet?
    var error: String?
    @ObservationIgnored weak var view: DafPDFView?
    @ObservationIgnored var pendingHighlight: String?
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var sentPct = 0.0
    @ObservationIgnored private var timer: Timer?
    /// Where a text-view highlight was found on a page: (page index, rects in page space).
    @ObservationIgnored private var found: [String: (Int, [CGRect])] = [:]
    @MainActor static var kept: [String: PDFDocument] = [:]
    @MainActor static weak var last: PDFModel?

    init(id: String) { self.id = id }

    var title: String { doc?.s("title") ?? "PDF" }

    func load() async {
        Self.last = self
        doc = try? await API.shared.json("/api/docs/\(API.enc(id))?prefetch=1")
        highlights = doc?.a("highlights") ?? []
        sentPct = doc?.d("progress") ?? 0
        if let d = Self.kept[id] { document = d } else {
            do {
                let data = try await API.shared.data("/api/docs/\(API.enc(id))/pdf")
                guard let d = PDFDocument(data: data) else { throw APIError(status: 0, message: "That isn't a PDF Daf can show.") }
                if Self.kept.count > 6 { Self.kept.removeAll() }
                Self.kept[id] = d
                document = d
            } catch is CancellationError { return
            } catch let e as URLError where e.code == .cancelled { return
            } catch { self.error = error.localizedDescription; return }
        }
        draw()
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in MainActor.assumeIsolated { self?.beatIfReading() } }
    }

    func stop() { timer?.invalidate(); timer = nil }

    // MARK: drawing them

    static func colour(_ c: String?) -> NSColor {
        switch c {
        case "green": return NSColor.systemGreen.withAlphaComponent(0.4)
        case "blue": return NSColor.systemBlue.withAlphaComponent(0.35)
        case "pink", "red": return NSColor.systemPink.withAlphaComponent(0.35)
        case "purple": return NSColor.systemPurple.withAlphaComponent(0.35)
        default: return NSColor.systemYellow.withAlphaComponent(0.5)
        }
    }

    /// Where a highlight is: its own page and boxes, else its words found on a page.
    private func place(_ h: J) -> (Int, [CGRect])? {
        guard let document, let hid = h.s("id") else { return nil }
        if let p = h.o("pos")?.o("pdf"), let pg = p.i("pg"), pg >= 1, pg <= document.pageCount, let page = document.page(at: pg - 1) {
            let box = page.bounds(for: .cropBox)
            let rects = p.list("r").compactMap { r -> CGRect? in
                guard let v = r as? [Any], v.count == 4 else { return nil }
                let n = v.compactMap { ($0 as? NSNumber)?.doubleValue }
                guard n.count == 4 else { return nil }
                return CGRect(x: box.minX + n[0] * box.width, y: box.maxY - (n[1] + n[3]) * box.height, width: n[2] * box.width, height: n[3] * box.height)
            }
            return rects.isEmpty ? nil : (pg - 1, rects)
        }
        if let f = found[hid] { return f }
        let want = Self.norm(h.s("text"))
        guard want.count >= 8 else { return nil }
        let look = want.count > 60 ? String(want.prefix(60)) : want
        guard let sel = document.findString(look, withOptions: [.caseInsensitive]).first, let page = sel.pages.first else { return nil }
        let rects = sel.selectionsByLine().filter { $0.pages.first == page }.map { $0.bounds(for: page) }
        let f = (document.index(for: page), rects)
        found[hid] = f
        return f
    }

    /// The highlights as PDF highlight annotations (named "daf:<id>"), drawn again.
    func draw() {
        guard let document else { return }
        for i in 0..<document.pageCount {
            guard let page = document.page(at: i) else { continue }
            for a in page.annotations where a.userName?.hasPrefix("daf:") == true { page.removeAnnotation(a) }
        }
        for h in highlights {
            guard let hid = h.s("id"), let (pi, rects) = place(h), let page = document.page(at: pi) else { continue }
            for r in rects {
                let a = PDFAnnotation(bounds: r.insetBy(dx: -1, dy: -1), forType: .highlight, withProperties: nil)
                a.color = Self.colour(h.s("color"))
                a.userName = "daf:" + hid
                if let n = h.s("user_note"), !n.isEmpty { a.contents = n }
                page.addAnnotation(a)
            }
        }
        if let v = view { for i in 0..<document.pageCount { if let p = document.page(at: i) { v.annotationsChanged(on: p) } } }
    }

    /// Daf's highlights drawn on the pages now.
    var marks: Int {
        guard let document else { return 0 }
        return (0..<document.pageCount).reduce(0) { n, i in n + (document.page(at: i)?.annotations.filter { $0.userName?.hasPrefix("daf:") == true }.count ?? 0) }
    }

    func highlight(at point: NSPoint, in page: PDFPage) -> String? {
        let p = view?.convert(point, to: page) ?? point
        return page.annotations.first { $0.userName?.hasPrefix("daf:") == true && $0.bounds.contains(p) }?.userName.map { String($0.dropFirst(4)) }
    }

    /// A highlight's page, shown (#pdf/<doc>/hl:<id>).
    func reveal(_ hid: String) {
        guard let h = highlights.first(where: { $0.s("id") == hid }), let (pi, rects) = place(h), let page = document?.page(at: pi) else { return }
        view?.go(to: rects.first ?? page.bounds(for: .cropBox), on: page)
    }

    // MARK: making one

    static func norm(_ s: String?) -> String {
        var t = (s ?? "").replacingOccurrences(of: "\u{00AD}", with: "")
        t = t.replacingOccurrences(of: "-\\s+(?=\\p{Ll})", with: "", options: .regularExpression)
        return t.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    /// Where these words are in the text view, so the highlight shows there as well.
    private func textPlace(_ text: String) -> (b: Int, s: Int, e: Int)? {
        let words = Self.norm(text).split(separator: " ").map(String.init)
        guard words.count >= 2, let blocks = doc?.list("blocks") else { return nil }
        let esc = { (w: String) in NSRegularExpression.escapedPattern(for: w) }
        guard let head = try? NSRegularExpression(pattern: words.prefix(8).map(esc).joined(separator: "\\s+")),
              let tail = try? NSRegularExpression(pattern: words.suffix(5).map(esc).joined(separator: "\\s+")) else { return nil }
        for (i, any) in blocks.enumerated() {
            let full = (J(any)?.s("x") ?? "") as NSString
            guard let m = head.firstMatch(in: full as String, range: NSRange(location: 0, length: full.length)) else { continue }
            let rest = NSRange(location: m.range.location, length: full.length - m.range.location)
            let t = words.count > 8 ? tail.firstMatch(in: full as String, range: rest) : nil
            let e = t.map { NSMaxRange($0.range) } ?? min(full.length, m.range.location + max(m.range.length, (text as NSString).length))
            return (i, m.range.location, e)
        }
        return nil
    }

    /// The selection highlighted: its boxes on the page where it starts, as fractions of the page.
    func highlightSelection(thenNote: Bool = false) async {
        guard let v = view, let sel = v.currentSelection, let document, let page = sel.pages.first else { return }
        let text = Self.norm(sel.string)
        guard text.count >= 2 else { return }
        let box = page.bounds(for: .cropBox)
        let rects = sel.selectionsByLine().filter { $0.pages.first == page }.map { $0.bounds(for: page) }.filter { $0.width > 0.5 }
        guard !rects.isEmpty else { return }
        let r = rects.map { q -> [Double] in
            [(q.minX - box.minX) / box.width, (box.maxY - q.maxY) / box.height, q.width / box.width, q.height / box.height].map { ($0 * 1e5).rounded() / 1e5 }
        }
        let pg = document.index(for: page) + 1
        let colour = HLTools.lastColour
        var body: [String: Any] = ["text": text, "color": colour, "pdf": ["pg": pg, "r": r]]
        let at = textPlace(text)
        body["b"] = at?.b ?? NSNull()
        body["s"] = at?.s ?? NSNull()
        body["e"] = at?.e ?? NSNull()
        do {
            let res = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/highlights", body))
            var pos: [String: Any] = ["pdf": ["pg": pg, "r": r]]
            if let at { pos["b"] = at.b; pos["s"] = at.s; pos["e"] = at.e }
            let made: [String: Any] = ["id": res?.s("id") ?? UUID().uuidString, "text": text, "color": colour, "pos": pos]
            highlights.append(J(made))
            v.clearSelection()
            draw()
            if thenNote { editing = .init(h: J(made)) }
        } catch { self.error = error.localizedDescription }
    }

    // MARK: reading

    func pageChanged() {
        lastActive = Date()
        guard let v = view, let document, let page = v.currentPage, document.pageCount > 0 else { return }
        let pct = (Double(document.index(for: page) + 1) / Double(document.pageCount) * 100).rounded()
        guard pct > sentPct else { return }
        sentPct = pct
        let id = self.id
        Task { try? await API.shared.send("PUT", "/api/docs/\(API.enc(id))/progress", ["pct": Int(pct)]) }
    }

    private func beatIfReading() {
        guard let w = view?.window, w.occlusionState.contains(.visible), NSApp.isActive, Date().timeIntervalSince(lastActive) < 90 else { return }
        let id = self.id
        Task { try? await API.shared.send("POST", "/api/read/beat", ["doc_id": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
    }
}

extension PDFModel: HighlightHost {
    func highlight(withID hid: String) -> J? { highlights.first { $0.s("id") == hid } }
    var shareTitle: String { title }
    var shareAuthor: String? { doc?.s("author") ?? doc?.s("source") }
    func paragraph(around loc: Int) -> String { "" }

    func set(color: String, of hid: String) async {
        do {
            try await API.shared.send("PUT", "/api/highlights/\(API.enc(hid))/color", ["color": color])
            changed(hid) { $0["color"] = color }
        } catch { self.error = error.localizedDescription }
    }

    func changed(_ hid: String, _ f: (inout [String: Any]) -> Void) {
        guard let k = highlights.firstIndex(where: { $0.s("id") == hid }) else { return }
        var raw = highlights[k].raw
        f(&raw)
        highlights[k] = J(raw)
        draw()
    }

    func remove(highlight hid: String) async {
        do {
            try await API.shared.send("DELETE", "/api/highlights/\(API.enc(hid))", nil)
            highlights.removeAll { $0.s("id") == hid }
            draw()
            let doc = id
            AppModel.shared.say("Highlight removed", undo: "Remove Highlight") { [weak self] in
                _ = try? await API.shared.send("POST", "/api/highlights/\(API.enc(hid))/restore", [:])
                if let self, let d = try? await API.shared.json("/api/docs/\(API.enc(doc))?prefetch=1") { self.highlights = d.a("highlights"); self.draw() }
            }
        } catch { self.error = error.localizedDescription }
    }
}

/// Apple's PDF view, with Daf's highlights: its keys, its menu, highlighting as you select.
final class DafPDFView: PDFView {
    weak var model: PDFModel?

    override func mouseUp(with event: NSEvent) {
        super.mouseUp(with: event)
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        guard HLTools.autoHighlight, !NSEvent.modifierFlags.contains(.option), event.clickCount == 1,
              let s = currentSelection?.string, PDFModel.norm(s).contains(" ") else { return }
        Task { @MainActor in await m?.highlightSelection() }
    }

    override func scrollWheel(with event: NSEvent) {
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        super.scrollWheel(with: event)
    }

    override func keyDown(with event: NSEvent) {
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        let plain = event.modifierFlags.intersection([.command, .control, .option]).isEmpty
        switch plain ? event.characters ?? "" : "" {
        case "h": Task { @MainActor in await m?.highlightSelection() }
        case "n": Task { @MainActor in await m?.highlightSelection(thenNote: true) }
        case "+", "=": zoomIn(nil)
        case "-": zoomOut(nil)
        default: super.keyDown(with: event)
        }
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        guard let m = model else { return menu }
        var extra: [NSMenuItem] = []
        if let s = currentSelection?.string, !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            extra.append(MenuAction.item("Highlight") { Task { @MainActor in await m.highlightSelection() } })
            extra.append(MenuAction.item("Highlight with a Note") { Task { @MainActor in await m.highlightSelection(thenNote: true) } })
        }
        let at = convert(event.locationInWindow, from: nil)
        if let page = page(for: at, nearest: false), let hid = MainActor.assumeIsolated({ m.highlight(at: at, in: page) }) {
            extra += MainActor.assumeIsolated { HLMenu.items(for: hid, host: m) }
        }
        for (k, item) in extra.enumerated() { menu.insertItem(item, at: k) }
        if !extra.isEmpty { menu.insertItem(.separator(), at: extra.count) }
        return menu
    }
}

struct PDFKitView: NSViewRepresentable {
    let model: PDFModel
    let document: PDFDocument

    func makeNSView(context: Context) -> DafPDFView {
        let v = DafPDFView()
        v.model = model
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displaysPageBreaks = true
        v.backgroundColor = .windowBackgroundColor
        v.document = document
        model.view = v
        NotificationCenter.default.addObserver(forName: .PDFViewPageChanged, object: v, queue: .main) { [weak model] _ in
            MainActor.assumeIsolated { model?.pageChanged() }
        }
        DispatchQueue.main.async {
            if let hid = model.pendingHighlight { model.pendingHighlight = nil; model.reveal(hid) }
            else if let p = model.doc?.d("progress"), p > 1, p < 99, document.pageCount > 1,
                    let page = document.page(at: min(document.pageCount - 1, Int(p / 100 * Double(document.pageCount)) - 1)) { v.go(to: page) }
        }
        return v
    }

    func updateNSView(_ v: DafPDFView, context: Context) {
        if v.document !== document { v.document = document }
    }
}

struct PDFPane: View {
    @Environment(AppModel.self) private var app
    let id: String
    var at: String? = nil
    @State private var model: PDFModel

    init(id: String, at: String? = nil) {
        self.id = id
        self.at = at
        _model = State(initialValue: PDFModel(id: id))
    }

    var body: some View {
        Group {
            if let d = model.document { PDFKitView(model: model, document: d) }
            else if let e = model.error { ContentUnavailableView("The PDF didn't open", systemImage: "doc.richtext", description: Text(e)) }
            else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .task(id: id) {
            model.pendingHighlight = at.flatMap { $0.hasPrefix("hl:") ? String($0.dropFirst(3)) : nil }
            await model.load()
        }
        .onDisappear { model.stop() }
        .sheet(item: $model.editing) { e in
            NoteSheet(h: e.h, saved: { n in model.changed(e.id) { $0["user_note"] = n } }).environment(app)
        }
        .sheet(item: $model.sheet) { s in
            HLSheetView(sheet: s) { hid, fields in model.changed(hid) { raw in for (k, v) in fields { raw[k] = v } } }.environment(app)
        }
        .onChange(of: model.error) { _, e in if let e, model.document != nil { app.error = e; model.error = nil } }
    }
}
