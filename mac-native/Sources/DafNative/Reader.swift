import AppKit
import Observation
import SwiftUI

/// An article from Daf, laid out as native text: its blocks one after another, its highlights
/// drawn in their colours, a selection highlighted with H or the menu, the place and the reading
/// time sent as the page sends them (/api/docs/{id}/progress, /api/read/beat every 15 s).
@MainActor
@Observable
final class ReaderModel {
    private(set) var id: String
    var doc: J?
    var highlights: [J] = []
    var error: String?
    var movedToLibrary = false
    @ObservationIgnored let storage = NSTextStorage()
    /// Each block's text in the storage, by its index in the doc's blocks.
    @ObservationIgnored private(set) var blocks: [(i: Int, range: NSRange)] = []
    @ObservationIgnored weak var textView: ReaderTextView?
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var sentPct = 0.0
    @ObservationIgnored private var sentAt = Date.distantPast
    @ObservationIgnored var restored = false
    /// A highlight to bring into view once laid out (Open at Its Spot).
    @ObservationIgnored var pendingReveal: String?
    /// For the self-test: what the reader has sent.
    @ObservationIgnored var beatsSent = 0
    @ObservationIgnored var placeSent: [Int] = []
    @ObservationIgnored var lastFraction = -1.0

    init(id: String) { self.id = id }

    var title: String { doc?.s("title") ?? "" }

    func load() async {
        do {
            let d = try await API.shared.json("/api/docs/\(API.enc(id))")
            doc = d
            highlights = d.a("highlights")
            sentPct = d.d("progress") ?? 0
            compose()
            startBeats()
        } catch { self.error = error.localizedDescription }
    }

    func stop() {
        beatTimer?.invalidate()
        beatTimer = nil
    }

    // MARK: laying it out

    static let column: CGFloat = 680
    static var serif: NSFont {
        let base = NSFont.systemFont(ofSize: 19)
        return NSFont(descriptor: base.fontDescriptor.withDesign(.serif) ?? base.fontDescriptor, size: 19) ?? base
    }

    private func para(_ spacing: CGFloat = 14, before: CGFloat = 0, indent: CGFloat = 0, first: CGFloat? = nil, align: NSTextAlignment = .natural, line: CGFloat = 1.38) -> NSParagraphStyle {
        let p = NSMutableParagraphStyle()
        p.lineHeightMultiple = line
        p.paragraphSpacing = spacing
        p.paragraphSpacingBefore = before
        p.headIndent = indent
        p.firstLineHeadIndent = first ?? indent
        p.alignment = align
        p.tabStops = [NSTextTab(textAlignment: .left, location: indent)]
        return p
    }

    func compose() {
        guard let d = doc else { return }
        let out = NSMutableAttributedString()
        let serif = Self.serif
        let ink = NSColor.textColor, quiet = NSColor.secondaryLabelColor
        let baseURL = URL(string: d.s("url") ?? API.shared.base.absoluteString) ?? API.shared.base

        func bold(_ f: NSFont, _ size: CGFloat) -> NSFont {
            NSFont(descriptor: f.fontDescriptor.withSymbolicTraits(.bold), size: size) ?? f
        }
        // the head: title, then where it's from
        out.append(NSAttributedString(string: d.s("title") ?? "Untitled", attributes: [.font: bold(serif, 30), .foregroundColor: ink, .paragraphStyle: para(8, line: 1.15)]))
        out.append(NSAttributedString(string: "\n"))
        let by = [d.s("source"), d.s("author"), d.i("mins").map { "\($0) min" }].compactMap { $0 }.joined(separator: " · ")
        out.append(NSAttributedString(string: by, attributes: [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: quiet, .paragraphStyle: para(26, line: 1.2)]))

        var map: [(Int, NSRange)] = []
        for (i, any) in d.list("blocks").enumerated() {
            guard let b = J(any) else { continue }
            let t = b.s("t") ?? "p"
            if t == "pg" { continue }
            out.append(NSAttributedString(string: "\n"))
            if t == "img" {
                if let src = b.s("src") { out.append(image(src, baseURL: baseURL)) }
                continue
            }
            let x = b.s("x") ?? ""
            if x.isEmpty { continue }
            var a: [NSAttributedString.Key: Any] = [.font: serif, .foregroundColor: ink, .paragraphStyle: para()]
            var prefix = ""
            switch t {
            case "h1", "h2": a[.font] = bold(serif, 25); a[.paragraphStyle] = para(10, before: 16, line: 1.2)
            case "h3", "h4", "h5", "h6": a[.font] = bold(serif, 21); a[.paragraphStyle] = para(8, before: 12, line: 1.2)
            case "li": prefix = "•\t"; a[.paragraphStyle] = para(8, indent: 24, first: 4)
            case "blockquote", "quote":
                a[.font] = NSFont(descriptor: serif.fontDescriptor.withSymbolicTraits(.italic), size: 19) ?? serif
                a[.foregroundColor] = quiet; a[.paragraphStyle] = para(14, indent: 28)
            case "figcaption", "caption": a[.font] = NSFont.systemFont(ofSize: 13); a[.foregroundColor] = quiet; a[.paragraphStyle] = para(20, line: 1.25)
            case "pre", "code": a[.font] = NSFont.monospacedSystemFont(ofSize: 14, weight: .regular); a[.paragraphStyle] = para(14, line: 1.25)
            default: break
            }
            if !prefix.isEmpty { out.append(NSAttributedString(string: prefix, attributes: a)) }
            let start = out.length
            out.append(InlineHTML.styled(b.s("h"), plain: x, base: a, baseURL: baseURL))
            map.append((i, NSRange(location: start, length: out.length - start)))
        }
        out.append(NSAttributedString(string: "\n\n"))
        storage.setAttributedString(out)
        blocks = map
        applyHighlights()
        restored = false
    }

    private func image(_ src: String, baseURL: URL) -> NSAttributedString {
        let att = NSTextAttachment()
        att.bounds = CGRect(x: 0, y: 0, width: 1, height: 1)
        let s = NSMutableAttributedString(attachment: att)
        s.addAttribute(.paragraphStyle, value: para(18, align: .center), range: NSRange(location: 0, length: s.length))
        let url = src.hasPrefix("/") ? API.shared.url(src) : (URL(string: src, relativeTo: baseURL)?.absoluteURL ?? API.shared.url(src))
        Task { [weak self] in
            guard let data = try? await API.shared.session.data(from: url).0, let img = NSImage(data: data), img.size.width > 0 else { return }
            let w = min(Self.column, img.size.width), h = img.size.height * w / img.size.width
            att.image = img
            att.bounds = CGRect(x: 0, y: 0, width: w, height: h)
            guard let self else { return }
            var at = NSRange(location: NSNotFound, length: 0)
            self.storage.enumerateAttribute(.attachment, in: NSRange(location: 0, length: self.storage.length)) { v, r, stop in
                if (v as? NSTextAttachment) === att { at = r; stop.pointee = true }
            }
            if at.location != NSNotFound { self.storage.edited(.editedAttributes, range: at, changeInLength: 0) }
        }
        return s
    }

    // MARK: highlights

    static func colour(_ name: String?) -> NSColor {
        switch name {
        case "green": return NSColor.systemGreen.withAlphaComponent(0.28)
        case "blue": return NSColor.systemBlue.withAlphaComponent(0.24)
        case "pink", "red": return NSColor.systemPink.withAlphaComponent(0.24)
        case "purple": return NSColor.systemPurple.withAlphaComponent(0.24)
        default: return NSColor.systemYellow.withAlphaComponent(0.38)
        }
    }

    private func range(of h: J) -> NSRange? {
        guard let pos = h.o("pos"), let b = pos.i("b"), let s = pos.i("s"), let e = pos.i("e") else { return nil }
        let be = pos.i("be") ?? b
        guard let r1 = blocks.first(where: { $0.i == b })?.range, let r2 = blocks.first(where: { $0.i == be })?.range else { return nil }
        let start = r1.location + min(max(s, 0), r1.length), end = r2.location + min(max(e, 0), r2.length)
        return end > start ? NSRange(location: start, length: end - start) : nil
    }

    func applyHighlights() {
        let all = NSRange(location: 0, length: storage.length)
        storage.beginEditing()
        storage.removeAttribute(.backgroundColor, range: all)
        storage.removeAttribute(.dafHighlight, range: all)
        for h in highlights {
            guard let r = range(of: h) else { continue }
            storage.addAttribute(.backgroundColor, value: Self.colour(h.s("color")), range: r)
            storage.addAttribute(.dafHighlight, value: h.s("id") ?? "", range: r)
        }
        storage.endEditing()
    }

    /// Where a character of the storage is, as Daf counts it: (block, offset in its text).
    private func position(_ loc: Int, end: Bool) -> (b: Int, o: Int)? {
        for (k, blk) in blocks.enumerated() {
            if loc < blk.range.location { return end ? (k > 0 ? (blocks[k - 1].i, blocks[k - 1].range.length) : nil) : (blk.i, 0) }
            if loc <= blk.range.location + blk.range.length { return (blk.i, loc - blk.range.location) }
        }
        return blocks.last.map { ($0.i, $0.range.length) }
    }

    /// The selection as Daf keeps a highlight, widened to whole words as the page does.
    func selectionPosition(_ sel: NSRange) -> (b: Int, s: Int, be: Int, e: Int, text: String)? {
        guard sel.length > 0, var a = position(sel.location, end: false), var z = position(sel.location + sel.length, end: true) else { return nil }
        guard let ra = blocks.first(where: { $0.i == a.b })?.range, let rz = blocks.first(where: { $0.i == z.b })?.range else { return nil }
        let ns = storage.string as NSString
        let t1 = ns.substring(with: ra) as NSString, t2 = ns.substring(with: rz) as NSString
        func isWord(_ s: NSString, _ i: Int) -> Bool {
            guard i >= 0, i < s.length, let u = Unicode.Scalar(s.character(at: i)) else { return false }
            return CharacterSet.alphanumerics.contains(u) || u == "'" || u == "’" || u == "-"
        }
        while a.o > 0 && isWord(t1, a.o - 1) && isWord(t1, a.o) { a.o -= 1 }
        while a.o < t1.length, let u = Unicode.Scalar(t1.character(at: a.o)), CharacterSet.whitespacesAndNewlines.contains(u) { a.o += 1 }
        while z.o < t2.length && isWord(t2, z.o - 1) && isWord(t2, z.o) { z.o += 1 }
        while z.o > 0, let u = Unicode.Scalar(t2.character(at: z.o - 1)), CharacterSet.whitespacesAndNewlines.contains(u) { z.o -= 1 }
        guard z.b > a.b || (z.b == a.b && z.o > a.o) else { return nil }
        let r = NSRange(location: ra.location + a.o, length: rz.location + z.o - ra.location - a.o)
        return (a.b, a.o, z.b, z.o, ns.substring(with: r))
    }

    func highlightSelection(color: String = "yellow") async {
        guard let tv = textView, let p = selectionPosition(tv.selectedRange()) else { return }
        do {
            var body: [String: Any] = ["b": p.b, "s": p.s, "e": p.e, "text": p.text, "color": color]
            body["be"] = p.be != p.b ? p.be : NSNull()
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/highlights", body))
            if let moved = r?.s("saved_as") { id = moved; movedToLibrary = true }   // a Feed item goes to the Library with its first highlight
            var pos: [String: Any] = ["b": p.b, "s": p.s, "e": p.e]
            if p.be != p.b { pos["be"] = p.be }
            highlights.append(J(["id": r?.s("id") ?? UUID().uuidString, "text": p.text, "pos": pos, "color": color]))
            applyHighlights()
            tv.setSelectedRange(NSRange(location: tv.selectedRange().location + tv.selectedRange().length, length: 0))
        } catch { self.error = error.localizedDescription }
    }

    func remove(highlight hid: String) async {
        do {
            try await API.shared.send("DELETE", "/api/highlights/\(API.enc(hid))", nil)
            highlights.removeAll { $0.s("id") == hid }
            applyHighlights()
        } catch { self.error = error.localizedDescription }
    }

    func reveal(highlight hid: String) {
        guard let h = highlights.first(where: { $0.s("id") == hid }), let r = range(of: h), let tv = textView else { return }
        tv.scrollRangeToVisible(r)
        tv.showFindIndicator(for: r)
    }

    // MARK: the place and the reading time

    func scrolled(_ fraction: Double) {
        lastActive = Date()
        lastFraction = fraction
        let pct = (fraction * 100).rounded()
        guard restored, pct > sentPct, Date().timeIntervalSince(sentAt) > 4 else { return }
        sentPct = pct
        sentAt = Date()
        placeSent.append(Int(pct))
        let id = self.id
        Task { try? await API.shared.send("PUT", "/api/docs/\(API.enc(id))/progress", ["pct": Int(pct)]) }
    }

    private func startBeats() {
        beatTimer?.invalidate()
        beatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.beatIfReading() }
        }
    }

    /// 15 seconds of reading, as the page counts it: the article in front, looked at in the last 90 s.
    func beatIfReading() {
        guard let w = textView?.window, w.occlusionState.contains(.visible), NSApp.isActive,
              Date().timeIntervalSince(lastActive) < 90 else { return }
        beat()
    }

    func beat() {
        beatsSent += 1
        let id = self.id
        Task { try? await API.shared.send("POST", "/api/read/beat", ["doc_id": id, "seconds": 15, "at": Int(Date().timeIntervalSince1970)]) }
    }
}

extension NSAttributedString.Key {
    static let dafHighlight = NSAttributedString.Key("dafHighlight")
}

/// The text view: selectable, not editable, a column in the middle, H to highlight.
final class ReaderTextView: NSTextView {
    weak var model: ReaderModel?

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        let side = max(28, (newSize.width - ReaderModel.column) / 2)
        if abs(textContainerInset.width - side) > 0.5 { textContainerInset = NSSize(width: side, height: 36) }
    }

    override func keyDown(with event: NSEvent) {
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        if event.charactersIgnoringModifiers == "h", event.modifierFlags.intersection([.command, .control, .option]).isEmpty, selectedRange().length > 0 {
            Task { @MainActor in await m?.highlightSelection() }
            return
        }
        super.keyDown(with: event)
    }

    override func mouseMoved(with event: NSEvent) {
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        super.mouseMoved(with: event)
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let menu = super.menu(for: event) ?? NSMenu()
        let at = characterIndexForInsertion(at: convert(event.locationInWindow, from: nil))
        var extra: [NSMenuItem] = []
        if selectedRange().length > 0 {
            extra.append(NSMenuItem(title: "Highlight", action: #selector(highlightNow), keyEquivalent: ""))
        }
        if at < textStorage?.length ?? 0, let hid = textStorage?.attribute(.dafHighlight, at: at, effectiveRange: nil) as? String, !hid.isEmpty {
            let item = NSMenuItem(title: "Remove Highlight", action: #selector(removeHighlight(_:)), keyEquivalent: "")
            item.representedObject = hid
            extra.append(item)
        }
        for (k, item) in extra.enumerated() { item.target = self; menu.insertItem(item, at: k) }
        if !extra.isEmpty { menu.insertItem(.separator(), at: extra.count) }
        return menu
    }

    @objc func highlightNow() { let m = model; Task { @MainActor in await m?.highlightSelection() } }
    @objc func removeHighlight(_ sender: NSMenuItem) {
        guard let hid = sender.representedObject as? String else { return }
        let m = model
        Task { @MainActor in await m?.remove(highlight: hid) }
    }
}

/// The scroll view tells the reader every time what's visible moves, by hand or by code.
final class ReaderScrollView: NSScrollView {
    var onScroll: (() -> Void)?
    override func reflectScrolledClipView(_ cView: NSClipView) {
        super.reflectScrolledClipView(cView)
        onScroll?()
    }
}

/// The reader in SwiftUI: the text view in its scroll view, the place restored once laid out.
struct ArticleReader: NSViewRepresentable {
    let model: ReaderModel

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSScrollView {
        let layout = NSLayoutManager()
        for old in model.storage.layoutManagers { model.storage.removeLayoutManager(old) }   // one view shows it at a time
        model.storage.addLayoutManager(layout)
        let container = NSTextContainer(size: NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude))
        container.widthTracksTextView = true
        layout.addTextContainer(container)
        let tv = ReaderTextView(frame: .zero, textContainer: container)
        tv.model = model
        tv.isEditable = false
        tv.isSelectable = true
        tv.isRichText = true
        tv.drawsBackground = true
        tv.backgroundColor = .textBackgroundColor
        tv.isVerticallyResizable = true
        tv.isHorizontallyResizable = false
        tv.autoresizingMask = [.width]
        tv.linkTextAttributes = [.foregroundColor: NSColor.controlAccentColor, .underlineStyle: NSUnderlineStyle.single.rawValue, .cursor: NSCursor.pointingHand]
        tv.usesFindBar = true
        tv.isIncrementalSearchingEnabled = true
        let scroll = ReaderScrollView()
        scroll.documentView = tv
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = true
        scroll.backgroundColor = .textBackgroundColor
        context.coordinator.watch(scroll, model)
        model.textView = tv
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let tv = scroll.documentView as? ReaderTextView else { return }
        if tv.model !== model {
            tv.model = model
            model.textView = tv
            if let lm = tv.layoutManager, lm.textStorage !== model.storage {
                lm.textStorage?.removeLayoutManager(lm)
                model.storage.addLayoutManager(lm)
            }
            context.coordinator.watch(scroll, model)
        }
        context.coordinator.restore(scroll, model)
    }

    static func dismantleNSView(_ scroll: NSScrollView, coordinator: Coordinator) {
        coordinator.stop()
    }

    @MainActor
    final class Coordinator {
        private weak var model: ReaderModel?

        func watch(_ scroll: NSScrollView, _ model: ReaderModel) {
            self.model = model
            (scroll as? ReaderScrollView)?.onScroll = { [weak scroll, weak model] in
                MainActor.assumeIsolated {
                    guard let scroll, let model, let doc = scroll.documentView else { return }
                    let h = doc.frame.height, seen = scroll.contentView.bounds.maxY
                    if h > 0 { model.scrolled(min(1, seen / h)) }
                }
            }
        }

        func restore(_ scroll: NSScrollView, _ model: ReaderModel) {
            guard !model.restored, model.doc != nil, model.storage.length > 0 else { return }
            DispatchQueue.main.async { [weak scroll] in
                MainActor.assumeIsolated {
                    guard let scroll, let tv = scroll.documentView as? NSTextView, !model.restored else { return }
                    tv.layoutManager?.ensureLayout(for: tv.textContainer!)
                    let p = model.doc?.d("progress") ?? 0
                    if let hid = model.pendingReveal {
                        model.pendingReveal = nil
                        model.restored = true
                        model.reveal(highlight: hid)
                        return
                    }
                    if p > 3 && p < 97 {
                        let h = tv.frame.height, y = max(0, h * p / 100 - scroll.contentView.bounds.height)
                        scroll.contentView.scroll(to: NSPoint(x: 0, y: y))
                        scroll.reflectScrolledClipView(scroll.contentView)
                    }
                    model.restored = true
                }
            }
        }

        func stop() {
            model?.stop()
        }
    }
}
