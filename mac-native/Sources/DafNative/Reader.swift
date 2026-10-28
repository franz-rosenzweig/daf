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
    /// My note on the article, and its tags.
    var note = ""
    var tags: [String] = []
    /// Ask: what's been asked about it, the questions Daf suggests, and an answer on its way.
    var asks: [J] = []
    var questions: [String] = []
    var asking = false
    /// A highlight whose note is being written.
    var editing: Editing?
    /// A highlight's tags, flashcards or share card, or a word looked up.
    var sheet: HLSheet?
    /// The paragraph j and k move to (a block's index), where h and n highlight with no selection.
    var focus: Int?
    struct Editing: Identifiable { let h: J; var id: String { h.s("id") ?? "" } }
    @ObservationIgnored private var noteTask: Task<Void, Never>?
    @ObservationIgnored private var noteDirty = false
    @ObservationIgnored let storage = NSTextStorage()
    /// Each block's text in the storage, by its index in the doc's blocks.
    @ObservationIgnored private(set) var blocks: [(i: Int, range: NSRange)] = []
    /// The pictures, each where it is in the text (one character), for picture highlights.
    @ObservationIgnored private(set) var pictures: [(i: Int, at: Int, src: String, alt: String)] = []
    /// Highlighted pictures, framed in their colour by the text view.
    @ObservationIgnored private(set) var pictureMarks: [(at: Int, color: NSColor)] = []
    @ObservationIgnored weak var textView: ReaderTextView?
    @ObservationIgnored var lastActive = Date()
    @ObservationIgnored private var beatTimer: Timer?
    @ObservationIgnored private var sentPct = 0.0
    @ObservationIgnored private var sentAt = Date.distantPast
    @ObservationIgnored private var placeLater: Task<Void, Never>?
    @ObservationIgnored var restored = false
    /// A highlight to bring into view once laid out (Open at Its Spot).
    @ObservationIgnored var pendingReveal: String?
    /// Opened from a search in the text: the words, found and shown.
    @ObservationIgnored var pendingFind: String?
    /// For the self-test: what the reader has sent.
    @ObservationIgnored var beatsSent = 0
    @ObservationIgnored var placeSent: [Int] = []
    @ObservationIgnored var lastFraction = -1.0

    init(id: String) {
        self.id = id
        // another theme: the article set again in its colours, where it is
        NotificationCenter.default.addObserver(forName: .dafTheme, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.textView?.backgroundColor = Theme.nsBG
                self.textView?.enclosingScrollView?.backgroundColor = Theme.nsBG
                if self.doc != nil { self.compose(keepPlace: true) }
            }
        }
    }

    var title: String { doc?.s("title") ?? "" }

    func load() async {
        do {
            let d = try await API.shared.json("/api/docs/\(API.enc(id))")
            doc = d
            highlights = d.a("highlights")
            note = d.s("note") ?? ""
            tags = d.strings("tags")
            asks = d.a("asks")
            questions = d.strings("questions")
            sentPct = d.d("progress") ?? 0
            if video == nil, let v = player(for: d) {
                v.onTick = { [weak self] t, playing in self?.syncCue(t, playing) }
                video = v
            }
            compose()
            startBeats()
        } catch { self.error = error.localizedDescription }
    }

    // MARK: a video's transcript

    /// The player, for a video (YouTube's, or a reel's own copy) or an episode, above the transcript.
    var video: VideoPlayer?
    /// A time to play an episode from (#read/<doc>/t:<sec>, a clip on the Podcasts page).
    @ObservationIgnored var podAt: Double?
    /// Whether it opens as a video or an episode, over its transcript.
    var playsMedia: Bool { doc?.s("kind") == "video" || doc?.o("episode") != nil }

    /// A reel's video once Daf has it, an episode's audio from where the last play anywhere
    /// stopped, or YouTube's player.
    private func player(for d: J) -> VideoPlayer? {
        if let e = d.o("episode"), let audio = e.s("audio") {
            let v = VideoPlayer(media: audio, kind: .episode)
            v.docID = id
            v.nowPlaying = (d.s("title") ?? "", e.s("podcast") ?? d.s("source") ?? "")
            let pos = e.o("position"), dur = e.d("duration") ?? 0
            if let t = podAt {
                v.startAt = t
                v.startPlaying = true
            } else if let t = pos?.d("t"), t > 15, dur == 0 || t < dur - 30 {
                v.startAt = t
                AppModel.shared.say("From " + VideoPlayer.clock(t) + ", where " + (pos?.s("from") ?? "AntennaPod") + " left off")
            }
            podAt = nil
            return v
        }
        if d.b("reel") { return d.s("media").map { VideoPlayer(media: $0, kind: .reel) } }
        if d.s("kind") == "video", let yt = VideoPlayer.id(d.s("url")) { return VideoPlayer(ytID: yt) }
        return nil
    }
    /// The transcript's cues: each block's place in the video.
    @ObservationIgnored private(set) var cues: [(i: Int, ts: Double)] = []
    @ObservationIgnored private var nowCue = -1

    /// The cue being said, marked, and kept in view while it plays (Follow Along).
    func syncCue(_ t: Double, _ playing: Bool) {
        if playing { lastActive = Date() }
        let i = cues.last { $0.ts <= t }?.i ?? -1
        guard i != nowCue else { return }
        nowCue = i
        let r = blocks.first { $0.i == i }?.range
        textView?.nowRange = r
        if let r, playing, video?.follow == true, let tv = textView, let scroll = tv.enclosingScrollView, let lm = tv.layoutManager, let tc = tv.textContainer {
            let box = lm.boundingRect(forGlyphRange: lm.glyphRange(forCharacterRange: r, actualCharacterRange: nil), in: tc).offsetBy(dx: 0, dy: tv.textContainerOrigin.y)
            let seen = scroll.contentView.bounds
            if box.minY < seen.minY + 10 || box.maxY > seen.maxY - 60 {
                scroll.contentView.animator().setBoundsOrigin(NSPoint(x: 0, y: max(0, box.minY - seen.height / 3)))
                scroll.reflectScrolledClipView(scroll.contentView)
            }
        }
    }

    /// Clip 30s: the cues of the last 30 seconds highlighted, each with its time.
    func clip(_ seconds: Double) async {
        guard let v = video else { return }
        let now = v.time
        let these = cues.filter { $0.ts >= now - seconds && $0.ts <= now }
        let episode = v.kind == .episode
        if these.isEmpty, episode, now > 3 { await clipOnServer(now, seconds); return }
        guard !these.isEmpty else { AppModel.shared.say(episode ? "Play it first; Clip takes the last 30 seconds." : "Play the video first; Clip takes the last 30 seconds."); return }
        let colour = HLTools.lastColour
        for c in these {
            guard let r = blocks.first(where: { $0.i == c.i })?.range else { continue }
            let text = (storage.string as NSString).substring(with: r).trimmingCharacters(in: .whitespacesAndNewlines)
            do {
                let res = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/highlights", ["b": c.i, "s": 0, "e": r.length, "text": text, "t": c.ts, "color": colour]))
                highlights.append(J(["id": res?.s("id") ?? UUID().uuidString, "text": text, "pos": ["b": c.i, "s": 0, "e": r.length], "color": colour]))
            } catch { self.error = error.localizedDescription; break }
        }
        applyHighlights()
        AppModel.shared.say("Clipped " + VideoPlayer.clock(these[0].ts) + "–" + VideoPlayer.clock(now))
    }

    /// Clip on an episode with no transcript yet: the server transcribes that stretch into a
    /// highlight (/api/podcasts/clip), looked for every 15 seconds for three minutes.
    private func clipOnServer(_ now: Double, _ seconds: Double) async {
        do {
            try await API.shared.send("POST", "/api/podcasts/clip", ["doc": id, "t": now, "sec": Int(seconds)])
        } catch { AppModel.shared.error = error.localizedDescription; return }
        AppModel.shared.say("Clipping " + VideoPlayer.clock(max(0, now - seconds)) + "–" + VideoPlayer.clock(now) + ". It's in the Notebook in a minute.")
        let had = highlights.count, doc = id
        Task { [weak self] in
            for _ in 0..<12 {
                try? await Task.sleep(nanoseconds: 15_000_000_000)
                guard let self, self.id == doc else { return }
                if let d = try? await API.shared.json("/api/docs/\(API.enc(doc))?prefetch=1"), d.a("highlights").count > had {
                    self.highlights = d.a("highlights")
                    self.applyHighlights()
                    return
                }
            }
        }
    }

    /// An episode met only in AntennaPod, into the Library: it becomes a doc of its own there (a
    /// new id), and the player plays on.
    func saveToLibrary() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/save", [:]))
            if let moved = r?.s("id"), moved != id { self.moved(to: moved) }
            AppModel.shared.say("Saved to the Library")
            await loadMeta()
        } catch { AppModel.shared.error = error.localizedDescription }
    }

    /// The doc has a new id (saved to the Library): what's sent from now on goes there.
    private func moved(to newID: String) {
        id = newID
        movedToLibrary = true
        if video?.docID != nil { video?.docID = newID }
    }

    /// Only the doc's own fields (the note, the tags), for a PDF or a video in the inspector.
    func loadMeta() async {
        guard let d = try? await API.shared.json("/api/docs/\(API.enc(id))") else { return }
        doc = d
        note = d.s("note") ?? ""
        tags = d.strings("tags")
        asks = d.a("asks")
        questions = d.strings("questions")
    }

    /// A question about the article, or about a passage of it (/api/docs/{id}/ask); the answer joins the others.
    func ask(_ q: String, quote: String? = nil) async {
        let q = q.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !asking else { return }
        asking = true
        defer { asking = false }
        var body: [String: Any] = ["q": q]
        if let quote { body["quote"] = quote }
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/ask", body))
            var a: [String: Any] = ["q": q, "a": r?.s("a") ?? "", "at": Int(Date().timeIntervalSince1970)]
            if let quote { a["quote"] = quote }
            asks.append(J(a))
        } catch { self.error = error.localizedDescription }
    }

    func stop() {
        beatTimer?.invalidate()
        beatTimer = nil
        if placeLater != nil { placeLater?.cancel(); placeLater = nil; sentAt = .distantPast; scrolled(lastFraction) }   // the place still waiting goes now
        video?.stop()
        noteTask?.cancel()
        noteTask = nil
        if noteDirty {                           // a note still being typed: kept now
            noteDirty = false
            let id = self.id, text = note
            Task { try? await API.shared.send("PUT", "/api/docs/\(API.enc(id))/note", ["note": text]) }
        }
    }

    // MARK: the note and the tags

    /// The note as it's typed: kept a moment after the last key (/api/docs/{id}/note).
    func write(note text: String) {
        note = text
        noteDirty = true
        noteTask?.cancel()
        let id = self.id
        noteTask = Task {
            try? await Task.sleep(nanoseconds: 700_000_000)
            guard !Task.isCancelled else { return }
            self.noteDirty = false
            try? await API.shared.send("PUT", "/api/docs/\(API.enc(id))/note", ["note": text])
        }
    }

    /// Writes the note now (the self-test, a window closing).
    func flushNote() async {
        noteTask?.cancel()
        noteTask = nil
        noteDirty = false
        try? await API.shared.send("PUT", "/api/docs/\(API.enc(id))/note", ["note": note])
    }

    /// The tags, as Daf cleans them; and every tag Daf knows, for suggestions.
    @discardableResult
    func set(tags new: [String]) async -> [String] {
        do {
            let r = J(try await API.shared.send("PUT", "/api/docs/\(API.enc(id))/tags", ["tags": new]))
            tags = r?.strings("tags") ?? new
            return r?.strings("all") ?? []
        } catch {
            self.error = error.localizedDescription
            return []
        }
    }

    func set(color: String, of hid: String) async {
        do {
            try await API.shared.send("PUT", "/api/highlights/\(API.enc(hid))/color", ["color": color])
            changed(hid) { $0["color"] = color }
        } catch { self.error = error.localizedDescription }
    }

    /// A highlight's fields after a change (its colour, its note), drawn again.
    func changed(_ hid: String, _ f: (inout [String: Any]) -> Void) {
        guard let k = highlights.firstIndex(where: { $0.s("id") == hid }) else { return }
        var raw = highlights[k].raw
        f(&raw)
        highlights[k] = J(raw)
        applyHighlights()
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

    /// The article set as text; `keepPlace` when it's set again where it's already open (a new title).
    func compose(keepPlace: Bool = false) {
        guard let d = doc else { return }
        let out = NSMutableAttributedString()
        let serif = Self.serif
        let ink = Theme.nsRead, quiet = Theme.nsQuiet
        let baseURL = URL(string: d.s("url") ?? API.shared.base.absoluteString) ?? API.shared.base

        func bold(_ f: NSFont, _ size: CGFloat) -> NSFont {
            NSFont(descriptor: f.fontDescriptor.withSymbolicTraits(.bold), size: size) ?? f
        }
        // the head: title, then where it's from
        out.append(NSAttributedString(string: d.s("title") ?? "Untitled", attributes: [.font: bold(serif, 30), .foregroundColor: ink, .paragraphStyle: para(8, line: 1.15)]))
        out.append(NSAttributedString(string: "\n"))
        let by = [d.s("source"), d.s("author"), d.s("kind") == "podcast" ? "episode" : d.i("mins").map { "\($0) min" }].compactMap { $0 }.joined(separator: " · ")
        out.append(NSAttributedString(string: by, attributes: [.font: NSFont.systemFont(ofSize: 13), .foregroundColor: quiet, .paragraphStyle: para(26, line: 1.2)]))

        var map: [(Int, NSRange)] = []
        var pics: [(i: Int, at: Int, src: String, alt: String)] = []
        var cueList: [(i: Int, ts: Double)] = []
        for (i, any) in d.list("blocks").enumerated() {
            guard let b = J(any) else { continue }
            let t = b.s("t") ?? "p"
            if t == "pg" { continue }
            out.append(NSAttributedString(string: "\n"))
            if t == "img" {
                if let src = b.s("src") {
                    pics.append((i, out.length, src, b.s("alt") ?? ""))
                    out.append(image(src, baseURL: baseURL))
                }
                continue
            }
            // a line of a video's transcript: its time (a click plays from there), then the words
            if t == "cue", let x = b.s("x"), !x.isEmpty {
                let ts = b.d("ts") ?? 0
                cueList.append((i, ts))
                out.append(NSAttributedString(string: VideoPlayer.clock(ts) + "  ", attributes: [.font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium),
                    .foregroundColor: Theme.nsAccent, .dafSeek: ts, .cursor: NSCursor.pointingHand, .paragraphStyle: para()]))
                if let spk = b.s("spk"), !spk.isEmpty { out.append(NSAttributedString(string: spk + ": ", attributes: [.font: bold(serif, serif.pointSize), .foregroundColor: quiet, .paragraphStyle: para()])) }
                let start = out.length
                out.append(InlineHTML.styled(b.s("h"), plain: x, base: [.font: serif, .foregroundColor: ink, .paragraphStyle: para()], baseURL: baseURL))
                map.append((i, NSRange(location: start, length: out.length - start)))
                continue
            }
            // a verse of Torah: the Hebrew, right to left, and the English, or one of them (Article › Torah)
            if t == "verse" {
                let lang = UserDefaults.standard.string(forKey: "torahLang") ?? "both"
                let n = b.s("n") ?? "", num: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium), .foregroundColor: quiet]
                if lang != "en", let he = b.s("he"), !he.isEmpty {
                    let p = para(lang == "he" ? 14 : 4, align: .right, line: 1.5).mutableCopy() as! NSMutableParagraphStyle
                    p.baseWritingDirection = .rightToLeft
                    let font = NSFont(name: "Taamey Frank CLM", size: 24) ?? NSFont(name: "New Peninim MT", size: 23) ?? NSFont(name: "Times New Roman", size: 23) ?? serif
                    let line = NSMutableAttributedString(string: n + "  ", attributes: num.merging([.paragraphStyle: p]) { a, _ in a })
                    line.append(NSAttributedString(string: he, attributes: [.font: font, .foregroundColor: ink, .paragraphStyle: p]))
                    out.append(line)
                    if lang == "both" { out.append(NSAttributedString(string: "\n")) }
                }
                if lang != "he", let x = b.s("x"), !x.isEmpty {
                    var a: [NSAttributedString.Key: Any] = [.font: serif, .foregroundColor: ink, .paragraphStyle: para(18)]
                    out.append(NSAttributedString(string: n + "  ", attributes: num.merging([.paragraphStyle: a[.paragraphStyle]!]) { a, _ in a }))
                    let start = out.length
                    a[.paragraphStyle] = para(18)
                    out.append(InlineHTML.styled(b.s("h"), plain: x, base: a, baseURL: baseURL))
                    map.append((i, NSRange(location: start, length: out.length - start)))
                }
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
        pictures = pics
        cues = cueList
        nowCue = -1
        applyHighlights()
        if !keepPlace { restored = false }
    }

    private func image(_ src: String, baseURL: URL) -> NSAttributedString {
        let att = NSTextAttachment()
        att.bounds = CGRect(x: 0, y: 0, width: 1, height: 1)
        let s = NSMutableAttributedString(attachment: att)
        s.addAttribute(.paragraphStyle, value: para(18, align: .center), range: NSRange(location: 0, length: s.length))
        let url = src.hasPrefix("/") ? API.shared.url(src) : (URL(string: src, relativeTo: baseURL)?.absoluteURL ?? API.shared.url(src))
        Task { [weak self] in
            guard let data = await API.shared.picture(url), let img = NSImage(data: data), img.size.width > 0 else { return }
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

    /// A highlight's colour, as the theme mixes it into its page.
    static func colour(_ name: String?) -> NSColor { Theme.highlight(name) }

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
        storage.removeAttribute(.toolTip, range: all)
        storage.removeAttribute(.underlineStyle, range: all)
        var marks: [(at: Int, color: NSColor)] = []
        for h in highlights {
            if let pic = HLPicture.of(h.s("text")) {
                // a picture: by its block, else by its address
                let b = h.o("pos")?.i("b")
                guard let p = pictures.first(where: { $0.i == b && $0.src == pic.src }) ?? pictures.first(where: { $0.src == pic.src }) else { continue }
                let r = NSRange(location: p.at, length: 1)
                storage.addAttribute(.dafHighlight, value: h.s("id") ?? "", range: r)
                if let n = h.s("user_note"), !n.isEmpty { storage.addAttribute(.toolTip, value: n, range: r) }
                marks.append((p.at, Self.colour(h.s("color")).withAlphaComponent(0.95)))
                continue
            }
            guard let r = range(of: h) else { continue }
            storage.addAttribute(.backgroundColor, value: Self.colour(h.s("color")), range: r)
            storage.addAttribute(.dafHighlight, value: h.s("id") ?? "", range: r)
            if let n = h.s("user_note"), !n.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {      // a note: dotted, and shown on hover
                storage.addAttributes([.toolTip: n, .underlineStyle: NSUnderlineStyle.single.rawValue | NSUnderlineStyle.patternDot.rawValue,
                                       .underlineColor: NSColor.secondaryLabelColor], range: r)
            }
        }
        storage.endEditing()
        pictureMarks = marks
        textView?.needsDisplay = true
    }

    /// The picture at a character, if there's one there.
    func picture(at loc: Int) -> (i: Int, at: Int, src: String, alt: String)? { pictures.first { $0.at == loc } }

    /// Highlight the Picture, as the page's: kept as ![alt](address), at its block.
    func highlightPicture(at loc: Int, thenNote: Bool = false) async {
        guard let p = picture(at: loc) else { return }
        if let hid = storage.attribute(.dafHighlight, at: loc, effectiveRange: nil) as? String, !hid.isEmpty, let h = highlight(withID: hid) {
            if thenNote { editing = .init(h: h) }
            return
        }
        let text = "![" + p.alt.replacingOccurrences(of: "[\\[\\]\n]+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespaces) + "](" + p.src + ")"
        let colour = HLTools.lastColour
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/highlights", ["b": p.i, "s": 0, "e": 0, "text": text, "img": p.src, "color": colour]))
            if let moved = r?.s("saved_as") { self.moved(to: moved) }
            let made: [String: Any] = ["id": r?.s("id") ?? UUID().uuidString, "text": text, "pos": ["b": p.i, "s": 0, "e": 0, "img": p.src], "color": colour]
            highlights.append(J(made))
            applyHighlights()
            if thenNote { editing = .init(h: J(made)) }
        } catch { self.error = error.localizedDescription }
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

    /// The selection (or a range: the focused paragraph) highlighted. Highlights it overlaps merge into
    /// it, their notes and tags carried (`replaces`), as the page does; a selection inside a highlight
    /// is that highlight. `thenNote` opens the note.
    func highlightSelection(color: String? = nil, range given: NSRange? = nil, thenNote: Bool = false) async {
        guard let tv = textView else { return }
        var sel = given ?? tv.selectedRange()
        guard sel.length > 0 else { return }
        let over = highlights.compactMap { h -> (J, NSRange)? in
            guard let r = range(of: h), NSIntersectionRange(r, sel).length > 0 else { return nil }
            return (h, r)
        }
        if let inside = over.first(where: { $0.1.location <= sel.location && NSMaxRange(sel) <= NSMaxRange($0.1) }) {
            if thenNote { editing = .init(h: inside.0) }
            tv.setSelectedRange(NSRange(location: NSMaxRange(sel), length: 0))
            return
        }
        for (_, r) in over { sel = NSUnionRange(sel, r) }
        guard let p = selectionPosition(sel) else { return }
        let colour = color ?? over.first?.0.s("color") ?? HLTools.lastColour
        do {
            var body: [String: Any] = ["b": p.b, "s": p.s, "e": p.e, "text": p.text, "color": colour]
            if let ts = cues.first(where: { $0.i == p.b })?.ts { body["t"] = ts }
            body["be"] = p.be != p.b ? p.be : NSNull()
            if !over.isEmpty { body["replaces"] = over.compactMap { $0.0.s("id") } }
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/highlights", body))
            if let moved = r?.s("saved_as") { self.moved(to: moved) }   // a Feed item goes to the Library with its first highlight
            var pos: [String: Any] = ["b": p.b, "s": p.s, "e": p.e]
            if p.be != p.b { pos["be"] = p.be }
            let gone = Set(over.compactMap { $0.0.s("id") })
            let notes = over.compactMap { $0.0.s("user_note") }
            highlights.removeAll { gone.contains($0.s("id") ?? "") }
            var made: [String: Any] = ["id": r?.s("id") ?? UUID().uuidString, "text": p.text, "pos": pos, "color": colour]
            if !notes.isEmpty { made["user_note"] = notes.joined(separator: "\n\n") }
            highlights.append(J(made))
            applyHighlights()
            tv.setSelectedRange(NSRange(location: NSMaxRange(sel), length: 0))
            if thenNote { editing = .init(h: J(made)) }
        } catch { self.error = error.localizedDescription }
    }

    /// Remove, with Undo bringing it back (/api/highlights/{id}/restore).
    func remove(highlight hid: String) async {
        do {
            try await API.shared.send("DELETE", "/api/highlights/\(API.enc(hid))", nil)
            highlights.removeAll { $0.s("id") == hid }
            applyHighlights()
            let doc = id
            AppModel.shared.say("Highlight removed", undo: "Remove Highlight") { [weak self] in
                _ = try? await API.shared.send("POST", "/api/highlights/\(API.enc(hid))/restore", [:])
                if let self, let d = try? await API.shared.json("/api/docs/\(API.enc(doc))") { self.highlights = d.a("highlights"); self.applyHighlights() }
            }
        } catch { self.error = error.localizedDescription }
    }

    // MARK: the article's own tools

    /// Reset reading progress (/api/docs/{id}/progress), as the page's R.
    func resetProgress() async {
        do {
            try await API.shared.send("DELETE", "/api/docs/\(API.enc(id))/progress", nil)
            sentPct = 0
            AppModel.shared.say("Reading progress reset")
        } catch { self.error = error.localizedDescription }
    }

    /// The whole article from its page, for a feed that sends only a summary (/api/docs/{id}/full).
    func loadFull() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/full", [:]))
            AppModel.shared.say("The full article: " + plural(r?.i("words") ?? 0, "word"))
            await load()
        } catch { self.error = error.localizedDescription }
    }

    /// Summarize it now (/api/docs/{id}/summary): the Feed's aren't summarized ahead of time.
    func summarize() async {
        do {
            let r = J(try await API.shared.send("POST", "/api/docs/\(API.enc(id))/summary", [:]))
            if var raw = doc?.raw { raw["ai_summary"] = r?.s("ai_summary"); doc = J(raw) }
        } catch { self.error = error.localizedDescription }
    }

    /// Edit the title and author (/api/docs/{id}/meta).
    func editMeta(title: String, author: String) async -> Bool {
        do {
            let r = J(try await API.shared.send("PUT", "/api/docs/\(API.enc(id))/meta", ["title": title, "author": author]))
            if var raw = doc?.raw { raw["title"] = r?.s("title"); raw["author"] = r?.s("author"); doc = J(raw); compose(keepPlace: true) }
            AppModel.shared.reload()
            return true
        } catch { self.error = error.localizedDescription; return false }
    }

    /// Open the article's note in Obsidian, where the first highlight wrote it.
    func openInObsidian() {
        guard let p = doc?.s("vault_path") else { return }
        let f = p.hasSuffix(".md") ? String(p.dropLast(3)) : p
        if let u = URL(string: "obsidian://open?vault=" + API.enc(doc?.s("vault_name") ?? "vault") + "&file=" + API.enc(f)) { NSWorkspace.shared.open(u) }
    }

    // MARK: the focused paragraph (j, k)

    func moveFocus(_ d: Int) {
        guard !blocks.isEmpty, let tv = textView else { return }
        let cur = focus.flatMap { f in blocks.firstIndex { $0.i == f } } ?? (d > 0 ? -1 : blocks.count)
        let next = max(0, min(blocks.count - 1, cur + d))
        focus = blocks[next].i
        tv.focusRange = blocks[next].range
        tv.scrollRangeToVisible(blocks[next].range)
        lastActive = Date()
    }

    /// h or n with nothing selected: the focused paragraph.
    func highlightFocus(thenNote: Bool) async {
        guard let f = focus, let r = blocks.first(where: { $0.i == f })?.range else { return }
        await highlightSelection(range: r, thenNote: thenNote)
    }

    // MARK: read aloud

    /// The paragraph read aloud, marked (around the highlights in it) and, while playing, kept in view.
    func markSpeaking(_ b: Int?, follow: Bool = false) {
        guard let tv = textView, let lm = tv.layoutManager else { return }
        lm.removeTemporaryAttribute(.backgroundColor, forCharacterRange: NSRange(location: 0, length: storage.length))
        guard let b, let r = blocks.first(where: { $0.i == b })?.range else { return }
        storage.enumerateAttribute(.dafHighlight, in: r) { v, sub, _ in
            if (v as? String)?.isEmpty ?? true { lm.addTemporaryAttribute(.backgroundColor, value: Theme.nsAccent.withAlphaComponent(0.13), forCharacterRange: sub) }
        }
        guard follow, let container = tv.textContainer else { return }
        let glyphs = lm.glyphRange(forCharacterRange: r, actualCharacterRange: nil)
        var rect = lm.boundingRect(forGlyphRange: glyphs, in: container)
        rect.origin.y += tv.textContainerOrigin.y
        let seen = tv.visibleRect
        if rect.minY < seen.minY + 60 || rect.maxY > seen.maxY - 110 {
            tv.scroll(NSPoint(x: 0, y: max(0, rect.minY - seen.height / 3)))
        }
    }

    /// The first paragraph at the top of the window, where reading aloud starts.
    func firstVisibleBlock() -> Int? {
        guard let tv = textView, let lm = tv.layoutManager, let container = tv.textContainer else { return nil }
        let top = NSPoint(x: tv.visibleRect.midX - tv.textContainerOrigin.x, y: tv.visibleRect.minY + 30 - tv.textContainerOrigin.y)
        let at = lm.characterIndex(for: top, in: container, fractionOfDistanceBetweenInsertionPoints: nil)
        return block(at: at)
    }

    /// p: listen, or pause; from the top of the window when it isn't this article that's being read.
    func listen() {
        let s = Speaker.shared
        if s.docID == id { s.toggle() } else { s.start(self) }
    }

    /// L, or Read Aloud from Here: from the paragraph a character is in.
    func listen(from loc: Int) { Speaker.shared.start(self, at: loc) }

    /// The block a character of the storage is in, or the next one.
    func block(at loc: Int) -> Int? {
        blocks.first { loc < $0.range.location + $0.range.length }?.i
    }

    /// The first place the longest of the words is, as the page's findInDoc.
    func reveal(words q: String) {
        guard let tv = textView, let w = q.split(separator: " ").map(String.init).max(by: { $0.count < $1.count }) else { return }
        let r = (storage.string as NSString).range(of: w, options: [.caseInsensitive, .diacriticInsensitive])
        guard r.location != NSNotFound else { return }
        foundRange = r
        tv.scrollRangeToVisible(r)
        tv.showFindIndicator(for: r)
    }
    @ObservationIgnored var foundRange: NSRange?

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
        guard restored, pct > sentPct else { return }
        // at most every four seconds; the last of a run of scrolls goes once they're up
        let wait = 4 - Date().timeIntervalSince(sentAt)
        if wait > 0 {
            placeLater?.cancel()
            placeLater = Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: UInt64((wait + 0.05) * 1_000_000_000))
                guard !Task.isCancelled, let self else { return }
                self.scrolled(self.lastFraction)
            }
            return
        }
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
        if Speaker.shared.playing && Speaker.shared.docID == id { return }      // the listening counts it already
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
    /// A transcript's timestamp: the second it plays from.
    static let dafSeek = NSAttributedString.Key("dafSeek")
}

extension ReaderModel: HighlightHost {
    func highlight(withID hid: String) -> J? { highlights.first { $0.s("id") == hid } }
    var shareTitle: String { title }
    var shareAuthor: String? { doc?.s("author") ?? doc?.s("source") }
    func paragraph(around loc: Int) -> String {
        guard let r = blocks.first(where: { loc >= $0.range.location && loc <= NSMaxRange($0.range) })?.range else { return "" }
        return (storage.string as NSString).substring(with: r)
    }
}

/// The text view: selectable, not editable, a column in the middle, the page's reading keys.
final class ReaderTextView: NSTextView {
    weak var model: ReaderModel?
    /// The focused paragraph (j, k), marked with a bar in the margin.
    var focusRange: NSRange? { didSet { needsDisplay = true } }
    /// The line of a video's transcript being said, tinted.
    var nowRange: NSRange? { didSet { needsDisplay = true } }

    override func drawBackground(in rect: NSRect) {
        super.drawBackground(in: rect)
        if let lm = layoutManager, let tc = textContainer, let marks = MainActor.assumeIsolated({ model?.pictureMarks }) {
            for mark in marks where mark.at < (textStorage?.length ?? 0) {
                var box = lm.boundingRect(forGlyphRange: lm.glyphRange(forCharacterRange: NSRange(location: mark.at, length: 1), actualCharacterRange: nil), in: tc)
                box.origin.x += textContainerOrigin.x
                box.origin.y += textContainerOrigin.y
                mark.color.setStroke()
                let frame = NSBezierPath(roundedRect: box.insetBy(dx: -5, dy: -5), xRadius: 6, yRadius: 6)
                frame.lineWidth = 4
                frame.stroke()
            }
        }
        if let r = nowRange, let lm = layoutManager, let tc = textContainer, NSMaxRange(r) <= (textStorage?.length ?? 0) {
            var box = lm.boundingRect(forGlyphRange: lm.glyphRange(forCharacterRange: r, actualCharacterRange: nil), in: tc)
            box.origin.x += textContainerOrigin.x
            box.origin.y += textContainerOrigin.y
            Theme.nsAccent.withAlphaComponent(0.1).setFill()
            NSBezierPath(roundedRect: box.insetBy(dx: -8, dy: -3), xRadius: 6, yRadius: 6).fill()
        }
        guard let r = focusRange, let lm = layoutManager, let tc = textContainer, NSMaxRange(r) <= (textStorage?.length ?? 0) else { return }
        var box = lm.boundingRect(forGlyphRange: lm.glyphRange(forCharacterRange: r, actualCharacterRange: nil), in: tc)
        box.origin.x += textContainerOrigin.x
        box.origin.y += textContainerOrigin.y
        Theme.nsAccent.withAlphaComponent(0.7).setFill()
        NSBezierPath(roundedRect: NSRect(x: box.minX - 16, y: box.minY + 2, width: 3, height: max(8, box.height - 4)), xRadius: 1.5, yRadius: 1.5).fill()
    }

    /// Highlight on selecting (a selection of words, unless ⌥ is held), as the page does.
    override func mouseDown(with event: NSEvent) {
        let at = characterIndexForInsertion(at: convert(event.locationInWindow, from: nil))
        if at < (textStorage?.length ?? 0), let ts = textStorage?.attribute(.dafSeek, at: at, effectiveRange: nil) as? Double {
            let m = model
            MainActor.assumeIsolated { m?.video?.seek(ts) }
            return
        }
        super.mouseDown(with: event)
        let sel = selectedRange()
        guard HLTools.autoHighlight, sel.length > 1, !NSEvent.modifierFlags.contains(.option), event.clickCount == 1,
              (string as NSString).substring(with: sel).trimmingCharacters(in: .whitespacesAndNewlines).contains(" ") else { return }
        let m = model
        Task { @MainActor in await m?.highlightSelection() }
    }

    override func setFrameSize(_ newSize: NSSize) {
        let wider = abs(newSize.width - frame.width) > 0.5
        super.setFrameSize(newSize)
        let side = max(28, (newSize.width - ReaderModel.column) / 2)
        if abs(textContainerInset.width - side) > 0.5 { textContainerInset = NSSize(width: side, height: 36) }
        if wider { fitSoon() }
    }

    /// Its height from its text, laid out. The text is set straight into the storage (compose),
    /// and on macOS 27 the view stopped growing to it by itself: an article stayed one screen tall
    /// and sprang back when scrolled. So whenever the text, a picture or the width changes, it's
    /// measured and the view made that tall.
    private var fitting = false
    func fitSoon() {
        guard !fitting else { return }
        fitting = true
        DispatchQueue.main.async { [weak self] in MainActor.assumeIsolated { self?.fitting = false; self?.fit() } }
    }
    func fit() {
        guard let lm = layoutManager, let tc = textContainer else { return }
        lm.ensureLayout(for: tc)
        let used = ceil(lm.usedRect(for: tc).height + textContainerInset.height * 2)
        let want = max(used, enclosingScrollView?.contentSize.height ?? 0)
        if abs(frame.height - want) > 0.5 { setFrameSize(NSSize(width: frame.width, height: want)) }
    }

    override func keyDown(with event: NSEvent) {
        let m = model
        MainActor.assumeIsolated { m?.lastActive = Date() }
        let plain = event.modifierFlags.intersection([.command, .control, .option]).isEmpty
        // an episode: ← back 15 seconds, → ahead 30
        if plain, [123, 124].contains(event.keyCode), MainActor.assumeIsolated({ () -> Bool in
            guard let v = m?.video, v.kind == .episode else { return false }
            v.skip(event.keyCode == 123 ? -15 : 30)
            return true
        }) { return }
        guard plain, let ch = event.characters, MainActor.assumeIsolated({ articleKey(ch) }) else { return super.keyDown(with: event) }
    }

    /// The page's article keys (keys.js, scope article).
    @MainActor
    private func articleKey(_ ch: String) -> Bool {
        let m = model, app = AppModel.shared, sel = selectedRange()
        let item = app.selected
        switch ch {
        case "h", "n":
            let note = ch == "n"
            if sel.length == 1, m?.picture(at: sel.location) != nil { Task { await m?.highlightPicture(at: sel.location, thenNote: note) } }
            else { Task { if sel.length > 0 { await m?.highlightSelection(thenNote: note) } else { await m?.highlightFocus(thenNote: note) } } }
        case "j": m?.moveFocus(1)
        case "k": m?.moveFocus(-1)
        case "p": if let v = m?.video { v.toggle() } else { m?.listen() }  // play or pause; listen or pause
        case "L": m?.listen(from: sel.location)                             // read aloud from here
        case "e": if let item { Task { await app.done(item) } }
        case "l": if let item, item.whereIn != "feed" { Task { await app.later(item) } }
        case "s": if let item, item.whereIn == "feed" { Task { await app.saveToLibrary(item) } }
        case "f": if let item, item.whereIn != "feed" { Task { await app.star(item) } }
        case "t": app.showInspector = true; app.focusTags += 1
        case "N": app.showInspector = true; app.focusNote += 1
        case "d": if let item { Task { await app.delete(item) } }
        case "z": app.undoLast()
        case "o": if let u = m?.doc?.s("url").flatMap(URL.init(string:)) { NSWorkspace.shared.open(u) }
        case "J": app.step(1)
        case "K": app.step(-1)
        case "C": if let u = m?.doc?.s("url") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(u, forType: .string); app.say("Link copied") }
        case "R": Task { await m?.resetProgress() }
        case "c": if m?.video != nil { Task { await m?.clip(30) } } else { return false }
        case "M": app.editMeta = true
        case "F": Focus.shared.toggle(window)                               // focus mode (Focus.swift)
        default: return false
        }
        return true
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
        let sel = selectedRange()
        // a picture: Highlight the Picture, unless it is already
        let picAt = [at, max(0, at - 1)].first { i in MainActor.assumeIsolated { model?.picture(at: i) != nil } }
        if let p = picAt, (textStorage?.attribute(.dafHighlight, at: p, effectiveRange: nil) as? String ?? "").isEmpty {
            extra.append(MenuAction.item("Highlight the Picture") { let m = self.model; Task { @MainActor in await m?.highlightPicture(at: p) } })
            extra.append(MenuAction.item("Highlight It with a Note") { let m = self.model; Task { @MainActor in await m?.highlightPicture(at: p, thenNote: true) } })
        } else if let p = picAt, let hid = textStorage?.attribute(.dafHighlight, at: p, effectiveRange: nil) as? String, let m = model, at != p {
            extra += MainActor.assumeIsolated { HLMenu.items(for: hid, host: m) }
        }
        if sel.length > 0 {
            extra.append(NSMenuItem(title: "Highlight", action: #selector(highlightNow), keyEquivalent: ""))
            extra.append(MenuAction.item("Highlight with a Note") { let m = self.model; Task { @MainActor in await m?.highlightSelection(thenNote: true) } })
        }
        if at < textStorage?.length ?? 0, let hid = textStorage?.attribute(.dafHighlight, at: at, effectiveRange: nil) as? String, !hid.isEmpty, let m = model {
            extra += MainActor.assumeIsolated { HLMenu.items(for: hid, host: m) }
        }
        if sel.length > 0 {
            extra.append(NSMenuItem(title: "Ask About This Passage", action: #selector(askAboutSelection), keyEquivalent: ""))
            if let m = model, let look = MainActor.assumeIsolated({ HLMenu.lookup((string as NSString).substring(with: sel), at: sel.location, host: m) }) { extra.append(look) }
        }
        let aloud = NSMenuItem(title: "Read Aloud from Here", action: #selector(readFromHere(_:)), keyEquivalent: "")
        aloud.representedObject = at
        extra.append(aloud)
        for (k, item) in extra.enumerated() { if item.target == nil { item.target = self }; menu.insertItem(item, at: k) }
        if !extra.isEmpty { menu.insertItem(.separator(), at: extra.count) }
        return menu
    }

    @objc func highlightNow() { let m = model; Task { @MainActor in await m?.highlightSelection() } }
    @objc func editNote(_ sender: NSMenuItem) {
        guard let hid = sender.representedObject as? String else { return }
        MainActor.assumeIsolated { if let m = model, let h = m.highlights.first(where: { $0.s("id") == hid }) { m.editing = .init(h: h) } }
    }
    @objc func recolor(_ sender: NSMenuItem) {
        guard let v = sender.representedObject as? [String], v.count == 2 else { return }
        let m = model
        Task { @MainActor in await m?.set(color: v[1], of: v[0]) }
    }
    @objc func askAboutSelection() {
        let quote = (string as NSString).substring(with: selectedRange()).trimmingCharacters(in: .whitespacesAndNewlines)
        let m = model
        MainActor.assumeIsolated { AppModel.shared.showInspector = true }
        Task { @MainActor in await m?.ask("What does this passage mean here?", quote: quote) }
    }
    @objc func readFromHere(_ sender: NSMenuItem) {
        guard let at = sender.representedObject as? Int else { return }
        MainActor.assumeIsolated { model?.listen(from: at) }
    }
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
        tv.backgroundColor = Theme.nsBG
        tv.isVerticallyResizable = true
        tv.isHorizontallyResizable = false
        tv.autoresizingMask = [.width]
        tv.linkTextAttributes = [.foregroundColor: Theme.nsAccent, .underlineStyle: NSUnderlineStyle.single.rawValue, .cursor: NSCursor.pointingHand]
        tv.usesFindBar = true
        tv.isIncrementalSearchingEnabled = true
        let scroll = ReaderScrollView()
        scroll.documentView = tv
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = true
        scroll.backgroundColor = Theme.nsBG
        context.coordinator.watch(scroll, model)
        model.textView = tv
        Speaker.shared.attach(model)
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
        private var edits: NSObjectProtocol?

        func watch(_ scroll: NSScrollView, _ model: ReaderModel) {
            self.model = model
            if let e = edits { NotificationCenter.default.removeObserver(e) }
            edits = NotificationCenter.default.addObserver(forName: NSTextStorage.didProcessEditingNotification, object: model.storage, queue: .main) { [weak scroll] _ in
                MainActor.assumeIsolated { (scroll?.documentView as? ReaderTextView)?.fitSoon() }
            }
            (scroll.documentView as? ReaderTextView)?.fitSoon()
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
                    if let q = model.pendingFind {
                        model.pendingFind = nil
                        model.restored = true
                        model.reveal(words: q)
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
            if let e = edits { NotificationCenter.default.removeObserver(e); edits = nil }
            model?.stop()
        }
    }
}
