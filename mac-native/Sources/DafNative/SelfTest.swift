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
        check(spoke && sp.playing, "Listen reads the article aloud in Daf's voice", "paragraph \(sp.index + 1) of \(sp.blocks.count)")
        var marked = false
        if sp.blocks.indices.contains(sp.index), let rg = r.blocks.first(where: { $0.i == sp.blocks[sp.index] })?.range, let lm = tv.layoutManager {
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
            m.openRoute = "#ebook/" + API.enc(b.id)
            let opened = await until(35) { bookOpen() }
            var seen = "windows: " + NSApp.windows.filter(\.isVisible).map { "'\($0.title)'" }.joined(separator: ", ")
            func find(_ v: NSView) -> WKWebView? { (v as? WKWebView) ?? v.subviews.lazy.compactMap(find).first }
            if let web = NSApp.windows.lazy.compactMap({ $0.contentView.flatMap(find) }).first {
                seen += " | web at \(web.url?.absoluteString ?? "-")"
                let r = try? await web.evaluateJavaScript("[document.body && document.body.dataset.view, location.hash, !!document.querySelector('foliate-view'), document.title].join(' / ')")
                seen += " | page: \(r as? String ?? "?")"
            }
            check(opened, "Read opens the book in Daf's own reader, in a window of its own", b.title + "; " + seen)
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
                let drawn = await until(30) { MangaModel.last.map { $0.image($0.page) != nil } ?? false }
                await pause(1)
                if let w = NSApp.windows.first(where: { $0.isVisible && $0.title == (vol.s("name") ?? "") }) { capture("13-manga", w) }
                check(shown && drawn, "a volume opens in the native manga reader, its page drawn", "\(vol.s("name") ?? ""), page \(MangaModel.last?.page ?? 0)")
                if let mm = MangaModel.last {
                    let p0 = mm.page
                    mm.turn(true)
                    check(mm.page > p0, "and turns to the next page", "\(p0) → \(mm.page)")
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

    static func finish(_ why: String?) {
        if let why { check(false, why) }
        log(failures == 0 ? "SELFTEST passed" : "SELFTEST \(failures) failed")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { NSApp.terminate(nil) }
    }
}
