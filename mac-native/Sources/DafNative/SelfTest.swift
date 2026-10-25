import AppKit
import SwiftUI
import WebKit
import PDFKit

/// The app testing itself against a sandbox Daf, never the real one:
///   DafNative -SelfTestBase http://… -SelfTestCookie c:<cookie> -SelfTestOut <dir>
/// Each check is a PASS or FAIL line in <dir>/log.txt, with a picture of the window at each step;
/// it ends with "SELFTEST passed" or "SELFTEST n failed" and quits.
@MainActor
enum SelfTest {
    private static var out: URL!
    private static var lines: [String] = []
    private static var failures = 0

    static func startIfAsked() {
        let d = UserDefaults.standard
        guard let base = d.string(forKey: "SelfTestBase"), let cookie = d.string(forKey: "SelfTestCookie"), let dir = d.string(forKey: "SelfTestOut") else { return }
        out = URL(fileURLWithPath: dir, isDirectory: true)
        try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        UserDefaults.standard.set(base, forKey: API.baseKey)
        API.shared.setCookie(String(cookie.dropFirst(cookie.hasPrefix("c:") ? 2 : 0)))
        AppModel.shared.needsSignIn = false
        Task { await run(AppModel.shared) }
    }

    static func log(_ s: String) {
        lines.append(s)
        try? lines.joined(separator: "\n").appending("\n").write(to: out.appendingPathComponent("log.txt"), atomically: true, encoding: .utf8)
    }

    static func check(_ ok: Bool, _ what: String, _ detail: String = "") {
        if !ok { failures += 1 }
        log((ok ? "PASS  " : "FAIL  ") + what + (detail.isEmpty ? "" : "  [\(detail)]"))
    }

    static func pause(_ s: Double) async { try? await Task.sleep(nanoseconds: UInt64(s * 1e9)) }

    static func until(_ timeout: Double, _ cond: () -> Bool) async -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end { if cond() { return true }; await pause(0.2) }
        return cond()
    }

    static var window: NSWindow? { main ?? NSApp.windows.first { $0.isVisible && $0.contentView != nil && $0.title != "" } }
    static var main: NSWindow?

    /// The windows other than the main one go (a book or a volume opened by a check).
    static func closeOthers() {
        for w in NSApp.windows where w.isVisible && w != main && w.level == .normal { w.close() }
    }

    static func capture(_ name: String, _ which: NSWindow? = nil) {
        guard let w = which ?? window, let v = w.contentView?.superview ?? w.contentView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return }
        v.cacheDisplay(in: v.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: out.appendingPathComponent(name + ".png"))
        if let sheet = w.attachedSheet { capture(name + "-sheet", sheet) }        // a sheet is a window of its own
    }

    /// Daf's book reader in the window's web view has laid out a page.
    private static var bookAnswer = false
    static func bookOpen() -> Bool {
        func find(_ v: NSView) -> WKWebView? { (v as? WKWebView) ?? v.subviews.lazy.compactMap(find).first }
        guard let web = NSApp.windows.lazy.compactMap({ $0.contentView.flatMap(find) }).first else { return false }
        web.evaluateJavaScript("!!(document.querySelector('foliate-view') && document.querySelector('foliate-view').lastLocation)") { r, _ in
            MainActor.assumeIsolated { bookAnswer = (r as? Bool) == true }
        }
        return bookAnswer
    }

    static func go(_ m: AppModel, _ p: Place) async {
        m.place = p
        m.selection = nil
        await m.load()
        await pause(0.8)
    }

    static func run(_ m: AppModel) async {
        log("SELFTEST against \(API.shared.base.absoluteString)")
        _ = await until(10) { NSApp.windows.contains { $0.isVisible && $0.title != "" } }
        main = NSApp.windows.first { $0.isVisible && $0.title != "" }
        window?.setContentSize(NSSize(width: 1280, height: 820))
        await pause(1)

        // Today
        await go(m, .today)
        check(m.today?.d("counted") != nil, "Today opens: the minutes and the goal", m.today?.o("main")?.s("text") ?? m.error ?? "")
        check(!m.continueItems.isEmpty, "and what to keep reading", "\(m.continueItems.count)")
        check(m.today?.o("year30")?.list("days").count == 365 && m.today?.o("review") != nil, "with Year 30's days and the day's review", "\(m.today?.o("year30")?.list("days").count ?? -1)")
        await pause(1)
        capture("01-today")
        check(m.place?.isPage == true, "Today is a page across the window")
        let y29 = try? await API.shared.json("/api/year/29")
        check(y29?.list("days").count == 365, "and Year 29 is there to show", "\(y29?.i("days_read") ?? -1) days read")
        // the whole page, in a tall window
        window?.setContentSize(NSSize(width: 1280, height: 2000))
        await pause(2)
        capture("01b-today-whole")
        window?.setContentSize(NSSize(width: 1280, height: 820))
        await pause(1)
        let stand = (m.today?.a("nightstand") ?? []) + (m.today?.a("nightstand_suggested") ?? [])
        if let id = stand.first?.s("id") {
            m.showBook(id)
            let opened = await until(8) { m.place == .books && m.selected?.id == id }
            check(opened, "a nightstand book opens its page on Books", stand.first?.s("title") ?? id)
            await pause(1.5)
            capture("50-today-nightstand")
            await go(m, .today)
        }

        // daf:// links (this build's are daf-selftest://): a place for Shortcuts, a link from the share menu
        Links.handle(URL(string: "daf-selftest://go/review")!)
        await pause(1)
        check(m.place == .review, "daf://go/review opens Review", String(describing: m.place))
        Links.handle(URL(string: "daf-selftest://save?url=https%3A%2F%2Fexample.com%2Fdaf-selftest&title=A%20link%20from%20the%20share%20menu")!)
        let savedLink = await until(20) { Links.saved.contains("https://example.com/daf-selftest") }
        check(savedLink && m.error == nil, "daf://save (Save to Daf in the share menu) saves the link to the Library", m.error ?? "")
        m.error = nil

        // the new-post alerts ask Daf with the Mac's own device token; Safari needs the signed build
        await FeedNews.shared.check(force: true)
        check(FeedNews.shared.last?.i("cursor") != nil, "the new-post alerts ask Daf with this Mac's device token", "\(FeedNews.shared.last?.i("feeds") ?? -1) feeds to tell me about")
        let safari = await Safari.connect(again: false) ?? ""
        check(safari.contains("isn't signed"), "and Daf for Safari says when the build isn't signed for it", safari)
        await go(m, .today)

        // the Library
        await go(m, .library("inbox"))
        check(!m.items.isEmpty, "the Library's Inbox lists its articles", "\(m.items.count)")
        check(m.count(.library("inbox")) != nil, "with the counts beside the sidebar")
        capture("02-library")

        // its order and filters
        let sort0 = m.sortLibrary
        m.sortLibrary = "short"
        await m.load()
        let lens = m.items.compactMap(\.mins)
        check(!lens.isEmpty && lens == lens.sorted(), "Shortest First puts the short ones at the top", "\(lens.prefix(6))")
        m.sortLibrary = sort0
        m.listFilter.length = "0-10"
        await m.load()
        let short = m.items.compactMap(\.mins)
        check(!short.isEmpty && short.allSatisfy { $0 <= 10 }, "the Under 10 Minutes filter keeps only those", "\(m.items.count): \(short.prefix(6))")
        m.listFilter = ListFilter()
        await m.load()

        // an article, natively
        guard let article = m.items.first(where: { $0.kind == "article" && ($0.j.i("words") ?? 0) > 300 }) else { return finish("no article to read") }
        m.selection = article.id
        let opened = await until(15) { (m.reader?.storage.length ?? 0) > 500 && m.reader?.textView != nil }
        check(opened, "an article opens in the native reader", "\(m.reader?.storage.length ?? 0) characters")
        await pause(1.5)
        capture("03-reader")
        guard let r = m.reader, let tv = r.textView else { return finish("the reader didn't open") }
        check(!r.blocks.isEmpty, "its blocks are laid out", "\(r.blocks.count) blocks")

        // focus mode (Focus.swift): the article on the whole screen, the toolbar away until the top
        if let w = main {
            // the panes the window shows, by the split view's subviews wider than nothing
            func panes() -> Int {
                func split(_ v: NSView) -> NSSplitView? { (v as? NSSplitView) ?? v.subviews.lazy.compactMap(split).first }
                return w.contentView.flatMap(split)?.arrangedSubviews.filter { !$0.isHidden && $0.frame.width > 2 }.count ?? -1
            }
            let panesBefore = panes(), textView = r.textView
            Focus.shared.enter(w)
            let full = await until(10) { w.styleMask.contains(.fullScreen) }
            await pause(1.5)
            check(full && Focus.shared.main && Focus.shared.barTucked(w), "focus mode puts the article on the whole screen, the toolbar hidden till the top",
                  "full screen \(full), options \(NSApp.presentationOptions.rawValue), toolbar shown \(w.toolbar?.isVisible ?? false)")
            check(panes() == 1 && m.reader?.textView === textView, "with only the article, the sidebar and the list gone, and the same reader still open", "panes \(panesBefore) → \(panes())")
            capture("70-focus")
            Focus.shared.leave(w)
            let back = await until(10) { !w.styleMask.contains(.fullScreen) }
            await pause(1.5)
            check(back && !Focus.shared.main && w.toolbar?.isVisible != false, "and leaving it gives the window back as it was")

            // the window is still when nothing happens: no toolbar item drawn over and over (the
            // focus button once was, and scrolling in the lists and articles broke)
            let drawn0 = FocusButton.drawn
            await pause(3)
            check(FocusButton.drawn - drawn0 <= 3, "the window is still when nothing happens", "\(FocusButton.drawn - drawn0) toolbar draws in 3 s")
            // a scroll of the wheel over the article moves it, and it stays there
            if let sv = tv.enclosingScrollView, let cg = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: -400, wheel2: 0, wheel3: 0) {
                let y0 = sv.contentView.bounds.origin.y
                let mid = sv.convert(NSPoint(x: sv.bounds.midX, y: sv.bounds.midY), to: nil)
                let onScreen = w.convertPoint(toScreen: mid)
                cg.location = CGPoint(x: onScreen.x, y: (w.screen?.frame.maxY ?? 0) - onScreen.y)
                if let e = NSEvent(cgEvent: cg) { w.sendEvent(e) }
                await pause(0.6)
                let y1 = sv.contentView.bounds.origin.y
                await pause(2.5)
                let y2 = sv.contentView.bounds.origin.y
                check(y1 > y0 + 50 && abs(y2 - y1) < 2, "the wheel scrolls an article, and it stays where it was scrolled", "\(Int(y0)) → \(Int(y1)) → \(Int(y2))")
            }
        }

        // a highlight from a selection
        let before = r.highlights.count
        // a paragraph with no highlight yet (a highlight over one would merge into it)
        let highlighted = Set(r.highlights.compactMap { $0.o("pos")?.i("b") })
        let blk = r.blocks.first { $0.range.length > 120 && !highlighted.contains($0.i) } ?? r.blocks.first { $0.range.length > 120 } ?? r.blocks[0]
        tv.setSelectedRange(NSRange(location: blk.range.location + 4, length: 40))
        let pos = r.selectionPosition(tv.selectedRange())
        check(pos != nil, "a selection becomes Daf's position (block, offsets)", pos.map { "b\($0.b) \($0.s)–\($0.e): \($0.text.prefix(30))" } ?? "")
        await r.highlightSelection()
        let fresh = try? await API.shared.json("/api/docs/\(API.enc(r.id))")
        check(r.highlights.count == before + 1 && (fresh?.a("highlights").count ?? 0) >= before + 1, "H highlights it, and Daf keeps the highlight", "\(before) → \(fresh?.a("highlights").count ?? -1)")
        let painted = r.storage.attribute(.dafHighlight, at: blk.range.location + 10, effectiveRange: nil) as? String
        check(!(painted ?? "").isEmpty, "and it's painted in the text")
        capture("04-highlight")

        // the highlight's colour and note
        if let hid = r.highlights.last?.s("id") {
            await r.set(color: "green", of: hid)
            try? await API.shared.send("PUT", "/api/highlights/\(API.enc(hid))/note", ["note": "A note from the self-test"])
            r.changed(hid) { $0["user_note"] = "A note from the self-test" }
            let back = (try? await API.shared.json("/api/docs/\(API.enc(r.id))"))?.a("highlights").first { $0.s("id") == hid }
            let tip = r.storage.attribute(.toolTip, at: blk.range.location + 10, effectiveRange: nil) as? String
            check(back?.s("color") == "green" && back?.s("user_note") == "A note from the self-test" && tip != nil,
                  "a highlight takes a colour and a note, the note shown on hover", "\(back?.s("color") ?? "-") / \(back?.s("user_note") ?? "-") / \(tip ?? "no tip")")
            if let h = r.highlights.first(where: { $0.s("id") == hid }) {
                r.editing = .init(h: h)
                await pause(1.2)
                capture("18-hlnote")
                r.editing = nil
                await pause(0.5)
            }
        }

        // the article's note and tags, in the inspector
        let oldTags = r.tags
        r.write(note: "A note from the self-test")
        await r.flushNote()
        await r.set(tags: oldTags + ["Self Test"])
        let meta = try? await API.shared.json("/api/docs/\(API.enc(r.id))")
        check(meta?.s("note") == "A note from the self-test" && meta?.strings("tags").contains("Self Test") == true,
              "the article keeps a note and a new tag", "\(meta?.s("note") ?? "-") / \(meta?.strings("tags") ?? [])")
        m.showInspector = true
        await pause(1.5)
        capture("19-inspector")
        m.showInspector = false
        r.write(note: "")
        await r.flushNote()
        await r.set(tags: oldTags)
        let clean = try? await API.shared.json("/api/docs/\(API.enc(r.id))")
        check(clean?.s("note") == nil && clean?.strings("tags") == oldTags, "and both go again", "\(clean?.s("note") ?? "-") / \(clean?.strings("tags") ?? [])")

        // overlapping highlights merge into one, as the page merges them
        if let blk2 = r.blocks.first(where: { $0.range.length > 80 }) {
            let before2 = r.highlights.count
            tv.setSelectedRange(NSRange(location: blk2.range.location + 2, length: 20))
            await r.highlightSelection()
            tv.setSelectedRange(NSRange(location: blk2.range.location + 12, length: 40))
            await r.highlightSelection()
            let after2 = (try? await API.shared.json("/api/docs/\(API.enc(r.id))"))?.a("highlights") ?? []
            let merged = after2.count == before2 + 1 && (after2.last?.s("text")?.count ?? 0) >= 40
            check(merged, "a highlight over another merges them into one", "\(before2) → \(after2.count): “\((after2.last?.s("text") ?? "").prefix(50))”")

            // the highlight's tools: tags, a flashcard, a card to share, a word looked up
            if let hid = r.highlights.last?.s("id"), let hj = r.highlights.last {
                let tags = J(try? await API.shared.send("PUT", "/api/highlights/\(API.enc(hid))/tags", ["tags": ["self-test"]]))?.strings("tags") ?? []
                let fav = await HLTools.fav(hid, true)
                _ = await HLTools.fav(hid, false)
                let word = (hj.s("text") ?? "").split(separator: " ").first(where: { $0.count > 3 }).map(String.init) ?? "reading"
                let front = (hj.s("text") ?? "").replacingOccurrences(of: word, with: "{{" + word + "}}", options: [], range: (hj.s("text") ?? "").range(of: word))
                let card = J(try? await API.shared.send("POST", "/api/highlights/\(API.enc(hid))/cards", ["kind": "cloze", "front": front]))
                let cards = card?.a("cards").count ?? 0
                if let cid = card?.s("id") { _ = try? await API.shared.send("DELETE", "/api/cards/\(API.enc(cid))", nil) }
                let png = ShareCard(h: hj, title: r.title, author: r.shareAuthor).png()
                let size = png.flatMap { NSBitmapImageRep(data: $0) }.map { CGSize(width: $0.pixelsWide, height: $0.pixelsHigh) } ?? .zero
                check(tags == ["self-test"] && fav && cards == 1 && size == CGSize(width: 1080, height: 1350),
                      "a highlight takes tags, a favorite and a flashcard, and makes a card to share", "\(tags), \(cards) card, \(Int(size.width))×\(Int(size.height))")
                if let png { try? png.write(to: out.appendingPathComponent("43-share-card.png")) }
                r.sheet = .cards(hj)
                await pause(1.2)
                capture("44-flashcard")
                r.sheet = nil
                await pause(0.5)
                await r.remove(highlight: hid)
                let gone = (try? await API.shared.json("/api/docs/\(API.enc(r.id))"))?.a("highlights").count ?? -1
                m.undoLast()
                var back = -1
                for _ in 0..<20 { await pause(0.3); back = r.highlights.count; if back == before2 + 1 { break } }
                check(gone == before2 && back == before2 + 1, "Remove Highlight has Undo, which brings it back", "\(before2 + 1) → \(gone) → \(back)")
                await r.remove(highlight: hid)
            }

            // the focused paragraph: j, then h highlights all of it (one with no highlight in it yet)
            r.moveFocus(1)
            r.moveFocus(1)
            let marked = Set(r.highlights.compactMap { h in r.blocks.first { b in (h.o("pos")?.i("b")) == b.i }?.i })
            if let free = r.blocks.first(where: { !marked.contains($0.i) && $0.range.length > 40 }) { r.focus = free.i }
            let f = r.focus
            let b3 = r.highlights.count
            await r.highlightFocus(thenNote: false)
            check(f != nil && r.highlights.count == b3 + 1, "j moves the focus a paragraph on, and h highlights the whole of it", "block \(f ?? -1)")
            if let hid = r.highlights.last?.s("id") { await r.remove(highlight: hid) }
        }

        // the article's own tools: Summarize, the title and author, reset progress
        await r.summarize()
        check((r.doc?.s("ai_summary") ?? "").contains("stand-in"), "Summarize writes a summary (the sandbox's stand-in)")
        let title0 = r.doc?.s("title") ?? "", author0 = r.doc?.s("author") ?? ""
        let edited = await r.editMeta(title: "Edited by the self-test", author: "The self-test")
        let seen = (try? await API.shared.json("/api/docs/\(API.enc(r.id))"))?.s("title")
        _ = await r.editMeta(title: title0, author: author0)
        check(edited && seen == "Edited by the self-test", "Edit the Title and Author changes them", seen ?? "-")
        await r.resetProgress()
        check(((try? await API.shared.json("/api/docs/\(API.enc(r.id))"))?.d("progress") ?? -1) == 0, "Reset Reading Progress starts it again")
        if let item = m.selected, item.whereIn != "feed" {
            await m.star(item)
            let on = (try? await API.shared.json("/api/docs?where=library&tab=inbox&kind=starred&limit=200"))?.a("items").contains { $0.s("id") == item.id } ?? false
            if let again = m.items.first(where: { $0.id == item.id }) { await m.star(again) }
            check(on, "F puts it on the Shortlist (and off again)")
        }

        // Ask (the sandbox's stand-in answers; the model is never asked)
        let asked = r.asks.count
        await r.ask("What is this about?")
        check(r.asks.count == asked + 1 && (r.asks.last?.s("a") ?? "").contains("stand-in"), "Ask answers a question about the article", String((r.asks.last?.s("a") ?? r.error ?? "").prefix(60)))
        m.showInspector = true
        await pause(1.5)
        capture("27-ask")
        m.showInspector = false

        // the place
        let scroll = tv.enclosingScrollView!
        tv.layoutManager?.ensureLayout(for: tv.textContainer!)
        let h = tv.frame.height
        scroll.contentView.scroll(to: NSPoint(x: 0, y: max(0, h * 0.6 - scroll.contentView.bounds.height)))
        scroll.reflectScrolledClipView(scroll.contentView)
        await pause(2.5)
        let placed = try? await API.shared.json("/api/docs/\(API.enc(r.id))")
        check((placed?.d("progress") ?? 0) >= 50, "reading on keeps the place in Daf",
              "\(placed?.d("progress") ?? -1)%; restored \(r.restored), last scroll \(String(format: "%.2f", r.lastFraction)), sent \(r.placeSent)")

        // the reading time
        let t0 = (try? await API.shared.json("/api/today"))?.o("minutes")?.d("article") ?? 0
        r.lastActive = Date()
        r.beat()
        await pause(2)
        let t1 = (try? await API.shared.json("/api/today"))?.o("minutes")?.d("article") ?? 0
        check(t1 > t0, "15 seconds of reading count toward today's minutes", "\(t0) → \(t1)")

        // and the highlight goes again
        if let hid = r.highlights.last?.s("id") {
            await r.remove(highlight: hid)
            let after = try? await API.shared.json("/api/docs/\(API.enc(r.id))")
            check((after?.a("highlights").count ?? -1) == before, "Remove Highlight takes it back", "\(after?.a("highlights").count ?? -1)")
        }

        // read aloud: Daf's speech for each paragraph, the paragraph marked (with the sound off)
        let sp = Speaker.shared
        sp.volume = 0
        sp.start(r)
        let spoke = await until(90) { sp.started >= 1 }
        check(spoke && sp.playing, "Listen reads the article aloud in Daf's voice", "paragraph \(sp.index + 1) of \(sp.paragraphs.count)")
        var marked = false
        if sp.paragraphs.indices.contains(sp.index), let rg = r.blocks.first(where: { $0.i == sp.paragraphs[sp.index] })?.range, let lm = tv.layoutManager {
            marked = stride(from: rg.location, to: rg.location + rg.length, by: 3).contains { lm.temporaryAttribute(.backgroundColor, atCharacterIndex: $0, effectiveRange: nil) != nil }
        }
        check(marked, "and marks the paragraph it's reading")
        await pause(0.5)
        capture("20-listen")
        let i0 = sp.index
        sp.skip(1)
        let onward = await until(60) { sp.started >= 2 }
        check(onward && sp.index == i0 + 1, "the next-paragraph button goes on to the next one", "\(i0 + 1) → \(sp.index + 1)")
        sp.stop()
        check(!sp.on, "and Stop ends it")

        // no connection: what was seen opens from this Mac, and a change waits until Daf answers
        Connection.shared.forced = true
        await go(m, .library("inbox"))
        check(Connection.shared.offline && !m.items.isEmpty && m.error == nil, "with no connection, the Inbox opens from what this Mac kept", "\(m.items.count) \(m.error ?? "")")
        m.reader = nil
        m.selection = article.id
        let again = await until(15) { m.reader?.id == article.id && (m.reader?.storage.length ?? 0) > 500 }
        check(again, "and so does an article read before")
        let waiting = Outbox.shared.ops.count
        try? await API.shared.send("PUT", "/api/docs/\(API.enc(article.id))/note", ["note": "Written with no connection"])
        check(Outbox.shared.ops.count == waiting + 1, "a change made then waits on this Mac", "\(Outbox.shared.ops.count) waiting")
        await pause(1)
        capture("32-offline")
        Connection.shared.forced = false
        _ = try? await API.shared.get("/api/health")
        let sent = await until(15) { Outbox.shared.ops.isEmpty }
        let note = (try? await API.shared.json("/api/docs/\(API.enc(article.id))"))?.s("note")
        check(sent && note == "Written with no connection", "and goes to Daf when it answers again", note ?? "-")
        try? await API.shared.send("PUT", "/api/docs/\(API.enc(article.id))/note", ["note": ""])
        await go(m, .library("inbox"))

        // the Library's home: its shelves
        await go(m, .home)
        await pause(2)
        check(!(m.home?.a("continue").isEmpty ?? true), "Home has the Library's shelves", (m.home?.raw.keys.sorted() ?? []).joined(separator: ", "))
        capture("42-home")

        // a list filtered by its source
        await go(m, .library("inbox"))
        if let src = m.items.compactMap({ $0.j.s("source") }).first {
            m.listFilter.source = src
            await m.load()
            check(!m.items.isEmpty && m.items.allSatisfy { $0.j.s("source") == src }, "the Source filter keeps only that source", "\(src): \(m.items.count)")
            m.listFilter = ListFilter()
            await m.load()
        }
        let first = m.selection
        m.step(1)
        check(m.selection != nil && m.selection != first, "Next in the List opens the next one")

        // the Feed, its folders and their feeds
        await go(m, .feed(nil))
        await m.markSeen(.feed(nil), older: 400 * 86_400)
        check(m.error == nil, "Mark Seen Older Than leaves what came since", m.toast ?? "")
        if m.toastUndo { m.undoLast(); await pause(1) }
        check(!m.items.isEmpty, "the Feed lists what's unseen", "\(m.items.count)")
        await m.loadSources()
        let feeds = m.feedFolders.flatMap { $0.a("feeds") }
        check(!feeds.isEmpty, "with its folders and their feeds in the sidebar", "\(m.feedFolders.count) folders, \(feeds.count) feeds")
        if let first = m.folderNames.first(where: { !$0.isEmpty }) { UserDefaults.standard.set(first, forKey: "openFolders") }
        await pause(1)
        capture("05-feed")

        // several chosen at once: marked seen together, then Undo
        let some = Array(m.items.filter { $0.id.hasPrefix("fr:") }.prefix(3))
        if some.count >= 2 {
            m.multi = Set(some.map(\.id))
            await pause(1)
            check(m.selection == nil && m.chosen.count == some.count, "several can be chosen at once", "\(m.chosen.count)")
            capture("25-bulk")
            await m.bulk(some, "seen")
            var seenNow = 0
            for p in some { if (try? await API.shared.json("/api/docs/\(API.enc(p.id))"))?.s("status") == "seen" { seenNow += 1 } }
            m.undoLast()
            var unseenAgain = 0
            for _ in 0..<30 {
                await pause(0.3)
                unseenAgain = 0
                for p in some { if (try? await API.shared.json("/api/docs/\(API.enc(p.id))"))?.s("status") == "unseen" { unseenAgain += 1 } }
                if unseenAgain == some.count { break }
            }
            check(seenNow == some.count && unseenAgain == some.count, "and marked seen together, and Undo puts them back", "\(seenNow) seen, then \(unseenAgain) unseen")
        } else { check(false, "several can be chosen at once", "only \(some.count) posts in the Feed") }

        if let small = feeds.filter({ ($0.i("count") ?? 0) > 0 }).min(by: { ($0.i("count") ?? 0) < ($1.i("count") ?? 0) }), let fid = small.s("id") {
            await go(m, .feedSource(fid))
            check(!m.items.isEmpty && m.items.allSatisfy { $0.j.s("feed") == fid }, "a feed lists only its own posts", "\(small.s("title") ?? ""): \(m.items.count)")
            capture("21-onefeed")

            // all of it seen, then Edit › Undo
            let n0 = m.count(.feedSource(fid)) ?? 0
            await m.markSeen(.feedSource(fid))
            let n1 = m.count(.feedSource(fid)) ?? 0
            check(n0 > 0 && n1 == 0 && m.toastUndo, "Mark All Seen empties it, with Undo offered", "\(n0) → \(n1)")
            capture("22-markseen")
            let viaMenu = m.undoManager?.canUndo == true
            if viaMenu { m.undoManager?.undo() } else { m.undoLast() }
            let back = await until(10) { (m.count(.feedSource(fid)) ?? 0) == n0 }
            check(back && viaMenu, "and Edit › Undo puts it all back", "\(m.count(.feedSource(fid)) ?? -1) of \(n0); the window's undo \(viaMenu)")

            // the list kept as a view in the sidebar, then removed
            if await m.saveCurrentView(named: "Self-test view"), case .view(let vid)? = m.place {
                await m.load()
                check(m.view(vid) != nil && !m.items.isEmpty, "Save as View keeps the list in the sidebar", "\(m.views.count) views, \(m.items.count) in it")
                await pause(0.8)
                capture("28-view")
                // its filters change in place, and Update the View keeps them
                m.viewFilter.fresh = true
                let changed = m.viewChanged
                await m.updateView()
                await m.loadViews()
                let kept = ListFilter(m.view(vid)?.o("filter")?.raw ?? [:]).fresh
                m.viewAsSaved()
                check(changed && kept && !m.viewChanged, "a view's filters change, and Update the View keeps them", "\(m.view(vid)?.o("filter")?.raw ?? [:])")
                await m.removeView(vid)
                check(m.view(vid) == nil, "and Remove the View takes it away")
                await go(m, .feedSource(fid))
            } else { check(false, "Save as View keeps the list in the sidebar", m.error ?? "") }

            // renamed, moved, switched: in the FreshRSS stand-in, and back again
            let oldTitle = small.s("title") ?? "", oldFolder = small.s("folder") ?? ""
            await m.editFeed(fid, ["title": "Renamed by the self-test"])
            check(m.feed(fid)?.s("title") == "Renamed by the self-test", "a feed can be renamed", m.feed(fid)?.s("title") ?? m.error ?? "")
            await m.editFeed(fid, ["title": oldTitle])
            if let other = m.folderNames.first(where: { !$0.isEmpty && $0 != oldFolder }) {
                await m.editFeed(fid, ["folder": other])
                check(m.feed(fid)?.s("folder") == other, "and moved to another folder", other)
                await m.editFeed(fid, ["folder": oldFolder])
            }
            let full0 = small.b("full")
            await m.editFeed(fid, ["full": !full0])
            check(m.feed(fid)?.b("full") == !full0, "and its full-article switch turned")
            await m.editFeed(fid, ["full": full0])

            // a post to the Kindle (the sandbox's own folder)
            if let post = m.items.first {
                await m.sendToKindle([post.id])
                check(m.error == nil && (m.toast ?? "").hasPrefix("Sent to the Kindle"), "Send to Kindle makes it a book for the Kindle", m.toast ?? m.error ?? "")
            }

            // a post deleted, then Undo
            if let post = m.items.first {
                await m.delete(post)
                let gone = (try? await API.shared.json("/api/docs/\(API.enc(post.id))"))?.s("status")
                m.undoLast()
                var again: String?
                for _ in 0..<30 {
                    await pause(0.3)
                    again = (try? await API.shared.json("/api/docs/\(API.enc(post.id))"))?.s("status")
                    if again == "unseen" { break }
                }
                check(gone == "deleted" && again == "unseen", "Delete takes a post out, and Undo puts it back", "\(gone ?? "-") → \(again ?? "-")")
            }
            m.confirmUnfollow = fid
            await pause(1.2)
            capture("23-unfollow")
            m.confirmUnfollow = nil
            await pause(0.5)
        }
        await m.refreshFeed()
        check(m.error == nil && m.toast == "Nothing new", "Check for New Posts asks FreshRSS", m.toast ?? m.error ?? "")
        m.sheet = .follow
        await pause(1.2)
        capture("24-follow")
        check(m.sheet == .follow, "Follow a Site… opens its sheet")
        m.sheet = nil
        await pause(0.5)

        // a PDF, in Apple's PDF view
        let lib = (try? await API.shared.json("/api/docs?where=library&tab=inbox&kind=pdf&limit=10"))?.a("items").map(Item.init) ?? []
        if let pdf = lib.first {
            m.place = .library("inbox")
            await m.load()
            if !m.items.contains(where: { $0.id == pdf.id }) { m.items.insert(pdf, at: 0) }
            m.selection = pdf.id
            func findPDF(_ v: NSView) -> PDFView? { (v as? PDFView) ?? v.subviews.lazy.compactMap(findPDF).first }
            let pages = { (window?.contentView.flatMap(findPDF)?.document?.pageCount) ?? 0 }
            let shown = await until(30) { pages() > 0 }
            let first = pages()
            var trace: [String] = []
            for k in 0..<6 {
                await pause(0.5)
                trace.append("\(k): sel \(m.selection == pdf.id ? "pdf" : (m.selection ?? "nil")) in-items \(m.items.contains { $0.id == pdf.id }) n\(m.items.count) pages \(pages()) place \(String(describing: m.place))")
            }
            log("INFO  " + trace.joined(separator: " | "))
            capture("06-pdf")
            check(shown && pages() > 0, "a PDF opens in Apple's PDF view, and stays open", "\(pdf.title): \(first) pages, then \(pages())")
            // a few words on its first page highlighted, kept with the page and its boxes, then removed
            if let pm = PDFModel.last, pm.id == pdf.id, let v = pm.view, let page = v.document?.page(at: 0),
               let text = page.string, (text as NSString).length > 40, let sel = page.selection(for: NSRange(location: 0, length: min(90, (text as NSString).length))) {
                v.setCurrentSelection(sel, animate: false)
                let before = pm.highlights.count, marks0 = pm.marks
                await pm.highlightSelection()
                let made = pm.highlights.last
                let kept = made?.o("pos")?.o("pdf")?.i("pg") == 1 && !(made?.o("pos")?.o("pdf")?.list("r") ?? []).isEmpty
                await pause(1)
                capture("63-pdf-highlight")
                check(pm.highlights.count == before + 1 && pm.marks > marks0 && kept, "a PDF's words highlight on the page, kept with the page and its boxes", "\(marks0) → \(pm.marks) marks: " + String((made?.s("text") ?? "").prefix(60)))
                let server = (try? await API.shared.json("/api/docs/\(API.enc(pdf.id))?prefetch=1"))?.a("highlights").contains { $0.s("id") == made?.s("id") } ?? false
                check(server, "and Daf has it")
                if let hid = made?.s("id") { await pm.remove(highlight: hid) }
                check(pm.marks == marks0, "Remove Highlight takes it off the page")
            } else { log("INFO  the PDF's first page has no words to select") }
            if let route = m.route(for: pdf) {
                m.openRoute = route
                let own = await until(30) { NSApp.windows.contains { $0.isVisible && $0 != main && ($0.contentView.flatMap(findPDF)?.document?.pageCount ?? 0) > 0 } }
                check(own, "and Open in a New Window opens it in a window of its own", route)
                closeOthers()
            }
        } else { log("SKIP  no PDF in the Inbox") }

        // books: the book's page natively; Read opens Daf's own reader in a window of its own
        await go(m, .books)
        check(!m.items.isEmpty, "Books lists the books", "\(m.items.count)")
        if let b = m.items.first {
            m.selection = b.id
            await pause(3)
            capture("07-bookpage")

            // a shelf made with the book on it, shown, then deleted
            if await m.newShelf("Self-test shelf", with: b.id), let sid = m.shelves.first(where: { $0.s("name") == "Self-test shelf" })?.s("id") {
                await go(m, .shelf(sid))
                check(m.items.contains { $0.id == b.id }, "a new shelf holds the book it was made with", "\(m.shelves.count) shelves")
                capture("26-shelf")
                await m.deleteShelf(sid)
                check(!m.shelves.contains { $0.s("id") == sid }, "and Delete the Shelf takes it away")
                await go(m, .books)
                m.selection = b.id
                await pause(1)
            } else { check(false, "a new shelf holds the book it was made with", m.error ?? "") }
            await readBook(m, fallback: b)
            closeOthers()
        }

        await recovery(m)

        // a book's page: a note on it, how often it comes up in review, Hardcover
        let note0 = (try? await API.shared.json("/api/books/cal:45"))?.a("notes").count ?? 0
        _ = try? await API.shared.send("POST", "/api/notes", ["text": "A note from the self-test", "book_id": "cal:45"])
        let note1 = (try? await API.shared.json("/api/books/cal:45"))?.a("notes").count ?? 0
        _ = try? await API.shared.send("PUT", "/api/books/cal:45/review", ["freq": "more"])
        let freq = (try? await API.shared.json("/api/books/cal:45"))?.s("review_freq")
        _ = try? await API.shared.send("PUT", "/api/books/cal:45/review", ["freq": "normal"])
        let hc = try? await API.shared.json("/api/hardcover/book/cal:45")
        check(note1 == note0 + 1 && freq == "more" && hc != nil, "a book's page keeps a note, its review frequency and its Hardcover status", "\(note0) → \(note1) notes, \(freq ?? "-"), Hardcover \(hc?.s("status") ?? "-")")
        await go(m, .books)
        m.selection = "cal:45"
        await pause(4)
        capture("47-bookpage")

        // manga: the series, its volumes, a volume read natively
        await go(m, .manga)
        check(!m.items.isEmpty, "Manga lists the series", "\(m.items.count)")
        if let s = m.items.first {
            m.selection = s.id
            await pause(3)
            capture("12-series")
            if let vol = (try? await API.shared.json("/api/manga/series/" + API.enc(s.id)))?.a("books").first, let vid = vol.s("id") {
                m.openRoute = "#mread/" + API.enc(vid)
                let shown = await until(25) { NSApp.windows.contains { $0.isVisible && $0.title == (vol.s("name") ?? "") } }
                let drawn = await until(30) { MangaModel.last.map { m in !m.shownPages.isEmpty && m.shownPages.allSatisfy { m.image($0) != nil } } ?? false }
                await pause(1)
                let mw = NSApp.windows.first(where: { $0.isVisible && $0.title == (vol.s("name") ?? "") })
                if let mm = MangaModel.last {
                    log("INFO  manga: shown \(mm.shownPages) loaded \(mm.shownPages.map { mm.image($0) != nil }) sizes \(mm.shownPages.map { mm.image($0)?.size ?? .zero }) stage \(mm.stage) two \(mm.twoUp) unit \(mm.unit) window \(mw?.frame.size ?? .zero)")
                }
                if let mw { capture("13-manga", mw) }
                if let mm = MangaModel.last {                // the same pages drawn by SwiftUI itself, apart from the window
                    let r = ImageRenderer(content: MangaUnitView(m: mm, unit: mm.unit, size: mm.stage, ink: .white).background(Color.black))
                    r.scale = 1
                    if let png = r.nsImage?.tiffRepresentation.flatMap({ NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) }) {
                        try? png.write(to: out.appendingPathComponent("13b-manga-drawn.png"))
                    }
                    let e = ImageRenderer(content: MangaEndCard(m: mm, ink: .white).frame(width: 600, height: 500).background(Color.black))
                    if let png = e.nsImage?.tiffRepresentation.flatMap({ NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) }) {
                        try? png.write(to: out.appendingPathComponent("13c-manga-end-drawn.png"))
                    }
                }
                check(shown && drawn, "a volume opens in the native manga reader, its page drawn", "\(vol.s("name") ?? ""), page \((MangaModel.last?.shownPages.first ?? -1) + 1)")
                if let mm = MangaModel.last {
                    let p0 = mm.shownPages.first ?? 0
                    mm.go(1)
                    await pause(0.6)
                    check((mm.shownPages.first ?? 0) > p0 || mm.unit == .end, "and turns to the next page", "\(p0 + 1) → \((mm.shownPages.first ?? 0) + 1)")

                    // one page or two, as the layout says; the cover alone
                    let mode0 = mm.p.mode, layout0 = mm.p.layout
                    mm.set("mode", "rtl")
                    mm.set("layout", "double")
                    let pairs = mm.units.filter { $0.pages.count == 2 }.count
                    mm.set("layout", "single")
                    let singles = mm.units.allSatisfy { $0.pages.count <= 1 }
                    check(pairs > 0 && singles && mm.units.first(where: { !$0.pages.isEmpty })?.pages == [0], "Two Pages pairs them (the cover alone), One Page doesn't", "\(pairs) pairs")

                    // the settings are the series' own, kept by Daf as the page keeps them
                    mm.set("scale", "width")
                    await pause(1.5)
                    let kept = (try? await API.shared.json("/api/manga/prefs"))?.o("series")?.o(mm.seriesID)
                    check(kept?.s("layout") == "single" && kept?.s("scale") == "width", "a series keeps its own reading settings in Daf", "\(kept?.raw ?? [:])")

                    // the long strip
                    mm.set("mode", "strip")
                    await pause(2)
                    if let mw { capture("39-manga-strip", mw) }
                    check(!mm.p.paged && mm.units.last == .end, "Long Strip reads it as one column", "\(mm.count) pages")
                    mm.set("mode", mode0)
                    mm.set("layout", layout0)
                    mm.set("scale", "screen")

                    // the end card, then every page at a glance
                    mm.lastPage()
                    mm.go(1)
                    await pause(0.8)
                    check(mm.unit == .end, "past the last page, the end card (finished, the next volume)")
                    if let mw { capture("40-manga-end", mw) }
                    mm.go(to: 0)
                    await pause(0.5)
                }
                closeOthers()
            }
        }

        // Torah: the week's readings, opened in the native reader
        await go(m, .torah)
        check(m.torah?.o("parasha") != nil && !m.items.isEmpty, "Torah has this week's parasha and readings", m.torah?.o("parasha")?.s("name") ?? "")
        if let reading = m.items.first {
            m.selection = reading.id
            let opened = await until(15) { (m.reader?.storage.length ?? 0) > 300 && m.reader?.id == reading.id }
            check(opened, "and a reading opens in the native reader", reading.title)
            await pause(1)
            capture("14-torah")
            // the verses in Hebrew and English, or one of them
            // Hebrew letters in the reading: the verses' (a heading may have some of its own)
            let hebrew = { (m.reader?.storage.string ?? "").unicodeScalars.filter { (0x05D0...0x05EA).contains($0.value) }.count }
            let heBoth = hebrew(), lenBoth = m.reader?.storage.length ?? 0
            let both = heBoth > 200
            UserDefaults.standard.set("en", forKey: "torahLang")
            m.reader?.compose(keepPlace: true)
            let english = hebrew() < heBoth / 10 && (m.reader?.storage.length ?? 0) < lenBoth
            UserDefaults.standard.set("he", forKey: "torahLang")
            m.reader?.compose(keepPlace: true)
            let onlyHebrew = hebrew() > heBoth * 9 / 10 && (m.reader?.storage.length ?? 0) < lenBoth
            await pause(0.8)
            capture("14b-torah-hebrew")
            UserDefaults.standard.removeObject(forKey: "torahLang")
            m.reader?.compose(keepPlace: true)
            check(both && english && onlyHebrew, "its verses show in Hebrew and English, or in one of them", "both \(both), English \(english), Hebrew \(onlyHebrew)")
        }

        // an essay from the vault on this week's parasha (Reference/torah/<parasha>/) opens in the reader
        await go(m, .torah)
        if let t = m.torah, let e = AppModel.essays(t).first, let eid = e.s("id") {
            m.selection = eid
            let opened = await until(20) { m.reader?.id == eid && (m.reader?.storage.length ?? 0) > 200 }
            await pause(1)
            capture("68-torah-essay")
            check(opened, "an essay from the vault on this week's parasha opens in the reader", (e.s("title") ?? "") + ": \(m.reader?.storage.length ?? -1) characters")
        } else { log("INFO  no vault essay on this week's parasha in the sandbox") }

        // a video: the player above its transcript, a line marked as it's said, Clip 30s
        let vids = (try? await API.shared.json("/api/docs?where=library&tab=inbox&kind=video&sort=new&limit=50"))?.a("items") ?? []
        var vidID: String?
        for v in vids.prefix(10) {
            if let id = v.s("id"), let d = try? await API.shared.json("/api/docs/" + API.enc(id)), d.s("kind") == "video",
               d.list("blocks").filter({ J($0)?.s("t") == "cue" }).count >= 2, VideoPlayer.id(d.s("url")) != nil { vidID = id; break }
        }
        if let vid = vidID {
            await go(m, .library("inbox"))
            if !m.items.contains(where: { $0.id == vid }), let v = vids.first(where: { $0.s("id") == vid }) { m.items.insert(Item(v), at: 0) }
            m.selection = vid
            let ready = await until(20) { m.reader?.id == vid && m.reader?.video != nil && (m.reader?.cues.count ?? 0) >= 2 && m.reader?.textView != nil }
            if ready, let r = m.reader, let v = r.video, let c = r.cues.last {
                r.syncCue(c.ts + 1, false)
                let marked = r.textView?.nowRange != nil
                v.time = c.ts + 5
                let before = r.highlights.count
                await r.clip(30)
                let clipped = r.highlights.count > before
                await pause(2)
                capture("66-video")
                check(marked && clipped, "a video opens natively: its player, its transcript marked as it's said, Clip 30s", "\(r.cues.count) cues, \(r.highlights.count - before) clipped")
                for h in r.highlights.dropFirst(before) { if let hid = h.s("id") { await r.remove(highlight: hid) } }
            } else { check(false, "a video opens natively", "\(vid): \(m.reader?.error ?? "not ready")") }
        } else { log("INFO  no video with a transcript in the sandbox's Inbox") }

        // a picture highlighted, as the page keeps it (![alt](address)), framed in its colour
        await go(m, .library("inbox"))
        var picDoc: String?
        for it in m.items.prefix(30) where it.kind == "article" {
            if let d = try? await API.shared.json("/api/docs/" + API.enc(it.id)), d.list("blocks").contains(where: { J($0)?.s("t") == "img" }) { picDoc = it.id; break }
        }
        if let pid = picDoc {
            m.selection = pid
            let ready = await until(15) { m.reader?.id == pid && !(m.reader?.pictures.isEmpty ?? true) && m.reader?.restored == true }
            let picked = Set(m.reader?.highlights.compactMap { HLPicture.of($0.s("text"))?.src } ?? [])
            if ready, let r = m.reader, let p = r.pictures.first(where: { !picked.contains($0.src) }) {
                let before = r.highlights.count
                await r.highlightPicture(at: p.at)
                let made = r.highlights.last
                let marked = !r.pictureMarks.isEmpty && HLPicture.of(made?.s("text"))?.src == p.src
                r.textView?.scrollRangeToVisible(NSRange(location: p.at, length: 1))
                await pause(2)
                capture("62-picture-highlight")
                check(r.highlights.count == before + 1 && marked, "a picture is highlighted, as the page keeps it", String((made?.s("text") ?? "").prefix(80)))
                if let hid = made?.s("id") { await r.remove(highlight: hid) }
            } else { check(false, "a picture is highlighted", "the article didn't open: \(pid)") }
        } else { log("INFO  no article with a picture in the sandbox's Inbox") }

        // Podcasts and Sources
        await go(m, .podcasts)
        await pause(2.5)
        capture("15-podcasts")
        await go(m, .sources)
        await pause(2.5)
        capture("16-sources")
        check(true, "Podcasts and Sources open (see 15 and 16)")

        // Settings
        let shownBefore = Set(NSApp.windows.filter(\.isVisible).map(ObjectIdentifier.init))
        UserDefaults.standard.set("reading", forKey: "prefsTab")
        m.showSettings = true
        let prefs = await until(6) { NSApp.windows.contains { $0.isVisible && !shownBefore.contains(ObjectIdentifier($0)) } }
        await pause(2)
        if let w = NSApp.windows.first(where: { $0.isVisible && !shownBefore.contains(ObjectIdentifier($0)) }) { capture("17-settings", w); w.close() }
        UserDefaults.standard.removeObject(forKey: "prefsTab")

        // Settings › Goals: the goals as the page's Preferences has them
        let goals = (try? await API.shared.json("/api/goals"))?.a("goals") ?? []
        UserDefaults.standard.set("goals", forKey: "prefsTab")
        let beforeGoals = Set(NSApp.windows.filter(\.isVisible).map(ObjectIdentifier.init))
        m.showSettings = true
        let goalsShown = await until(6) { NSApp.windows.contains { $0.isVisible && !beforeGoals.contains(ObjectIdentifier($0)) } }
        await pause(2.5)
        if let w = NSApp.windows.first(where: { $0.isVisible && !beforeGoals.contains(ObjectIdentifier($0)) }) { capture("38-goals", w); w.close() }
        UserDefaults.standard.removeObject(forKey: "prefsTab")
        let target0 = goals.first { $0.s("id") == "minutes" }?.i("target") ?? 60
        _ = try? await API.shared.send("PUT", "/api/goals", ["goals": [["id": "minutes", "target": target0 + 5]]])
        let changed = (try? await API.shared.json("/api/goals"))?.a("goals").first { $0.s("id") == "minutes" }?.i("target")
        _ = try? await API.shared.send("PUT", "/api/goals", ["goals": [["id": "minutes", "target": target0]]])
        check(goalsShown && goals.count == 7 && changed == target0 + 5, "Settings › Goals has the seven goals, and a target changes", "\(goals.count) goals; \(target0) → \(changed ?? -1) → \(target0)")

        // a photo of a paper page: read (by the sandbox's stand-in), its lines, a book, kept as highlights
        let photo = NSImage(size: NSSize(width: 900, height: 1200), flipped: false) { r in
            NSColor.white.setFill(); r.fill()
            let a: [NSAttributedString.Key: Any] = [.font: NSFont(name: "Times New Roman", size: 34) ?? NSFont.systemFont(ofSize: 34), .foregroundColor: NSColor.black]
            for (k, line) in ["A page from a paper book,", "photographed for the self-test.", "The pencil marked this line."].enumerated() {
                (line as NSString).draw(at: NSPoint(x: 80, y: r.height - 200 - CGFloat(k) * 60), withAttributes: a)
            }
            return true
        }
        let png = photo.tiffRepresentation.flatMap { NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) } ?? Data()
        await PaperPages.add([png])
        let pid = m.selection ?? ""
        var pageJ: J?
        for _ in 0..<40 {
            pageJ = try? await API.shared.json("/api/paper/pages/" + API.enc(pid))
            if let p = pageJ, !PaperPages.reading(p) { break }
            await pause(0.5)
        }
        check(m.place == .paper && !(pageJ?.a("lines").isEmpty ?? true), "a photo of a page is sent to Daf and read, line by line", "\(pageJ?.a("lines").count ?? 0) lines, \(pageJ?.list("chosen").count ?? 0) marked")
        await pause(5)
        capture("37-paper")
        var kept: J?, why = ""
        do { kept = J(try await API.shared.send("POST", "/api/paper/pages/" + API.enc(pid), ["chosen": [1, 2], "book_id": "cal:45", "page": "12"])) }
        catch { why = error.localizedDescription }
        check((kept?.i("highlights") ?? 0) == 1, "its chosen lines become one highlight in the book", "\(kept?.i("highlights") ?? -1) \(pid) \(why)")
        _ = try? await API.shared.send("DELETE", "/api/paper/pages/" + API.enc(pid), nil)
        await go(m, .today)

        check(prefs, "Settings opens", NSApp.windows.map { "'\($0.title)' \($0.isVisible)" }.joined(separator: ", "))

        // the rest of Daf's preferences, each a tab: Account, Connections, AI, Tags, Import
        for (k, (tab, shot)) in [("account", "52-account"), ("connections", "53-connections"), ("ai", "54-ai"), ("tags", "55-tags"), ("import", "56-import")].enumerated() {
            UserDefaults.standard.set(tab, forKey: "prefsTab")
            let before = Set(NSApp.windows.filter(\.isVisible).map(ObjectIdentifier.init))
            m.showSettings = true
            let shown = await until(6) { NSApp.windows.contains { $0.isVisible && !before.contains(ObjectIdentifier($0)) } }
            await pause(k == 1 ? 4 : 2.5)
            if let w = NSApp.windows.first(where: { $0.isVisible && !before.contains(ObjectIdentifier($0)) }) { capture(shot, w); w.close() }
            check(shown, "Settings › \(tab.capitalized) opens (see \(shot))")
        }
        UserDefaults.standard.removeObject(forKey: "prefsTab")
        let tagList = (try? await API.shared.json("/api/doc-tags"))?.a("tags") ?? []
        if let t = tagList.first?.s("name") {
            let renamed = J(try? await API.shared.send("POST", "/api/doc-tags/rename", ["from": t, "to": t + "-selftest"]))
            _ = try? await API.shared.send("POST", "/api/doc-tags/rename", ["from": t + "-selftest", "to": t])
            check((renamed?.i("changed") ?? 0) > 0, "a Library tag renames (and back)", t)
        }
        m.sheet = .feedback
        await pause(1.5)
        capture("57-feedback")
        check(m.sheet == .feedback, "Help › Send Feedback… opens its sheet")
        m.sheet = nil
        await pause(0.5)

        // Daf's themes: Paper when it's light, Nord dark, kept in Daf; then back as they were
        let was = (Theme.shared.mode, Theme.shared.light, Theme.shared.dark)
        await go(m, .today)
        Theme.shared.choose(mode: "light", light: "paper")
        await pause(1.5)
        var paperBG = ""
        NSAppearance(named: .aqua)?.performAsCurrentDrawingAppearance {
            paperBG = Theme.nsBG.usingColorSpace(.sRGB).map { String(format: "#%02x%02x%02x", Int(($0.redComponent * 255).rounded()), Int(($0.greenComponent * 255).rounded()), Int(($0.blueComponent * 255).rounded())) } ?? ""
        }
        capture("64-theme-paper")
        Theme.shared.choose(mode: "dark", dark: "nord")
        await pause(1.5)
        capture("65-theme-nord")
        var keptTheme: J?
        for _ in 0..<16 {          // the choice reaches Daf in the background
            keptTheme = (try? await API.shared.json("/api/settings"))?.o("appearance")
            if keptTheme?.s("dark") == "nord" && keptTheme?.s("mode") == "dark" { break }
            await pause(0.5)
        }
        check(paperBG == "#f7f0e3" && keptTheme?.s("light") == "paper" && keptTheme?.s("dark") == "nord" && keptTheme?.s("mode") == "dark",
              "a theme for light and one for dark, kept in Daf (see 64 and 65)", "\(paperBG), \(keptTheme?.raw ?? [:])")
        Theme.shared.choose(mode: was.0, light: was.1, dark: was.2)
        await pause(0.5)

        // ⌘K, Add to Daf (a file, a drop, a paste), the shortcuts
        m.sheet = .palette
        await pause(1.5)
        capture("58-palette")
        check(m.sheet == .palette, "⌘K opens the palette")
        m.sheet = nil
        await pause(0.5)
        let found = try? await API.shared.json("/api/search?q=the")
        check(!(found?.a("docs") ?? []).isEmpty && found?.raw["text"] != nil && found?.raw["vault"] != nil,
              "and searches articles, the words in them, books, highlights and the vault", "\((found?.a("docs") ?? []).count) articles, \((found?.a("text") ?? []).count) in the text")
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("Daf self-test.epub")
        try? Data("not really a book".utf8).write(to: file)
        let up = J(try? await API.shared.uploadFile("/api/add/file", name: file.lastPathComponent, data: (try? Data(contentsOf: file)) ?? Data()))
        check(up?.s("where") == "books", "a book sent as a file goes into Calibre (the sandbox's folder)", up?.s("name") ?? "")
        if let provider = NSItemProvider(contentsOf: file) {
            _ = m.dropped([provider])
            let opened = await until(5) { m.sheet == .addLink }
            await pause(2.5)
            capture("59-add-dropped")
            check(opened, "a book dropped on the window opens Add to Daf, and goes")
            m.sheet = nil
            await pause(0.5)
        }
        let pb = NSPasteboard(name: NSPasteboard.Name("daf-selftest"))
        pb.clearContents()
        pb.setString("https://example.com/daf-selftest-paste", forType: .string)
        let took = m.pasted(from: pb)
        await pause(1)
        check(took && m.sheet == .addLink, "a link pasted with nothing to paste into opens Add to Daf with it")
        capture("60-add-pasted")
        m.sheet = nil
        pb.clearContents()
        pb.setString("just words", forType: .string)
        check(!m.pasted(from: pb), "and words that aren't a link are left alone")
        pb.releaseGlobally()
        await pause(0.5)
        m.sheet = .shortcuts
        await pause(1)
        capture("61-shortcuts")
        check(m.sheet == .shortcuts, "Help › Keyboard Shortcuts opens")
        m.sheet = nil
        await pause(0.5)

        // Review
        await go(m, .review)
        let reviewed = await until(10) { m.review.loaded }
        check(reviewed && m.review.error == nil, "Review opens with today's highlights", "\(m.review.items.count) to see")
        await pause(1)
        capture("08-review")
        if m.review.current != nil, !m.review.isCard {
            let first = m.review.current?.s("id")
            await m.review.act("keep", model: m)
            check(m.review.index == 1 && m.review.actions[first ?? ""] == "keep", "Keep takes the next one, and Daf has it kept")
        }

        // Highlights
        await go(m, .highlights)
        await m.highlights.load()
        check(!m.highlights.groups.isEmpty, "Highlights lists the books and articles", "\(m.highlights.groups.count) of \(m.highlights.count) highlights")
        await pause(1.5)
        capture("09-highlights")

        // Highlights' filters, as the page's: a colour, the order, export what they show, Review These
        let allCount = m.highlights.count
        if let c = m.highlights.groups.flatMap({ $0.a("items") }).compactMap({ $0.s("color") }).first {
            m.highlights.color = c
            await m.highlights.load()
            let colours = Set(m.highlights.groups.flatMap { $0.a("items") }.compactMap { $0.s("color") })
            check(colours == [c] && m.highlights.count <= allCount && m.highlights.filtered, "Highlights filters by colour", "\(c): \(m.highlights.count) of \(allCount)")
            let csv = (try? await API.shared.data("/api/highlights/export?fmt=csv&" + m.highlights.filter)).flatMap { String(data: $0, encoding: .utf8) } ?? ""
            check(csv.split(separator: "\n").count >= 2, "and exports what the filters show (CSV)", "\(csv.split(separator: "\n").count) lines")
            m.startReview(themed: "n=30&" + m.highlights.filter)
            let themed = await until(10) { m.place == .review && m.review.loaded && m.review.theme != nil }
            let reviewColours = Set(m.review.items.compactMap { $0.s("color") })
            check(themed && !m.review.items.isEmpty && reviewColours.isSubset(of: [c]), "Review These reviews them", "\(m.review.theme ?? "no theme"): \(m.review.items.count)")
            await pause(1)
            capture("49-review-themed")
            await go(m, .highlights)
            m.highlights.color = ""
        }
        m.highlights.sort = "oldest"
        await m.highlights.load()
        let firstAt = m.highlights.groups.first.flatMap { g in g.a("items").compactMap { $0.d("created") }.min() } ?? 0
        let laterAt = m.highlights.groups.dropFirst().compactMap { g in g.a("items").compactMap { $0.d("created") }.min() }.min() ?? .infinity
        check(m.highlights.count == allCount && firstAt <= laterAt, "and puts the oldest first", "\(firstAt) ≤ \(laterAt)")
        m.highlights.sort = "recent"
        await m.highlights.load()

        // Books, as the page has them: the nightstand, Want to Read, opened lately, the library, and a search
        await go(m, .books)
        let sections = m.bookSections.map(\.0)
        check(sections.contains("Your library") && (sections.contains("Nightstand") || sections.contains("Suggested for the nightstand")), "Books has the nightstand, opened lately and the library", sections.joined(separator: ", "))
        check(Set(m.items.map(\.id)).count == m.items.count, "each book once")
        await pause(1)
        capture("51-books")
        let everyBook = m.shown.count
        if let word = m.items.last?.title.split(separator: " ").first.map(String.init), word.count > 2 {
            m.booksQuery = word
            check(!m.shown.isEmpty && m.shown.count <= everyBook && m.shown.allSatisfy { $0.title.lowercased().contains(word.lowercased()) || ($0.j.s("author") ?? "").lowercased().contains(word.lowercased()) },
                  "and finds a book by title or author", "\(word): \(m.shown.count) of \(everyBook)")
            m.booksQuery = ""
        }

        // Stats
        await go(m, .stats)
        await pause(3)
        capture("10-stats")
        check(window != nil, "Stats opens (see 10-stats)")

        // the File menu's sheets
        m.place = .library("inbox")
        await pause(1)
        m.sheet = .paper
        await pause(1.5)
        capture("11-paper")
        check(m.sheet == .paper, "Log Paper Minutes… opens its sheet")
        m.sheet = nil
        await pause(0.5)

        // search
        m.query = "the"
        await go(m, .search)
        check(!m.items.isEmpty, "search finds things in Daf", "\(m.items.count)")

        finish(nil)
    }

    /// The native book reader, on a book with a highlight made in the page's reader when there is one.
    static func readBook(_ m: AppModel, fallback: Item) async {
        var bookID = fallback.id
        for candidate in ["cal:45"] + m.items.prefix(8).map(\.id) {
            if let d = try? await API.shared.json("/api/ebooks/" + API.enc(candidate)), ["EPUB", "KEPUB"].contains((d.s("format") ?? "").uppercased()), !d.b("private") {
                bookID = candidate
                if !d.a("highlights").isEmpty { break }
            }
        }
        let det = try? await API.shared.json("/api/ebooks/" + API.enc(bookID))
        m.openRoute = "#ebook/" + API.enc(bookID)
        let opened = await until(45) { BookModel.last?.id == bookID && BookModel.last?.text != nil && (BookModel.last?.pages?.pageCount ?? 0) > 0 }
        guard opened, let bm = BookModel.last, let pages = bm.pages, let epub = bm.epub, let t0 = bm.text else {
            let b = BookModel.last
            log("INFO  book: last \(b?.id ?? "none") epub \(b?.epub != nil) text \(b?.text != nil) pages \(b?.pages != nil) count \(b?.pages?.pageCount ?? -1) error \(b?.error ?? "-") | windows " +
                NSApp.windows.map { "'\($0.title)' \($0.isVisible) \(Int($0.frame.width))x\(Int($0.frame.height)) \(type(of: $0.contentView ?? NSView()))" }.joined(separator: ", "))
            if let w = NSApp.windows.first(where: { $0.isVisible && $0 != main && $0.title != "" }) { capture("29x-book-failed", w) }
            return check(false, "a book opens in the native reader, set as pages", "\(bookID): \(BookModel.last?.error ?? "nothing")")
        }
        await pause(1.5)
        let win = pages.window
        check(true, "a book opens in the native reader, set as pages",
              "\(det?.s("title") ?? bookID): \(epub.sections.count) chapters, \(epub.toc.flatMap(\.flat).count) in the contents, \(pages.pageCount) pages in this one, \(pages.perSpread) side by side")
        capture("29-book", win)

        // at the place Daf kept, read from the page's own CFI; and the same CFI written back
        if let pos = det?.o("position")?.s("cfi") {
            let parsed = CFI.parse(pos)
            let k = epub.section(ofCFI: parsed), at = t0.range(of: parsed)?.location ?? -1, vis = pages.visible
            check(k == bm.section && at >= vis.location && at <= NSMaxRange(vis), "it opens at the place Daf kept", "\(pos) → chapter \(k ?? -1), character \(at); showing \(vis.location)–\(NSMaxRange(vis))")
            let mine = t0.cfi(at).map { CFI.join(epub.sections[bm.section].cfi, $0) } ?? ""
            let theirs = CFI.wrap(CFI.string(parsed.collapse()))
            check(mine == theirs, "a place written here is the very CFI the page writes", "page \(theirs), here \(mine)")
        }

        // every highlight made in the page's reader lands on its own words
        func norm(_ s: String) -> String { s.split(whereSeparator: { $0.isWhitespace || $0 == "\u{2028}" }).joined(separator: " ") }
        for h in bm.highlights {
            guard let c = h.o("pos")?.s("cfi") else { continue }
            bm.go(cfi: c)
            let p = CFI.parse(c)
            let words = bm.text.flatMap { t in t.range(of: p).map { norm((t.string.string as NSString).substring(with: $0)) } } ?? ""
            check(words == norm(h.s("text") ?? ""), "a highlight made in the page lands on the same words here", "\(c): “\(words.prefix(60))”")
        }

        // places written as CFIs read back to the same characters
        if let t = bm.text {
            let sec = epub.sections[bm.section].cfi
            var same = 0, tried = 0, miss = ""
            for run in t.runs.enumerated().filter({ $0.offset % max(1, t.runs.count / 40) == 0 }).map(\.element) where run.raw.count > 2 {
                let i = run.start + run.raw.count / 2
                tried += 1
                if let c = t.cfi(i), let back = t.range(of: CFI.parse(CFI.join(sec, c)))?.location, back == i { same += 1 } else if miss.isEmpty { miss = "\(i): \(t.cfi(i) ?? "-")" }
            }
            check(tried >= 5 && same == tried, "places written as CFIs read back to the same characters", "\(same) of \(tried) \(miss)")
        }

        // pages turn, and Daf keeps the new place
        let f0 = pages.first, s0 = bm.section
        pages.turn(true)
        await pause(0.6)
        check(pages.first > f0 || bm.section > s0, "→ turns the page", "page \(f0 + 1) → \(pages.first + 1), chapter \(s0) → \(bm.section)")
        await pause(2)                     // the place saved on its own after a turn, then by hand
        await bm.savePosition()
        var kept = "", keptAt = -1
        for _ in 0..<6 {
            kept = (try? await API.shared.json("/api/ebooks/" + API.enc(bookID)))?.o("position")?.s("cfi") ?? ""
            keptAt = bm.text?.range(of: CFI.parse(kept))?.location ?? -1
            if keptAt >= pages.visible.location { break }
            await pause(0.5)
        }
        check(epub.section(ofCFI: CFI.parse(kept)) == bm.section && keptAt >= pages.visible.location && keptAt <= NSMaxRange(pages.visible),
              "and Daf keeps the new place", kept)

        // a highlight made here, kept by Daf, then taken away
        if let t = bm.text, let run = t.runs.first(where: { $0.start >= pages.visible.location && $0.start + $0.raw.count <= NSMaxRange(pages.visible) && $0.raw.count > 40 }) {
            let sel = NSRange(location: run.start + 3, length: 30)
            let before = bm.highlights.count
            await bm.highlight(sel)
            let hid = bm.highlights.last?.s("id") ?? ""
            let back = (try? await API.shared.json("/api/ebooks/" + API.enc(bookID)))?.a("highlights").first { $0.s("id") == hid }
            let painted = pages.storage.attribute(.dafHighlight, at: sel.location + 5, effectiveRange: nil) as? String
            check(bm.highlights.count == before + 1 && back != nil && painted == hid, "H highlights the selection, and Daf keeps it as a CFI", back?.o("pos")?.s("cfi") ?? m.error ?? "")
            capture("30-book-highlight", win)
            await bm.remove(highlight: hid)
            check(bm.highlights.count == before, "and Remove Highlight takes it away")
        } else { check(false, "H highlights the selection", "no text on this page to select") }

        // a bookmark on and off
        await bm.toggleBookmark()
        let on = bm.marked
        await bm.toggleBookmark()
        check(on && !bm.marked, "B bookmarks the page, and takes the bookmark off again")

        // the Kindle's highlights, found in this edition by their words, and drawn like Daf's own
        if !bm.kindle.isEmpty {
            var found = 0, tried = 0
            for h in bm.kindle.prefix(60) {
                guard let k = BookModel.kindleSection(h) else { continue }
                tried += 1
                if bm.kindleRanges(k).contains(where: { $0.id == h.s("id") }) { found += 1 }
            }
            check(tried > 0 && Double(found) >= Double(tried) * 0.8, "the Kindle's highlights are found in this edition by their words", "\(found) of \(tried)")
            if let h = bm.kindle.first(where: { h in BookModel.kindleSection(h).map { k in bm.kindleRanges(k).contains { $0.id == h.s("id") } } ?? false }) {
                await bm.go(kindle: h)
                await pause(0.6)
                let r = bm.kindleRanges(bm.section).first { $0.id == h.s("id") }?.range
                let painted = r.flatMap { pages.storage.attribute(.dafHighlight, at: $0.location + 1, effectiveRange: nil) as? String }
                check(painted == h.s("id") && r.map { NSLocationInRange($0.location, pages.visible) } == true, "and one is drawn on its page", String((h.s("text") ?? "").prefix(50)))
                capture("33-book-kindle", win)
            }
        } else { log("SKIP  no Kindle highlights in this book") }

        // searching the book
        await bm.search("the")
        check(!bm.results.isEmpty, "Search finds the words all through the book", "\(bm.results.count) places")
        if let hit = bm.results.dropFirst(min(5, bm.results.count - 1)).first {
            bm.go(hit)
            await pause(0.6)
            check(bm.section == hit.section && NSLocationInRange(hit.range.location, pages.visible), "and a place found opens at its page", "chapter \(hit.section)")
        }
        bm.sidebar = "search"
        bm.showContents = true
        await pause(1)
        capture("34-book-search", win)

        // Ask (the sandbox's stand-in answers; the model is never asked)
        await bm.ask("What is this chapter about?")
        check((bm.asks.last?.s("a") ?? "").contains("stand-in"), "Ask answers a question about the book", String((bm.asks.last?.s("a") ?? bm.error ?? "").prefix(50)))
        await pause(0.8)
        capture("35-book-ask", win)
        bm.showContents = false

        // read aloud, silently: a paragraph at a time, marked, then the next
        let sp = Speaker.shared
        sp.volume = 0
        let before = sp.started
        sp.start(bm)
        let spoke = await until(90) { sp.started > before }
        let at = sp.paragraphs.indices.contains(sp.index) ? sp.paragraphs[sp.index] : -1
        let ends = (pages.storage.string as NSString).range(of: "\n", range: NSRange(location: max(0, at), length: max(0, pages.storage.length - max(0, at)))).location
        let markedSome = at >= 0 && stride(from: at, to: ends == NSNotFound ? pages.storage.length : ends, by: 2).contains { pages.speaking(at: $0) }
        let anywhere = stride(from: 0, to: pages.storage.length, by: 7).filter { pages.speaking(at: $0) }.count
        let para = at >= 0 && ends != NSNotFound ? (pages.storage.string as NSString).substring(with: NSRange(location: at, length: ends - at)) : ""
        let hl = at >= 0 ? (pages.storage.attribute(.dafHighlight, at: at, effectiveRange: nil) as? String ?? "none") : "-"
        log("INFO  listen: “\(para.prefix(40))” highlight \(hl) last marked \(String(describing: pages.lastMarked)) spoke \(spoke) from \(before)")
        log("INFO  listen: key \(sp.key ?? "-") section \(bm.section) listening \(bm.listenSection) at \(at) ends \(ends) visible \(pages.visible) marked anywhere \(anywhere) playing \(sp.playing) waiting \(sp.waiting) started \(sp.started)")
        check(spoke && sp.key == bm.listenKey && markedSome, "Listen reads the book aloud, the paragraph marked", "paragraph \(sp.index + 1) of \(sp.paragraphs.count) in this chapter")
        await pause(0.5)
        capture("36-book-listen", win)
        sp.skip(1)
        let onward = await until(60) { sp.started > before + 1 }
        check(onward, "and goes on to the next paragraph", "\(sp.index + 1)")
        sp.stop()

        // bigger type: the same place
        let at0 = pages.visible.location
        var look = bm.look
        let size0 = look.size
        look.size += 4
        bm.restyle(look)
        await pause(0.8)
        check(at0 >= pages.visible.location && at0 <= NSMaxRange(pages.visible), "bigger type keeps the place", "\(pages.pageCount) pages now")
        look.size = size0
        bm.restyle(look)

        // the reading time
        let m0 = (try? await API.shared.json("/api/today"))?.d("counted") ?? 0
        bm.beat()
        await pause(2)
        let m1 = (try? await API.shared.json("/api/today"))?.d("counted") ?? 0
        check(m1 > m0, "15 seconds with the book count toward today's minutes", "\(m0) → \(m1)")

        bm.showContents = true
        await pause(1)
        capture("31-book-contents", win)

        // the book's own tools: the time left, a percent, the line width, a look just for this book, Forget My Place
        check(bm.footer.contains("left in the book"), "the footer has the time left in the chapter and the book", bm.footer)
        bm.go(fraction: 0.5)
        await pause(0.8)
        check(abs(bm.fraction - 0.5) < 0.06, "Go to a Percent goes there", String(format: "%.2f", bm.fraction))
        bm.sidebar = "info"
        await pause(0.8)
        capture("48-book-info", win)
        bm.showContents = false
        await pause(0.6)
        let pagesWide = pages.pageCount
        var narrow = bm.look
        let width0 = narrow.width
        narrow.width = "narrow"
        bm.ownLook = true
        bm.restyle(narrow)
        await pause(0.8)
        let own = UserDefaults.standard.dictionary(forKey: "book.look." + bookID) != nil
        check(own && pages.pageCount != pagesWide, "a narrower line, kept just for this book", "\(pagesWide) → \(pages.pageCount) pages")
        narrow.width = width0
        bm.ownLook = false
        UserDefaults.standard.removeObject(forKey: "book.look." + bookID)
        bm.restyle(narrow)
        await pause(0.6)
        // the Scroll layout: the chapter as one column, Space a window's worth on
        var scroll = bm.look
        scroll.flow = "scrolled"
        bm.restyle(scroll)
        await pause(1)
        let scrollFrom = pages.visible.location
        pages.turn(true)
        await pause(0.8)
        let scrollTo = pages.visible.location
        capture("67-book-scroll", win)
        check(pages.scrolls && pages.pageCount == 1 && pages.visible.length > 0 && scrollTo > scrollFrom, "the Scroll layout reads the chapter as one column", "\(scrollFrom) → \(scrollTo)")
        scroll.flow = "paginated"
        bm.restyle(scroll)
        await pause(0.6)
        await bm.forgetPlace()
        let forgot = (try? await API.shared.json("/api/ebooks/" + API.enc(bookID)))?.o("position") == nil
        check(forgot, "Forget My Place in Daf forgets it")
        Speaker.shared.sleep(after: 15)
        let sleeping = Speaker.shared.sleepAt != nil
        Speaker.shared.sleep(after: nil)
        check(sleeping, "the player's sleep timer sets and clears")
        closeOthers()
        await pause(0.5)

        // opened at a highlight (the page's #ebook/<id>/hl:<id>)
        if let h = bm.highlights.first, let hid = h.s("id") {
            m.openRoute = "#ebook/" + API.enc(bookID) + "/hl:" + API.enc(hid)
            let there = await until(30) { BookModel.last !== bm && BookModel.last?.id == bookID && BookModel.last?.text != nil }
            await pause(1)
            let b2 = BookModel.last
            let r = b2.flatMap { b in h.o("pos")?.s("cfi").flatMap { b.text?.range(of: CFI.parse($0)) } }
            check(there && r.map { r in b2?.pages.map { NSLocationInRange(r.location, $0.visible) } ?? false } == true, "a book opens at a highlight, as the page's addresses do")
            closeOthers()
            await pause(0.5)
        }
    }

    /// Recovery: its readings open at their words in the Big Book.
    static func recovery(_ m: AppModel) async {
        await go(m, .recovery)
        await pause(2)
        capture("45-recovery")
        guard let r = try? await API.shared.json("/api/recovery"), let bid = r.o("book")?.s("id"), let reading = r.a("readings").first, let find = reading.s("find") else {
            return check(false, "Recovery has its readings and the Big Book")
        }
        check(!r.a("first").isEmpty && !r.a("prayers").isEmpty, "Recovery has the readings, the chapters and the prayers", "\(r.a("readings").count) readings, \(r.a("first").count) chapters")
        m.openRoute = "#ebook/" + API.enc(bid) + "/q:" + API.enc(find)
        let opened = await until(40) { BookModel.last?.id == bid && BookModel.last?.text != nil }
        await pause(1.5)
        let words = BookModel.normal(find).text.lowercased.prefix(30)
        let shown = BookModel.last.flatMap { b in b.pages.map { p in BookModel.normal((p.storage.string as NSString).substring(with: p.visible)).text.lowercased } } ?? ""
        check(opened && shown.contains(words), "a reading opens at its words in the Big Book", String(reading.s("title") ?? ""))
        if let w = BookModel.last?.pages?.window { capture("46-recovery-reading", w) }
        closeOthers()
        await pause(0.5)
    }

    static func finish(_ why: String?) {
        if let why { check(false, why) }
        log(failures == 0 ? "SELFTEST passed" : "SELFTEST \(failures) failed")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }
}
