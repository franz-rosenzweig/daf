import AppKit

/// How I like a book set: the typeface, its size, the line spacing, justified or not, the theme.
struct BookLook: Equatable {
    var font = "New York"
    var size: CGFloat = 19
    var spacing: CGFloat = 1.45
    var justify = false
    var theme = "auto"          // auto, original, paper, quiet, night

    static let fonts = ["New York", "San Francisco", "Charter", "Iowan Old Style", "Palatino", "Georgia", "Athelas", "Seravek", "Baskerville"]
    static let themes = [("auto", "Automatic"), ("original", "Original"), ("paper", "Paper"), ("quiet", "Quiet"), ("night", "Night")]

    static func load() -> BookLook {
        let d = UserDefaults.standard
        var l = BookLook()
        if let f = d.string(forKey: "book.font") { l.font = f }
        if let s = d.object(forKey: "book.size") as? NSNumber { l.size = CGFloat(s.doubleValue) }
        if let s = d.object(forKey: "book.spacing") as? NSNumber { l.spacing = CGFloat(s.doubleValue) }
        l.justify = d.bool(forKey: "book.justify")
        if let t = d.string(forKey: "book.theme") { l.theme = t }
        return l
    }

    func save() {
        let d = UserDefaults.standard
        d.set(font, forKey: "book.font"); d.set(Double(size), forKey: "book.size"); d.set(Double(spacing), forKey: "book.spacing")
        d.set(justify, forKey: "book.justify"); d.set(theme, forKey: "book.theme")
    }

    var dark: Bool {
        switch theme {
        case "quiet", "night": return true
        case "auto": return NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        default: return false
        }
    }
    var background: NSColor {
        switch theme {
        case "original": return .white
        case "paper": return NSColor(red: 0.973, green: 0.945, blue: 0.890, alpha: 1)
        case "quiet": return NSColor(red: 0.290, green: 0.290, blue: 0.302, alpha: 1)
        case "night": return NSColor(red: 0.071, green: 0.071, blue: 0.071, alpha: 1)
        default: return dark ? NSColor(red: 0.118, green: 0.118, blue: 0.122, alpha: 1) : .white
        }
    }
    var ink: NSColor {
        switch theme {
        case "paper": return NSColor(red: 0.31, green: 0.20, blue: 0.11, alpha: 1)
        case "quiet": return NSColor(red: 0.84, green: 0.84, blue: 0.85, alpha: 1)
        case "night": return NSColor(red: 0.80, green: 0.80, blue: 0.80, alpha: 1)
        case "original": return .black
        default: return dark ? NSColor(white: 0.86, alpha: 1) : .black
        }
    }
    var quiet: NSColor { ink.withAlphaComponent(0.6) }

    func font(bold: Bool = false, italic: Bool = false, mono: Bool = false, scale: CGFloat = 1) -> NSFont {
        let size = self.size * scale
        if mono { return NSFont.monospacedSystemFont(ofSize: size * 0.88, weight: bold ? .semibold : .regular) }
        var base: NSFont
        switch font {
        case "New York":
            let sys = NSFont.systemFont(ofSize: size)
            base = NSFont(descriptor: sys.fontDescriptor.withDesign(.serif) ?? sys.fontDescriptor, size: size) ?? sys
        case "San Francisco": base = NSFont.systemFont(ofSize: size)
        default: base = NSFont(descriptor: NSFontDescriptor(fontAttributes: [.family: font]), size: size) ?? NSFont.systemFont(ofSize: size)
        }
        var traits: NSFontDescriptor.SymbolicTraits = []
        if bold { traits.insert(.bold) }
        if italic { traits.insert(.italic) }
        guard !traits.isEmpty else { return base }
        if let f = NSFont(descriptor: base.fontDescriptor.withSymbolicTraits(traits), size: size) { return f }
        var f = base
        if bold { f = NSFontManager.shared.convert(f, toHaveTrait: .boldFontMask) }
        if italic { f = NSFontManager.shared.convert(f, toHaveTrait: .italicFontMask) }
        return f
    }
}

/// A book's stylesheets, as much of them as matters for text: italic, bold, centred, indented,
/// hidden, small capitals; for plain selectors (p, .x, p.x) only.
struct BookCSS {
    struct Props {
        var italic: Bool?, bold: Bool?, align: NSTextAlignment?, indent: CGFloat?, hidden: Bool?
        var smallCaps: Bool?, mono: Bool?, scale: CGFloat?, superscript: Int?, block: Bool?

        mutating func merge(_ o: Props) {
            italic = o.italic ?? italic; bold = o.bold ?? bold; align = o.align ?? align; indent = o.indent ?? indent
            hidden = o.hidden ?? hidden; smallCaps = o.smallCaps ?? smallCaps; mono = o.mono ?? mono; scale = o.scale ?? scale
            superscript = o.superscript ?? superscript; block = o.block ?? block
        }
    }
    private var tags: [String: Props] = [:]
    private var classes: [String: Props] = [:]
    private var tagClasses: [String: Props] = [:]

    mutating func add(_ css: String) {
        let text = css.replacingOccurrences(of: "/\\*[\\s\\S]*?\\*/", with: "", options: .regularExpression)
            .replacingOccurrences(of: "@media[^{]*\\{([^{}]*\\{[^{}]*\\})*[^{}]*\\}", with: "", options: .regularExpression)
        for rule in text.components(separatedBy: "}") {
            let p = rule.components(separatedBy: "{")
            guard p.count == 2 else { continue }
            let props = Self.props(p[1])
            for sel in p[0].split(separator: ",").map({ $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }) {
                guard !sel.isEmpty, sel.range(of: "[\\s>+~:\\[#*]", options: .regularExpression) == nil else { continue }
                let bits = sel.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
                let tag = bits[0], cls = bits.dropFirst()
                if cls.isEmpty { tags[tag, default: Props()].merge(props) }
                else if tag.isEmpty { for c in cls { classes[c, default: Props()].merge(props) } }
                else { for c in cls { tagClasses[tag + "." + c, default: Props()].merge(props) } }
            }
        }
    }

    func props(tag: String, classes cls: [String], style: String?) -> Props {
        var out = tags[tag] ?? Props()
        for c in cls { if let x = classes[c] { out.merge(x) } }
        for c in cls { if let x = tagClasses[tag + "." + c] { out.merge(x) } }
        if let style { out.merge(Self.props(style)) }
        return out
    }

    static func props(_ decls: String) -> Props {
        var p = Props()
        for d in decls.split(separator: ";") {
            let kv = d.split(separator: ":", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            guard kv.count == 2 else { continue }
            let v = kv[1].replacingOccurrences(of: "!important", with: "").trimmingCharacters(in: .whitespaces)
            switch kv[0] {
            case "font-style": p.italic = v.hasPrefix("italic") || v.hasPrefix("oblique")
            case "font-weight": p.bold = v.hasPrefix("bold") || (Int(v) ?? 400) >= 600
            case "text-align":
                p.align = ["center": .center, "right": .right, "left": .left, "justify": .justified, "start": .natural, "end": .right][v]
            case "text-indent": p.indent = length(v)
            case "display":
                if v == "none" { p.hidden = true } else { p.hidden = false; p.block = v != "inline" && v != "inline-block" }
            case "font-variant": p.smallCaps = v.contains("small-caps")
            case "font-family": if v.contains("monospace") || v.contains("courier") { p.mono = true }
            case "vertical-align": p.superscript = v == "super" ? 1 : v == "sub" ? -1 : 0
            case "font-size":
                if v.hasSuffix("em"), let n = Double(v.dropLast(2)) { p.scale = CGFloat(n) }
                else if v.hasSuffix("%"), let n = Double(v.dropLast()) { p.scale = CGFloat(n / 100) }
                else { p.scale = ["smaller": 0.85, "small": 0.85, "x-small": 0.75, "larger": 1.15, "large": 1.15, "x-large": 1.35, "xx-large": 1.6, "medium": 1][v] }
            default: break
            }
        }
        return p
    }

    /// A length as ems (0.5em, 1.2em, 20px, 0).
    private static func length(_ v: String) -> CGFloat? {
        if v == "0" { return 0 }
        if v.hasSuffix("em"), let n = Double(v.dropLast(2)) { return CGFloat(n) }
        if v.hasSuffix("px"), let n = Double(v.dropLast(2)) { return CGFloat(n / 16) }
        if v.hasSuffix("pt"), let n = Double(v.dropLast(2)) { return CGFloat(n / 12) }
        if v.hasSuffix("%"), let n = Double(v.dropLast()) { return CGFloat(n / 100 * 30) }
        return nil
    }
}

extension NSAttributedString.Key {
    /// A link inside the book: the path and fragment it goes to.
    static let dafBookLink = NSAttributedString.Key("dafBookLink")
}

/// One chapter as native text, with the way back from each character to its place in the chapter's
/// XHTML (the node and the offset in it) and from a place to its character: the two halves of a CFI.
final class SectionText {
    let index: Int
    let path: String
    let doc: XMLDocument
    let string = NSMutableAttributedString()
    /// Footnotes the chapter hides from the page: shown when their link is clicked.
    private(set) var notes: [String: NSAttributedString] = [:]

    struct Run {
        let node: XMLNode
        let order: Int
        let start: Int
        var raw: [Int32]          // for each character shown, its offset in the text node
    }
    private(set) var runs: [Run] = []
    private var order: [ObjectIdentifier: Int] = [:]
    private var runOf: [ObjectIdentifier: Int] = [:]
    private var startOf: [ObjectIdentifier: Int] = [:]
    private var endOf: [ObjectIdentifier: Int] = [:]
    private(set) var ids: [String: XMLElement] = [:]
    /// Pictures in the text, by their character, for a place that starts at one.
    private var pictures: [Int: XMLNode] = [:]

    var length: Int { string.length }

    // the walk's state
    private let look: BookLook
    private let css: BookCSS
    private let epub: EPUB
    private var spaced = true            // the last character shown is a space or a line's start
    private var lists: [(ordered: Bool, n: Int)] = []
    private var quote = 0
    private var fonts: [String: NSFont] = [:]

    init?(epub: EPUB, index: Int, look: BookLook) {
        guard index >= 0, index < epub.sections.count, let data = epub.data(epub.sections[index].path) else { return nil }
        let sec = epub.sections[index]
        self.index = index
        path = sec.path
        self.look = look
        self.epub = epub
        let text = Entities.numbered(String(decoding: data, as: UTF8.self))
        guard let d = (try? XMLDocument(data: Data(text.utf8), options: [.nodePreserveWhitespace]))
                ?? (try? XMLDocument(data: Data(text.utf8), options: [.documentTidyHTML, .nodePreserveWhitespace])) else { return nil }
        doc = d
        var sheet = BookCSS()
        if let root = d.rootElement() {
            for link in EPUB.all(root, "link") where (link.attribute(forName: "rel")?.stringValue ?? "").lowercased().contains("stylesheet") {
                if let href = link.attribute(forName: "href")?.stringValue, let c = epub.data(EPUB.resolve(href, from: sec.path)) { sheet.add(String(decoding: c, as: UTF8.self)) }
            }
            for st in EPUB.all(root, "style") { sheet.add(st.stringValue ?? "") }
        }
        css = sheet
        var n = 0
        func number(_ x: XMLNode) {
            order[ObjectIdentifier(x)] = n; n += 1
            if let e = x as? XMLElement, let id = CFI.elementID(e) { ids[id] = e }
            for c in x.children ?? [] { number(c) }
        }
        if let root = d.rootElement() { number(root) }
        if let body = d.rootElement().flatMap({ EPUB.kids($0, "body").first }) ?? d.rootElement() {
            walk(body, Style(look: look))
        }
        trimEnd()
        string.append(NSAttributedString(string: "\n", attributes: [.font: look.font()]))
    }

    // MARK: the walk

    struct Style {
        var bold = false, italic = false, mono = false, smallCaps = false
        var scale: CGFloat = 1
        var align: NSTextAlignment?
        var indent: CGFloat?
        var pre = false
        var link: String?
        var colour: NSColor?
        var superscript = 0
        var heading = 0
        var rtl: Bool?
        init(look: BookLook) {}
    }

    private static let blocks: Set<String> = ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "blockquote", "pre", "section",
                                              "article", "aside", "header", "footer", "nav", "figure", "figcaption", "table", "tr", "thead",
                                              "tbody", "tfoot", "dl", "dt", "dd", "address", "center", "main", "body", "caption", "hr", "hgroup"]
    private static let hidden: Set<String> = ["head", "script", "style", "title", "template", "noscript"]

    private func walk(_ node: XMLNode, _ outer: Style) {
        if node.kind == .text { text(node, outer); return }
        guard let e = node as? XMLElement else { return }
        let tag = (e.localName ?? e.name ?? "").lowercased()
        let start = string.length
        startOf[ObjectIdentifier(e)] = start
        defer { endOf[ObjectIdentifier(e)] = string.length }
        if Self.hidden.contains(tag) { return }
        let type = e.attributes?.first(where: { $0.localName == "type" && ($0.prefix == "epub" || $0.uri?.contains("ops") == true) })?.stringValue ?? ""
        if tag == "aside" || type.contains("footnote") || type.contains("endnote") || type.contains("rearnote") {
            if type.contains("footnote") || type.contains("endnote") || type.contains("rearnote"), let id = CFI.elementID(e) {
                notes[id] = NSAttributedString(string: (e.stringValue ?? "").split(whereSeparator: \.isWhitespace).joined(separator: " "),
                                               attributes: [.font: look.font(scale: 0.9), .foregroundColor: look.ink])
                return
            }
        }
        let cls = (e.attribute(forName: "class")?.stringValue ?? "").lowercased().split(separator: " ").map(String.init)
        let p = css.props(tag: tag, classes: cls, style: e.attribute(forName: "style")?.stringValue)
        if p.hidden == true { return }
        var s = outer
        switch tag {
        case "b", "strong": s.bold = true
        case "i", "em", "cite", "var", "dfn": s.italic = true
        case "code", "kbd", "samp", "tt": s.mono = true
        case "pre": s.mono = true; s.pre = true
        case "sup": s.superscript = 1; s.scale *= 0.75
        case "sub": s.superscript = -1; s.scale *= 0.75
        case "small": s.scale *= 0.85
        case "h1": s.heading = 1; s.bold = true; s.scale = 1.55
        case "h2": s.heading = 2; s.bold = true; s.scale = 1.35
        case "h3": s.heading = 3; s.bold = true; s.scale = 1.18
        case "h4", "h5", "h6": s.heading = 4; s.bold = true; s.scale = 1.05
        case "figcaption", "caption": s.scale *= 0.85; s.colour = look.quiet; s.align = .center
        case "center": s.align = .center
        case "a":
            if let href = e.attribute(forName: "href")?.stringValue {
                s.link = href.hasPrefix("#") ? path + href : (href.contains("://") ? href : EPUB.resolve(href, from: path) + (href.contains("#") ? "#" + href.split(separator: "#", maxSplits: 1)[1] : ""))
            }
        default: break
        }
        if let v = p.italic { s.italic = v }
        if let v = p.bold { s.bold = v }
        if let v = p.mono { s.mono = v }
        if let v = p.smallCaps { s.smallCaps = v }
        if let v = p.scale, s.heading == 0 { s.scale *= max(0.6, min(2, v)) }
        if let v = p.superscript, v != 0 { s.superscript = v }
        if let v = p.align { s.align = v }
        if let dir = e.attribute(forName: "dir")?.stringValue { s.rtl = dir == "rtl" }
        let block = p.block ?? Self.blocks.contains(tag)
        if block {
            s.indent = p.indent ?? (tag == "p" ? outer.indent : nil)
            newParagraph()
            startOf[ObjectIdentifier(e)] = string.length      // the block starts at its own first character
        }
        switch tag {
        case "br":
            append("\u{2028}", s)
            spaced = true
            return
        case "img", "image":
            let src = e.attribute(forName: "src")?.stringValue ?? e.attributes?.first(where: { $0.localName == "href" })?.stringValue
            if let src, let data = epub.data(EPUB.resolve(src, from: path)), let img = NSImage(data: data) { picture(img, e, s) }
            return
        case "hr":
            append("⁂", s, align: .center, colour: look.quiet)
            newParagraph()
            return
        case "ul", "ol":
            lists.append((tag == "ol", Int(e.attribute(forName: "start")?.stringValue ?? "") ?? 1))
        case "li":
            if var top = lists.popLast() {
                append(top.ordered ? "\(top.n).\t" : "•\t", s)
                top.n += 1
                lists.append(top)
                spaced = true
            }
        case "blockquote": quote += 1
        default: break
        }
        for c in e.children ?? [] { walk(c, s) }
        switch tag {
        case "ul", "ol": _ = lists.popLast()
        case "blockquote": quote -= 1
        case "td", "th": append("\t", s); spaced = true
        default: break
        }
        if block { newParagraph() }
    }

    private func text(_ node: XMLNode, _ s: Style) {
        let raw = (node.stringValue ?? "") as NSString
        guard raw.length > 0 else { return }
        var units: [unichar] = []
        var offsets: [Int32] = []
        units.reserveCapacity(raw.length)
        for k in 0..<raw.length {
            let c = raw.character(at: k)
            if !s.pre && (c == 0x20 || c == 0x09 || c == 0x0A || c == 0x0D || c == 0x0C) {
                if spaced { continue }
                units.append(0x20); offsets.append(Int32(k)); spaced = true
            } else {
                if s.pre && c == 0x0A { units.append(0x2028) } else { units.append(c) }
                offsets.append(Int32(k)); spaced = false
            }
        }
        guard !units.isEmpty else { return }
        let start = string.length
        var shown = NSString(characters: units, length: units.count) as String
        if s.smallCaps { shown = shown.uppercased(); if (shown as NSString).length != units.count { shown = NSString(characters: units, length: units.count) as String } }
        string.append(NSAttributedString(string: shown, attributes: attributes(s, smallCaps: s.smallCaps)))
        runOf[ObjectIdentifier(node)] = runs.count
        runs.append(Run(node: node, order: order[ObjectIdentifier(node)] ?? 0, start: start, raw: offsets))
    }

    private func attributes(_ s: Style, align: NSTextAlignment? = nil, colour: NSColor? = nil, smallCaps: Bool = false) -> [NSAttributedString.Key: Any] {
        var a: [NSAttributedString.Key: Any] = [:]
        let key = "\(s.bold)\(s.italic)\(s.mono)\(s.scale * (smallCaps ? 0.8 : 1))"
        if fonts[key] == nil { fonts[key] = look.font(bold: s.bold, italic: s.italic, mono: s.mono, scale: s.scale * (smallCaps ? 0.8 : 1)) }
        a[.font] = fonts[key]
        a[.foregroundColor] = colour ?? s.colour ?? look.ink
        if s.superscript != 0 { a[.baselineOffset] = look.size * 0.33 * CGFloat(s.superscript) }
        if let l = s.link {
            a[.dafBookLink] = l
            a[.link] = URL(string: l.contains("://") ? l : "dafbook:" + (l.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? l))
        }
        let p = NSMutableParagraphStyle()
        p.lineHeightMultiple = s.heading > 0 ? 1.15 : (s.pre ? 1.2 : look.spacing)
        let em = look.size
        // the book's centred and right-aligned lines stay; justified or not is mine to choose
        var alignment = align ?? s.align ?? .natural
        if s.heading == 0, alignment == .natural || alignment == .justified || alignment == .left { alignment = look.justify ? .justified : .natural }
        p.alignment = alignment
        if alignment == .justified { p.hyphenationFactor = 0.9 }     // as a printed book: hyphens, not stretched letters
        p.baseWritingDirection = s.rtl.map { $0 ? .rightToLeft : .leftToRight } ?? .natural
        if s.heading > 0 {
            p.paragraphSpacingBefore = em * 1.1
            p.paragraphSpacing = em * 0.55
        } else if let ind = s.indent, ind > 0, alignment != .center {
            p.firstLineHeadIndent = em * ind
            p.paragraphSpacing = em * 0.08
        } else {
            p.paragraphSpacing = em * 0.5
        }
        let side = CGFloat(quote) * em * 1.4 + (lists.isEmpty ? 0 : em * 1.5 * CGFloat(lists.count))
        if side > 0 {
            p.headIndent = side
            p.firstLineHeadIndent = lists.isEmpty ? side : side - em * 1.2
            if quote > 0 { p.tailIndent = -em * 1.4 * CGFloat(quote) }
            p.tabStops = [NSTextTab(textAlignment: .natural, location: side)]
            p.defaultTabInterval = em * 2
        }
        a[.paragraphStyle] = p
        return a
    }

    private func append(_ text: String, _ s: Style, align: NSTextAlignment? = nil, colour: NSColor? = nil) {
        string.append(NSAttributedString(string: text, attributes: attributes(s, align: align, colour: colour)))
    }

    private func picture(_ img: NSImage, _ e: XMLNode, _ s: Style) {
        newParagraph()
        let att = NSTextAttachment()
        att.image = img
        att.bounds = CGRect(origin: .zero, size: img.size)
        let a = NSMutableAttributedString(attachment: att)
        var st = s
        st.align = .center
        a.addAttributes(attributes(st), range: NSRange(location: 0, length: a.length))
        pictures[string.length] = e
        startOf[ObjectIdentifier(e)] = string.length
        string.append(a)
        spaced = false
        newParagraph()
    }

    /// The text so far ends its paragraph (once: blocks inside blocks don't leave empty lines).
    private func newParagraph() {
        trimEnd()
        if string.length > 0, !(string.string.hasSuffix("\n")) {
            let attrs = string.attributes(at: string.length - 1, effectiveRange: nil)
            string.append(NSAttributedString(string: "\n", attributes: attrs))
        }
        spaced = true
    }

    /// A space left at a paragraph's end goes.
    private func trimEnd() {
        guard string.length > 0, (string.string as NSString).character(at: string.length - 1) == 0x20 else { return }
        string.deleteCharacters(in: NSRange(location: string.length - 1, length: 1))
        if var last = runs.popLast() {
            if last.start + last.raw.count > string.length { last.raw.removeLast() }
            if !last.raw.isEmpty { runs.append(last) } else { runOf[ObjectIdentifier(last.node)] = nil }
        }
    }

    // MARK: places

    /// The character a place in the chapter is at (from a CFI's steps).
    func location(of f: CFI.Found) -> Int {
        let id = ObjectIdentifier(f.node)
        if f.before { return startOf[id] ?? 0 }
        if f.after { return endOf[id] ?? length }
        if f.node.kind == .text {
            if let r = runOf[id] {
                let run = runs[r], off = Int32(f.offset ?? 0)
                var lo = 0, hi = run.raw.count
                while lo < hi { let mid = (lo + hi) / 2; if run.raw[mid] < off { lo = mid + 1 } else { hi = mid } }
                return run.start + lo
            }
            let o = order[id] ?? 0              // whitespace shown as nothing: the next text shown
            return runs.first { $0.order > o }?.start ?? length
        }
        return startOf[id] ?? 0
    }

    /// The place a character is at, as a node and an offset; `end` for the end of a range.
    func place(at i: Int, end: Bool = false) -> (node: XMLNode, offset: Int?)? {
        if !end, let p = pictures[i] { return (p, nil) }
        var lo = 0, hi = runs.count
        while lo < hi { let mid = (lo + hi) / 2; if runs[mid].start <= i { lo = mid + 1 } else { hi = mid } }
        let k = lo - 1                         // the last run starting at or before i
        if k >= 0 {
            let r = runs[k]
            if i < r.start + r.raw.count { return (r.node, Int(r.raw[i - r.start])) }
            if end || k + 1 >= runs.count { return (r.node, Int(r.raw.last! + 1)) }
        }
        if !end, k + 1 < runs.count { return (runs[k + 1].node, Int(runs[k + 1].raw[0])) }
        return runs.first.map { ($0.node, Int($0.raw[0])) }
    }

    /// The CFI inside the chapter for a character, or for the range between two.
    func cfi(_ from: Int, _ to: Int? = nil) -> String? {
        guard let a = place(at: from) else { return nil }
        let pa = CFI.parts(of: a.node, offset: a.offset)
        guard let to, to > from, let b = place(at: to, end: true) else { return CFI.wrap(CFI.string([pa])) }
        return CFI.range([pa], [CFI.parts(of: b.node, offset: b.offset)])
    }

    /// Where a CFI's steps inside this chapter lead: a range of characters (a place is one long).
    func range(of parsed: CFI.Parsed) -> NSRange? {
        guard let root = doc.rootElement() else { return nil }
        let s = parsed.collapse(), e = parsed.collapse(toEnd: true)
        guard s.count > 1, let fs = CFI.find(s[1], in: root, ids: ids) else { return nil }
        let a = location(of: fs)
        guard case .range = parsed, e.count > 1, let fe = CFI.find(e[1], in: root, ids: ids) else { return NSRange(location: a, length: 0) }
        let b = location(of: fe)
        return NSRange(location: a, length: max(0, b - a))
    }

    /// Where an element with an id starts (a link's fragment, the contents).
    func location(ofID id: String) -> Int? { ids[id].map { startOf[ObjectIdentifier($0)] ?? 0 } }
}
