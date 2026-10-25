import AppKit
import SwiftUI

/// A book read natively, the way Apple Books lays one out on the Mac: a chapter at a time, set as
/// pages, two side by side when the window is wide. Its place, highlights and bookmarks are the
/// page's own (CFIs, as foliate makes them), so the page, the Kindle and this agree on them.
@MainActor
@Observable
final class BookModel {
    let id: String
    var details: J?
    private(set) var epub: EPUB?
    private(set) var section = 0
    private(set) var text: SectionText?
    var error: String?
    /// Not an EPUB (MOBI, AZW3, FB2, comics): Daf's own reader opens it.
    var otherFormat = false
    var look: BookLook
    /// The look is this book's own, not everyone's.
    var ownLook: Bool
    /// Where to open instead of the place: "q:" and words, "hl:" and a highlight, a CFI, or a path in the book.
    @ObservationIgnored var target: String?
    var toast: String?
    @ObservationIgnored private var toastTask: Task<Void, Never>?
    /// Forget My Place: nothing is kept until I read on.
    @ObservationIgnored private var forget = false
    @ObservationIgnored private var forgotAt = Date.distantPast
    /// Near the end: the next in the series, and Hardcover's Finished.
    var nextInSeries: J?
    var hardcoverEnd = false
    var finishing = false
    @ObservationIgnored private var offeredEnd = false
    var fraction = 0.0
    var chapter = ""
    var footer = ""
    var highlights: [J] = []
    var bookmarks: [J] = []
    var marked = false
    var showContents = UserDefaults.standard.bool(forKey: "book.contents")
    var sidebar = "contents"            // contents, highlights, bookmarks
    var editing: ReaderModel.Editing?
    var sheet: HLSheet?
    /// The Kindle is further on than this place: offered as a jump.
    var kindleAhead: Double?
    /// The Kindle's highlights (KOReader's, with its words), found in this edition by their words.
    var kindle: [J] = []
    var results: [BookHit] = []
    var searching = false
    var query = ""
    var asks: [J] = []
    var asking = false
    /// ⌘F: the sidebar's search field takes the keys.
    var focusSearch = 0
    @ObservationIgnored var texts: [Int: String] = [:]
    @ObservationIgnored var placedKindle: [Int: [(id: String, range: NSRange)]] = [:]
    /// The chapter being read aloud (it goes on into the next one).
    @ObservationIgnored var listenSection = 0

    @ObservationIgnored weak var pages: BookPagesView?
    @ObservationIgnored private var pending: Int?
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var saveTask: Task<Void, Never>?
    @ObservationIgnored private var rendered: [Int: SectionText] = [:]
    @ObservationIgnored private var pageKey: String?
    @ObservationIgnored private var pageAt = Date()
    @ObservationIgnored private var pagesSeen = Set<String>()
    /// For the self-test.
    @ObservationIgnored var saves = 0
    @ObservationIgnored var beats = 0
    @ObservationIgnored static weak var last: BookModel?

    init(id: String, at target: String? = nil) {
        self.id = id
        self.target = target
        look = BookLook.load(book: id)
        ownLook = UserDefaults.standard.dictionary(forKey: "book.look." + id) != nil
    }

    func say(_ s: String) {
        toast = s
        toastTask?.cancel()
        toastTask = Task { try? await Task.sleep(nanoseconds: 2_600_000_000); if !Task.isCancelled { toast = nil } }
    }

    var title: String { details.map { $0.b("private") ? "Private reading" : ($0.s("title") ?? "") } ?? "" }

    // MARK: opening

    func load() async {
        Self.last = self                // the one on screen (SwiftUI may make others it throws away)
        do {
            let d = try await API.shared.json("/api/ebooks/" + API.enc(id))
            details = d
            guard ["EPUB", "KEPUB"].contains((d.s("format") ?? "").uppercased()) else { otherFormat = true; return }
            highlights = d.a("highlights")
            bookmarks = d.a("bookmarks")
            kindle = d.a("other_highlights").filter { $0.s("source") == "kindle" && ($0.s("text") ?? "").count > 3 }
            let data = try await file(size: d.i("size"))
            let book = try EPUB(data)
            epub = book
            var at = 0
            section = book.sections.firstIndex { $0.linear } ?? 0
            if let cfi = d.o("position")?.s("cfi") {
                let parsed = CFI.parse(cfi)
                if let k = book.section(ofCFI: parsed) {
                    section = k
                    at = render(k)?.range(of: parsed)?.location ?? 0
                }
            }
            open(section, at: at)
            if let t = target { target = nil; await go(target: t) }
            else if let f = d.o("position")?.d("fraction"), f > 0.005 {
                say("Picked up at \(Int((f * 100).rounded()))%" + (chapter.isEmpty ? "" : " · " + chapter))
            }
            if let k = d.o("kindle"), let kf = k.d("fraction"), kf > (d.o("position")?.d("fraction") ?? 0) + 0.02,
               (k.d("at") ?? 0) > (d.o("position")?.d("updated") ?? 0) { kindleAhead = kf }
            startBeats()
        } catch { self.error = error.localizedDescription }
    }

    private func file(size: Int?) async throws -> Data { try await Self.file(for: id, size: size) }

    /// A book's file: the copy kept on this Mac when it's the same size as Calibre's (or there's no
    /// connection), else Daf's, kept for next time.
    static func file(for id: String, size: Int?) async throws -> Data {
        let url = Store.folder("Books").appendingPathComponent(id.replacingOccurrences(of: "[^A-Za-z0-9_-]", with: "_", options: .regularExpression) + ".epub")
        let have = try? Data(contentsOf: url)
        if let have, size == nil || have.count == size || Connection.shared.offline { return have }
        do {
            let data = try await API.shared.data("/api/ebooks/\(API.enc(id))/file")
            try? data.write(to: url, options: .atomic)
            return data
        } catch {
            if let have { return have }
            throw error
        }
    }

    @discardableResult
    func render(_ k: Int) -> SectionText? {
        if let t = rendered[k] { return t }
        guard let epub, let t = SectionText(epub: epub, index: k, look: look) else { return nil }
        if rendered.count > 4 { rendered = rendered.filter { abs($0.key - k) <= 1 } }
        rendered[k] = t
        return t
    }

    /// A chapter, at a character in it.
    func open(_ k: Int, at char: Int) {
        guard let t = render(k) else { return }
        section = k
        text = t
        guard let pages else { pending = char; return }
        pages.look = look
        pages.rtl = epub?.rtl ?? false
        pages.show(t.string, at: char)
        paint()
    }

    func attach(_ p: BookPagesView) {
        pages = p
        p.model = self
        if let t = text {
            p.look = look
            p.rtl = epub?.rtl ?? false
            p.show(t.string, at: pending ?? 0)
            pending = nil
            paint()
        }
    }

    func nextSection() {
        guard let epub, section + 1 < epub.sections.count else { return }
        open(section + 1, at: 0)
    }

    func previousSection() {
        guard section > 0 else { return }
        let k = section - 1
        open(k, at: max(0, (render(k)?.length ?? 1) - 1))
    }

    /// The look changed: the chapter set again at the same place (the text is the same; only its
    /// attributes change, so the place's character stays the same).
    func restyle(_ l: BookLook) {
        look = l
        l.save(book: ownLook ? id : nil)
        rendered = [:]
        let at = pages?.visible.location ?? 0
        open(section, at: at)
    }

    func go(_ target: EPUB.Target) {
        guard let k = epub?.section(of: target.path), let t = render(k) else { return }
        open(k, at: target.fragment.flatMap { t.location(ofID: $0) } ?? 0)
    }

    /// A CFI's place (a highlight, a bookmark), its page shown.
    func go(cfi: String, flash: Bool = false) {
        let parsed = CFI.parse(cfi)
        guard let k = epub?.section(ofCFI: parsed), let r = render(k)?.range(of: parsed) else { return }
        open(k, at: r.location)
        if flash, r.length > 0 { pages?.flash(r) }
    }

    /// A fraction of the whole book (the Kindle's place).
    func go(fraction f: Double) {
        guard let epub else { return }
        let sizes = epub.sections.map { $0.linear ? $0.size : 0 }, total = max(1, sizes.reduce(0, +))
        var sum = 0
        for (k, s) in sizes.enumerated() where s > 0 {
            if Double(sum + s) / Double(total) >= f, let t = render(k) {
                let inside = (f * Double(total) - Double(sum)) / Double(s)
                open(k, at: Int(Double(t.length) * max(0, min(1, inside))))
                return
            }
            sum += s
        }
    }

    /// A link in the book: a footnote shown where it is, another place in the book, or a web page.
    func follow(_ link: String, from view: NSTextView, at char: Int) {
        if link.contains("://") { if let u = URL(string: link) { NSWorkspace.shared.open(u) }; return }
        let bits = link.split(separator: "#", maxSplits: 1).map(String.init)
        let path = bits[0], frag = bits.count > 1 ? bits[1] : nil
        if let frag, let k = epub?.section(of: path), let note = render(k)?.notes[frag] {
            pages?.showNote(note, from: view, at: char)
            return
        }
        go(EPUB.Target(label: "", path: path, fragment: frag))
    }

    // MARK: where I am

    /// The pages changed: the percentage, the chapter, the footer, the bookmark, the place kept.
    func relocated() {
        guard let epub, let text, let pages else { return }
        lastActive = Date()
        let vis = pages.visible
        let sizes = epub.sections.map { $0.linear ? $0.size : 0 }, total = max(1, sizes.reduce(0, +))
        let before = sizes.prefix(section).reduce(0, +)
        let inside = Double(vis.location) / Double(max(1, text.length))
        let bytes = Double(before) + inside * Double(sizes[section])
        fraction = bytes / Double(total)
        chapter = currentChapter(at: vis.location)
        let left = pages.pagesLeft
        _ = left
        // the time left, as the page reckons it (a minute is 1,600 bytes of the book)
        let inChapter = (1 - inside) * Double(sizes[section]) / 1600, inBook = (Double(total) - bytes) / 1600
        func time(_ m: Double) -> String { let n = Int(m.rounded()); return n >= 60 ? "\(n / 60) h \(n % 60) min" : "\(max(1, n)) min" }
        var bits = [inChapter >= 0.5 ? time(inChapter) + " left in the chapter" : "The end of the chapter", time(inBook) + " left in the book"]
        if let p = printed(at: vis.location) { bits.append("p. " + p.dropFirst()) }
        bits.append("\(Int((fraction * 100).rounded()))%")
        footer = bits.joined(separator: " · ")
        if forget && Date().timeIntervalSince(forgotAt) > 2 { forget = false }          // reading on after Forget: the place counts again
        if fraction > 0.985 && !offeredEnd { offeredEnd = true; Task { await nearTheEnd() } }
        marked = bookmarkHere() != nil
        notePage(printed(at: vis.location) ?? "l\(Int(bytes / 1500))")
        if let k = kindleAhead, fraction >= k - 0.005 { kindleAhead = nil }
        saveTask?.cancel()
        saveTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard !Task.isCancelled else { return }
            await self?.savePosition()
        }
    }

    private func currentChapter(at char: Int) -> String {
        guard let epub, let text else { return "" }
        var best = ""
        for item in epub.toc.flatMap(\.flat) {
            guard let k = epub.section(of: item.target.path) else { continue }
            if k < section { best = item.label }
            else if k == section, (item.target.fragment.flatMap { text.location(ofID: $0) } ?? 0) <= char { best = item.label }
        }
        return best
    }

    /// The printed book's page here, when the book has a page list ("p34"), for page goals.
    private func printed(at char: Int) -> String? {
        guard let epub, !epub.pageList.isEmpty, let text else { return nil }
        var label: String?
        for t in epub.pageList {
            guard let k = epub.section(of: t.path) else { continue }
            if k < section || (k == section && (t.fragment.flatMap { text.location(ofID: $0) } ?? 0) <= char) { label = t.label }
        }
        return label.map { "p" + $0 }
    }

    /// A page counts for page goals once it's been in front of me for five seconds, as the page counts them.
    private func notePage(_ key: String) {
        if let k = pageKey, k != key, Date().timeIntervalSince(pageAt) >= 5 { pagesSeen.insert(k) }
        if pageKey != key { pageKey = key; pageAt = Date() }
    }

    /// The place as the page keeps it: the range shown, as a CFI, with the fraction and the chapter.
    func savePosition(closing: Bool = false) async {
        guard !forget, let epub, let text, let pages else { return }
        let vis = pages.visible
        guard let local = text.cfi(vis.location, NSMaxRange(vis) > vis.location ? NSMaxRange(vis) : nil) else { return }
        var body: [String: Any] = ["cfi": CFI.join(epub.sections[section].cfi, local), "fraction": fraction, "chapter": chapter,
                                   "at": Int(Date().timeIntervalSince1970)]
        if closing, let k = pageKey, Date().timeIntervalSince(pageAt) >= 5 { pagesSeen.insert(k) }
        if !pagesSeen.isEmpty { body["pages"] = Array(pagesSeen); pagesSeen = [] }
        saves += 1
        _ = try? await API.shared.send("PUT", "/api/ebooks/\(API.enc(id))/position", body)
    }

    /// Near the end: the next book in the series, and (on Hardcover's shelves, not Read yet) Finished.
    private func nearTheEnd() async {
        if let next = details?.o("series")?.o("next") { nextInSeries = next }
        guard details?.b("private") == false, let s = try? await API.shared.json("/api/hardcover/book/" + API.enc(id)) else { return }
        if s.b("on_shelf") && s.i("status_id") != 3 { hardcoverEnd = true }
    }

    // MARK: the More menu

    func goToBeginning() { open(epub?.sections.firstIndex { $0.linear } ?? 0, at: 0) }

    func goToKindle() { if let f = details?.o("kindle")?.d("fraction") { go(fraction: f) } }

    /// Forget my place in Daf: the book opens at its start (or where the Kindle is) next time.
    func forgetPlace() async {
        do {
            try await API.shared.send("DELETE", "/api/ebooks/\(API.enc(id))/position", nil)
            forget = true
            forgotAt = Date()
            say("Daf forgot your place in this book")
        } catch { self.error = error.localizedDescription }
    }

    func exportHighlights() async {
        guard let data = try? await API.shared.data("/api/highlights/export?fmt=md&book=" + API.enc(id)) else { say("The export didn't come"); return }
        let p = NSSavePanel()
        p.nameFieldStringValue = PaperPages.short(title) + " highlights.md"
        if p.runModal() == .OK, let u = p.url { try? data.write(to: u) }
    }

    func downloadFile() async {
        guard let data = try? await Self.file(for: id, size: details?.i("size")) else { say("The file didn't come"); return }
        let p = NSSavePanel()
        p.nameFieldStringValue = PaperPages.short(title) + "." + ((details?.s("format") ?? "EPUB") == "KEPUB" ? "kepub.epub" : "epub")
        if p.runModal() == .OK, let u = p.url { try? data.write(to: u) }
    }

    // MARK: opening at a place

    /// "q:" and words (found in the book), "hl:" and a highlight, a CFI, or a path in the book with its anchor.
    func go(target t: String) async {
        if t.hasPrefix("q:") { await find(words: String(t.dropFirst(2))); return }
        if t.hasPrefix("hl:") {
            let hid = String(t.dropFirst(3))
            if let c = highlights.first(where: { $0.s("id") == hid })?.o("pos")?.s("cfi") { go(cfi: c, flash: true) }
            else if let k = kindle.first(where: { $0.s("id") == hid }) { await go(kindle: k) }
            return
        }
        if t.hasPrefix("epubcfi(") { go(cfi: t, flash: false); return }
        let bits = t.split(separator: "#", maxSplits: 1).map(String.init)
        go(EPUB.Target(label: "", path: bits[0], fragment: bits.count > 1 ? bits[1] : nil))
    }

    /// Words found in the book, and their page shown.
    func find(words: String) async {
        guard let epub else { return }
        for k in epub.sections.indices {
            if let r = Self.find(words, in: Self.normal(plain(k))) {
                open(k, at: r.location)
                pages?.flash(r)
                return
            }
            if k % 6 == 5 { await Task.yield() }
        }
        say("That passage isn't in this copy")
    }

    func close() {
        beatTimer?.invalidate()
        beatTimer = nil
        saveTask?.cancel()
        Task { await savePosition(closing: true) }
    }

    // MARK: the reading time

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, let w = self.pages?.window, w.occlusionState.contains(.visible), NSApp.isActive,
                      Date().timeIntervalSince(self.lastActive) < 90 else { return }
                if Speaker.shared.playing && Speaker.shared.key == self.listenKey { return }    // the listening counts it already
                self.beat()
            }
        }
    }

    func beat() {
        beats += 1
        let id = self.id
        Task { try? await API.shared.send("POST", "/api/read/beat", ["book_id": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
    }

    // MARK: highlights

    /// The highlights in this chapter, painted in their colours (a note: dotted, shown on hover).
    func paint() {
        guard let epub, let text, let s = pages?.storage else { return }
        let all = NSRange(location: 0, length: s.length)
        s.beginEditing()
        for k in [NSAttributedString.Key.backgroundColor, .dafHighlight, .toolTip, .underlineStyle] { s.removeAttribute(k, range: all) }
        for h in highlights {
            guard let cfi = h.o("pos")?.s("cfi") else { continue }
            let parsed = CFI.parse(cfi)
            guard epub.section(ofCFI: parsed) == section, var r = text.range(of: parsed), r.length > 0, NSMaxRange(r) <= s.length else { continue }
            let ns = s.string as NSString                 // a range that ends at the next paragraph stops at its own words
            while r.length > 0, let u = Unicode.Scalar(ns.character(at: NSMaxRange(r) - 1)), CharacterSet.whitespacesAndNewlines.contains(u) || u == "\u{2028}" { r.length -= 1 }
            s.addAttribute(.backgroundColor, value: ReaderModel.colour(h.s("color")), range: r)
            s.addAttribute(.dafHighlight, value: h.s("id") ?? "", range: r)
            if let n = h.s("user_note"), !n.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                s.addAttributes([.toolTip: n, .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                                 .underlineColor: look.quiet], range: r)
            }
        }
        for (kid, r) in kindleRanges(section) where NSMaxRange(r) <= s.length {        // the Kindle's, drawn like Daf's own
            guard let h = kindle.first(where: { $0.s("id") == kid }) else { continue }
            s.addAttribute(.backgroundColor, value: ReaderModel.colour(h.s("color")), range: r)
            s.addAttribute(.dafHighlight, value: kid, range: r)
            let n = h.s("user_note") ?? h.s("note")
            s.addAttribute(.toolTip, value: "From the Kindle" + (n.map { ": " + $0 } ?? ""), range: r)
        }
        s.endEditing()
    }

    /// The selection highlighted (H, or the menu), kept by Daf as the page keeps it: highlights it
    /// overlaps merge into it (`replaces`), and a selection inside one is that one.
    func highlight(_ sel: NSRange, color: String? = nil, thenNote: Bool = false) async {
        guard let epub, let text, let s = pages?.storage, sel.length > 0, NSMaxRange(sel) <= s.length else { return }
        let over = highlights.compactMap { h -> (J, NSRange)? in
            guard let c = h.o("pos")?.s("cfi") else { return nil }
            let p = CFI.parse(c)
            guard epub.section(ofCFI: p) == section, let r = text.range(of: p), NSIntersectionRange(r, sel).length > 0 else { return nil }
            return (h, r)
        }
        if let inside = over.first(where: { $0.1.location <= sel.location && NSMaxRange(sel) <= NSMaxRange($0.1) }) {
            if thenNote { editing = .init(h: inside.0) }
            pages?.deselect()
            return
        }
        var r = sel
        let letters = s.string as NSString                             // a selection snaps to whole words, as the page's
        func isWord(_ i: Int) -> Bool {
            guard i >= 0, i < letters.length, let u = Unicode.Scalar(letters.character(at: i)) else { return false }
            return CharacterSet.alphanumerics.contains(u) || u == "'" || u == "’"
        }
        while r.location > 0 && isWord(r.location - 1) && isWord(r.location) { r.location -= 1; r.length += 1 }
        while NSMaxRange(r) < letters.length && isWord(NSMaxRange(r) - 1) && isWord(NSMaxRange(r)) { r.length += 1 }
        for (_, o) in over { r = NSUnionRange(r, o) }
        let color = color ?? over.first?.0.s("color") ?? HLTools.lastColour
        let ns = s.string as NSString
        while r.length > 0, let u = Unicode.Scalar(ns.character(at: r.location)), CharacterSet.whitespacesAndNewlines.contains(u) { r.location += 1; r.length -= 1 }
        while r.length > 0, let u = Unicode.Scalar(ns.character(at: NSMaxRange(r) - 1)), CharacterSet.whitespacesAndNewlines.contains(u) { r.length -= 1 }
        guard r.length > 0, let local = text.cfi(r.location, NSMaxRange(r)) else { return }
        let cfi = CFI.join(epub.sections[section].cfi, local)
        let words = ns.substring(with: r).split(whereSeparator: \.isWhitespace).joined(separator: " ")
        do {
            var body: [String: Any] = ["cfi": cfi, "text": words, "chapter": chapter, "fraction": fraction, "color": color]
            if !over.isEmpty { body["replaces"] = over.compactMap { $0.0.s("id") } }
            let res = J(try await API.shared.send("POST", "/api/ebooks/\(API.enc(id))/highlights", body))
            let hid = res?.s("id") ?? UUID().uuidString
            let gone = Set(over.compactMap { $0.0.s("id") })
            let notes = over.compactMap { $0.0.s("user_note") }
            highlights.removeAll { $0.s("id") == hid || gone.contains($0.s("id") ?? "") }
            var made: [String: Any] = ["id": hid, "text": words, "chapter": chapter, "pos": ["cfi": cfi, "fraction": fraction], "color": color, "source": "epub"]
            if !notes.isEmpty { made["user_note"] = notes.joined(separator: "\n\n") }
            highlights.append(J(made))
            paint()
            pages?.deselect()
            if thenNote { editing = .init(h: J(made)) }
        } catch { self.error = error.localizedDescription }
    }

    /// Remove, with Undo bringing it back (/api/highlights/{id}/restore).
    func remove(highlight hid: String) async {
        do {
            try await API.shared.send("DELETE", "/api/highlights/\(API.enc(hid))", nil)
            highlights.removeAll { $0.s("id") == hid }
            kindle.removeAll { $0.s("id") == hid }
            placedKindle = placedKindle.mapValues { $0.filter { $0.id != hid } }
            paint()
            let book = id
            AppModel.shared.say("Highlight removed", undo: "Remove Highlight") { [weak self] in
                _ = try? await API.shared.send("POST", "/api/highlights/\(API.enc(hid))/restore", [:])
                if let self, let d = try? await API.shared.json("/api/ebooks/" + API.enc(book)) { self.highlights = d.a("highlights"); self.paint() }
            }
        } catch { self.error = error.localizedDescription }
    }

    func set(color: String, of hid: String) async {
        do {
            try await API.shared.send("PUT", "/api/highlights/\(API.enc(hid))/color", ["color": color])
            changed(hid) { $0["color"] = color }
        } catch { self.error = error.localizedDescription }
    }

    func changed(_ hid: String, _ f: (inout [String: Any]) -> Void) {
        if let k = highlights.firstIndex(where: { $0.s("id") == hid }) {
            var raw = highlights[k].raw
            f(&raw)
            highlights[k] = J(raw)
        } else if let k = kindle.firstIndex(where: { $0.s("id") == hid }) {
            var raw = kindle[k].raw
            f(&raw)
            kindle[k] = J(raw)
        }
        paint()
    }

    /// A highlight of either kind, by its id.
    func highlight(withID hid: String) -> J? { highlights.first { $0.s("id") == hid } ?? kindle.first { $0.s("id") == hid } }

    // MARK: bookmarks

    private func bookmarkHere() -> J? {
        guard let epub, let text, let vis = pages?.visible else { return nil }
        return bookmarks.first { b in
            guard let c = b.s("cfi") else { return false }
            let p = CFI.parse(c)
            guard epub.section(ofCFI: p) == section, let r = text.range(of: p) else { return false }
            return r.location >= vis.location && r.location <= NSMaxRange(vis)
        }
    }

    /// B: a bookmark on these pages, or off them.
    func toggleBookmark() async {
        guard let epub, let text, let vis = pages?.visible else { return }
        do {
            if let here = bookmarkHere(), let mid = here.s("id") {
                try await API.shared.send("DELETE", "/api/ebooks/\(API.enc(id))/bookmarks/\(API.enc(mid))", nil)
                bookmarks.removeAll { $0.s("id") == mid }
            } else if let local = text.cfi(vis.location) {
                let cfi = CFI.join(epub.sections[section].cfi, local)
                let excerpt = (text.string.string as NSString).substring(with: NSRange(location: vis.location, length: min(120, max(0, text.length - vis.location))))
                    .split(whereSeparator: \.isWhitespace).joined(separator: " ")
                let r = J(try await API.shared.send("POST", "/api/ebooks/\(API.enc(id))/bookmarks",
                                                  ["cfi": cfi, "fraction": fraction, "chapter": chapter, "excerpt": excerpt]))
                bookmarks.append(J(["id": r?.s("id") ?? "", "cfi": cfi, "fraction": fraction, "chapter": chapter, "excerpt": excerpt]))
            }
            marked = bookmarkHere() != nil
        } catch { self.error = error.localizedDescription }
    }
}

// MARK: the pages

/// The chapter set as pages: one text container a page, all on one layout manager (so a selection
/// runs from one page onto the next), one or two shown at a time.
final class BookPagesView: NSView, NSTextViewDelegate {
    weak var model: BookModel?
    let storage = NSTextStorage()
    private let layoutManager = NSLayoutManager()
    private var views: [BookTextView] = []
    private(set) var first = 0
    private(set) var perSpread = 2
    private var pageSize = NSSize.zero
    private var origin = NSPoint.zero
    private var gutter: CGFloat = 0
    private var laidFor = NSSize.zero
    private var swipe: CGFloat = 0
    private var swipeDone = false
    private var note: NSPopover?
    var rtl = false
    var look = BookLook() { didSet { needsDisplay = true } }
    /// The Scroll layout: the chapter as one long column in a scroll view, instead of pages.
    private var scroller: NSScrollView?
    var scrolls: Bool { look.flow == "scrolled" }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        storage.addLayoutManager(layoutManager)
    }
    required init?(coder: NSCoder) { fatalError() }

    var pageCount: Int { views.count }
    var pagesLeft: Int { scrolls ? 0 : max(0, views.count - first - perSpread) }

    /// The characters on the pages shown (in the Scroll layout, in the window).
    var visible: NSRange {
        if scrolls, let sv = scroller, let tv = views.first, let tc = tv.textContainer {
            let seen = sv.contentView.bounds.offsetBy(dx: -tv.textContainerOrigin.x, dy: -tv.textContainerOrigin.y)
            let g = layoutManager.glyphRange(forBoundingRect: seen, in: tc)
            return layoutManager.characterRange(forGlyphRange: g, actualGlyphRange: nil)
        }
        guard !views.isEmpty, let a = views[min(first, views.count - 1)].textContainer else { return NSRange(location: 0, length: 0) }
        let b = views[min(first + perSpread - 1, views.count - 1)].textContainer ?? a
        let ga = layoutManager.glyphRange(for: a), gb = layoutManager.glyphRange(for: b)
        let start = layoutManager.characterIndexForGlyph(at: ga.location)
        let end = NSMaxRange(gb) >= layoutManager.numberOfGlyphs ? storage.length : layoutManager.characterIndexForGlyph(at: NSMaxRange(gb))
        return NSRange(location: start, length: max(0, end - start))
    }

    func show(_ text: NSAttributedString, at char: Int) {
        note?.close()
        storage.setAttributedString(text)
        paginate()
        go(toChar: char, animated: false)
    }

    /// The chapter set again for the window's size: pages of the same size, the pictures fitted.
    func paginate() {
        let b = bounds.size
        guard b.width > 200, b.height > 200 else { return }
        if scrolls { column(b); return }
        scroller?.removeFromSuperview()
        scroller = nil
        perSpread = b.width >= 860 && b.width > b.height * 1.08 ? 2 : 1
        let top: CGFloat = 46, bottom: CGFloat = 58
        gutter = perSpread == 2 ? max(56, b.width * 0.065) : 0
        let column: CGFloat = ["narrow": 560, "wide": 820][look.width] ?? 680             // the line width, as the Aa panel has it
        let margin: CGFloat = ["narrow": 1.7, "wide": 0.6][look.width] ?? 1
        let side: CGFloat = perSpread == 2 ? max(36, b.width * 0.055 * margin) : max(40, (b.width - column) / 2)
        let w = perSpread == 2 ? (b.width - side * 2 - gutter) / 2 : b.width - side * 2
        pageSize = NSSize(width: floor(w), height: floor(b.height - top - bottom))
        origin = NSPoint(x: side, y: top)
        fitPictures()
        for v in views { v.removeFromSuperview() }
        views.removeAll()
        while !layoutManager.textContainers.isEmpty { layoutManager.removeTextContainer(at: 0) }
        var done = false
        while !done && views.count < 4000 {
            let tc = NSTextContainer(size: pageSize)
            tc.lineFragmentPadding = 0
            layoutManager.addTextContainer(tc)
            let tv = BookTextView(frame: NSRect(origin: .zero, size: pageSize), textContainer: tc)
            setUp(tv)
            views.append(tv)
            let g = layoutManager.glyphRange(for: tc)
            done = NSMaxRange(g) >= layoutManager.numberOfGlyphs || (g.length == 0 && views.count > 1)
        }
        laidFor = b
    }

    /// The Scroll layout: one text view the column's width, centred, as tall as the chapter.
    private func column(_ b: NSSize) {
        perSpread = 1
        first = 0
        let width: CGFloat = min(["narrow": 560, "wide": 820][look.width] ?? 680, b.width - 80)
        pageSize = NSSize(width: floor(width), height: b.height)
        fitPictures()
        for v in views { v.removeFromSuperview() }
        views.removeAll()
        while !layoutManager.textContainers.isEmpty { layoutManager.removeTextContainer(at: 0) }
        let tc = NSTextContainer(size: NSSize(width: pageSize.width, height: CGFloat.greatestFiniteMagnitude))
        tc.lineFragmentPadding = 0
        layoutManager.addTextContainer(tc)
        let tv = BookTextView(frame: NSRect(x: 0, y: 0, width: b.width, height: 100), textContainer: tc)
        setUp(tv)
        tv.textContainerInset = NSSize(width: floor((b.width - pageSize.width) / 2), height: 48)
        tv.isVerticallyResizable = true
        tv.minSize = NSSize(width: b.width, height: b.height)
        tv.maxSize = NSSize(width: b.width, height: .greatestFiniteMagnitude)
        layoutManager.ensureLayout(for: tc)
        tv.frame = NSRect(x: 0, y: 0, width: b.width, height: max(b.height, layoutManager.usedRect(for: tc).height + 140))
        views = [tv]
        let sv = scroller ?? {
            let s = NSScrollView()
            s.hasVerticalScroller = true
            s.autohidesScrollers = true
            s.drawsBackground = false
            s.contentView.drawsBackground = false
            s.contentView.postsBoundsChangedNotifications = true
            NotificationCenter.default.addObserver(forName: NSView.boundsDidChangeNotification, object: s.contentView, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.model?.relocated() }
            }
            scroller = s
            return s
        }()
        sv.frame = bounds
        sv.autoresizingMask = [.width, .height]
        sv.documentView = tv
        if sv.superview == nil { addSubview(sv) }
        laidFor = b
    }

    private func setUp(_ tv: BookTextView) {
        tv.pages = self
        tv.isEditable = false
        tv.isSelectable = true
        tv.isRichText = true
        tv.drawsBackground = false
        tv.textContainerInset = .zero
        tv.isVerticallyResizable = false
        tv.isHorizontallyResizable = false
        tv.delegate = self
        tv.linkTextAttributes = [.foregroundColor: look.ink, .underlineStyle: NSUnderlineStyle.single.rawValue,
                                 .underlineColor: look.quiet, .cursor: NSCursor.pointingHand]
        tv.selectedTextAttributes = [.backgroundColor: NSColor.selectedTextBackgroundColor]
    }

    /// Pictures no bigger than a page.
    private func fitPictures() {
        let all = NSRange(location: 0, length: storage.length)
        storage.enumerateAttribute(.attachment, in: all) { v, r, _ in
            guard let att = v as? NSTextAttachment, let img = att.image, img.size.width > 0, img.size.height > 0 else { return }
            let scale = min(1, pageSize.width / img.size.width, pageSize.height * 0.9 / img.size.height)
            att.bounds = CGRect(x: 0, y: 0, width: floor(img.size.width * scale), height: floor(img.size.height * scale))
            storage.edited(.editedAttributes, range: r, changeInLength: 0)
        }
    }

    func page(ofChar char: Int) -> Int {
        guard storage.length > 0 else { return 0 }
        let g = layoutManager.glyphIndexForCharacter(at: min(max(0, char), storage.length - 1))
        return views.firstIndex { tv in tv.textContainer.map { NSLocationInRange(g, layoutManager.glyphRange(for: $0)) } ?? false } ?? max(0, views.count - 1)
    }

    func go(toChar char: Int, animated: Bool) {
        if scrolls, let sv = scroller, let tv = views.first, let tc = tv.textContainer, storage.length > 0 {
            let g = layoutManager.glyphIndexForCharacter(at: min(max(0, char), storage.length - 1))
            let r = layoutManager.boundingRect(forGlyphRange: NSRange(location: g, length: 1), in: tc)
            sv.contentView.scroll(to: NSPoint(x: 0, y: max(0, r.minY + tv.textContainerOrigin.y - 48)))
            sv.reflectScrolledClipView(sv.contentView)
            model?.relocated()
            return
        }
        let p = page(ofChar: char)
        first = p - p % perSpread
        display(animated: animated, forward: true)
    }

    private func display(animated: Bool, forward: Bool) {
        for v in subviews where v is BookTextView { v.removeFromSuperview() }
        for k in 0..<perSpread {
            let i = first + k
            guard i < views.count else { break }
            let col = rtl ? perSpread - 1 - k : k
            views[i].frame = NSRect(x: origin.x + CGFloat(col) * (pageSize.width + gutter), y: origin.y, width: pageSize.width, height: pageSize.height)
            addSubview(views[i])
        }
        if animated {
            let t = CATransition()
            t.type = .push
            t.subtype = forward != rtl ? .fromRight : .fromLeft
            t.duration = 0.2
            t.timingFunction = CAMediaTimingFunction(name: .easeOut)
            layer?.add(t, forKey: "turn")
        }
        needsDisplay = true
        model?.relocated()
    }

    func turn(_ forward: Bool) {
        note?.close()
        model?.lastActive = Date()
        // the Scroll layout: a window's worth down or up, and on into the next chapter at the end
        if scrolls, let sv = scroller, let doc = sv.documentView {
            let cv = sv.contentView, step = cv.bounds.height - 60, y = cv.bounds.minY
            if forward {
                if cv.bounds.maxY >= doc.frame.height - 2 { model?.nextSection(); return }
                cv.animator().setBoundsOrigin(NSPoint(x: 0, y: min(y + step, doc.frame.height - cv.bounds.height)))
            } else {
                if y <= 1 { model?.previousSection(); return }
                cv.animator().setBoundsOrigin(NSPoint(x: 0, y: max(0, y - step)))
            }
            return
        }
        if forward {
            if first + perSpread < views.count { first += perSpread; display(animated: true, forward: true) }
            else { model?.nextSection() }
        } else {
            if first > 0 { first = max(0, first - perSpread); display(animated: true, forward: false) }
            else { model?.previousSection() }
        }
    }

    func deselect() { views.first?.setSelectedRange(NSRange(location: visible.location, length: 0)) }

    /// For the self-test: the paragraph read aloud is marked here.
    func speaking(at i: Int) -> Bool { i < storage.length && layoutManager.temporaryAttribute(.backgroundColor, atCharacterIndex: i, effectiveRange: nil) != nil }

    /// The paragraph read aloud, marked around the highlights in it.
    /// For the self-test: what was marked last.
    var lastMarked: NSRange?

    func markSpeaking(_ r: NSRange?) {
        lastMarked = r
        layoutManager.removeTemporaryAttribute(.backgroundColor, forCharacterRange: NSRange(location: 0, length: storage.length))
        guard let r, NSMaxRange(r) <= storage.length else { return }
        storage.enumerateAttribute(.dafHighlight, in: r) { v, sub, _ in
            if (v as? String)?.isEmpty ?? true {
                layoutManager.addTemporaryAttribute(.backgroundColor, value: NSColor.controlAccentColor.withAlphaComponent(look.dark ? 0.28 : 0.14), forCharacterRange: sub)
            }
        }
    }
    var selection: NSRange { views.first?.selectedRange() ?? NSRange(location: 0, length: 0) }

    /// A highlight's words flashed on its page (Open at Its Spot).
    func flash(_ r: NSRange) {
        go(toChar: r.location, animated: false)
        if let tv = views.first(where: { $0.superview != nil && $0.textContainer.map { NSLocationInRange(layoutManager.glyphIndexForCharacter(at: r.location), layoutManager.glyphRange(for: $0)) } ?? false }) {
            tv.showFindIndicator(for: r)
        }
    }

    func showNote(_ text: NSAttributedString, from view: NSTextView, at char: Int) {
        note?.close()
        let tv = NSTextView(frame: NSRect(x: 0, y: 0, width: 360, height: 10))
        tv.isEditable = false
        tv.drawsBackground = false
        tv.textStorage?.setAttributedString(text)
        tv.textContainerInset = NSSize(width: 14, height: 12)
        tv.sizeToFit()
        tv.layoutManager?.ensureLayout(for: tv.textContainer!)
        let h = min(320, (tv.layoutManager?.usedRect(for: tv.textContainer!).height ?? 60) + 26)
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 360, height: h))
        scroll.documentView = tv
        scroll.hasVerticalScroller = h >= 320
        scroll.drawsBackground = false
        let vc = NSViewController()
        vc.view = scroll
        let p = NSPopover()
        p.contentViewController = vc
        p.behavior = .transient
        let g = view.layoutManager!.glyphIndexForCharacter(at: char)
        let rect = view.layoutManager!.boundingRect(forGlyphRange: NSRange(location: g, length: 1), in: view.textContainer!)
        p.show(relativeTo: rect, of: view, preferredEdge: .maxY)
        note = p
    }

    // MARK: drawing, size, keys, swipes

    override func draw(_ dirtyRect: NSRect) {
        look.background.setFill()
        bounds.fill()
        let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 11), .foregroundColor: look.quiet]
        for k in 0..<perSpread where first + k < views.count && !scrolls {
            let col = rtl ? perSpread - 1 - k : k
            let s = "\(first + k + 1)" as NSString
            let size = s.size(withAttributes: attrs)
            let x = origin.x + CGFloat(col) * (pageSize.width + gutter) + (pageSize.width - size.width) / 2
            s.draw(at: NSPoint(x: x, y: bounds.height - 50), withAttributes: attrs)
        }
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        guard !inLiveResize, storage.length > 0, abs(newSize.width - laidFor.width) > 1 || abs(newSize.height - laidFor.height) > 1 else { return }
        let at = visible.location
        paginate()
        go(toChar: at, animated: false)
    }

    override func viewDidEndLiveResize() {
        super.viewDidEndLiveResize()
        guard storage.length > 0 else { return }
        let at = visible.location
        paginate()
        go(toChar: at, animated: false)
    }

    override func keyDown(with event: NSEvent) {
        if !handle(event) { super.keyDown(with: event) }
    }

    /// The reading keys, from the pages or from a page's text.
    func handle(_ event: NSEvent) -> Bool {
        model?.lastActive = Date()
        let mods = event.modifierFlags.intersection([.command, .control, .option])
        guard mods.isEmpty else { return false }
        switch event.keyCode {
        case 124: turn(!rtl); return true                         // →
        case 123: turn(rtl); return true                          // ←
        case 121, 125: turn(true); return true                    // page down, ↓
        case 116, 126: turn(false); return true                   // page up, ↑
        case 49: turn(!event.modifierFlags.contains(.shift)); return true   // space
        default: break
        }
        switch event.charactersIgnoringModifiers {
        case "h":
            let sel = selection
            guard sel.length > 0 else { return false }
            Task { @MainActor in await model?.highlight(sel) }
            return true
        case "b": Task { @MainActor in await model?.toggleBookmark() }; return true
        case "f": let w = window; MainActor.assumeIsolated { Focus.shared.toggle(w) }; return true      // focus mode (Focus.swift)
        default: break
        }
        switch event.characters {
        case "p":                                               // the page's keys: p listens or pauses,
            if let m = model { if Speaker.shared.key == m.listenKey { Speaker.shared.toggle() } else { Speaker.shared.start(m) } }
            return true
        case "L":                                               // L reads aloud from here
            if let m = model { Speaker.shared.start(m, at: selection.length > 0 ? selection.location : nil) }
            return true
        default: return false
        }
    }

    override func scrollWheel(with event: NSEvent) {
        if event.phase == .began || (event.phase.isEmpty && event.momentumPhase.isEmpty && abs(swipe) < 1) { swipe = 0; swipeDone = false }
        guard event.momentumPhase.isEmpty else { return }
        let dx = event.scrollingDeltaX, dy = event.scrollingDeltaY
        swipe += abs(dx) > abs(dy) ? dx : (event.hasPreciseScrollingDeltas ? 0 : dy * 8)
        if !swipeDone, abs(swipe) > 45 {
            swipeDone = true
            let back = swipe > 0
            turn(rtl ? back : !back)
        }
        if event.phase == .ended || event.phase == .cancelled || (event.phase.isEmpty && !event.hasPreciseScrollingDeltas) {
            if event.phase.isEmpty { swipeDone = false; swipe = 0 }
        }
    }

    override func mouseDown(with event: NSEvent) {
        let x = convert(event.locationInWindow, from: nil).x
        if x < bounds.width * 0.1 { turn(rtl) } else if x > bounds.width * 0.9 { turn(!rtl) } else { super.mouseDown(with: event) }
    }

    func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
        let target = (textView.textStorage?.attribute(.dafBookLink, at: charIndex, effectiveRange: nil) as? String) ?? (link as? URL)?.absoluteString ?? ""
        guard !target.isEmpty else { return false }
        model?.follow(target, from: textView, at: charIndex)
        return true
    }
}

/// A page's text: selectable, the reading keys passed to the pages, and the book's own menu.
final class BookTextView: NSTextView {
    weak var pages: BookPagesView?

    /// Highlight on selecting (a selection of words, unless ⌥ is held), as the page does.
    override func mouseDown(with event: NSEvent) {
        super.mouseDown(with: event)
        let sel = selectedRange()
        guard HLTools.autoHighlight, sel.length > 1, !NSEvent.modifierFlags.contains(.option), event.clickCount == 1,
              (string as NSString).substring(with: sel).trimmingCharacters(in: .whitespacesAndNewlines).contains(" ") else { return }
        let m = pages?.model
        Task { @MainActor in await m?.highlight(sel) }
    }

    override func keyDown(with event: NSEvent) {
        if pages?.handle(event) != true { super.keyDown(with: event) }
    }

    override func scrollWheel(with event: NSEvent) { pages?.scrollWheel(with: event) }

    override func mouseMoved(with event: NSEvent) {
        let m = pages?.model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        super.mouseMoved(with: event)
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        let at = characterIndexForInsertion(at: convert(event.locationInWindow, from: nil))
        var extra: [NSMenuItem] = []
        let sel = selectedRange()
        if sel.length > 0 {
            extra.append(item("Highlight", #selector(highlightNow)))
            extra.append(MenuAction.item("Highlight with a Note") { let m = self.pages?.model; Task { @MainActor in await m?.highlight(sel, thenNote: true) } })
        }
        if at < textStorage?.length ?? 0, let hid = textStorage?.attribute(.dafHighlight, at: at, effectiveRange: nil) as? String, !hid.isEmpty, let m = pages?.model {
            extra += MainActor.assumeIsolated { HLMenu.items(for: hid, host: m, kindle: m.kindle.contains { $0.s("id") == hid }) }
        }
        if sel.length > 0 {
            extra.append(item("Ask About This Passage", #selector(askAbout)))
            if let m = pages?.model, let look = MainActor.assumeIsolated({ HLMenu.lookup((string as NSString).substring(with: sel), at: sel.location, host: m) }) { extra.append(look) }
        }
        extra.append(item("Read Aloud from Here", #selector(readFromHere(_:)), at))
        let marked = MainActor.assumeIsolated { pages?.model?.marked ?? false }
        extra.append(item(marked ? "Remove the Bookmark" : "Bookmark This Page", #selector(bookmark)))
        for (k, i) in extra.enumerated() { menu.insertItem(i, at: k) }
        menu.insertItem(.separator(), at: extra.count)
        return menu
    }

    private func item(_ title: String, _ action: Selector, _ value: Any? = nil) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: "")
        i.target = self
        i.representedObject = value
        return i
    }

    @objc func highlightNow() { let sel = selectedRange(), m = pages?.model; Task { @MainActor in await m?.highlight(sel) } }
    @objc func bookmark() { let m = pages?.model; Task { @MainActor in await m?.toggleBookmark() } }
    @objc func readFromHere(_ sender: NSMenuItem) {
        guard let at = sender.representedObject as? Int else { return }
        MainActor.assumeIsolated { if let m = pages?.model { Speaker.shared.start(m, at: at) } }
    }
    @objc func askAbout() {
        let quote = (string as NSString).substring(with: selectedRange()).trimmingCharacters(in: .whitespacesAndNewlines)
        let m = pages?.model
        Task { @MainActor in await m?.ask("What does this passage mean here?", quote: quote) }
    }
    @objc func editNote(_ sender: NSMenuItem) {
        guard let hid = sender.representedObject as? String else { return }
        MainActor.assumeIsolated { if let m = pages?.model, let h = m.highlight(withID: hid) { m.editing = .init(h: h) } }
    }
    @objc func recolor(_ sender: NSMenuItem) {
        guard let v = sender.representedObject as? [String], v.count == 2 else { return }
        let m = pages?.model
        Task { @MainActor in await m?.set(color: v[1], of: v[0]) }
    }
    @objc func removeHighlight(_ sender: NSMenuItem) {
        guard let hid = sender.representedObject as? String else { return }
        let m = pages?.model
        Task { @MainActor in await m?.remove(highlight: hid) }
    }
}

struct BookPages: NSViewRepresentable {
    let model: BookModel
    func makeNSView(context: Context) -> BookPagesView {
        let v = BookPagesView(frame: .zero)
        model.attach(v)
        return v
    }
    func updateNSView(_ v: BookPagesView, context: Context) {}
}

// MARK: the window

struct BookReaderView: View {
    @Environment(AppModel.self) private var app
    @State private var m: BookModel
    @State private var window: NSWindow?
    @State private var showLook = false
    @State private var showPercent = false
    @State private var percent = ""

    init(id: String, at: String? = nil) { _m = State(initialValue: BookModel(id: id, at: at)) }

    var body: some View {
        Group {
            if m.otherFormat {
                WebPane(route: "#ebook/" + API.enc(m.id))
            } else if let e = m.error, m.epub == nil {
                ContentUnavailableView("The book didn't open", systemImage: "exclamationmark.triangle", description: Text(e))
            } else {
                HStack(spacing: 0) {
                    if m.showContents {
                        BookSidebar(m: m).frame(width: 270)
                        Divider()
                    }
                    BookPages(model: m)
                        .overlay(alignment: .bottom) {
                            Text(m.footer).font(.caption).foregroundStyle(Color(nsColor: m.look.quiet)).monospacedDigit().padding(.bottom, 12)
                        }
                        .overlay(alignment: .top) {
                            VStack(spacing: 8) {
                                kindleBanner
                                endNotices
                                if let t = m.toast { Text(t).font(.callout).padding(.horizontal, 14).padding(.vertical, 7).glassEffect(.regular, in: Capsule()) }
                            }
                            .padding(.top, 8)
                            .animation(.snappy, value: m.toast)
                        }
                        .overlay(alignment: .bottom) {
                            if Speaker.shared.key == m.listenKey { SpeakerBar().padding(.bottom, 72) }
                        }
                        .overlay { if m.epub == nil { ProgressView("Opening the book…").padding(40) } }
                }
            }
        }
        .background(Color(nsColor: m.look.background))
        .background(WindowFinder { if let w = $0, w !== window { window = w } })
        .onChange(of: Focus.shared.started) { _, _ in if Focus.shared.isOn(window) { m.showContents = false } }
        .navigationTitle(m.title)
        .navigationSubtitle(m.chapter)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                Button { m.showContents.toggle(); UserDefaults.standard.set(m.showContents, forKey: "book.contents") } label: {
                    Label("Contents", systemImage: "list.bullet")
                }
                .help("Contents, highlights and bookmarks")
                .keyboardShortcut("t", modifiers: [.command, .option])
            }
            ToolbarItemGroup {
                Button { m.sidebar = "search"; m.showContents = true; m.focusSearch += 1 } label: { Label("Search the Book", systemImage: "magnifyingglass") }
                    .help("Search the book (⌘F)")
                    .keyboardShortcut("f", modifiers: .command)
                Button { if Speaker.shared.key == m.listenKey { Speaker.shared.toggle() } else { Speaker.shared.start(m) } } label: {
                    Label("Listen", systemImage: Speaker.shared.key == m.listenKey && Speaker.shared.playing ? "pause.circle" : "play.circle")
                }
                .help("Read aloud from this page (P)")
                Button { showLook.toggle() } label: { Label("Appearance", systemImage: "textformat.size") }
                    .help("Typeface, size and theme")
                    .popover(isPresented: $showLook, arrowEdge: .bottom) { LookPanel(m: m) }
                Button { Task { await m.toggleBookmark() } } label: { Label(m.marked ? "Remove the Bookmark" : "Bookmark", systemImage: m.marked ? "bookmark.fill" : "bookmark") }
                    .help(m.marked ? "Remove the bookmark (B)" : "Bookmark this page (B)")
                FocusButton()
                Menu {
                    Button("Go to the Beginning") { m.goToBeginning() }
                    Button("Go to the Kindle's Page") { m.goToKindle() }.disabled(m.details?.o("kindle") == nil)
                    Button("Go to a Percent…") { percent = "\(Int((m.fraction * 100).rounded()))"; showPercent = true }
                    Divider()
                    Button("The Book's Page") { app.place = .books; let id = m.id; Task { try? await Task.sleep(nanoseconds: 300_000_000); app.selection = id }; NSApp.activate() }
                    Button("Export the Highlights…") { Task { await m.exportHighlights() } }
                    Button("Download the File…") { Task { await m.downloadFile() } }
                    Divider()
                    Toggle("Highlight When Selecting", isOn: Binding(get: { HLTools.autoHighlight }, set: { UserDefaults.standard.set($0, forKey: "autoHighlight") }))
                    Button("Forget My Place in Daf") { Task { await m.forgetPlace() } }
                } label: { Label("More", systemImage: "ellipsis.circle") }
                .popover(isPresented: $showPercent, arrowEdge: .bottom) {
                    HStack {
                        TextField("Percent", text: $percent).frame(width: 70).textFieldStyle(.roundedBorder)
                            .onSubmit { if let v = Double(percent) { m.go(fraction: max(0, min(100, v)) / 100) }; showPercent = false }
                        Text("%")
                        Button("Go") { if let v = Double(percent) { m.go(fraction: max(0, min(100, v)) / 100) }; showPercent = false }
                    }
                    .padding(14)
                }
            }
        }
        .sheet(isPresented: $m.finishing) { FinishSheet(bookID: m.id, title: m.title) { m.hardcoverEnd = false }.environment(app) }
        .task { await m.load() }
        .onDisappear { m.close(); if Speaker.shared.key == m.listenKey { Speaker.shared.stop() } }
        .sheet(item: $m.editing) { e in
            NoteSheet(h: e.h, saved: { n in m.changed(e.id) { $0["user_note"] = n } }).environment(app)
        }
        .sheet(item: $m.sheet) { s in
            HLSheetView(sheet: s) { hid, fields in m.changed(hid) { raw in for (k, v) in fields { raw[k] = v } } }
        }
        .alert("Daf", isPresented: Binding(get: { m.error != nil && m.epub != nil }, set: { if !$0 { m.error = nil } })) {
            Button("OK") { m.error = nil }
        } message: { Text(m.error ?? "") }
        .frame(minWidth: 640, minHeight: 520)
    }

    /// Near the end: the next in the series; Finished on Hardcover.
    @ViewBuilder
    private var endNotices: some View {
        if let next = m.nextInSeries, let nid = next.s("id") {
            HStack(spacing: 12) {
                Text("Next in \(m.details?.o("series")?.s("name") ?? "the series"): \(next.s("title") ?? "")").font(.callout).lineLimit(1)
                Button("Start It") { m.nextInSeries = nil; app.openRoute = "#ebook/" + API.enc(nid) }
                Button("Not Now") { m.nextInSeries = nil }
            }
            .padding(.horizontal, 16).padding(.vertical, 8)
            .glassEffect(.regular, in: Capsule())
        }
        if m.hardcoverEnd {
            HStack(spacing: 12) {
                Text("The end. Mark it read on Hardcover?").font(.callout)
                Button("Finished") { m.finishing = true }
                Button("Not Now") { m.hardcoverEnd = false }
            }
            .padding(.horizontal, 16).padding(.vertical, 8)
            .glassEffect(.regular, in: Capsule())
        }
    }

    @ViewBuilder
    private var kindleBanner: some View {
        if let k = m.kindleAhead {
            HStack(spacing: 12) {
                Text("The Kindle is further on, at \(Int((k * 100).rounded()))%").font(.callout)
                Button("Go There") { m.go(fraction: k); m.kindleAhead = nil }
                Button("Not Now") { m.kindleAhead = nil }
            }
            .padding(.horizontal, 16).padding(.vertical, 8)
            .glassEffect(.regular, in: Capsule())
            .padding(.top, 8)
        }
    }
}

/// Contents, highlights, bookmarks, search and Ask, beside the pages.
struct BookSidebar: View {
    let m: BookModel
    @State private var q = ""
    @State private var question = ""
    @FocusState private var searchField: Bool

    var body: some View {
        @Bindable var m = m
        VStack(spacing: 0) {
            Picker("Show", selection: $m.sidebar) {
                Image(systemName: "info.circle").help("About the book").tag("info")
                Image(systemName: "list.bullet").help("Contents").tag("contents")
                Image(systemName: "highlighter").help("Highlights").tag("highlights")
                Image(systemName: "bookmark").help("Bookmarks").tag("bookmarks")
                Image(systemName: "magnifyingglass").help("Search the book").tag("search")
                Image(systemName: "bubble.left.and.text.bubble.right").help("Ask").tag("ask")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(10)
            if m.sidebar == "search" {
                TextField("Search the book", text: $q)
                    .textFieldStyle(.roundedBorder)
                    .focused($searchField)
                    .onSubmit { Task { await m.search(q) } }
                    .padding(.horizontal, 10).padding(.bottom, 6)
                    .onAppear { searchField = true }
                    .onChange(of: m.focusSearch) { _, _ in searchField = true }
            }
            List {
                switch m.sidebar {
                case "highlights": highlights
                case "bookmarks": bookmarks
                case "search": search
                case "ask": ask
                case "info": info
                default:
                    if let epub = m.epub {
                        OutlineGroup(epub.toc, children: \.kids) { item in
                            Button { m.go(item.target) } label: {
                                Text(item.label).lineLimit(2).fontWeight(item.label == m.chapter ? .semibold : .regular)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .listStyle(.sidebar)
        }
    }

    /// About the book: its details, its series, the Kindle's page, its note in the vault.
    @ViewBuilder private var info: some View {
        if let d = m.details {
            VStack(alignment: .leading, spacing: 8) {
                if d.b("has_cover") {
                    AsyncImage(url: API.shared.url("/api/cover/" + API.enc(m.id))) { p in
                        if let i = p.image { i.resizable().aspectRatio(contentMode: .fit) } else { Color.secondary.opacity(0.08) }
                    }
                    .frame(height: 160)
                }
                Text(m.title).font(.system(.headline, design: .serif))
                if let a = d.s("author") { Text(a).font(.callout).foregroundStyle(.secondary) }
                if let desc = d.s("description") {
                    Text(String(desc.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression).prefix(700))).font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding(.vertical, 4)
            LabeledContent("Type", value: d.s("format") ?? "")
            if let y = d.s("year") { LabeledContent("Published", value: y) }
            if let l = d.s("language") { LabeledContent("Language", value: Locale.current.localizedString(forLanguageCode: l) ?? l) }
            LabeledContent("Progress", value: "\(Int((m.fraction * 100).rounded()))%")
            LabeledContent("Read here", value: plural(d.i("minutes_here") ?? 0, "minute"))
            LabeledContent("Highlights", value: "\(m.highlights.count + m.kindle.count)")
            if let s = d.o("series") {
                LabeledContent("Series", value: (s.s("name") ?? "") + (s.d("index").map { " #" + $0.formatted() } ?? ""))
                if let n = s.o("next"), let nid = n.s("id") {
                    Button("Next: " + (n.s("title") ?? "")) { AppModel.shared.openRoute = "#ebook/" + API.enc(nid) }.buttonStyle(.link)
                }
            }
            if let k = d.o("kindle"), let p = k.i("page"), let t = k.i("total") {
                LabeledContent("On the Kindle") {
                    HStack {
                        Text("p. \(p) of \(t)" + (k.d("at").map { " · " + Date(timeIntervalSince1970: $0).formatted(date: .abbreviated, time: .omitted) } ?? ""))
                        Button("Go There") { m.goToKindle() }.buttonStyle(.link)
                    }
                }
            }
            if let v = d.s("vault_path") { Text("In the vault: " + v).font(.caption).foregroundStyle(.tertiary).textSelection(.enabled) }
        }
    }

    @ViewBuilder private var highlights: some View {
        ForEach(m.highlights, id: \.self) { h in
            Button { if let c = h.o("pos")?.s("cfi") { m.go(cfi: c, flash: true) } } label: { card(h, place: h.s("chapter")) }
                .buttonStyle(.plain)
        }
        if !m.kindle.isEmpty {
            Section("From the Kindle") {
                ForEach(m.kindle, id: \.self) { h in
                    Button { Task { await m.go(kindle: h) } } label: { card(h, place: h.s("page").map { "p. " + $0 } ?? h.s("chapter")) }
                        .buttonStyle(.plain)
                }
            }
        }
        if m.highlights.isEmpty && m.kindle.isEmpty { Text("Select words and press H to highlight them.").foregroundStyle(.secondary) }
    }

    private func card(_ h: J, place: String?) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(h.s("text") ?? "").font(.system(.callout, design: .serif)).lineLimit(4)
            if let n = h.s("user_note") ?? h.s("note") { Text(n).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
            if let place { Text(place).font(.caption2).foregroundStyle(.tertiary).lineLimit(1) }
        }
        .padding(.leading, 6)
        .overlay(alignment: .leading) { Rectangle().fill(Color(ReaderModel.colour(h.s("color")).withAlphaComponent(1))).frame(width: 3) }
    }

    @ViewBuilder private var bookmarks: some View {
        ForEach(m.bookmarks, id: \.self) { b in
            Button { if let c = b.s("cfi") { m.go(cfi: c) } } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Text(b.s("chapter") ?? "Bookmark").font(.callout.weight(.medium)).lineLimit(1)
                    if let e = b.s("excerpt") { Text(e).font(.caption).foregroundStyle(.secondary).lineLimit(2) }
                }
            }
            .buttonStyle(.plain)
        }
        if m.bookmarks.isEmpty { Text("Press B to bookmark a page.").foregroundStyle(.secondary) }
    }

    @ViewBuilder private var search: some View {
        if m.searching { HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Searching…").foregroundStyle(.secondary) } }
        if !m.query.isEmpty && !m.searching { Text(m.results.isEmpty ? "Not in this book" : (m.results.count >= 500 ? "500 or more" : plural(m.results.count, "place"))).font(.caption).foregroundStyle(.secondary) }
        ForEach(m.results) { hit in
            Button { m.go(hit) } label: {
                VStack(alignment: .leading, spacing: 2) {
                    (Text(hit.before) + Text(hit.match).bold() + Text(hit.after)).font(.system(.callout, design: .serif)).lineLimit(3)
                    Text(m.chapterTitle(of: hit.section)).font(.caption2).foregroundStyle(.tertiary).lineLimit(1)
                }
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder private var ask: some View {
        ForEach(Array(m.asks.enumerated()), id: \.offset) { _, a in
            VStack(alignment: .leading, spacing: 5) {
                if let qt = a.s("quote") { Text("“\(qt)”").font(.system(.caption, design: .serif)).foregroundStyle(.secondary).lineLimit(3) }
                Text(a.s("q") ?? "").font(.callout.weight(.semibold))
                Text(Inspector.markdown(a.s("a") ?? "")).font(.callout).textSelection(.enabled)
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 3)
        }
        if m.asking { HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Thinking it over…").foregroundStyle(.secondary) } }
        TextField("Ask about the book", text: $question, axis: .vertical)
            .onSubmit { let q = question; question = ""; Task { await m.ask(q) } }
            .disabled(m.asking)
        if m.asks.isEmpty && !m.asking {
            ForEach((m.details?.strings("questions") ?? []).prefix(4), id: \.self) { q in
                Button(q) { Task { await m.ask(q) } }.buttonStyle(.link).multilineTextAlignment(.leading)
            }
        }
    }
}

extension EPUB.TOCItem {
    var kids: [EPUB.TOCItem]? { children.isEmpty ? nil : children }
}

/// The Aa panel: typeface, size, spacing, justified, theme.
struct LookPanel: View {
    let m: BookModel
    @State private var look = BookLook()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                ForEach(BookLook.themes, id: \.0) { t in
                    let l = { var x = look; x.theme = t.0; return x }()
                    Button { look.theme = t.0; m.restyle(look) } label: {
                        ZStack {
                            Circle().fill(Color(nsColor: l.background))
                            Text("Aa").font(.system(size: 13, weight: .semibold, design: .serif)).foregroundStyle(Color(nsColor: l.ink))
                        }
                        .frame(width: 38, height: 38)
                        .overlay(Circle().stroke(look.theme == t.0 ? Color.daf : Color.secondary.opacity(0.35), lineWidth: look.theme == t.0 ? 2.5 : 1))
                    }
                    .buttonStyle(.plain)
                    .help(t.1)
                }
            }
            Picker("Typeface", selection: Binding(get: { look.font }, set: { look.font = $0; m.restyle(look) })) {
                ForEach(BookLook.fonts, id: \.self) { f in Text(f).tag(f) }
            }
            HStack {
                Button { look.size = max(13, look.size - 1); m.restyle(look) } label: { Image(systemName: "textformat.size.smaller") }
                Text("\(Int(look.size)) pt").monospacedDigit().frame(width: 52)
                Button { look.size = min(34, look.size + 1); m.restyle(look) } label: { Image(systemName: "textformat.size.larger") }
            }
            LabeledContent("Line spacing") {
                Slider(value: Binding(get: { Double(look.spacing) }, set: { look.spacing = CGFloat(($0 * 20).rounded() / 20) }), in: 1.1...2.0) { editing in
                    if !editing { m.restyle(look) }
                }
                .frame(width: 150)
            }
            Toggle("Justify the text", isOn: Binding(get: { look.justify }, set: { look.justify = $0; m.restyle(look) }))
            Picker("Line width", selection: Binding(get: { look.width }, set: { look.width = $0; m.restyle(look) })) {
                ForEach(BookLook.widths, id: \.0) { Text($0.1).tag($0.0) }
            }
            .pickerStyle(.segmented)
            Picker("Layout", selection: Binding(get: { look.flow }, set: { look.flow = $0; m.restyle(look) })) {
                Text("Pages").tag("paginated")
                Text("Scroll").tag("scrolled")
            }
            .pickerStyle(.segmented)
            Toggle("Just for this book", isOn: Binding(get: { m.ownLook }, set: { on in
                m.ownLook = on
                if !on { UserDefaults.standard.removeObject(forKey: "book.look." + m.id); look = BookLook.load(); m.restyle(look) }
                else { m.restyle(look) }
            }))
            .help("This book keeps its own typeface, size, spacing and width")
        }
        .padding(18)
        .frame(width: 300)
        .onAppear { look = m.look }
    }
}
