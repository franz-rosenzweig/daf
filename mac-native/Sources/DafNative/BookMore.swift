import AppKit

/// A place a search found: its chapter, its characters there, and a few words either side.
struct BookHit: Identifiable, Hashable {
    let id = UUID()
    let section: Int
    let range: NSRange
    let before: String
    let match: String
    let after: String
}

extension BookModel {
    /// A chapter's text as shown, for searching it and for finding the Kindle's highlights in it.
    func plain(_ k: Int) -> String {
        if let t = texts[k] { return t }
        if let t = text, t.index == k { texts[k] = t.string.string; return t.string.string }
        guard let epub, let s = SectionText(epub: epub, index: k, look: look) else { return "" }
        texts[k] = s.string.string
        return s.string.string
    }

    /// The contents' label for a chapter (the last one that starts in it or before it).
    func chapterTitle(of k: Int) -> String {
        guard let epub else { return "" }
        var best = ""
        for item in epub.toc.flatMap(\.flat) { if let s = epub.section(of: item.target.path), s <= k { best = item.label } }
        return best
    }

    // MARK: search

    /// Every place in the book with these words (case and accents aside), a chapter at a time.
    func search(_ q: String) async {
        let q = q.trimmingCharacters(in: .whitespacesAndNewlines)
        query = q
        guard q.count >= 2, let epub else { results = []; return }
        searching = true
        defer { if query == q { searching = false } }
        var out: [BookHit] = []
        for k in epub.sections.indices {
            guard query == q else { return }                      // a newer search took over
            let t = plain(k) as NSString
            var from = 0
            while out.count < 500 {
                let f = t.range(of: q, options: [.caseInsensitive, .diacriticInsensitive], range: NSRange(location: from, length: t.length - from))
                guard f.location != NSNotFound else { break }
                let a = max(0, f.location - 50), b = min(t.length, NSMaxRange(f) + 70)
                func clean(_ s: String) -> String { s.replacingOccurrences(of: "\n", with: " ").replacingOccurrences(of: "\u{2028}", with: " ") }
                var before = clean(t.substring(with: NSRange(location: a, length: f.location - a)))
                var after = clean(t.substring(with: NSRange(location: NSMaxRange(f), length: b - NSMaxRange(f))))
                if a > 0, let sp = before.firstIndex(of: " ") { before = "…" + String(before[before.index(after: sp)...]) }     // whole words either side
                if b < t.length, let sp = after.lastIndex(of: " ") { after = String(after[..<sp]) + "…" }
                out.append(BookHit(section: k, range: f, before: before, match: t.substring(with: f), after: after))
                from = NSMaxRange(f)
            }
            if k % 4 == 3 { results = out; await Task.yield() }
        }
        if query == q { results = out }
    }

    func go(_ hit: BookHit) {
        open(hit.section, at: hit.range.location)
        pages?.flash(hit.range)
    }

    // MARK: the Kindle's highlights

    /// The chapter a Kindle highlight is in (KOReader's DocFragment), when it says.
    static func kindleSection(_ h: J) -> Int? {
        guard let xp = h.s("xp"), let r = xp.range(of: #"DocFragment\[(\d+)\]"#, options: .regularExpression) else { return nil }
        return Int(xp[r].filter(\.isNumber)).map { $0 - 1 }
    }

    /// The Kindle's highlights in a chapter, found by their words (this edition has the same words,
    /// not the Kindle's positions).
    func kindleRanges(_ k: Int) -> [(id: String, range: NSRange)] {
        if let p = placedKindle[k] { return p }
        let mine = kindle.filter { Self.kindleSection($0) == k }
        guard !mine.isEmpty else { placedKindle[k] = []; return [] }
        let t = plain(k)
        let hay = Self.normal(t)
        var out: [(String, NSRange)] = []
        for h in mine {
            if let id = h.s("id"), let r = Self.find(h.s("text") ?? "", in: hay) { out.append((id, r)) }
        }
        placedKindle[k] = out
        return out
    }

    /// A Kindle highlight shown on its page: in its own chapter, or wherever its words are.
    func go(kindle h: J) async {
        guard let id = h.s("id"), let epub else { return }
        if let k = Self.kindleSection(h), let r = kindleRanges(k).first(where: { $0.id == id })?.range {
            open(k, at: r.location)
            pages?.flash(r)
            return
        }
        let words = h.s("text") ?? ""
        for k in epub.sections.indices {
            if let r = Self.find(words, in: Self.normal(plain(k))) {
                open(k, at: r.location)
                pages?.flash(r)
                return
            }
            if k % 6 == 5 { await Task.yield() }
        }
        AppModel.shared.say("That passage isn't in this copy")
    }

    /// Text as matched: quotes and dashes made plain, white space one space; with the way back.
    struct Normal { let text: NSString; let map: [Int] }

    static func normal(_ s: String) -> Normal {
        let ns = s as NSString
        var out: [unichar] = [], map: [Int] = []
        out.reserveCapacity(ns.length)
        map.reserveCapacity(ns.length)
        var space = true
        for i in 0..<ns.length {
            var c = ns.character(at: i)
            switch c {
            case 0x2018, 0x2019, 0x201B, 0x2032: c = 0x27                 // ’ → '
            case 0x201C, 0x201D, 0x201F, 0x2033: c = 0x22                 // ” → "
            case 0x2013, 0x2014, 0x2015, 0x2212: c = 0x2D                 // — → -
            case 0x00AD, 0xFFFC: continue                                 // soft hyphens, pictures
            default: break
            }
            if c == 0x20 || c == 0x0A || c == 0x0D || c == 0x09 || c == 0x2028 || c == 0xA0 {
                if space { continue }
                c = 0x20; space = true
            } else { space = false }
            out.append(c); map.append(i)
        }
        return Normal(text: NSString(characters: out, length: out.count), map: map)
    }

    /// Words in a chapter's text: the whole of them, else from their first words to their last.
    static func find(_ words: String, in hay: Normal) -> NSRange? {
        let needle = normal(words).text.trimmingCharacters(in: .whitespaces) as NSString
        guard needle.length > 3, hay.text.length > 0 else { return nil }
        let opts: NSString.CompareOptions = [.caseInsensitive, .diacriticInsensitive]
        func back(_ r: NSRange) -> NSRange? {
            guard r.location != NSNotFound, r.length > 0, NSMaxRange(r) - 1 < hay.map.count else { return nil }
            let a = hay.map[r.location], b = hay.map[NSMaxRange(r) - 1] + 1
            return NSRange(location: a, length: b - a)
        }
        let whole = hay.text.range(of: needle as String, options: opts)
        if whole.location != NSNotFound { return back(whole) }
        let w = (needle as String).split(separator: " ")
        guard w.count >= 8 else { return nil }
        let head = w.prefix(7).joined(separator: " "), tail = w.suffix(7).joined(separator: " ")
        let h = hay.text.range(of: head, options: opts)
        guard h.location != NSNotFound else { return nil }
        let limit = min(hay.text.length, h.location + needle.length * 2 + 200)
        let t = hay.text.range(of: tail, options: opts, range: NSRange(location: h.location, length: limit - h.location))
        guard t.location != NSNotFound else { return back(NSRange(location: h.location, length: min(needle.length, hay.text.length - h.location))) }
        return back(NSRange(location: h.location, length: NSMaxRange(t) - h.location))
    }

    // MARK: Ask

    /// A question about the book, or a passage of it, with the pages I'm on as the context.
    func ask(_ q: String, quote: String? = nil) async {
        let q = q.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !asking else { return }
        asking = true
        defer { asking = false }
        sidebar = "ask"
        if !showContents { showContents = true }
        var body: [String: Any] = ["q": q]
        if let quote { body["quote"] = quote }
        if let p = pages, let t = text {
            let v = p.visible
            body["context"] = String((t.string.string as NSString).substring(with: NSRange(location: v.location, length: min(v.length, max(0, t.length - v.location)))).prefix(6000))
        }
        do {
            let r = J(try await API.shared.send("POST", "/api/ebooks/\(API.enc(id))/ask", body))
            var a: [String: Any] = ["q": q, "a": r?.s("a") ?? ""]
            if let quote { a["quote"] = quote }
            asks.append(J(a))
        } catch { self.error = error.localizedDescription }
    }
}

// MARK: a book read aloud

extension BookModel: Listenable {
    var listenKey: String { "book:" + id }
    var listenTitle: String { title }

    /// Where each paragraph of the chapter being read starts (not the empty ones or a picture alone).
    func paragraphs() -> [Int] {
        guard let t = render(listenSection) else { return [] }
        let s = t.string.string as NSString
        var out: [Int] = [], start = 0
        let letters = CharacterSet.letters.union(.decimalDigits)
        for i in 0...s.length {
            if i == s.length || s.character(at: i) == 0x0A {
                let r = NSRange(location: start, length: i - start)
                if r.length > 0, s.substring(with: r).rangeOfCharacter(from: letters) != nil { out.append(start) }
                start = i + 1
            }
        }
        return out
    }

    func paragraph(at place: Int?) -> Int? {
        listenSection = section
        let at = place ?? pages?.visible.location ?? 0
        let all = paragraphs()
        return all.last { $0 <= at } ?? all.first
    }

    func speech(_ p: Int) async -> Data? {
        guard let t = render(listenSection) else { return nil }
        let s = t.string.string as NSString
        guard p < s.length else { return nil }
        let end = s.range(of: "\n", range: NSRange(location: p, length: s.length - p)).location
        let words = s.substring(with: NSRange(location: p, length: (end == NSNotFound ? s.length : end) - p))
            .replacingOccurrences(of: "\u{2028}", with: " ").replacingOccurrences(of: "\u{FFFC}", with: "")
        return try? await API.shared.post("/api/tts/text", ["text": words])
    }

    func mark(_ p: Int?, follow: Bool) {
        guard let pages else { return }
        if let p, follow, section != listenSection { open(listenSection, at: p) }
        guard section == listenSection, let p else { pages.markSpeaking(nil); return }
        let s = pages.storage.string as NSString
        guard p < s.length else { return }
        let end = s.range(of: "\n", range: NSRange(location: p, length: s.length - p)).location
        let r = NSRange(location: p, length: (end == NSNotFound ? s.length : end) - p)
        pages.markSpeaking(r)
        let v = pages.visible                 // only when it's off these pages altogether: never back a page for its first lines
        if follow, p >= NSMaxRange(v) || NSMaxRange(r) <= v.location { pages.go(toChar: p, animated: true) }
    }

    func listened() { beat() }

    func advance() -> Bool {
        guard let epub, listenSection + 1 < epub.sections.count else { return false }
        listenSection += 1
        open(listenSection, at: 0)
        return true
    }
}

extension BookModel: HighlightHost {
    var shareTitle: String { title }
    var shareAuthor: String? { details?.s("author") }
    func paragraph(around loc: Int) -> String {
        guard let s = pages?.storage.string as NSString?, loc <= s.length else { return "" }
        let a = s.range(of: "\n", options: .backwards, range: NSRange(location: 0, length: loc)).location
        let start = a == NSNotFound ? 0 : a + 1
        let b = s.range(of: "\n", range: NSRange(location: loc, length: s.length - loc)).location
        return s.substring(with: NSRange(location: start, length: (b == NSNotFound ? s.length : b) - start))
    }
}
