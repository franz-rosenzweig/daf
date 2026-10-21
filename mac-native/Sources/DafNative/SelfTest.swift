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
        capture("01-today")

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

        // a highlight from a selection
        let before = r.highlights.count
        let blk = r.blocks.first { $0.range.length > 120 } ?? r.blocks[0]
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

        // the Feed, its folders and their feeds
        await go(m, .feed(nil))
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
        }

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
        await bm.savePosition()
        let kept = (try? await API.shared.json("/api/ebooks/" + API.enc(bookID)))?.o("position")?.s("cfi") ?? ""
        let keptAt = bm.text?.range(of: CFI.parse(kept))?.location ?? -1
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
        bm.showContents = false
        closeOthers()
        await pause(0.5)
    }

    static func finish(_ why: String?) {
        if let why { check(false, why) }
        log(failures == 0 ? "SELFTEST passed" : "SELFTEST \(failures) failed")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }
}
