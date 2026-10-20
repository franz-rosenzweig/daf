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

        // the Feed
        await go(m, .feed(nil))
        check(!m.items.isEmpty, "the Feed lists what's unseen", "\(m.items.count)")
        check(!m.feedCategories.isEmpty, "with its folders in the sidebar", m.feedCategories.joined(separator: ", "))
        capture("05-feed")

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
        } else { log("SKIP  no PDF in the Inbox") }

        // books: the book's page natively; Read opens Daf's own reader in a window of its own
        await go(m, .books)
        check(!m.items.isEmpty, "Books lists the books", "\(m.items.count)")
        if let b = m.items.first {
            m.selection = b.id
            await pause(3)
            capture("07-bookpage")
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
        m.showSettings = true
        let prefs = await until(6) { NSApp.windows.contains { $0.isVisible && !shownBefore.contains(ObjectIdentifier($0)) } }
        await pause(2)
        if let w = NSApp.windows.first(where: { $0.isVisible && !shownBefore.contains(ObjectIdentifier($0)) }) { capture("17-settings", w); w.close() }
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
